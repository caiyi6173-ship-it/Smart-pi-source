from typing import Any

import httpx

from app.config import Settings


class RagClientError(RuntimeError):
    pass


class RagClient:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.rag_base_url.rstrip("/")
        self.timeout = settings.agent_request_timeout_seconds

    def query(
        self,
        question: str,
        *,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
        user_context: dict[str, Any] | None = None,
        include_chunks: bool = True,
    ) -> dict[str, Any]:
        payload = {
            "question": question,
            "top_k": top_k,
            "filters": filters or {},
            "user_context": user_context or {},
            "include_chunks": include_chunks,
        }
        url = f"{self.base_url}/api/v1/query"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError as exc:
            raise RagClientError(f"RAG service is not reachable: {url}") from exc
        except httpx.TimeoutException as exc:
            raise RagClientError(f"RAG service timed out after {self.timeout} seconds: {url}") from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise RagClientError(f"RAG service returned HTTP {exc.response.status_code}: {detail}") from exc
        except httpx.HTTPError as exc:
            raise RagClientError(f"RAG service request failed: {exc}") from exc
