from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import QuerySpec


class ConfigError(Exception):
    pass


def load_manifest(
    manifest_path: Path,
    queries_dir: Path,
) -> tuple[dict[str, Any], list[QuerySpec]]:
    """Charge et valide le manifeste YAML. Retourne (config_dict, liste de QuerySpec)."""
    with open(manifest_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    meta = data.get("meta", {})
    defaults = data.get("defaults", {})
    raw_queries = data.get("queries", [])

    default_timeout: int = defaults.get("statement_timeout_ms", 30000)
    read_only: bool = defaults.get("read_only", True)

    seen_ids: set[str] = set()
    specs: list[QuerySpec] = []

    for i, q in enumerate(raw_queries):
        for required_field in ("id", "title", "file", "scope"):
            if required_field not in q:
                raise ConfigError(
                    f"Requête #{i} : champ obligatoire manquant : '{required_field}'"
                )

        qid: str = q["id"]

        if qid in seen_ids:
            raise ConfigError(f"id dupliqué : '{qid}'")
        seen_ids.add(qid)

        if q["scope"] not in ("instance", "database"):
            raise ConfigError(
                f"'{qid}' : scope invalide '{q['scope']}' (attendu : instance | database)"
            )

        side = q.get("side", "source")
        if side not in ("source", "target", "both"):
            raise ConfigError(
                f"'{qid}' : side invalide '{side}' (attendu : source | target | both)"
            )

        min_server_version = q.get("min_server_version")
        if min_server_version is not None and not isinstance(min_server_version, int):
            raise ConfigError(
                f"'{qid}' : min_server_version invalide '{min_server_version}' "
                "(attendu : entier au format server_version_num, ex. 150000 pour PG 15.0)"
            )

        max_server_version = q.get("max_server_version")
        if max_server_version is not None and not isinstance(max_server_version, int):
            raise ConfigError(
                f"'{qid}' : max_server_version invalide '{max_server_version}' "
                "(attendu : entier au format server_version_num, ex. 149999 pour PG < 15.0)"
            )

        sql_path = queries_dir / q["file"]
        if not sql_path.exists():
            raise ConfigError(f"'{qid}' : fichier SQL introuvable : {sql_path}")

        sql = sql_path.read_text(encoding="utf-8").strip()

        iterate_over = q.get("iterate_over")
        iterate_over_sql: Any = None
        if iterate_over is not None:
            discovery_path = queries_dir / iterate_over
            if not discovery_path.exists():
                raise ConfigError(
                    f"'{qid}' : requête de découverte introuvable (iterate_over) : {discovery_path}"
                )
            iterate_over_sql = discovery_path.read_text(encoding="utf-8").strip()

        sample_target_rows = q.get("sample_target_rows")
        if sample_target_rows is not None and (
            not isinstance(sample_target_rows, int) or sample_target_rows <= 0
        ):
            raise ConfigError(
                f"'{qid}' : sample_target_rows invalide '{sample_target_rows}' "
                "(attendu : entier positif, ou absent)"
            )

        specs.append(
            QuerySpec(
                id=qid,
                title=q["title"],
                file=q["file"],
                scope=q["scope"],
                description=(q.get("description") or "").strip() or None,
                enabled=q.get("enabled", True),
                tags=q.get("tags", []),
                requires_superuser=q.get("requires_superuser", False),
                skip_reason_if_disabled=q.get("skip_reason_if_disabled"),
                statement_timeout_ms=q.get("statement_timeout_ms", default_timeout),
                expect_rows=q.get("expect_rows"),
                severity_if_unexpected=q.get("severity_if_unexpected") or "vigilance",
                side=side,
                applies_to=q.get("applies_to", []),
                min_server_version=min_server_version,
                max_server_version=max_server_version,
                sql=sql,
                iterate_over=iterate_over,
                iterate_over_sql=iterate_over_sql,
                sample_target_rows=sample_target_rows,
            )
        )

    return {"meta": meta, "defaults": defaults, "read_only": read_only}, specs
