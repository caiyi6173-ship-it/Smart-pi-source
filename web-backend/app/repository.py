from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.database import Database
from app.schemas import (
    AgentRunCreate,
    AuditLogCreate,
    DeviceActionCreate,
    RagMessageCreate,
    RuntimeSettingSet,
    ServiceSnapshotCreate,
)


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    for key in list(result):
        if key.endswith("_json"):
            plain = key.removesuffix("_json")
            result[plain] = json.loads(result.pop(key) or "{}")
    for key in ("success", "dry_run", "executed", "requires_confirmation", "no_answer", "refused"):
        if key in result:
            result[key] = bool(result[key])
    return result


class Repository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create_audit_log(self, item: AuditLogCreate) -> dict[str, Any]:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO audit_logs(event_type, actor, summary, payload_json, success)
                VALUES (?, ?, ?, ?, ?)
                """,
                (item.event_type, item.actor, item.summary, dumps(item.payload), int(item.success)),
            )
            return self.get_by_id(conn, "audit_logs", cursor.lastrowid)

    def list_audit_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.list_rows("audit_logs", limit)

    def create_device_action(self, item: DeviceActionCreate) -> dict[str, Any]:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO device_actions(action, method, path, parameters_json, dry_run, executed, requires_confirmation, result)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.action,
                    item.method,
                    item.path,
                    dumps(item.parameters),
                    int(item.dry_run),
                    int(item.executed),
                    int(item.requires_confirmation),
                    item.result,
                ),
            )
            return self.get_by_id(conn, "device_actions", cursor.lastrowid)

    def list_device_actions(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.list_rows("device_actions", limit)

    def create_rag_message(self, item: RagMessageCreate) -> dict[str, Any]:
        with self.db.connect() as conn:
            conversation_id = item.conversation_id or self.ensure_conversation(conn, item.session_id, item.question)
            cursor = conn.execute(
                """
                INSERT INTO rag_messages(conversation_id, question, answer, citations_json, no_answer, evidence_status, latency_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    item.question,
                    item.answer,
                    dumps(item.citations),
                    int(item.no_answer),
                    item.evidence_status,
                    item.latency_ms,
                ),
            )
            conn.execute("UPDATE rag_conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (conversation_id,))
            return self.get_by_id(conn, "rag_messages", cursor.lastrowid)

    def list_rag_messages(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.list_rows("rag_messages", limit)

    def create_agent_run(self, item: AgentRunCreate) -> dict[str, Any]:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO agent_runs(session_id, message, answer, intent, risk_level, refused, actions_json, citations_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.session_id,
                    item.message,
                    item.answer,
                    item.intent,
                    item.risk_level,
                    int(item.refused),
                    dumps(item.actions),
                    dumps(item.citations),
                ),
            )
            return self.get_by_id(conn, "agent_runs", cursor.lastrowid)

    def list_agent_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.list_rows("agent_runs", limit)

    def create_service_snapshot(self, item: ServiceSnapshotCreate) -> dict[str, Any]:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO service_snapshots(service_name, state, detail, latency_ms, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (item.service_name, item.state, item.detail, item.latency_ms, dumps(item.payload)),
            )
            return self.get_by_id(conn, "service_snapshots", cursor.lastrowid)

    def list_service_snapshots(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.list_rows("service_snapshots", limit)

    def set_runtime_setting(self, key: str, item: RuntimeSettingSet) -> dict[str, Any]:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO runtime_settings(key, value_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=CURRENT_TIMESTAMP
                """,
                (key, dumps(item.value)),
            )
            row = conn.execute("SELECT * FROM runtime_settings WHERE key=?", (key,)).fetchone()
            return row_to_dict(row)

    def list_runtime_settings(self) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM runtime_settings ORDER BY key ASC").fetchall()
            return [row_to_dict(row) for row in rows]

    def ensure_conversation(self, conn: sqlite3.Connection, session_id: str, title: str) -> int:
        cursor = conn.execute(
            "INSERT INTO rag_conversations(session_id, title) VALUES (?, ?)",
            (session_id, title[:80]),
        )
        return int(cursor.lastrowid)

    def list_rows(self, table: str, limit: int) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 200))
        with self.db.connect() as conn:
            rows = conn.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (safe_limit,)).fetchall()
            return [row_to_dict(row) for row in rows]

    def get_by_id(self, conn: sqlite3.Connection, table: str, row_id: int | None) -> dict[str, Any]:
        row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()
        if row is None:
            raise RuntimeError(f"row not found: {table}#{row_id}")
        return row_to_dict(row)
