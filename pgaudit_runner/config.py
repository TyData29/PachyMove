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

        sql_path = queries_dir / q["file"]
        if not sql_path.exists():
            raise ConfigError(f"'{qid}' : fichier SQL introuvable : {sql_path}")

        sql = sql_path.read_text(encoding="utf-8").strip()

        specs.append(
            QuerySpec(
                id=qid,
                title=q["title"],
                file=q["file"],
                scope=q["scope"],
                enabled=q.get("enabled", True),
                tags=q.get("tags", []),
                requires_superuser=q.get("requires_superuser", False),
                skip_reason_if_disabled=q.get("skip_reason_if_disabled"),
                statement_timeout_ms=q.get("statement_timeout_ms", default_timeout),
                sql=sql,
            )
        )

    return {"meta": meta, "defaults": defaults, "read_only": read_only}, specs
