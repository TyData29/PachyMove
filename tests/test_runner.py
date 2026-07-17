from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import psycopg
import pytest

from pgaudit_runner.models import QuerySpec
from pgaudit_runner.runner import _WRITE_RE, _coerce, run_query

REPO_ROOT = Path(__file__).resolve().parents[1]


def _spec(sql: str, **overrides) -> QuerySpec:
    defaults = dict(id="q", title="Q", file="q.sql", scope="instance", sql=sql)
    defaults.update(overrides)
    return QuerySpec(**defaults)


def test_read_only_guard_rejects_write_keyword():
    result = run_query(conn=None, spec=_spec("DROP TABLE foo"), target="instance", read_only=True)
    assert result.status == "error"
    assert "read_only" in result.error.message


def test_read_only_guard_rejects_keyword_inside_comment():
    # Régression : le garde-fou est purement textuel et scanne aussi les commentaires
    # (rencontré en pratique avec "CREATE" dans un commentaire -- voir CLAUDE.md).
    sql = "-- on pourrait faire un CREATE INDEX ici\nSELECT 1"
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
    """Le garde-fou de run_query() scanne le texte SQL brut (commentaires inclus) —
    aucune requête du dépôt ne doit contenir un mot-clé d'écriture, y compris en commentaire."""
    offenders = [
        f for f in (REPO_ROOT / "queries").rglob("*.sql")
        if _WRITE_RE.search(f.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"mots-clés d'écriture détectés dans : {offenders}"
