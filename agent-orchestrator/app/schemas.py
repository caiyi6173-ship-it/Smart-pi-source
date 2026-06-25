from typing import Any, Literal

from pydantic import BaseModel, Field


InputType = Literal["voice", "text", "api"]
RiskLevel = Literal["low", "medium", "high", "urgent"]
IntentType = Literal[
    "tcm_knowledge",
    "classic_interpret",
    "tongue_explain",
    "device_control",
    "project_help",
    "general_chat",
    "unsafe_medical",
    "unknown",
]


class AgentOptions(BaseModel):
    include_trace: bool = False
    include_citations: bool = True


class AgentChatRequest(BaseModel):
    session_id: str = "default"
    message: str
    input_type: InputType = "text"
    tongue_labels: list[str] = Field(default_factory=list)
    tongue_confidences: dict[str, float] = Field(default_factory=dict)
    user_context: dict[str, Any] = Field(default_factory=dict)
    options: AgentOptions = Field(default_factory=AgentOptions)


class Citation(BaseModel):
    title: str = ""
    source_id: str = ""
    document_id: str = ""
    chunk_id: str = ""
    source_type: str = ""
    score: float | None = None


class AgentAction(BaseModel):
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    method: str = ""
    path: str = ""
    action_marker: str = ""
    requires_confirmation: bool = False
    executed: bool = False
    dry_run: bool = True
    result: str = ""


class TraceStep(BaseModel):
    agent: str
    status: Literal["ok", "skipped", "error"]
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)


class SafetyResult(BaseModel):
    risk_level: RiskLevel = "low"
    safety_required: bool = False
    must_refuse: bool = False
    safety_message: str = "仅供中医知识参考，不能替代医生诊断。"
    reason: str = ""


class IntentResult(BaseModel):
    primary_intent: IntentType = "unknown"
    secondary_intents: list[IntentType] = Field(default_factory=list)
    need_rag: bool = False
    need_device_action: bool = False
    need_clarification: bool = False


class RagResult(BaseModel):
    answer: str = ""
    citations: list[Citation] = Field(default_factory=list)
    chunks: list[dict[str, Any]] = Field(default_factory=list)
    no_answer: bool = True
    retrieval_strategy: str = "mock"
    rerank_provider: str = "none"
    latency_ms: int = 0


class TongueResult(BaseModel):
    explanation: str = ""
    followup_questions: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    labels: list[dict[str, Any]] = Field(default_factory=list)
    rag_question: str = ""
    source_available: bool = False


class AgentChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    actions: list[AgentAction] = Field(default_factory=list)
    risk_level: RiskLevel = "low"
    intent: IntentType = "unknown"
    refused: bool = False
    trace: list[TraceStep] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"] = "ok"
    service: str = "smartpi-agent-orchestrator"
    version: str = "0.1.0"
    rag_base_url: str
    openclaw_configured: bool
