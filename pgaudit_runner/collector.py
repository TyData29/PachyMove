from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import psycopg

from .config import load_manifest
from .connection import get_server_version, open_connection, resolve_password
from .models import (
    ConnectionInfo,
    ErrorDetail,
    QueryResult,
    QuerySpec,
    RunMetadata,
    RunSummary,
    SelectionInfo,
)
from .runner import run_query

TOOL_VERSION = "1.0.0"


def _select_queries(
    specs: list[QuerySpec],
    only: list[str],
    tags: list[str],
    exclude: list[str],
) -> list[QuerySpec]:
    """Applique la logique de sélection : --only > enabled+tags − exclude."""
    if only:
        return [s for s in specs if s.id in only]
    result = [s for s in specs if s.enabled]
    if tags:
        result = [s for s in result if any(t in s.tags for t in tags)]
    if exclude:
        result = [s for s in result if s.id not in exclude]
    return result


def _conn_error_result(spec: QuerySpec, target: str, exc: Exception) -> QueryResult:
    return QueryResult(
        id=spec.id,
        title=spec.title,
        scope=spec.scope,
        target=target,
        sql=spec.sql or "",
        status="error",
        requires_superuser=spec.requires_superuser,
        error=ErrorDetail(
            message=str(exc).splitlines()[0],
            full_traceback=str(exc),
        ),
    )


def collect(
    host: str,
    port: int,
    user: str,
    dbnames: list[str],
    maintenance_db: str,
    manifest_path: Path,
    queries_dir: Path,
    output_dir: Path,
    tags: list[str],
    only: list[str],
    exclude: list[str],
    dry_run: bool,
    service: Optional[str] = None,
) -> Path:
    config, all_specs = load_manifest(manifest_path, queries_dir)
    manifest_name: str = config["meta"].get("name", manifest_path.stem)
    read_only: bool = config["read_only"]

    selected = _select_queries(all_specs, only, tags, exclude)
    selected_ids = {s.id for s in selected}

    started_at = datetime.now(tz=timezone.utc)
    results: list[QueryResult] = []
    server_version: Optional[str] = None

    if dry_run:
        for spec in selected:
            targets = ["instance"] if spec.scope == "instance" else (dbnames or ["(aucune base)"])
            for target in targets:
                results.append(QueryResult(
                    id=spec.id, title=spec.title, scope=spec.scope, target=target,
                    sql=spec.sql or "", status="skipped", skip_reason="dry-run",
                    requires_superuser=spec.requires_superuser,
                ))
    else:
        password = resolve_password(host, port, user, maintenance_db, service)

        instance_specs = [s for s in selected if s.scope == "instance"]
        if instance_specs:
            try:
                with open_connection(host, port, user, maintenance_db, service, password) as conn:
                    if server_version is None:
                        server_version = get_server_version(conn)
                    for spec in instance_specs:
                        results.append(run_query(conn, spec, "instance", read_only))
            except psycopg.OperationalError as exc:
                for spec in instance_specs:
                    results.append(_conn_error_result(spec, "instance", exc))

        db_specs = [s for s in selected if s.scope == "database"]
        if db_specs:
            for dbname in dbnames:
                try:
                    with open_connection(host, port, user, dbname, service, password) as conn:
                        if server_version is None:
                            server_version = get_server_version(conn)
                        for spec in db_specs:
                            results.append(run_query(conn, spec, dbname, read_only))
                except psycopg.OperationalError as exc:
                    for spec in db_specs:
                        results.append(_conn_error_result(spec, dbname, exc))

    # Requêtes non sélectionnées → skipped (désactivées ou filtrées)
    for spec in all_specs:
        if spec.id not in selected_ids:
            results.append(QueryResult(
                id=spec.id, title=spec.title, scope=spec.scope,
                target="instance" if spec.scope == "instance" else "(toutes bases)",
                sql=spec.sql or "",
                status="skipped",
                requires_superuser=spec.requires_superuser,
                skip_reason=spec.skip_reason_if_disabled or "désactivée ou filtrée",
            ))

    finished_at = datetime.now(tz=timezone.utc)
    summary = RunSummary(
        total=len(results),
        success=sum(1 for r in results if r.status == "success"),
        skipped=sum(1 for r in results if r.status == "skipped"),
        error=sum(1 for r in results if r.status == "error"),
    )
    metadata = RunMetadata(
        tool_version=TOOL_VERSION,
        manifest_name=manifest_name,
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        connection=ConnectionInfo(
            host=host, port=port, user=user,
            server_version=server_version,
            databases_targeted=dbnames,
        ),
        selection=SelectionInfo(tags=tags, only=only, exclude=exclude, dry_run=dry_run),
        summary=summary,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    ts = started_at.strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"audit_{ts}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            {"metadata": asdict(metadata), "results": [asdict(r) for r in results]},
            f,
            ensure_ascii=False,
            indent=2,
        )

    return output_file
