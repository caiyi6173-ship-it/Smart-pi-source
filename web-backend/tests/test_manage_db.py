import json
from pathlib import Path
import sqlite3

from scripts.manage_db import main


def test_manage_db_stats_backup_export_and_clear(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "smartpi_test.db"
    backup_dir = tmp_path / "backups"
    export_path = tmp_path / "exports" / "audit.json"

    assert main(["--db", str(db_path), "stats"]) == 0
    stats = json.loads(capsys.readouterr().out)
    assert stats["tables"]["audit_logs"] == 0

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO audit_logs(event_type, actor, summary, payload_json, success) VALUES (?, ?, ?, ?, ?)",
            ("smoke_test", "codex", "demo smoke", '{"demo":true}', 1),
        )
        conn.commit()

    assert main(["--db", str(db_path), "backup", "--output-dir", str(backup_dir)]) == 0
    backup_output = json.loads(capsys.readouterr().out)
    assert Path(backup_output["backup"]).exists()

    assert main(["--db", str(db_path), "export", "--table", "audit_logs", "--output", str(export_path)]) == 0
    export_output = json.loads(capsys.readouterr().out)
    assert export_output["tables"] == ["audit_logs"]
    exported = json.loads(export_path.read_text(encoding="utf-8"))
    assert exported["tables"]["audit_logs"][0]["payload"]["demo"] is True

    assert main(["--db", str(db_path), "clear-demo"]) == 0
    clear_output = json.loads(capsys.readouterr().out)
    assert clear_output["cleared"] == "demo"

    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    assert count == 0


def test_clear_all_requires_yes(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "smartpi_test.db"
    assert main(["--db", str(db_path), "clear-demo", "--all"]) == 2
    assert "without --yes" in capsys.readouterr().err
