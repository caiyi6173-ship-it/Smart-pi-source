from app.agents.supervisor import SupervisorAgent
from app.schemas import AgentChatRequest, AgentOptions, Citation, RagResult


class FakeRagAgent:
    def run(self, question, *, source_type=None, top_k=8, user_context=None):
        return RagResult(
            answer=f"RAG answer: {question}",
            citations=[
                Citation(
                    title="测试来源",
                    source_id="source-1",
                    document_id="doc-1",
                    chunk_id="chunk-1",
                    source_type=source_type or "mixed",
                    score=0.9,
                )
            ],
            no_answer=False,
            retrieval_strategy="fake",
            rerank_provider="fake",
            latency_ms=1,
        )


class FailingRagAgent:
    def run(self, question, *, source_type=None, top_k=8, user_context=None):
        from app.agents.rag_agent import RagAgentError

        raise RagAgentError("offline")


def make_supervisor_with_fake_rag():
    supervisor = SupervisorAgent()
    supervisor.rag_agent = FakeRagAgent()
    return supervisor


def test_supervisor_tongue_labels_use_generated_rag_question():
    supervisor = make_supervisor_with_fake_rag()

    response = supervisor.run(
        AgentChatRequest(
            message="帮我解释这次舌象",
            tongue_labels=["yellowcoates", "chihenshe"],
            options=AgentOptions(include_trace=True),
        )
    )

    assert response.intent == "tongue_explain"
    assert response.refused is False
    assert "黄苔舌、齿痕舌" in response.answer
    assert response.citations
    assert any(step.agent == "TongueDiagnosisAgent" and step.status == "ok" for step in response.trace)
    assert any(step.agent == "RagAgent" and step.status == "ok" for step in response.trace)


def test_supervisor_device_command_is_dry_run_and_skips_rag():
    supervisor = make_supervisor_with_fake_rag()

    response = supervisor.run(
        AgentChatRequest(message="打开摄像头识别", options=AgentOptions(include_trace=True))
    )

    assert response.intent == "device_control"
    assert response.actions[0].action == "camera.start"
    assert response.actions[0].dry_run is True
    assert response.actions[0].executed is False
    assert any(step.agent == "RagAgent" and step.status == "skipped" for step in response.trace)


def test_supervisor_urgent_medical_question_refuses_and_skips_rag():
    supervisor = make_supervisor_with_fake_rag()

    response = supervisor.run(
        AgentChatRequest(message="我胸痛可以喝什么中药？", options=AgentOptions(include_trace=True))
    )

    assert response.intent == "unsafe_medical"
    assert response.refused is True
    assert response.risk_level == "urgent"
    assert any(step.agent == "RagAgent" and step.status == "skipped" for step in response.trace)


def test_supervisor_handles_rag_failure_without_crashing():
    supervisor = SupervisorAgent()
    supervisor.rag_agent = FailingRagAgent()

    response = supervisor.run(
        AgentChatRequest(message="舌苔黄腻说明什么？", options=AgentOptions(include_trace=True))
    )

    assert response.intent == "tongue_explain"
    assert response.refused is True
    assert "知识库未找到可靠依据" in response.answer
    assert any(step.agent == "RagAgent" and step.status == "error" for step in response.trace)
