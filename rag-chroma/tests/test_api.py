from fastapi.testclient import TestClient

from app import main as rag_main
from app.main import app
from app.schemas import Chunk


def test_health():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["vector_backend"] in {"local", "qdrant", "chroma"}


def test_query_refuses_when_no_evidence(monkeypatch):
    class DummyRetrieval:
        chunks = []
        rewritten_queries = ["完全无关的问题"]
        strategy = "hybrid_rrf_bm25_vector"
        rerank_provider = "local"

    class DummyRetrievalService:
        def retrieve(self, question, top_k=None, filters=None):
            return DummyRetrieval()

    class DummyAnswerGenerator:
        configured = False

        def generate(self, question, chunks, user_context=None):
            return "知识库未找到可靠依据，因此不生成推断性回答。"

    monkeypatch.setattr(rag_main, "retrieval_service", DummyRetrievalService())
    monkeypatch.setattr(rag_main, "answer_generator", DummyAnswerGenerator())

    client = TestClient(app)
    response = client.post("/api/v1/query", json={"question": "完全无关的问题"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["no_answer"] is True
    assert payload["evidence_status"] == "insufficient_evidence"
    assert payload["evidence_count"] == 0
    assert payload["citations"] == []


def test_query_returns_traceable_citations(monkeypatch):
    chunk = Chunk(
        id="chunk-1",
        document_id="doc-1",
        text="舌苔黄腻多提示湿热内蕴，需结合其他症状综合判断。",
        score=0.92,
        vector_score=0.88,
        lexical_score=0.73,
        rerank_score=0.92,
        retrieval_source="hybrid+dashscope_rerank",
        metadata={
            "title": "四诊基础",
            "source_id": "modern_basics/05_四诊基础.md",
            "source_type": "modern_basics",
            "path": "data/raw/modern_basics/05_四诊基础.md",
            "section": "舌诊",
        },
    )

    class DummyRetrieval:
        chunks = [chunk]
        rewritten_queries = ["舌苔黄腻说明什么？", "湿热"]
        strategy = "tongue_hybrid_rrf_bm25_vector_metadata_routes"
        rerank_provider = "dashscope"

    class DummyRetrievalService:
        def retrieve(self, question, top_k=None, filters=None):
            return DummyRetrieval()

    class DummyAnswerGenerator:
        configured = False

        def generate(self, question, chunks, user_context=None):
            return "舌苔黄腻通常提示湿热相关问题，需要结合症状判断。[1]"

    monkeypatch.setattr(rag_main, "retrieval_service", DummyRetrievalService())
    monkeypatch.setattr(rag_main, "answer_generator", DummyAnswerGenerator())

    client = TestClient(app)
    response = client.post("/api/v1/query", json={"question": "舌苔黄腻说明什么？", "include_chunks": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["no_answer"] is False
    assert payload["evidence_status"] == "supported"
    assert payload["evidence_count"] == 1
    assert payload["citations"][0]["index"] == 1
    assert payload["citations"][0]["source_type"] == "modern_basics"
    assert payload["citations"][0]["chunk_id"] == "chunk-1"
    assert payload["citations"][0]["retrieval_source"] == "hybrid+dashscope_rerank"
    assert "湿热内蕴" in payload["citations"][0]["excerpt"]
    assert payload["chunks"][0]["id"] == "chunk-1"
