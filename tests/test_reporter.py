from __future__ import annotations

import json
from pathlib import Path

from pgaudit_runner.reporter import generate_report


def _audit_json(tmp_path: Path, results: list[dict]) -> Path:
    metadata = {
        "manifest_name": "Test",
        "started_at": "2026-01-01T10:00:00+00:00",
        "connection": {"server_version": "PostgreSQL 17.0", "databases_targeted": ["db1"]},
        "summary": {
            "total": len(results),
            "success": sum(1 for r in results if r["status"] == "success"),
            "skipped": sum(1 for r in results if r["status"] == "skipped"),
            "error": sum(1 for r in results if r["status"] == "error"),
        },
    }
    path = tmp_path / "audit.json"
    path.write_text(json.dumps({"metadata": metadata, "results": results}), encoding="utf-8")
    return path


def _result(**overrides) -> dict:
    base = {
        "id": "q1", "title": "Requête 1", "scope": "database", "target": "db1",
        "sql": "SELECT 1", "status": "success", "requires_superuser": False,
        "columns": None, "rows": None, "row_count": None, "error": None, "skip_reason": None,
    }
    base.update(overrides)
    return base


def test_report_renders_success_table_and_truncation(tmp_path: Path):
    rows = [{"n": i} for i in range(5)]
    audit = _audit_json(tmp_path, [_result(columns=["n"], rows=rows, row_count=5)])

    report = generate_report(audit, max_rows=2)

    assert "✅" in report
    assert "| n |" in report
    assert "3 ligne(s) supplémentaire(s)" in report


def test_report_renders_skipped_and_error_sections(tmp_path: Path):
    audit = _audit_json(tmp_path, [
        _result(id="q_skip", status="skipped", skip_reason="désactivée", requires_superuser=True),
        _result(id="q_err", status="error", error={
            "message": "boom", "sqlstate": "42P01", "full_traceback": "...",
        }),
    ])

    report = generate_report(audit, max_rows=100)

    assert "⏭️" in report
    assert "❌" in report
    assert "## Points d'attention" in report
    assert "boom" in report
    assert "À relancer avec superuser" in report


def test_report_empty_rows_shows_no_result_message(tmp_path: Path):
    audit = _audit_json(tmp_path, [_result(columns=["n"], rows=[], row_count=0)])

    report = generate_report(audit)

    assert "Aucun résultat" in report
