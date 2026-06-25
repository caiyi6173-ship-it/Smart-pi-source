from app.agents.citation_answer_agent import CitationAnswerAgent
from app.agents.device_agent import DeviceControlAgent
from app.agents.intent_router import IntentRouterAgent
from app.agents.rag_agent import RagAgent, RagAgentError
from app.agents.safety_triage import SafetyTriageAgent
from app.agents.tongue_agent import TongueDiagnosisAgent
from app.clients.edge_bridge import EdgeBridgeClient
from app.clients.rag_client import RagClient
from app.clients.tongue_labels import TongueLabelResolver
from app.config import Settings, get_settings
from app.schemas import AgentChatRequest, AgentChatResponse, RagResult, TongueResult, TraceStep


class SupervisorAgent:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.safety_agent = SafetyTriageAgent()
        self.intent_agent = IntentRouterAgent()
        self.rag_agent = RagAgent(RagClient(self.settings))
        self.tongue_agent = TongueDiagnosisAgent(TongueLabelResolver(self.settings.tongue_class_map_path))
        self.device_agent = DeviceControlAgent(self.settings, EdgeBridgeClient(self.settings))
        self.answer_agent = CitationAnswerAgent()

    def run(self, request: AgentChatRequest) -> AgentChatResponse:
        trace: list[TraceStep] = []

        safety = self.safety_agent.run(request.message)
        trace.append(
            TraceStep(
                agent="SafetyTriageAgent",
                status="ok",
                summary=f"risk_level={safety.risk_level}, must_refuse={safety.must_refuse}",
                data=safety.model_dump(),
            )
        )

        intent = self.intent_agent.run(request.message, safety.must_refuse)
        if request.tongue_labels and not safety.must_refuse and intent.primary_intent in {"general_chat", "unknown"}:
            intent.primary_intent = "tongue_explain"
            intent.secondary_intents = ["tcm_knowledge"]
            intent.need_rag = True
        trace.append(
            TraceStep(
                agent="IntentRouterAgent",
                status="ok",
                summary=f"primary_intent={intent.primary_intent}",
                data=intent.model_dump(),
            )
        )

        rag: RagResult | None = None
        tongue: TongueResult | None = None
        actions = []

        if intent.primary_intent == "tongue_explain" and not safety.must_refuse:
            tongue = self.tongue_agent.run(
                request.message,
                tongue_labels=request.tongue_labels,
                tongue_confidences=request.tongue_confidences,
            )
            trace.append(
                TraceStep(
                    agent="TongueDiagnosisAgent",
                    status="ok",
                    summary=f"labels={len(tongue.labels)}, followups={len(tongue.followup_questions)}",
                    data={
                        "labels": tongue.labels,
                        "followup_questions": tongue.followup_questions,
                        "rag_question": tongue.rag_question,
                        "source_available": tongue.source_available,
                    },
                )
            )
        else:
            trace.append(TraceStep(agent="TongueDiagnosisAgent", status="skipped", summary="Tongue flow not required"))

        if intent.need_rag and not safety.must_refuse:
            source_type = "classic_text" if intent.primary_intent == "classic_interpret" else None
            rag_question = tongue.rag_question if tongue is not None and tongue.rag_question else request.message
            try:
                rag = self.rag_agent.run(
                    rag_question,
                    source_type=source_type,
                    user_context=request.user_context,
                )
                trace.append(
                    TraceStep(
                        agent="RagAgent",
                        status="ok",
                        summary=f"no_answer={rag.no_answer}, citations={len(rag.citations)}",
                        data={
                            "no_answer": rag.no_answer,
                            "citation_count": len(rag.citations),
                            "chunk_count": len(rag.chunks),
                            "retrieval_strategy": rag.retrieval_strategy,
                            "rerank_provider": rag.rerank_provider,
                            "latency_ms": rag.latency_ms,
                        },
                    )
                )
            except RagAgentError as exc:
                rag = RagResult(
                    answer="知识库服务当前不可用，请先启动 rag-chroma 后再重试。",
                    no_answer=True,
                    retrieval_strategy="error",
                    rerank_provider="none",
                )
                trace.append(
                    TraceStep(
                        agent="RagAgent",
                        status="error",
                        summary=str(exc),
                        data={"error": str(exc), "rag_base_url": self.settings.rag_base_url},
                    )
                )
        else:
            trace.append(TraceStep(agent="RagAgent", status="skipped", summary="RAG not required"))

        if intent.need_device_action and not safety.must_refuse:
            confirm_device_action = bool(request.user_context.get("confirm_device_action", False))
            action = self.device_agent.run(request.message, confirm=confirm_device_action)
            actions.append(action)
            trace.append(
                TraceStep(
                    agent="DeviceControlAgent",
                    status="ok",
                    summary=f"action={action.action}, dry_run={action.dry_run}, executed={action.executed}",
                    data={
                        "action": action.action,
                        "method": action.method,
                        "path": action.path,
                        "action_marker": action.action_marker,
                        "requires_confirmation": action.requires_confirmation,
                        "dry_run": action.dry_run,
                        "executed": action.executed,
                        "parameters": action.parameters,
                    },
                )
            )
        else:
            trace.append(TraceStep(agent="DeviceControlAgent", status="skipped", summary="Device action not required"))

        trace.append(
            TraceStep(
                agent="CitationAnswerAgent",
                status="ok",
                summary="final answer composed",
            )
        )
        response = self.answer_agent.run(request.message, safety, intent, rag, tongue, actions, trace)

        if not request.options.include_trace:
            response.trace = []
        if not request.options.include_citations:
            response.citations = []
        return response
