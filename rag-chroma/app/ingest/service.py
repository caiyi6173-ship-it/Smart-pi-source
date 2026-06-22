from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

from app.config import Settings
from app.ingest.chunker import chunk_text
from app.ingest.loaders import iter_supported_files, load_path
from app.retrieval.embeddings import EmbeddingClient
from app.retrieval.vector_store import VectorStore
from app.schemas import DocumentMetadata, IngestResponse


class IngestService:
    def __init__(self, settings: Settings, embeddings: EmbeddingClient, store: VectorStore) -> None:
        self.settings = settings
        self.embeddings = embeddings
        self.store = store

    def ingest_path(self, path: Path, source_type: str = "mixed", tags: list[str] | None = None) -> list[IngestResponse]:
        tags = tags or []
        files = iter_supported_files(path)
        if not files:
            return [
                IngestResponse(
                    document_id="",
                    chunk_count=0,
                    status="skipped",
                    message=f"No supported files found at {path}",
                )
            ]

        responses: list[IngestResponse] = []
        for file_path in files:
            responses.append(self._ingest_file(file_path, source_type, tags))
        return responses

    def _ingest_file(self, path: Path, source_type: str, tags: list[str]) -> IngestResponse:
        text, extra = load_path(path)
        resolved_source_type = _resolve_source_type(path, source_type)
        chunks = chunk_text(text, self.settings.chunk_size, self.settings.chunk_overlap, resolved_source_type)
        document_id = str(uuid5(NAMESPACE_URL, str(path.resolve())))
        if not chunks:
            return IngestResponse(document_id=document_id, chunk_count=0, status="skipped", message="Empty document")

        self.store.delete_document(document_id)
        vectors = self.embeddings.embed_texts([chunk.text for chunk in chunks])
        imported_at = datetime.now(timezone.utc)
        merged_tags = _merge_tags(tags, extra.get("tags"))
        metadata = DocumentMetadata(
            document_id=document_id,
            source_id=path.stem,
            source_type=resolved_source_type,
            title=str(extra.get("title") or path.stem),
            path=str(path),
            tags=merged_tags,
            imported_at=imported_at,
            chunk_count=len(chunks),
        )

        points = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            chunk_id = str(uuid5(NAMESPACE_URL, f"{document_id}:{chunk.index}"))
            chunk_meta = {
                **metadata.model_dump(mode="json"),
                **_payload_extra_metadata(extra),
                "chunk_index": chunk.index,
                "chunk_key": f"{document_id}:{chunk.index}",
                "text": chunk.text,
            }
            if chunk.section:
                chunk_meta["section"] = chunk.section
            points.append((chunk_id, vector, chunk_meta))
        self.store.upsert(points)
        return IngestResponse(document_id=document_id, chunk_count=len(chunks), status="indexed")


def _resolve_source_type(path: Path, source_type: str) -> str:
    if source_type != "mixed":
        return source_type

    parts = {part.lower() for part in path.parts}
    stem = path.stem.lower()

    if "modern_basics" in parts:
        if any(keyword in stem for keyword in ("安全", "禁忌", "辨别", "儿童", "孕产", "慢病", "老年")):
            return "safety_rule"
        return "modern_basics"

    if "classic_texts" in parts:
        return "classic_text"

    return "mixed"


def _merge_tags(explicit_tags: list[str], inferred_tags: object) -> list[str]:
    merged: list[str] = []
    for candidate in [*explicit_tags, *(_as_tag_list(inferred_tags))]:
        value = candidate.strip()
        if value and value not in merged:
            merged.append(value)
    return merged


def _as_tag_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _payload_extra_metadata(extra: dict) -> dict:
    protected_keys = {"document_id", "source_id", "source_type", "title", "path", "tags", "imported_at", "chunk_count"}
    return {key: value for key, value in extra.items() if key not in protected_keys}
