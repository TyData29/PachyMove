from __future__ import annotations

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
