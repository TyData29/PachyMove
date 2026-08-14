from __future__ import annotations

import json
import os
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import psycopg

from .config import ConfigError, load_manifest
from .connection import get_server_version, get_server_version_num, open_connection, resolve_password
from .models import (
    ConnectionInfo,
    ErrorDetail,
    QueryResult,
    QuerySpec,
    RunMetadata,
    RunSummary,
    SelectionInfo,
)
from .runner import run_derived_query, run_query

TOOL_VERSION = "1.0.0"


def _run_spec(
    conn: psycopg.Connection,
    spec: QuerySpec,
    target: str,
    read_only: bool,
    side: str,
    server_version_num: Optional[int],
) -> QueryResult:
    """Dispatch vers run_derived_query (requête "dérivée", iterate_over posé)
    ou run_query (comportement standard, inchangé)."""
    if spec.iterate_over:
        result = run_derived_query(
            conn, spec, target, read_only, side=side, server_version_num=server_version_num,
        )
        if spec.id == "deprecated_tables_no_recent_timestamp" and result.status == "success":
            result = _aggregate_deprecated_tables(result)
        elif spec.id == "true_duplicate_tables" and result.status == "success":
            result = _aggregate_true_duplicates(result)
        return result
    return run_query(
        conn, spec, target, read_only, side=side, server_version_num=server_version_num,
    )


def _aggregate_deprecated_tables(result: QueryResult) -> QueryResult:
    """Post-traitement spécifique à `deprecated_tables_no_recent_timestamp`
    (specs_data_quality_on_tables.md §4.4) : une table peut avoir plusieurs
    colonnes temporelles, une ligne brute par colonne. On regroupe par table
    (OU logique des trois seuils sur toutes ses colonnes), et on ne garde que
    les tables sans aucune activité récente, classées par ancienneté."""
    if not result.rows:
        return result

    groups: dict[tuple[Any, Any], dict[str, Any]] = {}
    for row in result.rows:
        key = (row.get("schema_"), row.get("relation"))
        g = groups.setdefault(
            key, {"recent_6_mois": False, "recent_1_an": False, "recent_3_ans": False, "erreur": None}
        )
        for champ in ("recent_6_mois", "recent_1_an", "recent_3_ans"):
            if row.get(champ):
                g[champ] = True
        if row.get("erreur") and not g["erreur"]:
            g["erreur"] = row["erreur"]

    new_rows: list[dict[str, Any]] = []
    for (schema_, relation), g in groups.items():
        if g["recent_6_mois"]:
            continue  # saine, absente du résultat

        if g["erreur"] and not (g["recent_1_an"] or g["recent_3_ans"]):
            new_rows.append({"schema_": schema_, "relation": relation, "verdict": None, "erreur": g["erreur"]})
            continue

        if g["recent_1_an"]:
            verdict = "aucune activité depuis 6 mois"
        elif g["recent_3_ans"]:
            verdict = "aucune activité depuis 1 an"
        else:
            verdict = "aucune activité depuis 3 ans (potentiellement dépréciée)"
        new_rows.append({"schema_": schema_, "relation": relation, "verdict": verdict})

    columns = ["schema_", "relation", "verdict"]
    if any("erreur" in r for r in new_rows):
        columns.append("erreur")

    return replace(result, rows=new_rows, row_count=len(new_rows), columns=columns)


def _aggregate_true_duplicates(result: QueryResult) -> QueryResult:
    """Post-traitement spécifique à `true_duplicate_tables` (specs_data_quality_on_tables.md
    §4.5) : regroupe les candidats par (nb_lignes, empreinte) — un même contenu
    garantit implicitement une même structure (pas besoin de reporter la
    signature depuis la découverte). Un groupe de plus d'une table est un vrai
    doublon."""
    if not result.rows:
        return result

    groups: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
    errors: list[dict[str, Any]] = []
    for row in result.rows:
        if row.get("erreur"):
            errors.append(row)
            continue
        key = (row.get("nb_lignes"), row.get("empreinte"))
        groups.setdefault(key, []).append(row)

    new_rows: list[dict[str, Any]] = []
    groupe_id = 0
    for (nb_lignes, _empreinte), members in groups.items():
        if len(members) < 2:
            continue
        groupe_id += 1
        for m in members:
            new_rows.append({
                "groupe": groupe_id,
                "schema_": m.get("schema_"),
                "relation": m.get("relation"),
                "nb_lignes": nb_lignes,
            })
    new_rows.extend(errors)

    columns = ["groupe", "schema_", "relation", "nb_lignes"]
    if errors:
        columns.append("erreur")

    return replace(result, rows=new_rows, row_count=len(new_rows), columns=columns)


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


def _conn_error_result(
    spec: QuerySpec, target: str, exc: Exception, side: str = "source"
) -> QueryResult:
    return QueryResult(
        id=spec.id,
        title=spec.title,
        scope=spec.scope,
        description=spec.description,
        target=target,
        sql=spec.sql or "",
        status="error",
        requires_superuser=spec.requires_superuser,
        side=side,
        applies_to=spec.applies_to,
        error=ErrorDetail(
            message=str(exc).splitlines()[0],
            full_traceback=str(exc),
        ),
    )


def _skip_result(spec: QuerySpec, target: str, side: str, reason: str) -> QueryResult:
    return QueryResult(
        id=spec.id,
        title=spec.title,
        scope=spec.scope,
        description=spec.description,
        target=target,
        sql=spec.sql or "",
        status="skipped",
        skip_reason=reason,
        requires_superuser=spec.requires_superuser,
        side=side,
        applies_to=spec.applies_to,
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
    target_host: Optional[str] = None,
    target_port: Optional[int] = None,
    target_user: Optional[str] = None,
    target_service: Optional[str] = None,
    target_maintenance_db: Optional[str] = None,
    target_dbnames: Optional[list[str]] = None,
    migration_method: Optional[str] = None,
    work_mem: Optional[str] = None,
) -> Path:
    # Une cible n'existe que si elle a été explicitement demandée (aucun flag
    # --target-* ne doit en créer une par héritage silencieux).
    target_defined = target_host is not None

    if target_defined and (host, port) == (target_host, target_port):
        raise ConfigError(
            f"Erreur : source et cible désignent la même instance ({host}:{port})."
        )

    no_service_either_side = not service and not target_service
    same_host_user = target_defined and host == target_host and user == target_user
    if (
        target_defined
        and no_service_either_side
        and os.environ.get("PGPASSWORD")
        and not same_host_user
    ):
        raise ConfigError(
            "Erreur : PGPASSWORD ne peut pas servir deux connexions distinctes. "
            "Utilisez ~/.pgpass (recommandé) ou --service / --target-service."
        )

    # Dérivée de la topologie, jamais déclarée : pg_upgrade exige un accès local
    # aux deux clusters, donc n'est physiquement possible que sur le même hôte.
    same_server_hint: Optional[bool] = (host == target_host) if target_defined else None

    if migration_method == "pg_upgrade" and same_server_hint is False:
        raise ConfigError(
            "Erreur : pg_upgrade nécessite que source et cible soient sur le même serveur. "
            f"Source : {host} (hôte). Cible : {target_host} (hôte). "
            "Utilisez dump_restore, ou vérifiez la configuration."
        )

    config, all_specs = load_manifest(manifest_path, queries_dir)
    manifest_name: str = config["meta"].get("name", manifest_path.stem)
    read_only: bool = config["read_only"]

    selected = _select_queries(all_specs, only, tags, exclude)
    selected_ids = {s.id for s in selected}

    started_at = datetime.now(tz=timezone.utc)
    results: list[QueryResult] = []
    server_version: Optional[str] = None
    server_version_num: Optional[int] = None
    target_server_version: Optional[str] = None
    target_server_version_num: Optional[int] = None
    same_server: Optional[bool] = same_server_hint
    target_error: Optional[str] = None
    target_databases_targeted = target_dbnames if target_dbnames is not None else dbnames

    instance_specs_source = [
        s for s in selected if s.scope == "instance" and s.side in ("source", "both")
    ]
    instance_specs_target = [
        s for s in selected if s.scope == "instance" and s.side in ("target", "both")
    ]
    db_specs = [s for s in selected if s.scope == "database"]

    if dry_run:
        for spec in selected:
            source_targets = ["instance"] if spec.scope == "instance" else (dbnames or ["(aucune base)"])
            if spec.side in ("source", "both"):
                for t in source_targets:
                    results.append(_skip_result(spec, t, "source", "dry-run"))
            if spec.side in ("target", "both"):
                target_targets = ["instance"] if spec.scope == "instance" else (
                    (target_dbnames if target_dbnames is not None else dbnames) or ["(aucune base)"]
                )
                for t in target_targets:
                    reason = "dry-run" if target_defined else "aucune cible définie"
                    results.append(_skip_result(spec, t, "target", reason))
    else:
        password = resolve_password(
            host, port, user, maintenance_db, service,
            label="source" if target_defined else None,
        )
        target_password = None
        if target_defined:
            target_password = resolve_password(
                target_host, target_port, target_user, target_maintenance_db,
                target_service, label="cible",
            )

        source_info: tuple[str, int] = (host, port)
        need_source_conn = bool(instance_specs_source) or target_defined
        if need_source_conn:
            try:
                with open_connection(
                    host, port, user, maintenance_db, service, password, work_mem,
                ) as conn:
                    server_version = get_server_version(conn)
                    server_version_num = get_server_version_num(conn)
                    source_info = (conn.info.host, conn.info.port)
                    for spec in instance_specs_source:
                        results.append(_run_spec(
                            conn, spec, "instance", read_only, "source",
                            server_version_num,
                        ))
            except psycopg.OperationalError as exc:
                for spec in instance_specs_source:
                    results.append(_conn_error_result(spec, "instance", exc, side="source"))

        target_db_set: Optional[set[str]] = None
        target_conn_exc: Optional[Exception] = None

        if target_defined:
            try:
                with open_connection(
                    target_host, target_port, target_user, target_maintenance_db,
                    target_service, target_password, work_mem,
                ) as tconn:
                    target_server_version = get_server_version(tconn)
                    target_server_version_num = get_server_version_num(tconn)
                    target_info = (tconn.info.host, tconn.info.port)
                    same_server = source_info[0] == target_info[0]

                    if source_info == target_info:
                        raise ConfigError(
                            "Erreur : source et cible désignent la même instance "
                            f"({source_info[0]}:{source_info[1]})."
                        )
                    if migration_method == "pg_upgrade" and same_server is False:
                        raise ConfigError(
                            "Erreur : pg_upgrade nécessite que source et cible soient sur le "
                            f"même serveur. Source : {source_info[0]} (hôte). "
                            f"Cible : {target_info[0]} (hôte). "
                            "Utilisez dump_restore, ou vérifiez la configuration."
                        )

                    target_db_set = {
                        row[0] for row in tconn.execute("SELECT datname FROM pg_database").fetchall()
                    }
                    for spec in instance_specs_target:
                        results.append(_run_spec(
                            tconn, spec, "instance", read_only, "target",
                            target_server_version_num,
                        ))
            except psycopg.OperationalError as exc:
                target_error = str(exc).splitlines()[0]
                target_conn_exc = exc
                same_server = same_server_hint
                for spec in instance_specs_target:
                    results.append(_conn_error_result(spec, "instance", exc, side="target"))
        else:
            for spec in instance_specs_target:
                results.append(_skip_result(spec, "instance", "target", "aucune cible définie"))

        for dbname in dbnames:
            src_specs = [s for s in db_specs if s.side in ("source", "both")]
            if src_specs:
                try:
                    with open_connection(
                        host, port, user, dbname, service, password, work_mem,
                    ) as conn:
                        if server_version is None:
                            server_version = get_server_version(conn)
                        if server_version_num is None:
                            server_version_num = get_server_version_num(conn)
                        for spec in src_specs:
                            results.append(_run_spec(
                                conn, spec, dbname, read_only, "source",
                                server_version_num,
                            ))
                except psycopg.OperationalError as exc:
                    for spec in src_specs:
                        results.append(_conn_error_result(spec, dbname, exc, side="source"))

        tgt_specs = [s for s in db_specs if s.side in ("target", "both")]
        if tgt_specs:
            for dbname in (target_databases_targeted or dbnames):
                if not target_defined:
                    for spec in tgt_specs:
                        results.append(_skip_result(spec, dbname, "target", "aucune cible définie"))
                elif target_conn_exc is not None:
                    for spec in tgt_specs:
                        results.append(_conn_error_result(spec, dbname, target_conn_exc, side="target"))
                elif dbname not in (target_db_set or set()):
                    for spec in tgt_specs:
                        results.append(_skip_result(
                            spec, dbname, "target", f"base {dbname} absente de la cible"
                        ))
                else:
                    try:
                        with open_connection(
                            target_host, target_port, target_user, dbname,
                            target_service, target_password, work_mem,
                        ) as tconn:
                            if target_server_version is None:
                                target_server_version = get_server_version(tconn)
                            if target_server_version_num is None:
                                target_server_version_num = get_server_version_num(tconn)
                            for spec in tgt_specs:
                                results.append(_run_spec(
                                    tconn, spec, dbname, read_only, "target",
                                    target_server_version_num,
                                ))
                    except psycopg.OperationalError as exc:
                        for spec in tgt_specs:
                            results.append(_conn_error_result(spec, dbname, exc, side="target"))

    # Requêtes non sélectionnées → skipped (désactivées ou filtrées)
    for spec in all_specs:
        if spec.id not in selected_ids:
            results.append(QueryResult(
                id=spec.id, title=spec.title, scope=spec.scope, description=spec.description,
                target="instance" if spec.scope == "instance" else "(toutes bases)",
                sql=spec.sql or "",
                status="skipped",
                requires_superuser=spec.requires_superuser,
                skip_reason=spec.skip_reason_if_disabled or "désactivée ou filtrée",
                applies_to=spec.applies_to,
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
        source=ConnectionInfo(
            host=host, port=port, user=user,
            server_version=server_version,
            databases_targeted=dbnames,
        ),
        target=ConnectionInfo(
            host=target_host, port=target_port, user=target_user,
            server_version=target_server_version,
            databases_targeted=target_databases_targeted,
        ) if target_defined else None,
        selection=SelectionInfo(tags=tags, only=only, exclude=exclude, dry_run=dry_run),
        summary=summary,
        same_server=same_server,
        target_error=target_error,
        migration_method=migration_method,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    ts = started_at.strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"audit_{manifest_path.stem}_{ts}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            {"metadata": asdict(metadata), "results": [asdict(r) for r in results]},
            f,
            ensure_ascii=False,
            indent=2,
        )

    return output_file
