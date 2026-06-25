from app.schemas import (
    AgentAction,
    AgentChatResponse,
    Citation,
    IntentResult,
    RagResult,
    SafetyResult,
    TongueResult,
    TraceStep,
)


class CitationAnswerAgent:
    def run(
        self,
        message: str,
        safety: SafetyResult,
        intent: IntentResult,
        rag: RagResult | None,
        tongue: TongueResult | None,
        actions: list[AgentAction],
        trace: list[TraceStep],
    ) -> AgentChatResponse:
        citations: list[Citation] = []
        answer_parts: list[str] = []
        refused = False

        if safety.must_refuse:
            refused = True
            answer_parts.append(safety.safety_message)
        elif tongue is not None and not (rag is not None and rag.no_answer and rag.retrieval_strategy == "error"):
            if rag is not None and rag.answer:
                answer_parts.append(rag.answer)
                citations.extend(rag.citations)
            else:
                answer_parts.append(tongue.explanation)
                citations.extend(tongue.citations)
        elif rag is not None:
            if rag.no_answer:
                refused = True
                answer_parts.append("知识库未找到可靠依据，暂时不能基于当前资料回答。")
            else:
                answer_parts.append(rag.answer)
                citations.extend(rag.citations)
        elif actions:
            answer_parts.append(actions[0].result)
        else:
            answer_parts.append("我已收到你的问题。当前 Agent Orchestrator 还没有为这类问题配置专用工具。")

        medical_intents = {"tcm_knowledge", "classic_interpret", "tongue_explain", "unsafe_medical"}
        needs_medical_safety = safety.safety_required or intent.primary_intent in medical_intents
        current_answer = " ".join(answer_parts)
        if needs_medical_safety and safety.safety_message not in current_answer and "仅供中医知识参考" not in current_answer:
            answer_parts.append(safety.safety_message)

        return AgentChatResponse(
            answer="\n\n".join(part for part in answer_parts if part),
            citations=citations,
            actions=actions,
            risk_level=safety.risk_level,
            intent=intent.primary_intent,
            refused=refused,
            trace=trace,
        )
