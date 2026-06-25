import re

from app.schemas import Chunk
from app.retrieval.routing import route_metadata_boost
from app.retrieval.text import keyword_overlap_score


def reciprocal_rank_fusion(result_sets: list[list[Chunk]], vector_weight: float, lexical_weight: float, top_k: int) -> list[Chunk]:
    fused: dict[str, Chunk] = {}
    scores: dict[str, float] = {}
    source_names = ["vector", "bm25"]
    weights = {"vector": vector_weight, "bm25": lexical_weight}

    for result_index, results in enumerate(result_sets):
        source = source_names[result_index] if result_index < len(source_names) else "recall"
        weight = weights.get(source, 1.0)
        for rank, chunk in enumerate(results, start=1):
            if chunk.id not in fused:
                fused[chunk.id] = chunk.model_copy(deep=True)
                scores[chunk.id] = 0.0
            scores[chunk.id] += weight * (1.0 / (60 + rank))
            if source == "vector":
                fused[chunk.id].vector_score = chunk.score
            elif source == "bm25":
                fused[chunk.id].lexical_score = chunk.lexical_score or chunk.score

    ranked = sorted(fused.values(), key=lambda item: scores[item.id], reverse=True)
    if not ranked:
        return []
    max_score = scores[ranked[0].id] or 1.0
    for chunk in ranked:
        chunk.score = scores[chunk.id] / max_score
        chunk.retrieval_source = _source_label(chunk)
    return ranked[:top_k]


def local_rerank(question: str, chunks: list[Chunk], top_k: int) -> list[Chunk]:
    reranked = []
    for chunk in chunks:
        vector_score = chunk.vector_score if chunk.vector_score is not None else chunk.score or 0.0
        lexical_score = chunk.lexical_score or 0.0
        overlap = keyword_overlap_score(question, chunk.text)
        title_overlap = keyword_overlap_score(question, chunk.metadata.get("title", ""))
        source_overlap = keyword_overlap_score(question, chunk.metadata.get("source_id", ""))
        intent_boost = _intent_metadata_boost(question, chunk)
        exact_title_boost = _exact_title_boost(question, chunk)
        rerank_score = (
            0.34 * vector_score
            + 0.25 * lexical_score
            + 0.12 * overlap
            + 0.11 * max(title_overlap, source_overlap)
            + 0.08 * intent_boost
            + 0.10 * exact_title_boost
        )
        updated = chunk.model_copy(deep=True)
        updated.rerank_score = rerank_score
        updated.score = rerank_score
        reranked.append(updated)
    reranked.sort(key=lambda item: item.rerank_score or 0.0, reverse=True)
    if reranked:
        max_score = reranked[0].score or 1.0
        for chunk in reranked:
            chunk.score = (chunk.score or 0.0) / max_score
    return reranked[:top_k]


def apply_threshold(chunks: list[Chunk], min_score: float, min_count: int) -> list[Chunk]:
    filtered = [chunk for chunk in chunks if (chunk.score or 0.0) >= min_score]
    if len(filtered) < min_count:
        return []
    return filtered


def _source_label(chunk: Chunk) -> str:
    if chunk.vector_score is not None and chunk.lexical_score is not None:
        return "hybrid"
    if chunk.vector_score is not None:
        return "vector"
    if chunk.lexical_score is not None:
        return "bm25"
    return "unknown"


def _intent_metadata_boost(question: str, chunk: Chunk) -> float:
    source_type = chunk.metadata.get("source_type", "")
    return route_metadata_boost(question, source_type)


def _exact_title_boost(question: str, chunk: Chunk) -> float:
    normalized_question = _compact_text(question)
    candidates = [
        chunk.metadata.get("title", ""),
        chunk.metadata.get("source_id", ""),
    ]
    for candidate in candidates:
        normalized_candidate = _compact_text(str(candidate))
        normalized_candidate = re.sub(r"^[0-9]+[-_]", "", normalized_candidate)
        normalized_candidate = re.sub(r"\.(txt|md|markdown|pdf|docx|html?)$", "", normalized_candidate)
        if len(normalized_candidate) >= 2 and normalized_candidate in normalized_question:
            return 1.0
    return 0.0


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())
