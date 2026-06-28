import os
from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["SMARTPI_WEB_DB"] = str(ROOT / "data" / "test_smartpi_web.db")

from app.main import app, database  # noqa: E402


def setup_module() -> None:
    db_path = Path(os.environ["SMARTPI_WEB_DB"])
    if db_path.exists():
        db_path.unlink()
    database.init()


client = TestClient(app)


def test_health_initializes_database() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database_ready"] is True


def test_create_and_list_audit_log() -> None:
    response = client.post(
        "/api/v1/audit-logs",
        json={
            "event_type": "web_click",
            "actor": "tester",
            "summary": "clicked refresh",
            "payload": {"button": "refresh"},
            "success": True,
        },
    )
    assert response.status_code == 200
    created = response.json()
    assert created["event_type"] == "web_click"
    assert created["payload"]["button"] == "refresh"

    listed = client.get("/api/v1/audit-logs").json()
    assert any(item["id"] == created["id"] for item in listed)


def test_create_device_action_also_writes_audit_log() -> None:
    response = client.post(
        "/api/v1/device-actions",
        json={
            "action": "camera.start",
            "path": "/control/camera/start",
            "parameters": {"profile": "low-latency"},
            "dry_run": True,
            "executed": False,
            "requires_confirmation": True,
            "result": "dry run only",
        },
    )
    assert response.status_code == 200
    action = response.json()
    assert action["dry_run"] is True
    assert action["parameters"]["profile"] == "low-latency"

    logs = client.get("/api/v1/audit-logs").json()
    assert any(item["event_type"] == "device_action" for item in logs)


def test_create_rag_message() -> None:
    response = client.post(
        "/api/v1/rag/messages",
        json={
            "session_id": "test",
            "question": "舌苔黄腻说明什么？",
            "answer": "仅供中医知识参考。",
            "citations": [{"title": "demo"}],
            "no_answer": False,
            "evidence_status": "supported",
            "latency_ms": 123,
        },
    )
    assert response.status_code == 200
    message = response.json()
    assert message["question"].startswith("舌苔")
    assert message["citations"][0]["title"] == "demo"


def test_create_agent_run_and_setting() -> None:
    run_response = client.post(
        "/api/v1/agent/runs",
        json={
            "session_id": "test",
            "message": "打开摄像头识别",
            "answer": "dry-run",
            "intent": "device_control",
            "risk_level": "low",
            "refused": False,
            "actions": [{"action": "camera.start", "dry_run": True}],
            "citations": [],
        },
    )
    assert run_response.status_code == 200
    assert run_response.json()["actions"][0]["action"] == "camera.start"

    setting_response = client.put("/api/v1/settings/runtime_mode", json={"value": {"mode": "mock"}})
    assert setting_response.status_code == 200
    assert setting_response.json()["value"]["mode"] == "mock"

    settings = client.get("/api/v1/settings").json()
    assert any(item["key"] == "runtime_mode" for item in settings)
