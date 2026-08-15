from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from pgaudit_runner.cli import cli


def _manifest(tmp_path: Path) -> Path:
    queries_dir = tmp_path / "queries" / "instance"
    queries_dir.mkdir(parents=True)
    (queries_dir / "q.sql").write_text("SELECT 1", encoding="utf-8")

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    manifest = manifests_dir / "m.yaml"
    manifest.write_text(
        "queries:\n  - id: q\n    title: Q\n    file: instance/q.sql\n    scope: instance\n",
        encoding="utf-8",
    )
    return manifest


def test_collect_without_target_flags_passes_no_target(tmp_path: Path):
    manifest = _manifest(tmp_path)
    runner = CliRunner()

    with patch("pgaudit_runner.cli.collect", return_value=tmp_path / "out.json") as mock_collect:
        result = runner.invoke(cli, [
            "collect", "--host", "h", "--user", "u",
            "--manifest", str(manifest), "--output", str(tmp_path / "out"),
            "--dry-run", "--no-with-report",
        ])

    assert result.exit_code == 0, result.output
    assert mock_collect.call_args.kwargs["target_host"] is None
    assert mock_collect.call_args.kwargs["target_dbnames"] is None


def test_collect_with_only_target_dbnames_counts_as_target_defined(tmp_path: Path):
    manifest = _manifest(tmp_path)
    runner = CliRunner()

    with patch("pgaudit_runner.cli.collect", return_value=tmp_path / "out.json") as mock_collect:
        result = runner.invoke(cli, [
            "collect", "--host", "h", "--user", "u",
            "--manifest", str(manifest), "--output", str(tmp_path / "out"),
            "--target-dbnames", "db2,db3",
            "--dry-run", "--no-with-report",
        ])

    assert result.exit_code == 0, result.output
    kwargs = mock_collect.call_args.kwargs
    assert kwargs["target_host"] == "h"  # hérité de --host, cible bien définie
    assert kwargs["target_dbnames"] == ["db2", "db3"]


def test_collect_target_port_inherits_host_and_user(tmp_path: Path):
    manifest = _manifest(tmp_path)
    runner = CliRunner()

    with patch("pgaudit_runner.cli.collect", return_value=tmp_path / "out.json") as mock_collect:
        result = runner.invoke(cli, [
            "collect", "--host", "h", "--user", "u", "--port", "5432",
            "--manifest", str(manifest), "--output", str(tmp_path / "out"),
            "--target-port", "5433",
            "--dry-run", "--no-with-report",
        ])

    assert result.exit_code == 0, result.output
    kwargs = mock_collect.call_args.kwargs
    assert kwargs["target_host"] == "h"
    assert kwargs["target_port"] == 5433
    assert kwargs["target_user"] == "u"


def test_collect_dry_run_without_host_user_passes(tmp_path: Path):
    manifest = _manifest(tmp_path)
    runner = CliRunner()

    with patch("pgaudit_runner.cli.collect", return_value=tmp_path / "out.json"):
        result = runner.invoke(cli, [
            "collect",
            "--manifest", str(manifest), "--output", str(tmp_path / "out"),
            "--dry-run", "--no-with-report",
        ])

    assert result.exit_code == 0, result.output


def test_collect_without_dry_run_and_without_host_user_raises_usage_error(tmp_path: Path):
    manifest = _manifest(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli, [
        "collect",
        "--manifest", str(manifest), "--output", str(tmp_path / "out"),
    ])

    assert result.exit_code != 0
    assert "--host et --user sont obligatoires" in result.output


def test_collect_with_directory_manifest_runs_every_yaml_file(tmp_path: Path):
    queries_dir = tmp_path / "queries" / "instance"
    queries_dir.mkdir(parents=True)
    (queries_dir / "q.sql").write_text("SELECT 1", encoding="utf-8")

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    for name in ("a", "b"):
        (manifests_dir / f"{name}.yaml").write_text(
            "queries:\n  - id: q\n    title: Q\n    file: instance/q.sql\n    scope: instance\n",
            encoding="utf-8",
        )

    runner = CliRunner()
    with patch("pgaudit_runner.cli.collect") as mock_collect:
        mock_collect.side_effect = [
            tmp_path / "out" / "audit_a_1.json", tmp_path / "out" / "audit_b_1.json",
        ]
        result = runner.invoke(cli, [
            "collect", "--host", "h", "--user", "u",
            "--manifest", str(manifests_dir), "--output", str(tmp_path / "out"),
            "--dry-run", "--no-with-report",
        ])

    assert result.exit_code == 0, result.output
    assert mock_collect.call_count == 2
    manifest_names = [c.kwargs["manifest_path"].name for c in mock_collect.call_args_list]
    assert manifest_names == ["a.yaml", "b.yaml"]
    assert "Manifeste 1/2 : a.yaml" in result.output
    assert "Manifeste 2/2 : b.yaml" in result.output


def test_collect_with_single_file_manifest_has_no_batch_header(tmp_path: Path):
    manifest = _manifest(tmp_path)
    runner = CliRunner()

    with patch("pgaudit_runner.cli.collect", return_value=tmp_path / "out.json"):
        result = runner.invoke(cli, [
            "collect", "--host", "h", "--user", "u",
            "--manifest", str(manifest), "--output", str(tmp_path / "out"),
            "--dry-run", "--no-with-report",
        ])

    assert result.exit_code == 0, result.output
    assert "Manifeste" not in result.output


def test_migration_method_rejects_invalid_choice(tmp_path: Path):
    manifest = _manifest(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli, [
        "collect", "--host", "h", "--user", "u",
        "--manifest", str(manifest), "--output", str(tmp_path / "out"),
        "--migration-method", "bogus",
        "--dry-run",
    ])

    assert result.exit_code != 0


def test_collect_with_report_writes_markdown_alongside_json(tmp_path: Path):
    manifest = _manifest(tmp_path)
    runner = CliRunner()
    out_dir = tmp_path / "out"

    result = runner.invoke(cli, [
        "collect", "--manifest", str(manifest), "--output", str(out_dir), "--dry-run",
    ])

    assert result.exit_code == 0, result.output
    json_files = list(out_dir.glob("audit_*.json"))
    md_files = list(out_dir.glob("rapport_*.md"))
    assert len(json_files) == 1
    assert len(md_files) == 1
    assert "# Rapport de pré-audit PostgreSQL" in md_files[0].read_text(encoding="utf-8")


def test_collect_no_with_report_skips_markdown(tmp_path: Path):
    manifest = _manifest(tmp_path)
    runner = CliRunner()
    out_dir = tmp_path / "out"

    result = runner.invoke(cli, [
        "collect", "--manifest", str(manifest), "--output", str(out_dir),
        "--dry-run", "--no-with-report",
    ])

    assert result.exit_code == 0, result.output
    assert list(out_dir.glob("audit_*.json"))
    assert not list(out_dir.glob("rapport_*.md"))


def test_html_command_converts_markdown_file(tmp_path: Path):
    runner = CliRunner()
    md_file = tmp_path / "rapport.md"
    md_file.write_text("# Titre\n\n| a | b |\n|---|---|\n| 1 | 2 |\n", encoding="utf-8")
    html_file = tmp_path / "rapport.html"

    result = runner.invoke(cli, [
        "html", "--input", str(md_file), "--output", str(html_file),
    ])

    assert result.exit_code == 0, result.output
    html = html_file.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert "<table>" in html


def test_dashboard_command_generates_index_and_run_reports(tmp_path: Path):
    input_dir = tmp_path / "output"
    input_dir.mkdir()
    audit = input_dir / "audit_m_20260815_090000.json"
    audit.write_text(json.dumps({
        "metadata": {
            "manifest_name": "Test", "started_at": "2026-08-15T09:00:00+00:00",
            "source": {"host": "srv"},
            "summary": {"total": 1, "success": 1, "skipped": 0, "error": 0},
        },
        "results": [{
            "id": "q1", "title": "Q1", "scope": "database", "target": "db1",
            "sql": "SELECT 1", "status": "success", "requires_superuser": False,
            "columns": ["n"], "rows": [{"n": 1}], "row_count": 1, "error": None,
            "skip_reason": None, "expect_rows": None, "severity_if_unexpected": "vigilance",
        }],
    }), encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(cli, ["dashboard", "--input-dir", str(input_dir)])

    assert result.exit_code == 0, result.output
    index_file = input_dir / "index.html"
    assert index_file.exists()
    assert "Tableau de bord" in index_file.read_text(encoding="utf-8")
    assert (input_dir / "rapport_m_20260815_090000.html").exists()
    assert (input_dir / "rapport_m_20260815_090000.md").exists()


def test_dashboard_command_no_json_raises(tmp_path: Path):
    input_dir = tmp_path / "output"
    input_dir.mkdir()
    runner = CliRunner()

    result = runner.invoke(cli, ["dashboard", "--input-dir", str(input_dir)])

    assert result.exit_code != 0
    assert "Aucun audit_*.json" in result.output


def test_analyze_logs_command_writes_json_summary(tmp_path: Path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "postgresql.log").write_text(
        "2026-07-23 08:00:00.100 UTC [1001] LOG:  connection received: host=10.0.0.5 port=1\n"
        "2026-07-23 08:00:00.150 UTC [1001] LOG:  connection authorized: user=alice database=mydb\n",
        encoding="utf-8",
    )
    output_file = tmp_path / "out" / "connexions.json"
    runner = CliRunner()

    result = runner.invoke(cli, [
        "analyze-logs", "--input-dir", str(log_dir), "--output", str(output_file),
    ])

    assert result.exit_code == 0, result.output
    assert output_file.exists()
    data = json.loads(output_file.read_text(encoding="utf-8"))
    assert data["metadata"]["connections_total"] == 1
    assert data["roles"]["alice"]["databases"] == {"mydb": 1}
