import time
from pathlib import Path

from fastapi import FastAPI, HTTPException

from app.config import get_settings
from app.generation.qwen import AnswerGenerator
from app.ingest.service import IngestService
from app.retrieval.embeddings import EmbeddingClient
from app.retrieval.service import RetrievalService
from app.retrieval.vector_store import create_vector_store
from app.schemas import (
    Citation,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    QueryRequest,
    QueryResponse,
)

settings = get_settings()
embeddings = EmbeddingClient(settings)
vector_store = create_vector_store(settings)
retrieval_service = RetrievalService(settings, embeddings, vector_store)
ingest_service = IngestService(settings, embeddings, vector_store)
answer_generator = AnswerGenerator(settings)

app = FastAPI(title="smartpi RAG", version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    settings.data_raw_dir.mkdir(parents=True, exist_ok=True)
    settings.data_processed_dir.mkdir(parents=True, exist_ok=True)
    if vector_store.is_available():
        vector_store.ensure_ready()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    vector_ok = vector_store.is_available()
    return HealthResponse(
        status="ok" if vector_ok and embeddings.configured and answer_generator.configured else "degraded",
        vector_backend=settings.vector_backend,
        vector_store=vector_ok,
        embedding_configured=embeddings.configured,
        llm_configured=answer_generator.configured,
        collection=settings.qdrant_collection,
    )


@app.post("/api/v1/ingest", response_model=list[IngestResponse])
def ingest(request: IngestRequest) -> list[IngestResponse]:
    if not request.path and not request.source_id:
        raise HTTPException(status_code=400, detail="path or source_id is required")
    path = Path(request.path or request.source_id or "")
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"path not found: {path}")
    try:
        return ingest_service.ingest_path(path, request.source_type, request.tags)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/v1/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    start = time.perf_counter()
    try:
        retrieval = retrieval_service.retrieve(request.question, request.top_k, request.filters)
        chunks = retrieval.chunks
        answer = answer_generator.generate(request.question, chunks, request.user_context)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    citations = [
        Citation(
            title=chunk.metadata.get("title", "未知来源"),
            source_id=chunk.metadata.get("source_id", ""),
            document_id=chunk.document_id,
            chunk_id=chunk.id,
            page=chunk.metadata.get("page"),
            section=chunk.metadata.get("section"),
            score=chunk.score,
        )
        for chunk in chunks
    ]
    return QueryResponse(
        answer=answer,
        citations=citations,
        chunks=chunks if request.include_chunks else [],
        rewritten_queries=retrieval.rewritten_queries,
        retrieval_strategy=retrieval.strategy,
        rerank_provider=retrieval.rerank_provider,
        no_answer=not bool(chunks),
        model=settings.llm_model if answer_generator.configured else "offline-dev",
        latency_ms=int((time.perf_counter() - start) * 1000),
    )


@app.post("/api/v1/retrieve")
def retrieve(request: QueryRequest):
    try:
        retrieval = retrieval_service.retrieve(request.question, request.top_k, request.filters)
        return {
            "rewritten_queries": retrieval.rewritten_queries,
            "retrieval_strategy": retrieval.strategy,
            "rerank_provider": retrieval.rerank_provider,
            "no_answer": not bool(retrieval.chunks),
            "chunks": retrieval.chunks,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/v1/documents")
def list_documents():
    try:
        return vector_store.list_documents()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/api/v1/documents/{document_id}")
def delete_document(document_id: str):
    try:
        vector_store.delete_document(document_id)
        return {"document_id": document_id, "status": "deleted"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
