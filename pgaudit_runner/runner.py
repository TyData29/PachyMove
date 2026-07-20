from __future__ import annotations

import re
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

import psycopg

from .models import ErrorDetail, QueryResult, QuerySpec

_WRITE_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

_DOLLAR_QUOTED_RE = re.compile(r"\$([A-Za-z_][A-Za-z_0-9]*)?\$.*?\$\1\$", re.DOTALL)
_STRING_LITERAL_RE = re.compile(r"(?:E)?'(?:[^'\\]|\\.|'')*'")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")


def _strip_sql_noise(sql: str) -> str:
    """Retire littéraux puis commentaires avant le scan du garde-fou read_only.

    Les littéraux sont retirés en premier : un littéral peut contenir '--' ou '/*'
    (ex. "SELECT 'a--b'"), qui ne doivent alors pas être traités comme un vrai
    commentaire — sinon tout ce qui suit dans la requête (y compris un DROP/GRANT
    réel) serait effacé avec lui et échapperait au scan.
    """
    sql = _DOLLAR_QUOTED_RE.sub("$$", sql)
    sql = _STRING_LITERAL_RE.sub("''", sql)
    sql = _BLOCK_COMMENT_RE.sub(" ", sql)
    sql = _LINE_COMMENT_RE.sub("", sql)
    return sql


def _coerce(v: Any) -> Any:
    """Convertit les types non-JSON-sérialisables en str."""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (bytes, memoryview)):
        return f"<binary {len(v)} bytes>"
    return str(v)


def _version_gate_reason(spec: QuerySpec, server_version_num: Optional[int]) -> Optional[str]:
    """La requête est-elle hors de la plage de versions qu'elle déclare ?

    `server_version_num` absent (None) : on ne peut pas savoir, on n'exclut rien
    plutôt que de deviner. Format server_version_num (ex. 150003 pour PG 15.3).
    """
    if server_version_num is None:
        return None
    if spec.min_server_version is not None and server_version_num < spec.min_server_version:
        return (
            f"nécessite PostgreSQL ≥ {spec.min_server_version // 10000} "
            f"(serveur détecté : {server_version_num // 10000})"
        )
    if spec.max_server_version is not None and server_version_num > spec.max_server_version:
        return (
            f"nécessite PostgreSQL ≤ {spec.max_server_version // 10000} "
            f"(serveur détecté : {server_version_num // 10000})"
        )
    return None


def run_query(
    conn: psycopg.Connection,
    spec: QuerySpec,
    target: str,
    read_only: bool = True,
    side: str = "source",
    server_version_num: Optional[int] = None,
) -> QueryResult:
    assert spec.sql is not None

    version_skip = _version_gate_reason(spec, server_version_num)
    if version_skip:
        return QueryResult(
            id=spec.id,
            title=spec.title,
            scope=spec.scope,
            target=target,
            sql=spec.sql,
            status="skipped",
            skip_reason=version_skip,
            requires_superuser=spec.requires_superuser,
            expect_rows=spec.expect_rows,
            severity_if_unexpected=spec.severity_if_unexpected,
            side=side,
            applies_to=spec.applies_to,
        )

    if read_only and _WRITE_RE.search(_strip_sql_noise(spec.sql)):
        return QueryResult(
            id=spec.id,
            title=spec.title,
            scope=spec.scope,
            target=target,
            sql=spec.sql,
            status="error",
            requires_superuser=spec.requires_superuser,
            expect_rows=spec.expect_rows,
            severity_if_unexpected=spec.severity_if_unexpected,
            side=side,
            applies_to=spec.applies_to,
            error=ErrorDetail(
                message="Requête rejetée : mot-clé d'écriture détecté (mode read_only actif)",
                full_traceback="",
            ),
        )

    started_at = datetime.now(tz=timezone.utc)
    try:
        if spec.statement_timeout_ms:
            conn.execute(f"SET statement_timeout = {spec.statement_timeout_ms}")

        cur = conn.execute(spec.sql)
        columns = [d.name for d in cur.description] if cur.description else []
        rows = [
            {col: _coerce(val) for col, val in zip(columns, row)}
            for row in cur.fetchall()
        ]
        duration_ms = int(
            (datetime.now(tz=timezone.utc) - started_at).total_seconds() * 1000
        )
        return QueryResult(
            id=spec.id,
            title=spec.title,
            scope=spec.scope,
            target=target,
            sql=spec.sql,
            status="success",
            started_at=started_at.isoformat(),
            duration_ms=duration_ms,
            requires_superuser=spec.requires_superuser,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            expect_rows=spec.expect_rows,
            severity_if_unexpected=spec.severity_if_unexpected,
            side=side,
            applies_to=spec.applies_to,
        )

    except psycopg.Error as e:
        duration_ms = int(
            (datetime.now(tz=timezone.utc) - started_at).total_seconds() * 1000
        )
        return QueryResult(
            id=spec.id,
            title=spec.title,
            scope=spec.scope,
            target=target,
            sql=spec.sql,
            status="error",
            started_at=started_at.isoformat(),
            duration_ms=duration_ms,
            requires_superuser=spec.requires_superuser,
            expect_rows=spec.expect_rows,
            severity_if_unexpected=spec.severity_if_unexpected,
            side=side,
            applies_to=spec.applies_to,
            error=ErrorDetail(
                sqlstate=getattr(e, "sqlstate", None),
                message=str(e).splitlines()[0],
                full_traceback=traceback.format_exc(),
            ),
        )
