from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import psycopg
import pytest

from pgaudit_runner.models import QuerySpec
from pgaudit_runner.runner import _WRITE_RE, _coerce, _strip_sql_noise, run_query

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


def test_no_write_keywords_leak_into_real_query_files():
    """Même vérification que le garde-fou réel (littéraux/commentaires retirés avant
    le scan) — un littéral légitime comme 'CREATE' (privilege_type) ne doit pas
    faire échouer ce test, seul un vrai mot-clé d'écriture doit le faire."""
    offenders = [
        f for f in (REPO_ROOT / "queries").rglob("*.sql")
        if _WRITE_RE.search(_strip_sql_noise(f.read_text(encoding="utf-8")))
    ]
    assert not offenders, f"mots-clés d'écriture détectés dans : {offenders}"
