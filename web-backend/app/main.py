from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Database
from app.repository import Repository
from app.schemas import (
    AgentRunCreate,
    AuditLogCreate,
    DeviceActionCreate,
    HealthResponse,
    RagMessageCreate,
    RuntimeSettingSet,
    ServiceSnapshotCreate,
)

settings = get_settings()
database = Database(settings.database_path)
repository = Repository(database)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    database.init()
    yield


app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    database.init()
    return HealthResponse(
        service=settings.app_name,
        version=settings.version,
        database_path=str(settings.database_path),
        database_ready=settings.database_path.exists(),
    )


@app.post("/api/v1/audit-logs")
def create_audit_log(item: AuditLogCreate):
    return repository.create_audit_log(item)


@app.get("/api/v1/audit-logs")
def list_audit_logs(limit: int = Query(default=50, ge=1, le=200)):
    return repository.list_audit_logs(limit)


@app.post("/api/v1/device-actions")
def create_device_action(item: DeviceActionCreate):
    audit = AuditLogCreate(
        event_type="device_action",
        summary=f"{item.action} -> {item.path}",
        payload=item.model_dump(),
        success=True,
    )
    action = repository.create_device_action(item)
    repository.create_audit_log(audit)
    return action


@app.get("/api/v1/device-actions")
def list_device_actions(limit: int = Query(default=50, ge=1, le=200)):
    return repository.list_device_actions(limit)


@app.post("/api/v1/rag/messages")
def create_rag_message(item: RagMessageCreate):
    message = repository.create_rag_message(item)
    repository.create_audit_log(
        AuditLogCreate(
            event_type="rag_message",
            summary=item.question,
            payload={"conversation_id": message.get("conversation_id"), "no_answer": item.no_answer},
            success=not item.no_answer,
        )
    )
    return message


@app.get("/api/v1/rag/messages")
def list_rag_messages(limit: int = Query(default=50, ge=1, le=200)):
    return repository.list_rag_messages(limit)


@app.post("/api/v1/agent/runs")
def create_agent_run(item: AgentRunCreate):
    run = repository.create_agent_run(item)
    repository.create_audit_log(
        AuditLogCreate(
            event_type="agent_run",
            summary=f"{item.intent}: {item.message}",
            payload={"risk_level": item.risk_level, "refused": item.refused, "actions": item.actions},
            success=not item.refused,
        )
    )
    return run


@app.get("/api/v1/agent/runs")
def list_agent_runs(limit: int = Query(default=50, ge=1, le=200)):
    return repository.list_agent_runs(limit)


@app.post("/api/v1/service-snapshots")
def create_service_snapshot(item: ServiceSnapshotCreate):
    return repository.create_service_snapshot(item)


@app.get("/api/v1/service-snapshots")
def list_service_snapshots(limit: int = Query(default=50, ge=1, le=200)):
    return repository.list_service_snapshots(limit)


@app.put("/api/v1/settings/{key}")
def set_runtime_setting(key: str, item: RuntimeSettingSet):
    return repository.set_runtime_setting(key, item)


@app.get("/api/v1/settings")
def list_runtime_settings():
    return repository.list_runtime_settings()
