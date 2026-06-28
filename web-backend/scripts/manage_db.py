from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.database import Database  # noqa: E402


TABLES = [
    "audit_logs",
    "device_actions",
    "rag_conversations",
    "rag_messages",
    "agent_runs",
    "service_snapshots",
    "runtime_settings",
]


def json_default(value: Any) -> str:
    return str(value)


def db_path_from_args(args: argparse.Namespace) -> Path:
    if args.db:
        return Path(args.db)
    return get_settings().database_path


def connect(db_path: Path) -> sqlite3.Connection:
    Database(db_path).init()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


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


def command_stats(args: argparse.Namespace) -> int:
    db_path = db_path_from_args(args)
    with connect(db_path) as conn:
        stats = {
            "database": str(db_path),
            "size_bytes": db_path.stat().st_size if db_path.exists() else 0,
            "tables": {},
        }
        for table in TABLES:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            stats["tables"][table] = count
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


def command_backup(args: argparse.Namespace) -> int:
    db_path = db_path_from_args(args)
    Database(db_path).init()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = output_dir / f"{db_path.stem}_{stamp}.db"
    with sqlite3.connect(db_path) as source:
        with sqlite3.connect(backup_path) as target:
            source.backup(target)
    print(json.dumps({"source": str(db_path), "backup": str(backup_path)}, ensure_ascii=False, indent=2))
    return 0


def command_export(args: argparse.Namespace) -> int:
    db_path = db_path_from_args(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        exported: dict[str, Any] = {
            "database": str(db_path),
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "tables": {},
        }
        tables = TABLES if args.table == "all" else [args.table]
        for table in tables:
            rows = conn.execute(f"SELECT * FROM {table} ORDER BY rowid ASC").fetchall()
            exported["tables"][table] = [row_to_dict(row) for row in rows]
    output.write_text(json.dumps(exported, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    print(json.dumps({"output": str(output), "tables": list(exported["tables"].keys())}, ensure_ascii=False, indent=2))
    return 0


def command_clear_demo(args: argparse.Namespace) -> int:
    db_path = db_path_from_args(args)
    if args.all and not args.yes:
        print("Refusing to clear all data without --yes", file=sys.stderr)
        return 2
    with connect(db_path) as conn:
        if args.all:
            for table in [
                "service_snapshots",
                "agent_runs",
                "rag_messages",
                "rag_conversations",
                "device_actions",
                "audit_logs",
                "runtime_settings",
            ]:
                conn.execute(f"DELETE FROM {table}")
            mode = "all"
        else:
            conn.execute(
                """
                DELETE FROM audit_logs
                WHERE actor IN ('codex', 'web-dashboard')
                   OR event_type LIKE '%smoke%'
                   OR event_type LIKE '%mock%'
                   OR summary LIKE '%演示%'
                   OR summary LIKE '%smoke%'
                """
            )
            conn.execute("DELETE FROM device_actions WHERE dry_run=1 OR result LIKE '%演示%' OR result LIKE '%dry%'")
            conn.execute("DELETE FROM agent_runs WHERE answer LIKE '%演示%' OR message LIKE '%演示%'")
            conn.execute("DELETE FROM rag_messages WHERE answer LIKE '%演示%' OR question LIKE '%演示%'")
            conn.execute("DELETE FROM rag_conversations WHERE id NOT IN (SELECT DISTINCT conversation_id FROM rag_messages)")
            conn.execute("DELETE FROM service_snapshots WHERE detail LIKE '%mock%' OR payload_json LIKE '%mock%'")
            mode = "demo"
        conn.commit()
    print(json.dumps({"database": str(db_path), "cleared": mode}, ensure_ascii=False, indent=2))
    return 0


def command_vacuum(args: argparse.Namespace) -> int:
    db_path = db_path_from_args(args)
    with connect(db_path) as conn:
        conn.execute("VACUUM")
    print(json.dumps({"database": str(db_path), "vacuumed": True}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage smartpi web-backend SQLite database")
    parser.add_argument("--db", help="SQLite database path. Defaults to SMARTPI_WEB_DB or data/smartpi_web.db")
    subparsers = parser.add_subparsers(dest="command", required=True)

    stats = subparsers.add_parser("stats", help="Print table counts")
    stats.set_defaults(func=command_stats)

    backup = subparsers.add_parser("backup", help="Create a SQLite backup copy")
    backup.add_argument("--output-dir", default="backups", help="Backup output directory")
    backup.set_defaults(func=command_backup)

    export = subparsers.add_parser("export", help="Export database rows to JSON")
    export.add_argument("--output", default="exports/smartpi_web_export.json", help="JSON output path")
    export.add_argument("--table", choices=["all", *TABLES], default="all", help="Table to export")
    export.set_defaults(func=command_export)

    clear = subparsers.add_parser("clear-demo", help="Clear demo/mock/smoke data")
    clear.add_argument("--all", action="store_true", help="Clear all tables, including real records")
    clear.add_argument("--yes", action="store_true", help="Required with --all")
    clear.set_defaults(func=command_clear_demo)

    vacuum = subparsers.add_parser("vacuum", help="Run SQLite VACUUM")
    vacuum.set_defaults(func=command_vacuum)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
