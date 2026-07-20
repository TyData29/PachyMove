from __future__ import annotations

from pathlib import Path

import pytest

from pgaudit_runner.config import ConfigError, load_manifest

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_QUERIES_DIR = REPO_ROOT / "queries"
REAL_MANIFESTS = sorted((REPO_ROOT / "manifests").glob("*.yaml"))


def _write(tmp_path: Path, relpath: str, content: str) -> Path:
    path = tmp_path / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_load_manifest_applies_defaults_and_reads_sql(tmp_path: Path):
    _write(tmp_path, "queries/instance/ping.sql", "SELECT 1")
    manifest = _write(
        tmp_path,
        "manifests/m.yaml",
        """
meta:
  name: "Test"
defaults:
  statement_timeout_ms: 12345
  read_only: true
queries:
  - id: ping
    title: "Ping"
    file: instance/ping.sql
    scope: instance
""",
    )

    config, specs = load_manifest(manifest, tmp_path / "queries")

    assert config["meta"]["name"] == "Test"
    assert config["read_only"] is True
    assert len(specs) == 1
    spec = specs[0]
    assert spec.id == "ping"
    assert spec.scope == "instance"
    assert spec.enabled is True
    assert spec.tags == []
    assert spec.requires_superuser is False
    assert spec.statement_timeout_ms == 12345
    assert spec.sql == "SELECT 1"
    assert spec.side == "source"
    assert spec.applies_to == []


def test_load_manifest_reads_side_and_applies_to(tmp_path: Path):
    _write(tmp_path, "queries/instance/ping.sql", "SELECT 1")
    manifest = _write(
        tmp_path,
        "manifests/m.yaml",
        """
queries:
  - id: ping
    title: "Ping"
    file: instance/ping.sql
    scope: instance
    side: both
    applies_to: [pg_upgrade]
""",
    )

    _config, specs = load_manifest(manifest, tmp_path / "queries")

    assert specs[0].side == "both"
    assert specs[0].applies_to == ["pg_upgrade"]


def test_invalid_side_raises(tmp_path: Path):
    _write(tmp_path, "queries/instance/ping.sql", "SELECT 1")
    manifest = _write(
        tmp_path,
        "manifests/m.yaml",
        """
queries:
  - id: ping
    title: "Ping"
    file: instance/ping.sql
    scope: instance
    side: bogus
""",
    )
    with pytest.raises(ConfigError, match="side invalide"):
        load_manifest(manifest, tmp_path / "queries")


def test_missing_required_field_raises(tmp_path: Path):
    _write(tmp_path, "queries/instance/ping.sql", "SELECT 1")
    manifest = _write(
        tmp_path,
        "manifests/m.yaml",
        """
queries:
  - id: ping
    file: instance/ping.sql
    scope: instance
""",
    )
    with pytest.raises(ConfigError, match="title"):
        load_manifest(manifest, tmp_path / "queries")


def test_duplicate_id_raises(tmp_path: Path):
    _write(tmp_path, "queries/instance/ping.sql", "SELECT 1")
    manifest = _write(
        tmp_path,
        "manifests/m.yaml",
        """
queries:
  - id: ping
    title: "Ping"
    file: instance/ping.sql
    scope: instance
  - id: ping
    title: "Ping bis"
    file: instance/ping.sql
    scope: instance
""",
    )
    with pytest.raises(ConfigError, match="dupliqué"):
        load_manifest(manifest, tmp_path / "queries")


def test_invalid_scope_raises(tmp_path: Path):
    _write(tmp_path, "queries/instance/ping.sql", "SELECT 1")
    manifest = _write(
        tmp_path,
        "manifests/m.yaml",
        """
queries:
  - id: ping
    title: "Ping"
    file: instance/ping.sql
    scope: bogus
""",
    )
    with pytest.raises(ConfigError, match="scope invalide"):
        load_manifest(manifest, tmp_path / "queries")


def test_missing_sql_file_raises(tmp_path: Path):
    manifest = _write(
        tmp_path,
        "manifests/m.yaml",
        """
queries:
  - id: ping
    title: "Ping"
    file: instance/missing.sql
    scope: instance
""",
    )
    with pytest.raises(ConfigError, match="introuvable"):
        load_manifest(manifest, tmp_path / "queries")


@pytest.mark.parametrize("manifest_path", REAL_MANIFESTS, ids=lambda p: p.name)
def test_real_manifests_load_without_error(manifest_path: Path):
    """Garde-fou de non-régression : chaque manifeste du dépôt doit toujours charger."""
    _config, specs = load_manifest(manifest_path, REAL_QUERIES_DIR)
    assert specs
    for spec in specs:
        assert spec.sql
