from abc import ABC, abstractmethod
import json
import math
from typing import Any

from app.config import Settings
from app.schemas import Chunk, DocumentMetadata


class VectorStore(ABC):
    @abstractmethod
    def ensure_ready(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def upsert(self, points: list[tuple[str, list[float], dict[str, Any]]]) -> None:
        raise NotImplementedError

    @abstractmethod
    def search(self, vector: list[float], top_k: int, filters: dict[str, Any] | None = None) -> list[Chunk]:
        raise NotImplementedError

    @abstractmethod
    def list_documents(self) -> list[DocumentMetadata]:
        raise NotImplementedError

    @abstractmethod
    def iter_chunks(self, filters: dict[str, Any] | None = None, limit: int | None = None) -> list[Chunk]:
        raise NotImplementedError

    @abstractmethod
    def delete_document(self, document_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError


def create_vector_store(settings: Settings) -> VectorStore:
    if settings.vector_backend == "local":
        return LocalVectorStore(settings)
    if settings.vector_backend == "chroma":
        return ChromaVectorStore(settings)
    return QdrantVectorStore(settings)


class LocalVectorStore(VectorStore):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = settings.local_vector_path

    def ensure_ready(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def upsert(self, points: list[tuple[str, list[float], dict[str, Any]]]) -> None:
        self.ensure_ready()
        records = self._read_records()
        existing_ids = {point_id for point_id, _, _ in points}
        records = [record for record in records if record["id"] not in existing_ids]
        records.extend({"id": point_id, "vector": vector, "payload": payload} for point_id, vector, payload in points)
        self._write_records(records)

    def search(self, vector: list[float], top_k: int, filters: dict[str, Any] | None = None) -> list[Chunk]:
        self.ensure_ready()
        filters = filters or {}
        scored = []
        for record in self._read_records():
            payload = record.get("payload", {})
            if not _payload_matches(payload, filters):
                continue
            scored.append((_cosine_similarity(vector, record.get("vector", [])), record))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            Chunk(
                id=record["id"],
                document_id=record.get("payload", {}).get("document_id", ""),
                text=record.get("payload", {}).get("text", ""),
                score=score,
                metadata=record.get("payload", {}),
            )
            for score, record in scored[:top_k]
        ]

    def list_documents(self) -> list[DocumentMetadata]:
        self.ensure_ready()
        docs: dict[str, dict[str, Any]] = {}
        for record in self._read_records():
            payload = record.get("payload", {})
            document_id = payload.get("document_id")
            if document_id and document_id not in docs:
                docs[document_id] = payload
        return [_payload_to_document(payload) for payload in docs.values()]

    def iter_chunks(self, filters: dict[str, Any] | None = None, limit: int | None = None) -> list[Chunk]:
        self.ensure_ready()
        filters = filters or {}
        chunks = []
        for record in self._read_records():
            payload = record.get("payload", {})
            if not _payload_matches(payload, filters):
                continue
            chunks.append(
                Chunk(
                    id=record["id"],
                    document_id=payload.get("document_id", ""),
                    text=payload.get("text", ""),
                    metadata=payload,
                    retrieval_source="lexical-corpus",
                )
            )
            if limit is not None and len(chunks) >= limit:
                break
        return chunks

    def delete_document(self, document_id: str) -> None:
        self.ensure_ready()
        records = [
            record
            for record in self._read_records()
            if record.get("payload", {}).get("document_id") != document_id
        ]
        self._write_records(records)

    def is_available(self) -> bool:
        try:
            self.ensure_ready()
            return True
        except Exception:
            return False

    def _read_records(self) -> list[dict[str, Any]]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write_records(self, records: list[dict[str, Any]]) -> None:
        self.path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


class QdrantVectorStore(VectorStore):
    def __init__(self, settings: Settings) -> None:
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise RuntimeError("qdrant-client is not installed. Run pip install qdrant-client or set VECTOR_BACKEND=local.") from exc

        self.settings = settings
        self.client = QdrantClient(url=settings.qdrant_url, timeout=settings.request_timeout_seconds)

    def ensure_ready(self) -> None:
        from qdrant_client.http import models

        collections = self.client.get_collections().collections
        names = {collection.name for collection in collections}
        if self.settings.qdrant_collection not in names:
            self.client.create_collection(
                collection_name=self.settings.qdrant_collection,
                vectors_config=models.VectorParams(
                    size=self.settings.embedding_dimensions,
                    distance=models.Distance.COSINE,
                ),
            )

    def upsert(self, points: list[tuple[str, list[float], dict[str, Any]]]) -> None:
        from qdrant_client.http import models

        self.ensure_ready()
        self.client.upsert(
            collection_name=self.settings.qdrant_collection,
            points=[
                models.PointStruct(id=point_id, vector=vector, payload=payload)
                for point_id, vector, payload in points
            ],
        )

    def search(self, vector: list[float], top_k: int, filters: dict[str, Any] | None = None) -> list[Chunk]:
        self.ensure_ready()
        query_filter = _qdrant_filter(filters or {})
        hits = self.client.search(
            collection_name=self.settings.qdrant_collection,
            query_vector=vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
        return [_hit_to_chunk(hit) for hit in hits]

    def list_documents(self) -> list[DocumentMetadata]:
        self.ensure_ready()
        docs: dict[str, dict[str, Any]] = {}
        next_page = None
        while True:
            records, next_page = self.client.scroll(
                collection_name=self.settings.qdrant_collection,
                limit=256,
                offset=next_page,
                with_payload=True,
                with_vectors=False,
            )
            for record in records:
                payload = record.payload or {}
                document_id = payload.get("document_id")
                if document_id and document_id not in docs:
                    docs[document_id] = payload
            if next_page is None:
                break
        return [_payload_to_document(payload) for payload in docs.values()]

    def iter_chunks(self, filters: dict[str, Any] | None = None, limit: int | None = None) -> list[Chunk]:
        self.ensure_ready()
        chunks: list[Chunk] = []
        next_page = None
        query_filter = _qdrant_filter(filters or {})
        while True:
            records, next_page = self.client.scroll(
                collection_name=self.settings.qdrant_collection,
                limit=min(limit or 256, 256),
                offset=next_page,
                scroll_filter=query_filter,
                with_payload=True,
                with_vectors=False,
            )
            for record in records:
                payload = record.payload or {}
                chunks.append(
                    Chunk(
                        id=str(record.id),
                        document_id=payload.get("document_id", ""),
                        text=payload.get("text", ""),
                        metadata=payload,
                        retrieval_source="lexical-corpus",
                    )
                )
                if limit is not None and len(chunks) >= limit:
                    return chunks
            if next_page is None:
                break
        return chunks

    def delete_document(self, document_id: str) -> None:
        from qdrant_client.http import models

        self.ensure_ready()
        self.client.delete(
            collection_name=self.settings.qdrant_collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        )
                    ]
                )
            ),
        )

    def is_available(self) -> bool:
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False


class ChromaVectorStore(VectorStore):
    def __init__(self, settings: Settings) -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError("chromadb is not installed. Run pip install chromadb or set VECTOR_BACKEND=local.") from exc

        self.settings = settings
        self.client = chromadb.PersistentClient(path=str(settings.chroma_path))
        self.collection = self.client.get_or_create_collection(settings.qdrant_collection)

    def ensure_ready(self) -> None:
        self.settings.chroma_path.mkdir(parents=True, exist_ok=True)

    def upsert(self, points: list[tuple[str, list[float], dict[str, Any]]]) -> None:
        self.ensure_ready()
        self.collection.upsert(
            ids=[point_id for point_id, _, _ in points],
            embeddings=[vector for _, vector, _ in points],
            metadatas=[_chroma_metadata(payload) for _, _, payload in points],
            documents=[payload["text"] for _, _, payload in points],
        )

    def search(self, vector: list[float], top_k: int, filters: dict[str, Any] | None = None) -> list[Chunk]:
        self.ensure_ready()
        where = filters or None
        result = self.collection.query(query_embeddings=[vector], n_results=top_k, where=where)
        chunks: list[Chunk] = []
        for idx, point_id in enumerate(result.get("ids", [[]])[0]):
            metadata = result.get("metadatas", [[]])[0][idx] or {}
            distance = result.get("distances", [[]])[0][idx]
            chunks.append(
                Chunk(
                    id=point_id,
                    document_id=metadata.get("document_id", ""),
                    text=result.get("documents", [[]])[0][idx] or metadata.get("text", ""),
                    score=1.0 - float(distance),
                    metadata=metadata,
                )
            )
        return chunks

    def list_documents(self) -> list[DocumentMetadata]:
        result = self.collection.get(include=["metadatas"])
        docs: dict[str, dict[str, Any]] = {}
        for metadata in result.get("metadatas", []):
            if metadata and metadata.get("document_id") not in docs:
                docs[metadata["document_id"]] = metadata
        return [_payload_to_document(payload) for payload in docs.values()]

    def iter_chunks(self, filters: dict[str, Any] | None = None, limit: int | None = None) -> list[Chunk]:
        where = filters or None
        result = self.collection.get(where=where, limit=limit, include=["metadatas", "documents"])
        chunks: list[Chunk] = []
        for idx, point_id in enumerate(result.get("ids", [])):
            metadata = result.get("metadatas", [])[idx] or {}
            chunks.append(
                Chunk(
                    id=point_id,
                    document_id=metadata.get("document_id", ""),
                    text=result.get("documents", [])[idx] or metadata.get("text", ""),
                    metadata=metadata,
                    retrieval_source="lexical-corpus",
                )
            )
        return chunks

    def delete_document(self, document_id: str) -> None:
        self.collection.delete(where={"document_id": document_id})

    def is_available(self) -> bool:
        try:
            self.ensure_ready()
            return True
        except Exception:
            return False


def _qdrant_filter(filters: dict[str, Any]):
    from qdrant_client.http import models

    conditions = []
    for key, value in filters.items():
        if value is None:
            continue
        if isinstance(value, list):
            conditions.append(models.FieldCondition(key=key, match=models.MatchAny(any=value)))
        else:
            conditions.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
    if not conditions:
        return None
    return models.Filter(must=conditions)


def _hit_to_chunk(hit: Any) -> Chunk:
    payload = hit.payload or {}
    return Chunk(
        id=str(hit.id),
        document_id=payload.get("document_id", ""),
        text=payload.get("text", ""),
        score=float(hit.score) if hit.score is not None else None,
        metadata=payload,
    )


def _payload_to_document(payload: dict[str, Any]) -> DocumentMetadata:
    tags = payload.get("tags", [])
    if isinstance(tags, str):
        tags = [tag for tag in tags.split(",") if tag]
    return DocumentMetadata(
        document_id=payload.get("document_id", ""),
        source_id=payload.get("source_id", ""),
        source_type=payload.get("source_type", "mixed"),
        title=payload.get("title", payload.get("source_id", "")),
        path=payload.get("path"),
        tags=tags,
        imported_at=payload.get("imported_at"),
        chunk_count=int(payload.get("chunk_count", 0)),
    )


def _chroma_metadata(payload: dict[str, Any]) -> dict[str, str | int | float | bool]:
    normalized: dict[str, str | int | float | bool] = {}
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            normalized[key] = value
        elif isinstance(value, list):
            normalized[key] = ",".join(str(item) for item in value)
        else:
            normalized[key] = str(value)
    return normalized


def _payload_matches(payload: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        actual = payload.get(key)
        if isinstance(expected, list):
            if isinstance(actual, list):
                if not set(expected).intersection(actual):
                    return False
            elif actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)
