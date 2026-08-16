from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import psycopg
import pytest

from pgaudit_runner.collector import _aggregate_deprecated_tables, _aggregate_true_duplicates, collect
from pgaudit_runner.config import ConfigError
from pgaudit_runner.models import QueryResult


def _write(tmp_path: Path, relpath: str, content: str) -> Path:
    path = tmp_path / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _fake_conn(
    host: str, port: int = 5432, datnames: tuple[str, ...] = ("db1",),
    version_num: int = 170004,
) -> MagicMock:
    conn = MagicMock()
    conn.info = SimpleNamespace(host=host, port=port)
    cur = MagicMock()
    cur.description = [SimpleNamespace(name="x")]
    cur.fetchall.return_value = [(name,) for name in datnames]
    cur.fetchone.return_value = (str(version_num),)
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


def test_collect_prints_progress_by_default(tmp_path: Path, capsys):
    manifest = _simple_manifest(tmp_path, """
  - id: q
    title: Q
    file: instance/q.sql
    scope: instance
""")
    with patch("pgaudit_runner.collector.resolve_password", return_value=None), \
         patch("pgaudit_runner.collector.get_server_version", return_value="PG 17"), \
         patch("pgaudit_runner.collector.open_connection") as mock_open:
        mock_open.side_effect = lambda host, *a, **kw: _cm(_fake_conn(host))
        collect(**_base_kwargs(tmp_path, manifest))

    out = capsys.readouterr().out
    assert "[1/1] q (instance, source)..." in out
    assert "-> success" in out


def test_collect_quiet_suppresses_progress(tmp_path: Path, capsys):
    manifest = _simple_manifest(tmp_path, """
  - id: q
    title: Q
    file: instance/q.sql
    scope: instance
""")
    with patch("pgaudit_runner.collector.resolve_password", return_value=None), \
         patch("pgaudit_runner.collector.get_server_version", return_value="PG 17"), \
         patch("pgaudit_runner.collector.open_connection") as mock_open:
        mock_open.side_effect = lambda host, *a, **kw: _cm(_fake_conn(host))
        collect(**_base_kwargs(tmp_path, manifest, quiet=True))

    assert capsys.readouterr().out == ""


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


def test_min_server_version_gate_skips_cleanly_on_older_source(tmp_path: Path):
    # Cas réel trouvé en audit : database_collation_version.sql échoue (colonne
    # inexistante) sur une source PG14, puisque datcollversion n'existe qu'à
    # partir de PG15. Doit être ignorée proprement, jamais en erreur.
    manifest = _simple_manifest(tmp_path, """
  - id: q
    title: Q
    file: instance/q.sql
    scope: instance
    min_server_version: 150000
""")

    with patch("pgaudit_runner.collector.resolve_password", return_value=None), \
         patch("pgaudit_runner.collector.open_connection") as mock_open:
        mock_open.side_effect = lambda host, *a, **kw: _cm(_fake_conn(host, version_num=140011))
        output_file = collect(**_base_kwargs(tmp_path, manifest))

    data = _read_json(output_file)
    r = [x for x in data["results"] if x["id"] == "q"][0]
    assert r["status"] == "skipped"
    assert "PostgreSQL ≥ 15" in r["skip_reason"]


def test_max_server_version_gate_skips_cleanly_on_newer_source(tmp_path: Path):
    manifest = _simple_manifest(tmp_path, """
  - id: q
    title: Q
    file: instance/q.sql
    scope: instance
    max_server_version: 149999
""")

    with patch("pgaudit_runner.collector.resolve_password", return_value=None), \
         patch("pgaudit_runner.collector.open_connection") as mock_open:
        mock_open.side_effect = lambda host, *a, **kw: _cm(_fake_conn(host, version_num=170004))
        output_file = collect(**_base_kwargs(tmp_path, manifest))

    data = _read_json(output_file)
    r = [x for x in data["results"] if x["id"] == "q"][0]
    assert r["status"] == "skipped"
    assert "PostgreSQL ≤ 14" in r["skip_reason"]


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


# ── Post-traitement des requêtes dérivées (specs_data_quality_on_tables.md) ──


def _result(rows: list[dict]) -> QueryResult:
    return QueryResult(
        id="q", title="Q", scope="database", target="db1", sql="...",
        status="success", columns=["schema_", "relation", "colonne"], rows=rows, row_count=len(rows),
    )


def test_aggregate_deprecated_tables_healthy_table_is_dropped():
    rows = [{"schema_": "public", "relation": "t1", "colonne": "c1",
              "recent_6_mois": True, "recent_1_an": True, "recent_3_ans": True}]
    result = _aggregate_deprecated_tables(_result(rows))
    assert result.rows == []
    assert result.row_count == 0


def test_aggregate_deprecated_tables_classifies_by_oldest_threshold_crossed():
    rows = [
        {"schema_": "public", "relation": "t_6m", "colonne": "c",
         "recent_6_mois": False, "recent_1_an": True, "recent_3_ans": True},
        {"schema_": "public", "relation": "t_1y", "colonne": "c",
         "recent_6_mois": False, "recent_1_an": False, "recent_3_ans": True},
        {"schema_": "public", "relation": "t_3y", "colonne": "c",
         "recent_6_mois": False, "recent_1_an": False, "recent_3_ans": False},
    ]
    result = _aggregate_deprecated_tables(_result(rows))

    verdicts = {r["relation"]: r["verdict"] for r in result.rows}
    assert verdicts["t_6m"] == "aucune activité depuis 6 mois"
    assert verdicts["t_1y"] == "aucune activité depuis 1 an"
    assert verdicts["t_3y"] == "aucune activité depuis 3 ans (potentiellement dépréciée)"


def test_aggregate_deprecated_tables_ors_across_multiple_columns_of_same_table():
    # Une colonne récente suffit à sauver la table, même si une autre ne l'est pas.
    rows = [
        {"schema_": "public", "relation": "t1", "colonne": "created_at",
         "recent_6_mois": False, "recent_1_an": False, "recent_3_ans": False},
        {"schema_": "public", "relation": "t1", "colonne": "updated_at",
         "recent_6_mois": True, "recent_1_an": True, "recent_3_ans": True},
    ]
    result = _aggregate_deprecated_tables(_result(rows))
    assert result.rows == []


def test_aggregate_deprecated_tables_surfaces_error_when_no_signal_at_all():
    rows = [{"schema_": "public", "relation": "t1", "colonne": "c", "erreur": "permission denied"}]
    result = _aggregate_deprecated_tables(_result(rows))
    assert result.rows[0]["erreur"] == "permission denied"
    assert result.rows[0]["verdict"] is None
    assert result.error_row_count == 1


def test_aggregate_deprecated_tables_error_row_count_recomputed_after_grouping():
    # error_row_count doit refleter les lignes POST-regroupement (une par
    # table), pas le nombre de lignes brutes avant agregation (une par colonne).
    rows = [
        {"schema_": "public", "relation": "t1", "colonne": "c1", "erreur": "permission denied"},
        {"schema_": "public", "relation": "t1", "colonne": "c2", "erreur": "permission denied"},
    ]
    result = _aggregate_deprecated_tables(_result(rows))
    assert result.row_count == 1
    assert result.error_row_count == 1


def test_aggregate_true_duplicates_groups_matching_fingerprint_and_row_count():
    rows = [
        {"schema_": "a", "relation": "t1", "nb_lignes": 100, "empreinte": "hash1"},
        {"schema_": "b", "relation": "t2", "nb_lignes": 100, "empreinte": "hash1"},
        {"schema_": "c", "relation": "t3", "nb_lignes": 50, "empreinte": "hash2"},
    ]
    result = _aggregate_true_duplicates(_result(rows))

    relations = {r["relation"] for r in result.rows}
    assert relations == {"t1", "t2"}
    assert result.rows[0]["groupe"] == result.rows[1]["groupe"]


def test_aggregate_true_duplicates_error_row_count_reflects_kept_errors():
    rows = [
        {"schema_": "a", "relation": "t1", "nb_lignes": 100, "empreinte": "hash1"},
        {"schema_": "b", "relation": "t2", "nb_lignes": 100, "empreinte": "hash1"},
        {"schema_": "c", "relation": "t3", "erreur": "permission denied"},
    ]
    result = _aggregate_true_duplicates(_result(rows))

    assert result.row_count == 3  # 2 doublons + 1 erreur
    assert result.error_row_count == 1


def test_aggregate_true_duplicates_no_match_yields_empty():
    rows = [
        {"schema_": "a", "relation": "t1", "nb_lignes": 100, "empreinte": "hash1"},
        {"schema_": "b", "relation": "t2", "nb_lignes": 50, "empreinte": "hash2"},
    ]
    result = _aggregate_true_duplicates(_result(rows))
    assert result.rows == []
