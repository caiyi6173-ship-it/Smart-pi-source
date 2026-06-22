from app.config import Settings
from app.retrieval.embeddings import EmbeddingClient
from app.retrieval.hybrid import apply_threshold, reciprocal_rank_fusion
from app.retrieval.routing import RouteProfile, build_route_profile
from app.retrieval.reranker import RerankService
from app.retrieval.text import bm25_rank, rewrite_queries
from app.retrieval.vector_store import VectorStore
from app.schemas import Chunk


class RetrievalResult:
    def __init__(self, chunks: list[Chunk], rewritten_queries: list[str], strategy: str, rerank_provider: str) -> None:
        self.chunks = chunks
        self.rewritten_queries = rewritten_queries
        self.strategy = strategy
        self.rerank_provider = rerank_provider


class RetrievalService:
    def __init__(self, settings: Settings, embeddings: EmbeddingClient, store: VectorStore) -> None:
        self.settings = settings
        self.embeddings = embeddings
        self.store = store
        self.reranker = RerankService(settings)

    def retrieve(self, question: str, top_k: int | None = None, filters: dict | None = None) -> RetrievalResult:
        final_top_k = top_k or self.settings.default_top_k
        filters = filters or {}
        queries = rewrite_queries(question) if self.settings.enable_query_rewrite else [question]
        route_profile = build_route_profile(question, filters)
        base_filters = _base_filters(filters, route_profile)

        vector_results = self._vector_recall(queries, base_filters)
        lexical_results = self._lexical_recall(queries, base_filters) if self.settings.enable_hybrid_search else []
        routed_results = self._metadata_routed_recall(queries, filters, route_profile)

        if self.settings.enable_hybrid_search and vector_results:
            fused = reciprocal_rank_fusion(
                [vector_results, lexical_results, *routed_results],
                self.settings.vector_weight,
                self.settings.lexical_weight,
                top_k=max(final_top_k, self.settings.recall_top_k),
            )
            strategy = "hybrid_rrf_bm25_vector"
            if route_profile.hard_source_type or routed_results:
                strategy += "_metadata_routes"
        elif self.settings.enable_hybrid_search:
            fused = _merge_unique_chunks(lexical_results, routed_results)
            strategy = "bm25_metadata_fallback"
        else:
            fused = vector_results
            strategy = "vector_only"

        if route_profile.label not in {"general", "explicit_filter"}:
            strategy = f"{route_profile.label}_{strategy}"

        ranked, rerank_provider = self.reranker.rerank(question, fused, final_top_k)
        filtered = apply_threshold(ranked, self.settings.min_relevance_score, self.settings.min_chunks_for_answer)
        return RetrievalResult(
            chunks=filtered,
            rewritten_queries=queries,
            strategy=strategy,
            rerank_provider=rerank_provider,
        )

    def _vector_recall(self, queries: list[str], filters: dict) -> list[Chunk]:
        if self.embeddings.using_local_fallback:
            return []
        merged: dict[str, Chunk] = {}
        for query in queries:
            vector = self.embeddings.embed_query(query)
            if self.embeddings.using_local_fallback:
                return []
            for chunk in self.store.search(vector, self.settings.recall_top_k, filters):
                existing = merged.get(chunk.id)
                score = chunk.score or 0.0
                if existing is None or score > (existing.vector_score or existing.score or 0.0):
                    updated = chunk.model_copy(deep=True)
                    updated.vector_score = score
                    updated.retrieval_source = "vector"
                    merged[chunk.id] = updated
        return sorted(merged.values(), key=lambda item: item.vector_score or item.score or 0.0, reverse=True)

    def _lexical_recall(self, queries: list[str], filters: dict) -> list[Chunk]:
        candidates = self.store.iter_chunks(filters)
        merged: dict[str, Chunk] = {}
        for query in queries:
            for chunk in bm25_rank(query, candidates, self.settings.lexical_top_k):
                existing = merged.get(chunk.id)
                score = chunk.lexical_score or chunk.score or 0.0
                if existing is None or score > (existing.lexical_score or existing.score or 0.0):
                    merged[chunk.id] = chunk
        return sorted(merged.values(), key=lambda item: item.lexical_score or item.score or 0.0, reverse=True)

    def _metadata_routed_recall(self, queries: list[str], filters: dict, route_profile: RouteProfile) -> list[list[Chunk]]:
        if route_profile.hard_source_type or not route_profile.supplemental_source_types:
            return []

        result_sets: list[list[Chunk]] = []
        for source_type in route_profile.supplemental_source_types:
            merged_filter = {**filters, "source_type": source_type}
            routed_vector = self._vector_recall(queries, merged_filter)
            if routed_vector:
                result_sets.append(routed_vector)
            if self.settings.enable_hybrid_search:
                routed_lexical = self._lexical_recall(queries, merged_filter)
                if routed_lexical:
                    result_sets.append(routed_lexical)
        return result_sets


def _base_filters(filters: dict, route_profile: RouteProfile) -> dict:
    if route_profile.hard_source_type is None:
        return filters
    return {**filters, "source_type": route_profile.hard_source_type}


def _merge_unique_chunks(base_chunks: list[Chunk], extra_sets: list[list[Chunk]]) -> list[Chunk]:
    merged: dict[str, Chunk] = {chunk.id: chunk for chunk in base_chunks}
    ordered = list(base_chunks)
    for result_set in extra_sets:
        for chunk in result_set:
            if chunk.id in merged:
                continue
            merged[chunk.id] = chunk
            ordered.append(chunk)
    return ordered
