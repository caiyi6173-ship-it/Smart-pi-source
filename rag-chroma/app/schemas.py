from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    document_id: str
    source_id: str
    source_type: str = "mixed"
    title: str
    path: str | None = None
    tags: list[str] = Field(default_factory=list)
    imported_at: datetime
    chunk_count: int = 0


class Chunk(BaseModel):
    id: str
    document_id: str
    text: str
    score: float | None = None
    vector_score: float | None = None
    lexical_score: float | None = None
    rerank_score: float | None = None
    retrieval_source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Citation(BaseModel):
    title: str
    source_id: str
    document_id: str
    chunk_id: str
    page: int | None = None
    section: str | None = None
    score: float | None = None


class IngestRequest(BaseModel):
    path: str | None = None
    source_id: str | None = None
    source_type: str = "mixed"
    tags: list[str] = Field(default_factory=list)


class IngestResponse(BaseModel):
    document_id: str
    chunk_count: int
    status: Literal["indexed", "skipped", "error"]
    message: str | None = None


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=30)
    filters: dict[str, Any] = Field(default_factory=dict)
    user_context: dict[str, Any] = Field(default_factory=dict)
    include_chunks: bool = False


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    chunks: list[Chunk] = Field(default_factory=list)
    rewritten_queries: list[str] = Field(default_factory=list)
    retrieval_strategy: str = "hybrid"
    rerank_provider: str = "none"
    no_answer: bool = False
    model: str
    latency_ms: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    vector_backend: str
    vector_store: bool
    embedding_configured: bool
    llm_configured: bool
    collection: str
