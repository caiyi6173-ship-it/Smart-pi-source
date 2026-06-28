from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    version: str
    database_path: str
    database_ready: bool


class AuditLogCreate(BaseModel):
    event_type: str = Field(min_length=1)
    actor: str = "local-user"
    summary: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    success: bool = True


class DeviceActionCreate(BaseModel):
    action: str = Field(min_length=1)
    method: str = "POST"
    path: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True
    executed: bool = False
    requires_confirmation: bool = True
    result: str = ""


class RagMessageCreate(BaseModel):
    session_id: str = "default"
    conversation_id: int | None = None
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    no_answer: bool = False
    evidence_status: str = "unknown"
    latency_ms: int = 0


class AgentRunCreate(BaseModel):
    session_id: str = "default"
    message: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    intent: str = "unknown"
    risk_level: str = "low"
    refused: bool = False
    actions: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)


class ServiceSnapshotCreate(BaseModel):
    service_name: str = Field(min_length=1)
    state: str = Field(min_length=1)
    detail: str = ""
    latency_ms: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class RuntimeSettingSet(BaseModel):
    value: Any
