from __future__ import annotations

import re
import traceback
from datetime import datetime, timezone
from typing import Any

import psycopg

from .models import ErrorDetail, QueryResult, QuerySpec

_WRITE_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


def _coerce(v: Any) -> Any:
    """Convertit les types non-JSON-sérialisables en str."""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (bytes, memoryview)):
        return f"<binary {len(v)} bytes>"
    return str(v)


def run_query(
    conn: psycopg.Connection,
    spec: QuerySpec,
    target: str,
    read_only: bool = True,
) -> QueryResult:
    assert spec.sql is not None

    if read_only and _WRITE_RE.search(spec.sql):
        return QueryResult(
            id=spec.id,
            title=spec.title,
            scope=spec.scope,
            target=target,
            sql=spec.sql,
            status="error",
            requires_superuser=spec.requires_superuser,
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
            error=ErrorDetail(
                sqlstate=getattr(e, "sqlstate", None),
                message=str(e).splitlines()[0],
                full_traceback=traceback.format_exc(),
            ),
        )
