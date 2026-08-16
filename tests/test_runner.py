from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import psycopg
import pytest

from pgaudit_runner.models import QuerySpec
from pgaudit_runner.runner import (
    _WRITE_RE,
    _coerce,
    _compose_derived_sql,
    _sample_clause,
    _strip_sql_noise,
    run_derived_query,
    run_query,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _spec(sql: str, **overrides) -> QuerySpec:
    defaults = dict(id="q", title="Q", file="q.sql", scope="instance", sql=sql)
    defaults.update(overrides)
    return QuerySpec(**defaults)


def _mock_conn(rows=None) -> MagicMock:
    conn = MagicMock()
    cur = MagicMock()
    cur.description = [SimpleNamespace(name="x")]
    cur.fetchall.return_value = rows or [(1,)]
    conn.execute.return_value = cur
    return conn


def test_read_only_guard_rejects_write_keyword():
    result = run_query(conn=None, spec=_spec("DROP TABLE foo"), target="instance", read_only=True)
    assert result.status == "error"
    assert "read_only" in result.error.message


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1 -- ne pas CREATE ici",
        "SELECT 'CREATE' AS x",
        "SELECT date_creation FROM t",
        "SELECT * FROM t /* GRANT */",
    ],
    ids=["line_comment", "string_literal", "identifier_substring", "block_comment"],
)
def test_read_only_guard_accepts_legitimate_queries(sql):
    # Spec detection_migration §3 : un mot-clé d'écriture dans un commentaire, un
    # littéral ou une sous-chaîne d'identifiant ne doit pas rejeter la requête.
    result = run_query(conn=_mock_conn(), spec=_spec(sql), target="instance", read_only=True)
    assert result.status == "success"


def test_read_only_guard_not_fooled_by_dashdash_inside_literal():
    # Un littéral contenant '--' ne doit pas masquer un DROP qui le suit réellement —
    # justifie l'ordre littéraux-puis-commentaires de _strip_sql_noise().
    sql = "SELECT 'a--b' AS x; DROP TABLE t"
    result = run_query(conn=None, spec=_spec(sql), target="instance", read_only=True)
    assert result.status == "error"


@pytest.mark.parametrize(
    "sql",
    ["CREATE TABLE t (i int)", "SELECT 1; DROP TABLE t"],
    ids=["create_table", "chained_drop"],
)
def test_read_only_guard_rejects_real_write_statements(sql):
    result = run_query(conn=None, spec=_spec(sql), target="instance", read_only=True)
    assert result.status == "error"


def test_read_only_guard_ignored_when_disabled():
    conn = MagicMock()
    cur = MagicMock()
    cur.description = None
    cur.fetchall.return_value = []
    conn.execute.return_value = cur

    result = run_query(conn=conn, spec=_spec("DROP TABLE foo"), target="instance", read_only=False)
    assert result.status == "success"


def test_run_query_success_coerces_and_counts_rows():
    conn = MagicMock()
    cur = MagicMock()
    cur.description = [SimpleNamespace(name="id"), SimpleNamespace(name="data")]
    cur.fetchall.return_value = [(1, b"\x00\x01"), (2, None)]
    conn.execute.return_value = cur

    result = run_query(conn=conn, spec=_spec("SELECT id, data FROM t"), target="db1", read_only=True)

    assert result.status == "success"
    assert result.columns == ["id", "data"]
    assert result.row_count == 2
    assert result.rows[0] == {"id": 1, "data": "<binary 2 bytes>"}
    assert result.rows[1] == {"id": 2, "data": None}


def test_run_query_captures_psycopg_error():
    conn = MagicMock()
    conn.execute.side_effect = psycopg.Error("relation does not exist")

    result = run_query(conn=conn, spec=_spec("SELECT * FROM missing"), target="db1", read_only=True)

    assert result.status == "error"
    assert result.error.message == "relation does not exist"


def test_run_query_defaults_side_to_source():
    result = run_query(conn=_mock_conn(), spec=_spec("SELECT 1"), target="instance", read_only=True)
    assert result.side == "source"


def test_run_query_propagates_explicit_side_and_applies_to_on_success():
    spec = _spec("SELECT 1", applies_to=["pg_upgrade"])
    result = run_query(conn=_mock_conn(), spec=spec, target="instance", read_only=True, side="target")
    assert result.side == "target"
    assert result.applies_to == ["pg_upgrade"]


def test_run_query_propagates_side_on_read_only_rejection():
    result = run_query(conn=None, spec=_spec("DROP TABLE foo"), target="instance", read_only=True, side="target")
    assert result.side == "target"


def test_run_query_propagates_side_on_error():
    conn = MagicMock()
    conn.execute.side_effect = psycopg.Error("boom")
    result = run_query(conn=conn, spec=_spec("SELECT 1"), target="db1", read_only=True, side="target")
    assert result.side == "target"


# ── Garde-fou de version (min_server_version / max_server_version) ──────────


def test_run_query_skips_when_server_version_below_minimum():
    spec = _spec("SELECT 1", min_server_version=150000)
    result = run_query(conn=None, spec=spec, target="instance", server_version_num=140011)
    assert result.status == "skipped"
    assert "PostgreSQL ≥ 15" in result.skip_reason
    assert "14" in result.skip_reason


def test_run_query_runs_when_server_version_meets_minimum():
    spec = _spec("SELECT 1", min_server_version=150000)
    result = run_query(conn=_mock_conn(), spec=spec, target="instance", server_version_num=170004)
    assert result.status == "success"


def test_run_query_skips_when_server_version_above_maximum():
    spec = _spec("SELECT 1", max_server_version=149999)
    result = run_query(conn=None, spec=spec, target="instance", server_version_num=170004)
    assert result.status == "skipped"
    assert "PostgreSQL ≤ 14" in result.skip_reason


def test_run_query_runs_when_server_version_within_maximum():
    spec = _spec("SELECT 1", max_server_version=149999)
    result = run_query(conn=_mock_conn(), spec=spec, target="instance", server_version_num=140011)
    assert result.status == "success"


def test_run_query_ignores_version_gate_when_server_version_num_unknown():
    spec = _spec("SELECT 1", min_server_version=150000, max_server_version=149999)
    result = run_query(conn=_mock_conn(), spec=spec, target="instance", server_version_num=None)
    assert result.status == "success"


def test_run_query_ignores_version_gate_when_not_declared():
    result = run_query(conn=_mock_conn(), spec=_spec("SELECT 1"), target="instance", server_version_num=140011)
    assert result.status == "success"


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("x", "x"),
        (1, 1),
        (1.5, 1.5),
        (True, True),
        (b"\x00\x01\x02", "<binary 3 bytes>"),
    ],
)
def test_coerce_passthrough_and_binary(value, expected):
    assert _coerce(value) == expected


def _cur(columns: list[str], rows: list[tuple]) -> MagicMock:
    cur = MagicMock()
    cur.description = [SimpleNamespace(name=c) for c in columns]
    cur.fetchall.return_value = rows
    return cur


def _derived_spec(template_sql: str, discovery_sql: str, **overrides) -> QuerySpec:
    defaults = dict(
        id="q", title="Q", file="q.sql", scope="database",
        sql=template_sql, iterate_over="discover.sql", iterate_over_sql=discovery_sql,
    )
    defaults.update(overrides)
    return QuerySpec(**defaults)


# ── run_derived_query (requêtes "dérivées", specs_data_quality_on_tables.md) ─


def test_run_derived_query_executes_template_per_discovered_row():
    discovery_cur = _cur(
        ["schema_", "relation", "colonne"],
        [("public", "t1", "c1"), ("public", "t2", "c2")],
    )
    metric_cur_1 = _cur(["pct_remplissage"], [(5.0,)])
    metric_cur_2 = _cur(["pct_remplissage"], [(3.0,)])
    conn = MagicMock()
    conn.execute.side_effect = [discovery_cur, metric_cur_1, metric_cur_2]

    spec = _derived_spec("SELECT ... FROM {schema}.{table} {sample}", "SELECT ...")
    result = run_derived_query(conn, spec, target="db1", read_only=True)

    assert result.status == "success"
    assert result.row_count == 2
    assert result.rows[0] == {"schema_": "public", "relation": "t1", "colonne": "c1", "pct_remplissage": 5.0}
    assert result.rows[1] == {"schema_": "public", "relation": "t2", "colonne": "c2", "pct_remplissage": 3.0}
    assert result.columns == ["schema_", "relation", "colonne", "pct_remplissage"]


def test_run_derived_query_continues_after_per_row_error():
    discovery_cur = _cur(["schema_", "relation"], [("public", "t1"), ("public", "t2")])
    ok_cur = _cur(["nb_lignes"], [(10,)])
    conn = MagicMock()
    conn.execute.side_effect = [discovery_cur, psycopg.Error("permission denied"), ok_cur]

    spec = _derived_spec("SELECT count(*) AS nb_lignes FROM {schema}.{table}", "SELECT ...")
    result = run_derived_query(conn, spec, target="db1", read_only=True)

    assert result.status == "success"
    assert result.row_count == 2
    assert result.rows[0]["erreur"] == "permission denied"
    assert result.rows[1] == {"schema_": "public", "relation": "t2", "nb_lignes": 10}
    assert result.error_row_count == 1


def test_run_derived_query_error_row_count_zero_when_all_succeed():
    discovery_cur = _cur(["schema_", "relation"], [("public", "t1")])
    ok_cur = _cur(["nb_lignes"], [(10,)])
    conn = MagicMock()
    conn.execute.side_effect = [discovery_cur, ok_cur]

    spec = _derived_spec("SELECT count(*) AS nb_lignes FROM {schema}.{table}", "SELECT ...")
    result = run_derived_query(conn, spec, target="db1", read_only=True)

    assert result.error_row_count == 0


def test_run_derived_query_discovery_failure_returns_error():
    conn = MagicMock()
    conn.execute.side_effect = psycopg.Error("relation geometry_columns does not exist")

    spec = _derived_spec("SELECT 1 FROM {schema}.{table}", "SELECT * FROM geometry_columns")
    result = run_derived_query(conn, spec, target="db1", read_only=True)

    assert result.status == "error"
    assert "Découverte échouée" in result.error.message


def test_run_derived_query_rejects_write_keyword_in_template():
    spec = _derived_spec("DROP TABLE {schema}.{table}", "SELECT 1")
    result = run_derived_query(conn=None, spec=spec, target="db1", read_only=True)
    assert result.status == "error"
    assert "read_only" in result.error.message


def test_run_derived_query_skips_on_version_gate():
    spec = _derived_spec("SELECT 1 FROM {schema}.{table}", "SELECT 1", min_server_version=150000)
    result = run_derived_query(conn=None, spec=spec, target="db1", server_version_num=140011)
    assert result.status == "skipped"


def test_run_derived_query_empty_discovery_yields_empty_success():
    discovery_cur = _cur(["schema_", "relation"], [])
    conn = MagicMock()
    conn.execute.side_effect = [discovery_cur]

    spec = _derived_spec("SELECT 1 FROM {schema}.{table}", "SELECT ...")
    result = run_derived_query(conn, spec, target="db1", read_only=True)

    assert result.status == "success"
    assert result.rows == []
    assert result.row_count == 0


# ── Composition sécurisée (identifiants, échantillonnage) ────────────────────


def test_sample_clause_empty_when_no_target():
    assert _sample_clause(None, 1_000_000).as_string(None) == ""


def test_sample_clause_empty_when_under_threshold():
    assert _sample_clause(15000, 500).as_string(None) == ""


def test_sample_clause_applies_when_over_threshold():
    clause = _sample_clause(15000, 1_500_000).as_string(None)
    assert clause == "TABLESAMPLE SYSTEM (1.0)"


def test_compose_derived_sql_quotes_identifiers_safely():
    # Noms d'objets exotiques (espace, guillemet double) : doivent être
    # échappés par psycopg, jamais interpolés en texte brut (pas d'injection).
    template = "SELECT {column} FROM {schema}.{table} {sample}"
    drow = {"schema_": "public", "relation": 'Weird"Table', "colonne": "my col"}
    composed = _compose_derived_sql(template, drow, None).as_string(None)
    assert '"Weird""Table"' in composed
    assert '"my col"' in composed
    assert '"public"' in composed


def test_compose_derived_sql_omits_column_placeholder_when_absent():
    template = "SELECT count(*) FROM {schema}.{table} {sample}"
    drow = {"schema_": "public", "relation": "t1"}
    composed = _compose_derived_sql(template, drow, None).as_string(None)
    assert '"public"."t1"' in composed


def test_run_query_propagates_description_on_success():
    spec = _spec("SELECT 1", description="Ce que fait ce contrôle.")
    result = run_query(conn=_mock_conn(), spec=spec, target="instance", read_only=True)
    assert result.description == "Ce que fait ce contrôle."


def test_run_query_propagates_description_when_none():
    result = run_query(conn=_mock_conn(), spec=_spec("SELECT 1"), target="instance", read_only=True)
    assert result.description is None


def test_run_derived_query_propagates_description():
    discovery_cur = _cur(["schema_", "relation"], [])
    conn = MagicMock()
    conn.execute.side_effect = [discovery_cur]
    spec = _derived_spec(
        "SELECT 1 FROM {schema}.{table}", "SELECT ...", description="Description du scan.",
    )
    result = run_derived_query(conn, spec, target="db1", read_only=True)
    assert result.description == "Description du scan."


def test_no_write_keywords_leak_into_real_query_files():
    """Même vérification que le garde-fou réel (littéraux/commentaires retirés avant
    le scan) — un littéral légitime comme 'CREATE' (privilege_type) ne doit pas
    faire échouer ce test, seul un vrai mot-clé d'écriture doit le faire."""
    offenders = [
        f for f in (REPO_ROOT / "queries").rglob("*.sql")
        if _WRITE_RE.search(_strip_sql_noise(f.read_text(encoding="utf-8")))
    ]
    assert not offenders, f"mots-clés d'écriture détectés dans : {offenders}"
