from app.agents.rag_agent import RagAgent


class FakeRagClient:
    def query(self, question, *, top_k=8, filters=None, user_context=None, include_chunks=True):
        return {
            "answer": f"answer for {question}",
            "citations": [
                {
                    "title": "测试来源",
                    "source_id": "source-1",
                    "document_id": "doc-1",
                    "chunk_id": "chunk-1",
                    "score": 0.9,
                }
            ],
            "chunks": [
                {
                    "id": "chunk-1",
                    "document_id": "doc-1",
                    "text": "chunk text",
                    "metadata": {"source_type": "modern_basics"},
                }
            ],
            "no_answer": False,
            "retrieval_strategy": "hybrid",
            "rerank_provider": "fake",
            "latency_ms": 12,
        }


def test_rag_agent_maps_query_response():
    result = RagAgent(FakeRagClient()).run("舌苔黄腻说明什么？")

    assert result.no_answer is False
    assert result.answer.startswith("answer for")
    assert result.citations[0].title == "测试来源"
    assert result.citations[0].source_type == "modern_basics"
    assert result.retrieval_strategy == "hybrid"
    assert result.rerank_provider == "fake"
