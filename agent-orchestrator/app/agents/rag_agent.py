from typing import Any

from app.clients.rag_client import RagClient, RagClientError
from app.schemas import Citation, RagResult


class RagAgentError(RuntimeError):
    pass


class RagAgent:
    def __init__(self, client: RagClient) -> None:
        self.client = client

    def run(
        self,
        question: str,
        *,
        source_type: str | None = None,
        top_k: int = 8,
        user_context: dict[str, Any] | None = None,
    ) -> RagResult:
        filters = {"source_type": source_type} if source_type else {}
        try:
            data = self.client.query(
                question,
                top_k=top_k,
                filters=filters,
                user_context=user_context,
                include_chunks=True,
            )
        except RagClientError as exc:
            raise RagAgentError(str(exc)) from exc

        chunks = data.get("chunks", [])
        chunk_metadata = {
            chunk.get("id"): chunk.get("metadata", {})
            for chunk in chunks
            if isinstance(chunk, dict)
        }
        citations = [
            Citation(
                title=item.get("title", ""),
                source_id=item.get("source_id", ""),
                document_id=item.get("document_id", ""),
                chunk_id=item.get("chunk_id", ""),
                source_type=(
                    item.get("source_type")
                    or chunk_metadata.get(item.get("chunk_id"), {}).get("source_type")
                    or source_type
                    or ""
                ),
                score=item.get("score"),
            )
            for item in data.get("citations", [])
        ]
        return RagResult(
            answer=data.get("answer", ""),
            citations=citations,
            chunks=chunks,
            no_answer=bool(data.get("no_answer", False)),
            retrieval_strategy=data.get("retrieval_strategy", "unknown"),
            rerank_provider=data.get("rerank_provider", "unknown"),
            latency_ms=int(data.get("latency_ms", 0) or 0),
        )
