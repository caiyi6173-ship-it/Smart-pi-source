import hashlib
import logging
import math
import random

from openai import OpenAI

from app.config import Settings

logger = logging.getLogger(__name__)


class EmbeddingClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None
        self._runtime_fallback = False
        if settings.dashscope_api_key:
            self._client = OpenAI(
                api_key=settings.dashscope_api_key,
                base_url=settings.dashscope_base_url,
                timeout=settings.request_timeout_seconds,
            )

    @property
    def configured(self) -> bool:
        return self._client is not None and not self._runtime_fallback

    @property
    def using_local_fallback(self) -> bool:
        return self._client is None or self._runtime_fallback

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self._client:
            return [self._fake_embedding(text) for text in texts]

        try:
            embeddings: list[list[float]] = []
            batch_size = max(1, min(self.settings.embedding_batch_size, 20))
            for start in range(0, len(texts), batch_size):
                batch = texts[start : start + batch_size]
                response = self._client.embeddings.create(
                    model=self.settings.embedding_model,
                    input=batch,
                    dimensions=self.settings.embedding_dimensions,
                )
                embeddings.extend(item.embedding for item in response.data)
            return embeddings
        except Exception as exc:
            self._runtime_fallback = True
            logger.warning("Embedding API failed, falling back to local deterministic embeddings: %s", exc)
            return [self._fake_embedding(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def _fake_embedding(self, text: str) -> list[float]:
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)
        rng = random.Random(seed)
        vector = [rng.uniform(-1.0, 1.0) for _ in range(self.settings.embedding_dimensions)]
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]
