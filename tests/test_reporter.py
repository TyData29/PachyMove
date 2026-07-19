from __future__ import annotations

import json
from pathlib import Path

from pgaudit_runner.reporter import extraire_synthese, generate_report


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
        "expect_rows": None, "severity_if_unexpected": "vigilance",
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


# ── Synthèse / verdicts (specs_verdicts.md) ──────────────────────────────────


def test_report_without_severity_mechanism_has_no_synthese_section(tmp_path: Path):
    # Critère #1 : aucune requête n'utilise severite/expect_rows -> rapport
    # identique à avant, aucune régression (pas de section Synthèse du tout).
    audit = _audit_json(tmp_path, [_result(columns=["n"], rows=[{"n": 1}], row_count=1)])

    report = generate_report(audit)

    assert "## Synthèse" not in report


def test_report_expect_rows_satisfied_not_in_synthese(tmp_path: Path):
    # Critère #2 : expect_rows: 0 avec 0 ligne -> n'apparaît pas dans la synthèse.
    audit = _audit_json(tmp_path, [
        _result(id="invalid_indexes", scope="database", row_count=0,
                expect_rows=0, severity_if_unexpected="bloquant"),
    ])

    report = generate_report(audit)

    assert "## Synthèse" in report
    assert "_Aucun bloquant ni point de vigilance détecté._" in report
    synthese_section = report.split("## Synthèse")[1].split("## Sommaire")[0]
    assert "invalid_indexes" not in synthese_section


def test_report_expect_rows_mismatch_defaults_to_vigilance(tmp_path: Path):
    # Critère #3 : expect_rows: 0 avec 3 lignes -> vigilance par défaut.
    audit = _audit_json(tmp_path, [
        _result(id="invalid_indexes", scope="database", row_count=3, expect_rows=0),
    ])

    report = generate_report(audit)

    assert "### Points de vigilance" in report
    assert "### Bloquants" not in report
    assert "3 ligne(s) trouvée(s), 0 attendue(s)" in report


def test_report_severite_column_shows_exact_constat(tmp_path: Path):
    # Critère #4 : convention de colonnes -> le constat exact est affiché, pas
    # le message générique d'expect_rows.
    audit = _audit_json(tmp_path, [
        _result(
            id="collation_version_mismatch", scope="database",
            columns=["severite", "constat", "collname"],
            rows=[{"severite": "bloquant", "constat": "Collation fr_FR.utf8 en dérive", "collname": "fr_FR.utf8"}],
            row_count=1,
        ),
    ])

    report = generate_report(audit)

    assert "Collation fr_FR.utf8 en dérive" in report
    assert "### Bloquants" in report


def test_report_healthy_audit_shows_explicit_all_clear(tmp_path: Path):
    # Critère #5 : audit sain -> synthèse explicite, pas une section absente.
    audit = _audit_json(tmp_path, [
        _result(id="data_checksums", scope="instance", target="instance", row_count=0, expect_rows=0),
    ])

    report = generate_report(audit)

    assert "## Synthèse" in report
    assert "_Aucun bloquant ni point de vigilance détecté._" in report


def test_report_old_json_missing_new_fields_stays_readable(tmp_path: Path):
    # Critère #6 : un JSON produit avant cette spec (sans expect_rows/severity_if_unexpected
    # du tout dans les résultats) reste lisible, sans section Synthèse.
    old_result = {
        "id": "q1", "title": "Requête 1", "scope": "database", "target": "db1",
        "sql": "SELECT 1", "status": "success", "requires_superuser": False,
        "columns": ["n"], "rows": [{"n": 1}], "row_count": 1, "error": None, "skip_reason": None,
        # pas de clés expect_rows / severity_if_unexpected
    }
    audit = _audit_json(tmp_path, [old_result])

    report = generate_report(audit)

    assert "## Synthèse" not in report
    assert "| n |" in report


def test_report_unknown_severity_value_does_not_crash_and_is_treated_as_info(tmp_path: Path):
    # Critère #7 : valeur de sévérité inconnue -> pas de plantage, traitée en info
    # (donc absente des tableaux Bloquants/Points de vigilance).
    audit = _audit_json(tmp_path, [
        _result(
            id="q1", scope="database",
            columns=["severite", "constat"],
            rows=[{"severite": "URGENTISSIME", "constat": "valeur non standard"}],
            row_count=1,
        ),
    ])

    report = generate_report(audit)

    assert "### Bloquants" not in report
    assert "### Points de vigilance" not in report
    assert "_Aucun bloquant ni point de vigilance détecté._" in report


def test_report_incomplete_warning_shown_when_errors_present(tmp_path: Path):
    audit = _audit_json(tmp_path, [
        _result(id="ok", scope="database", row_count=0, expect_rows=0),
        _result(id="broken", scope="database", status="error",
                error={"message": "boom", "sqlstate": None, "full_traceback": "..."}),
    ])

    report = generate_report(audit)

    assert "La synthèse est incomplète" in report


def test_report_synthese_truncates_at_ten_per_controle(tmp_path: Path):
    rows = [{"severite": "vigilance", "constat": f"ligne {i}"} for i in range(13)]
    audit = _audit_json(tmp_path, [
        _result(id="q1", scope="database", columns=["severite", "constat"], rows=rows, row_count=13),
    ])

    report = generate_report(audit)
    synthese_section = report.split("## Synthèse")[1].split("## Sommaire")[0]

    assert synthese_section.count("ligne ") == 10
    assert "et 3 autre(s) pour" in synthese_section


def test_report_constat_missing_falls_back_to_generic_message(tmp_path: Path):
    audit = _audit_json(tmp_path, [
        _result(id="q1", scope="database", columns=["severite", "constat"],
                rows=[{"severite": "vigilance", "constat": None}], row_count=1),
    ])

    report = generate_report(audit)

    assert "q1 : 1 ligne(s)" in report


def test_extraire_synthese_ignores_non_success_status():
    results = [
        _result(id="q1", status="skipped", expect_rows=0),
        _result(id="q2", status="error", expect_rows=0),
    ]
    assert extraire_synthese(results) == []


def test_extraire_synthese_instance_scope_base_is_dash():
    entries = extraire_synthese([
        _result(id="q1", scope="instance", target="instance", row_count=1, expect_rows=0),
    ])
    assert entries[0]["base"] == "—"
