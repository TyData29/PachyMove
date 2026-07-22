from __future__ import annotations

import re
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

import psycopg
from psycopg import sql as pgsql

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


def _sample_clause(sample_target_rows: Optional[int], lignes_estimees: Any) -> pgsql.Composable:
    """TABLESAMPLE SYSTEM si l'estimation catalogue (reltuples) dépasse le seuil,
    sinon clause vide. Jamais de scan pour calculer l'estimation ; jamais de
    pourcentage en texte brut (composé via sql.Literal)."""
    if not sample_target_rows or lignes_estimees is None:
        return pgsql.SQL("")
    try:
        reltuples = float(lignes_estimees)
    except (TypeError, ValueError):
        return pgsql.SQL("")
    if reltuples <= sample_target_rows:
        return pgsql.SQL("")
    pct = min(100.0, sample_target_rows / reltuples * 100)
    return pgsql.SQL("TABLESAMPLE SYSTEM ({pct})").format(pct=pgsql.Literal(round(pct, 4)))


def _compose_derived_sql(
    template_sql: str, drow: dict[str, Any], sample_target_rows: Optional[int]
) -> pgsql.Composed:
    """Compose le gabarit d'une requête dérivée avec les valeurs d'une ligne de
    découverte — toujours via sql.Identifier/sql.Literal (psycopg), jamais par
    f-string ou .format() sur du texte brut : ce sont des identifiants d'objets
    réels (schéma/table/colonne), l'injection doit rester impossible même avec
    un nom d'objet exotique (espace, casse mixte, guillemet)."""
    kwargs: dict[str, pgsql.Composable] = {
        "sample": _sample_clause(sample_target_rows, drow.get("lignes_estimees")),
    }
    if drow.get("schema_") is not None:
        kwargs["schema"] = pgsql.Identifier(drow["schema_"])
    if drow.get("relation") is not None:
        kwargs["table"] = pgsql.Identifier(drow["relation"])
    if drow.get("colonne") is not None:
        kwargs["column"] = pgsql.Identifier(drow["colonne"])
    return pgsql.SQL(template_sql).format(**kwargs)


def run_derived_query(
    conn: psycopg.Connection,
    spec: QuerySpec,
    target: str,
    read_only: bool = True,
    side: str = "source",
    server_version_num: Optional[int] = None,
) -> QueryResult:
    """Exécute une requête « dérivée » : une requête de découverte (catalogue),
    puis le gabarit `spec.sql` une fois par ligne découverte, composé en toute
    sécurité (cf. `_compose_derived_sql`). Toutes les lignes obtenues sont
    concaténées en un seul `QueryResult` — une erreur sur une table donnée
    n'interrompt pas le scan des autres (continue-on-error au niveau table,
    même principe que le reste de l'outil au niveau requête)."""
    assert spec.sql is not None
    assert spec.iterate_over_sql is not None

    version_skip = _version_gate_reason(spec, server_version_num)
    if version_skip:
        return QueryResult(
            id=spec.id, title=spec.title, scope=spec.scope, target=target,
            sql=spec.sql, status="skipped", skip_reason=version_skip,
            requires_superuser=spec.requires_superuser,
            expect_rows=spec.expect_rows, severity_if_unexpected=spec.severity_if_unexpected,
            side=side, applies_to=spec.applies_to,
        )

    if read_only and _WRITE_RE.search(_strip_sql_noise(spec.sql)):
        return QueryResult(
            id=spec.id, title=spec.title, scope=spec.scope, target=target,
            sql=spec.sql, status="error",
            requires_superuser=spec.requires_superuser,
            expect_rows=spec.expect_rows, severity_if_unexpected=spec.severity_if_unexpected,
            side=side, applies_to=spec.applies_to,
            error=ErrorDetail(
                message="Requête rejetée : mot-clé d'écriture détecté (mode read_only actif)",
                full_traceback="",
            ),
        )

    if read_only and _WRITE_RE.search(_strip_sql_noise(spec.iterate_over_sql)):
        return QueryResult(
            id=spec.id, title=spec.title, scope=spec.scope, target=target,
            sql=spec.sql, status="error",
            requires_superuser=spec.requires_superuser,
            expect_rows=spec.expect_rows, severity_if_unexpected=spec.severity_if_unexpected,
            side=side, applies_to=spec.applies_to,
            error=ErrorDetail(
                message="Requête de découverte rejetée : mot-clé d'écriture détecté (mode read_only actif)",
                full_traceback="",
            ),
        )

    started_at = datetime.now(tz=timezone.utc)

    try:
        if spec.statement_timeout_ms:
            conn.execute(f"SET statement_timeout = {spec.statement_timeout_ms}")
        disc_cur = conn.execute(spec.iterate_over_sql)
        disc_columns = [d.name for d in disc_cur.description] if disc_cur.description else []
        discovery_rows = [dict(zip(disc_columns, row)) for row in disc_cur.fetchall()]
    except psycopg.Error as e:
        duration_ms = int((datetime.now(tz=timezone.utc) - started_at).total_seconds() * 1000)
        return QueryResult(
            id=spec.id, title=spec.title, scope=spec.scope, target=target,
            sql=spec.sql, status="error",
            started_at=started_at.isoformat(), duration_ms=duration_ms,
            requires_superuser=spec.requires_superuser,
            expect_rows=spec.expect_rows, severity_if_unexpected=spec.severity_if_unexpected,
            side=side, applies_to=spec.applies_to,
            error=ErrorDetail(
                sqlstate=getattr(e, "sqlstate", None),
                message=f"Découverte échouée : {str(e).splitlines()[0]}",
                full_traceback=traceback.format_exc(),
            ),
        )

    rows: list[dict[str, Any]] = []
    columns_order: list[str] = []

    def _ensure_column(name: str) -> None:
        if name not in columns_order:
            columns_order.append(name)

    for drow in discovery_rows:
        ident: dict[str, Any] = {}
        for key in ("schema_", "relation", "colonne"):
            if drow.get(key) is not None:
                ident[key] = _coerce(drow[key])
                _ensure_column(key)
        try:
            composed = _compose_derived_sql(spec.sql, drow, spec.sample_target_rows)
            cur = conn.execute(composed)
            cur_columns = [d.name for d in cur.description] if cur.description else []
            for row in cur.fetchall():
                row_dict = dict(ident)
                row_dict.update({col: _coerce(val) for col, val in zip(cur_columns, row)})
                rows.append(row_dict)
            for col in cur_columns:
                _ensure_column(col)
        except Exception as e:
            # Exception large et non seulement psycopg.Error : une requête composée
            # dynamiquement (gabarit + identifiants découverts à l'exécution) a une
            # surface d'erreur plus large qu'une requête statique (ex. gabarit mal
            # formé). Continue-on-error prime ici : une table ne doit jamais faire
            # échouer les suivantes.
            ident["erreur"] = str(e).splitlines()[0]
            rows.append(ident)
            _ensure_column("erreur")

    duration_ms = int((datetime.now(tz=timezone.utc) - started_at).total_seconds() * 1000)
    return QueryResult(
        id=spec.id, title=spec.title, scope=spec.scope, target=target,
        sql=spec.sql, status="success",
        started_at=started_at.isoformat(), duration_ms=duration_ms,
        requires_superuser=spec.requires_superuser,
        columns=columns_order, rows=rows, row_count=len(rows),
        expect_rows=spec.expect_rows, severity_if_unexpected=spec.severity_if_unexpected,
        side=side, applies_to=spec.applies_to,
    )
