from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import psycopg
import pytest

from pgaudit_runner.collector import collect
from pgaudit_runner.config import ConfigError


def _write(tmp_path: Path, relpath: str, content: str) -> Path:
    path = tmp_path / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _fake_conn(host: str, port: int = 5432, datnames: tuple[str, ...] = ("db1",)) -> MagicMock:
    conn = MagicMock()
    conn.info = SimpleNamespace(host=host, port=port)
    cur = MagicMock()
    cur.description = [SimpleNamespace(name="x")]
    cur.fetchall.return_value = [(name,) for name in datnames]
    conn.execute.return_value = cur
    return conn


@contextmanager
def _cm(conn_or_exc):
    if isinstance(conn_or_exc, Exception):
        raise conn_or_exc
    yield conn_or_exc


def _base_kwargs(tmp_path: Path, manifest: Path, **overrides) -> dict:
    kwargs = dict(
        host="src-host", port=5432, user="u", dbnames=["db1"],
        maintenance_db="postgres", manifest_path=manifest,
        queries_dir=tmp_path / "queries", output_dir=tmp_path / "out",
        tags=[], only=[], exclude=[], dry_run=False,
    )
    # collect() ne fait pas d'héritage lui-même (c'est le rôle de cli.py) : une
    # cible définie dans un test doit donc porter son propre maintenance_db,
    # comme cli.py l'aurait déjà résolu avant l'appel.
    if overrides.get("target_host") is not None and "target_maintenance_db" not in overrides:
        kwargs["target_maintenance_db"] = "postgres"
    kwargs.update(overrides)
    return kwargs


def _simple_manifest(tmp_path: Path, query_yaml: str) -> Path:
    _write(tmp_path, "queries/instance/q.sql", "SELECT 1")
    _write(tmp_path, "queries/database/qdb.sql", "SELECT 1")
    return _write(tmp_path, "manifests/m.yaml", f"queries:\n{query_yaml}")


def _read_json(output_file: Path) -> dict:
    import json
    return json.loads(output_file.read_text(encoding="utf-8"))


# ── Garde-fous ────────────────────────────────────────────────────────────────


def test_identical_instance_guard_raises(tmp_path: Path):
    manifest = _simple_manifest(tmp_path, """
  - id: q
    title: Q
    file: instance/q.sql
    scope: instance
""")
    with pytest.raises(ConfigError, match="même instance"):
        collect(**_base_kwargs(tmp_path, manifest, target_host="src-host", target_port=5432))


def test_pgpassword_dual_guard_raises_when_target_defined(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PGPASSWORD", "secret")
    manifest = _simple_manifest(tmp_path, """
  - id: q
    title: Q
    file: instance/q.sql
    scope: instance
""")
    with pytest.raises(ConfigError, match="PGPASSWORD"):
        collect(**_base_kwargs(tmp_path, manifest, target_host="tgt-host", target_port=5432, target_user="u"))


def test_pgpassword_dual_guard_allows_same_host_and_user(tmp_path: Path, monkeypatch):
    # Même hôte, deux instances (typique pg_upgrade) : (host,user) identiques,
    # donc PGPASSWORD reste plausible -> pas de refus, même si (host,port) diffère.
    monkeypatch.setenv("PGPASSWORD", "secret")
    manifest = _simple_manifest(tmp_path, """
  - id: q
    title: Q
    file: instance/q.sql
    scope: instance
""")
    with patch("pgaudit_runner.collector.resolve_password", return_value=None), \
         patch("pgaudit_runner.collector.get_server_version", return_value="PG 17"), \
         patch("pgaudit_runner.collector.open_connection") as mock_open:
        mock_open.side_effect = lambda host, port, *a, **kw: _cm(_fake_conn(host, port=port))
        collect(**_base_kwargs(
            tmp_path, manifest,
            target_host="src-host", target_port=5433, target_user="u",
        ))
    # N'a pas levé ConfigError -> le test passe simplement en atteignant cette ligne.


def test_migration_method_pg_upgrade_rejected_when_hosts_differ(tmp_path: Path):
    manifest = _simple_manifest(tmp_path, """
  - id: q
    title: Q
    file: instance/q.sql
    scope: instance
""")
    with pytest.raises(ConfigError, match="pg_upgrade"):
        collect(**_base_kwargs(
            tmp_path, manifest,
            target_host="tgt-host", target_port=5432, target_user="u",
            migration_method="pg_upgrade",
        ))


# ── Cible absente / injoignable ─────────────────────────────────────────────


def test_side_target_without_target_is_skipped_without_connecting(tmp_path: Path):
    manifest = _simple_manifest(tmp_path, """
  - id: q
    title: Q
    file: instance/q.sql
    scope: instance
    side: target
""")
    with patch("pgaudit_runner.collector.resolve_password", return_value=None), \
         patch("pgaudit_runner.collector.open_connection") as mock_open:
        output_file = collect(**_base_kwargs(tmp_path, manifest))

    mock_open.assert_not_called()
    data = _read_json(output_file)
    r = data["results"][0]
    assert r["status"] == "skipped"
    assert r["skip_reason"] == "aucune cible définie"
    assert r["side"] == "target"


def test_side_both_produces_source_and_target_success(tmp_path: Path):
    manifest = _simple_manifest(tmp_path, """
  - id: q
    title: Q
    file: instance/q.sql
    scope: instance
    side: both
""")
    with patch("pgaudit_runner.collector.resolve_password", return_value=None), \
         patch("pgaudit_runner.collector.get_server_version", return_value="PG 17"), \
         patch("pgaudit_runner.collector.open_connection") as mock_open:
        mock_open.side_effect = lambda host, *a, **kw: _cm(_fake_conn(host))
        output_file = collect(**_base_kwargs(
            tmp_path, manifest,
            target_host="tgt-host", target_port=5432, target_user="u",
        ))

    data = _read_json(output_file)
    sides = sorted(r["side"] for r in data["results"] if r["id"] == "q")
    assert sides == ["source", "target"]
    assert all(r["status"] == "success" for r in data["results"] if r["id"] == "q")
    assert data["metadata"]["same_server"] is False


def test_target_connection_failure_marks_all_target_results_error(tmp_path: Path):
    manifest = _simple_manifest(tmp_path, """
  - id: q_instance
    title: Q instance
    file: instance/q.sql
    scope: instance
    side: both
  - id: q_db
    title: Q db
    file: database/qdb.sql
    scope: database
    side: target
""")
    exc = psycopg.OperationalError("could not connect to server")

    def _open(host, *a, **kw):
        if host == "tgt-host":
            return _cm(exc)
        return _cm(_fake_conn(host))

    with patch("pgaudit_runner.collector.resolve_password", return_value=None), \
         patch("pgaudit_runner.collector.get_server_version", return_value="PG 17"), \
         patch("pgaudit_runner.collector.open_connection", side_effect=_open):
        output_file = collect(**_base_kwargs(
            tmp_path, manifest,
            target_host="tgt-host", target_port=5432, target_user="u",
        ))

    data = _read_json(output_file)
    target_results = [r for r in data["results"] if r["side"] == "target"]
    assert target_results
    assert all(r["status"] == "error" for r in target_results)
    assert data["metadata"]["target_error"]
    assert data["metadata"]["same_server"] is False  # repli sur la comparaison CLI brute

    source_instance = [r for r in data["results"] if r["id"] == "q_instance" and r["side"] == "source"]
    assert source_instance[0]["status"] == "success"


def test_database_absent_from_target_is_skipped_cleanly(tmp_path: Path):
    manifest = _simple_manifest(tmp_path, """
  - id: q_db
    title: Q db
    file: database/qdb.sql
    scope: database
    side: target
""")

    def _open(host, *a, **kw):
        if host == "tgt-host":
            return _cm(_fake_conn(host, datnames=("autre_base",)))
        return _cm(_fake_conn(host))

    with patch("pgaudit_runner.collector.resolve_password", return_value=None), \
         patch("pgaudit_runner.collector.get_server_version", return_value="PG 17"), \
         patch("pgaudit_runner.collector.open_connection", side_effect=_open) as mock_open:
        output_file = collect(**_base_kwargs(
            tmp_path, manifest,
            target_host="tgt-host", target_port=5432, target_user="u",
        ))

    data = _read_json(output_file)
    r = [x for x in data["results"] if x["id"] == "q_db"][0]
    assert r["status"] == "skipped"
    assert "absente de la cible" in r["skip_reason"]
    # Aucune tentative de connexion sur la base "db1" côté cible (absente) :
    target_db_calls = [c for c in mock_open.call_args_list if c.args and c.args[0] == "tgt-host" and len(c.args) > 3 and c.args[3] == "db1"]
    assert not target_db_calls
