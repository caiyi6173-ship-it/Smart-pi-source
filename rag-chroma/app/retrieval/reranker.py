import logging

import httpx

from app.config import Settings
from app.retrieval.hybrid import local_rerank
from app.schemas import Chunk

logger = logging.getLogger(__name__)


class RerankService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def provider(self) -> str:
        if not self.settings.enable_rerank:
            return "none"
        return self.settings.rerank_provider

    def rerank(self, question: str, chunks: list[Chunk], top_k: int) -> tuple[list[Chunk], str]:
        if not self.settings.enable_rerank or self.settings.rerank_provider == "none":
            return chunks[:top_k], "none"
        if self.settings.rerank_provider == "local":
            return local_rerank(question, chunks, top_k), "local"
        if self.settings.rerank_provider == "dashscope":
            try:
                return self._dashscope_rerank(question, chunks, top_k), "dashscope"
            except Exception as exc:
                logger.warning("DashScope rerank failed, falling back to local rerank: %s", exc)
                return local_rerank(question, chunks, top_k), "local_fallback"
        return local_rerank(question, chunks, top_k), "local_fallback"

    def _dashscope_rerank(self, question: str, chunks: list[Chunk], top_k: int) -> list[Chunk]:
        if not chunks:
            return []
        if not self.settings.dashscope_api_key:
            raise RuntimeError("DASHSCOPE_API_KEY is required for DashScope rerank")

        top_n = self.settings.rerank_top_n or min(top_k, len(chunks))
        response = httpx.post(
            self.settings.rerank_url,
            headers={
                "Authorization": f"Bearer {self.settings.dashscope_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.rerank_model,
                "query": question,
                "documents": [chunk.text for chunk in chunks],
                "top_n": top_n,
                "return_documents": False,
                "instruct": self.settings.rerank_instruction,
            },
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", [])

        reranked: list[Chunk] = []
        for item in results:
            index = item.get("index")
            if index is None or index < 0 or index >= len(chunks):
                continue
            updated = chunks[index].model_copy(deep=True)
            updated.rerank_score = float(item.get("relevance_score", 0.0))
            updated.score = updated.rerank_score
            updated.retrieval_source = f"{updated.retrieval_source or 'hybrid'}+dashscope_rerank"
            reranked.append(updated)

        if not reranked:
            raise RuntimeError("DashScope rerank returned no usable results")
        reranked.sort(key=lambda chunk: chunk.rerank_score or 0.0, reverse=True)
        return reranked[:top_k]
