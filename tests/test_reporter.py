from __future__ import annotations

import json
from pathlib import Path

from pgaudit_runner.reporter import (
    extraire_synthese,
    generate_dashboard,
    generate_report,
    render_html,
    report_stem,
)


def _audit_json(tmp_path: Path, results: list[dict], **meta_overrides) -> Path:
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
    metadata.update(meta_overrides)
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


def test_report_partial_scan_shows_warning_and_points_dattention_entry(tmp_path: Path):
    audit = _audit_json(tmp_path, [
        _result(
            id="low_fill_rate_columns", columns=["schema_", "relation", "erreur"],
            rows=[{"schema_": "s", "relation": "t", "erreur": "the connection is closed"}],
            row_count=1, error_row_count=1,
        ),
    ])

    report = generate_report(audit)

    assert "1/1 ligne(s) sont des erreurs de collecte" in report
    assert "### Scans partiels" in report
    assert "`low_fill_rate_columns`" in report


def test_report_old_json_without_error_row_count_shows_no_warning(tmp_path: Path):
    # Retrocompatibilite : un JSON pre-chantier (champ absent, pas juste None)
    # ne doit rien afficher de special ni planter.
    audit = _audit_json(tmp_path, [
        _result(columns=["n"], rows=[{"n": 1}], row_count=1),
    ])

    report = generate_report(audit)

    assert "erreurs de collecte" not in report
    assert "Scans partiels" not in report


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


# ── Deux serveurs (specs_deux_serveurs.md) ───────────────────────────────────


def test_report_side_both_scope_instance_renders_source_and_cible_blocks(tmp_path: Path):
    # Non-régression du bug corrigé : seul le premier résultat d'un groupe
    # scope:instance était rendu ("r = first") — un side:both y perdait
    # silencieusement son résultat côté cible.
    audit = _audit_json(tmp_path, [
        _result(id="q1", scope="instance", target="instance", side="source",
                columns=["n"], rows=[{"n": 1}], row_count=1),
        _result(id="q1", scope="instance", target="instance", side="target",
                columns=["n"], rows=[{"n": 2}], row_count=1),
    ], target={"host": "tgt", "port": 5432, "server_version": "PostgreSQL 18.0"})

    report = generate_report(audit)

    assert "**Source**" in report
    assert "**Cible**" in report
    assert "| 1 |" in report
    assert "| 2 |" in report


def test_report_side_target_without_source_skips_source_label(tmp_path: Path):
    audit = _audit_json(tmp_path, [
        _result(id="q1", scope="instance", target="instance", side="target",
                status="skipped", skip_reason="aucune cible définie", columns=None, rows=None),
    ])

    report = generate_report(audit)

    assert "**Source**" not in report
    assert "**Cible**" in report


def test_report_target_error_banner_shown(tmp_path: Path):
    audit = _audit_json(
        tmp_path,
        [_result(id="q1", scope="instance", target="instance", side="target", status="error",
                  error={"message": "connexion refusée", "sqlstate": None, "full_traceback": "..."})],
        target={"host": "tgt", "port": 5432, "server_version": None},
        target_error="connexion refusée",
    )

    report = generate_report(audit)

    assert "injoignable" in report
    assert "1 contrôle(s)" in report


def test_report_topology_excludes_pg_upgrade_when_same_server_false(tmp_path: Path):
    audit = _audit_json(
        tmp_path,
        [_result(id="data_checksums", scope="instance", target="instance",
                  row_count=3, expect_rows=0, severity_if_unexpected="bloquant",
                  applies_to=["pg_upgrade"])],
        same_server=False,
    )

    report = generate_report(audit)

    assert "_Aucun bloquant ni point de vigilance détecté._" in report
    assert "sans objet pour dump/restore" in report


def test_report_topology_override_excludes_when_same_server_ambiguous(tmp_path: Path):
    audit = _audit_json(
        tmp_path,
        [_result(id="data_checksums", scope="instance", target="instance",
                  row_count=3, expect_rows=0, severity_if_unexpected="bloquant",
                  applies_to=["pg_upgrade"])],
        same_server=True,
        migration_method="dump_restore",
    )

    report = generate_report(audit)

    assert "_Aucun bloquant ni point de vigilance détecté._" in report
    assert "sans objet pour dump_restore" in report


def test_report_no_topology_exclusion_when_ambiguous_and_no_override(tmp_path: Path):
    audit = _audit_json(
        tmp_path,
        [_result(id="data_checksums", scope="instance", target="instance",
                  row_count=3, expect_rows=0, severity_if_unexpected="bloquant",
                  applies_to=["pg_upgrade"])],
    )

    report = generate_report(audit)

    assert "### Bloquants" in report


def test_report_old_json_without_target_fields_renders_identically(tmp_path: Path):
    # Rétrocompatibilité stricte : ni "target", ni "same_server", ni "side" sur
    # les résultats -> rapport identique à avant ce chantier.
    audit = _audit_json(tmp_path, [
        _result(id="q1", scope="database", target="db1", columns=["n"], rows=[{"n": 1}], row_count=1),
    ])

    report = generate_report(audit)

    assert "**Source :**" not in report
    assert "**Cible :**" not in report
    assert "injoignable" not in report


def test_render_html_converts_tables_and_fenced_sql_inside_details(tmp_path: Path):
    audit = _audit_json(tmp_path, [
        _result(id="q1", scope="database", target="db1",
                sql="SELECT 1", columns=["n"], rows=[{"n": 1}], row_count=1),
    ])
    report = generate_report(audit)

    html = render_html(report)

    assert html.startswith("<!DOCTYPE html>")
    assert "<table>" in html
    # Le SQL est imbriqué dans <details> : sans md_in_html, resterait en texte brut.
    assert "<pre><code" in html
    assert "```" not in html
    # Les ancres explicites du sommaire (<a id="...">) doivent survivre intactes.
    assert '<a id="q1">' in html


def test_render_html_is_self_contained(tmp_path: Path):
    audit = _audit_json(tmp_path, [_result(columns=["n"], rows=[{"n": 1}], row_count=1)])
    report = generate_report(audit)

    html = render_html(report)

    assert "<style>" in html
    assert "http://" not in html and "https://" not in html


def test_report_renders_description_as_blockquote(tmp_path: Path):
    audit = _audit_json(tmp_path, [_result(description="Ce que fait ce contrôle et pourquoi.")])

    report = generate_report(audit)

    assert "> Ce que fait ce contrôle et pourquoi." in report


def test_report_omits_description_block_when_absent(tmp_path: Path):
    # Rétrocompatibilité : un JSON pré-chantier description (champ absent, pas
    # juste None) ne doit rien afficher de spécial ni planter.
    audit = _audit_json(tmp_path, [_result()])

    report = generate_report(audit)

    assert "\n> " not in report


def test_report_renders_multiline_description_with_quote_prefix_on_each_line(tmp_path: Path):
    audit = _audit_json(tmp_path, [_result(description="Ligne un.\nLigne deux.")])

    report = generate_report(audit)

    assert "> Ligne un." in report
    assert "> Ligne deux." in report


# ── Dashboard ────────────────────────────────────────────────────────────────


def _write_audit(tmp_path: Path, filename: str, results: list[dict], **meta_overrides) -> Path:
    metadata = {
        "manifest_name": meta_overrides.pop("manifest_name", "Test"),
        "started_at": meta_overrides.pop("started_at", "2026-01-01T10:00:00+00:00"),
        "source": {"host": meta_overrides.pop("host", "srv")},
        "summary": {
            "total": len(results),
            "success": sum(1 for r in results if r["status"] == "success"),
            "skipped": sum(1 for r in results if r["status"] == "skipped"),
            "error": sum(1 for r in results if r["status"] == "error"),
        },
    }
    metadata.update(meta_overrides)
    path = tmp_path / filename
    path.write_text(json.dumps({"metadata": metadata, "results": results}), encoding="utf-8")
    return path


def test_report_stem_replaces_audit_prefix():
    assert report_stem(Path("audit_data_quality_20260815_090000.json")) == "rapport_data_quality_20260815_090000"


def test_dashboard_no_calibration_shows_explicit_note_not_empty_table(tmp_path: Path):
    audit = _write_audit(tmp_path, "audit_m_1.json", [_result()])

    html = generate_dashboard([audit])

    assert "Aucun contrôle n&#x27;expose encore" in html or "n'expose encore" in html
    assert "<table>" not in html.split("<h2>Points de vigilance</h2>")[0].split("<h2>Bloquants</h2>")[1]


def test_dashboard_aggregates_bloquant_with_link_to_report(tmp_path: Path):
    audit = _write_audit(tmp_path, "audit_m_1.json", [
        _result(id="q1", columns=["severite", "constat"],
                rows=[{"severite": "bloquant", "constat": "Casse tout"}], row_count=1),
    ])

    html = generate_dashboard([audit])

    assert "Casse tout" in html
    assert 'href="rapport_m_1.html#q1"' in html


def test_dashboard_aggregates_collection_errors_across_runs(tmp_path: Path):
    audit = _write_audit(tmp_path, "audit_m_1.json", [
        _result(id="q_err", status="error", error={"message": "the connection is closed"}),
    ])

    html = generate_dashboard([audit])

    assert "the connection is closed" in html
    assert 'href="rapport_m_1.html#q-err"' in html


def test_dashboard_aggregates_partial_scans_across_runs(tmp_path: Path):
    audit = _write_audit(tmp_path, "audit_m_1.json", [
        _result(
            id="low_fill_rate_columns", columns=["schema_", "relation", "erreur"],
            rows=[{"schema_": "s", "relation": "t", "erreur": "the connection is closed"}],
            row_count=1, error_row_count=1,
        ),
    ])

    html = generate_dashboard([audit])

    assert "Scans partiels" in html
    assert "1/1" in html
    assert 'href="rapport_m_1.html#low-fill-rate-columns"' in html


def test_dashboard_no_partial_scans_shows_explicit_message(tmp_path: Path):
    audit = _write_audit(tmp_path, "audit_m_1.json", [_result()])

    html = generate_dashboard([audit])

    assert "Aucun scan dérivé partiellement en erreur" in html


def test_dashboard_runs_table_sorted_most_recent_first(tmp_path: Path):
    older = _write_audit(tmp_path, "audit_a_1.json", [_result()], started_at="2026-01-01T00:00:00+00:00")
    newer = _write_audit(tmp_path, "audit_b_1.json", [_result()], started_at="2026-06-01T00:00:00+00:00")

    html = generate_dashboard([older, newer])

    runs_section = html.split("<h2>Runs</h2>")[1]
    assert runs_section.index("2026-06-01") < runs_section.index("2026-01-01")


def test_dashboard_escapes_html_in_constat(tmp_path: Path):
    audit = _write_audit(tmp_path, "audit_m_1.json", [
        _result(id="q1", columns=["severite", "constat"],
                rows=[{"severite": "bloquant", "constat": "<script>alert(1)</script>"}], row_count=1),
    ])

    html = generate_dashboard([audit])

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
