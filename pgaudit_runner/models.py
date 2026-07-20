from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class QuerySpec:
    id: str
    title: str
    file: str
    scope: str  # "instance" | "database"
    enabled: bool = True
    tags: list[str] = field(default_factory=list)
    requires_superuser: bool = False
    skip_reason_if_disabled: Optional[str] = None
    statement_timeout_ms: Optional[int] = None
    expect_rows: Optional[int] = None
    severity_if_unexpected: str = "vigilance"
    side: str = "source"  # "source" | "target" | "both"
    applies_to: list[str] = field(default_factory=list)  # "pg_upgrade" | "dump_restore" ; vide = les deux
    min_server_version: Optional[int] = None  # format server_version_num (ex. 150000 = PG 15.0)
    max_server_version: Optional[int] = None  # format server_version_num (ex. 149999 = PG < 15.0)
    sql: Optional[str] = None  # chargé depuis le fichier .sql


@dataclass
class ErrorDetail:
    message: str
    full_traceback: str
    sqlstate: Optional[str] = None


@dataclass
class QueryResult:
    id: str
    title: str
    scope: str
    target: str  # "instance" ou nom de la base
    sql: str
    status: str  # "success" | "skipped" | "error"
    started_at: Optional[str] = None  # ISO 8601
    duration_ms: Optional[int] = None
    requires_superuser: bool = False
    columns: Optional[list[str]] = None
    rows: Optional[list[dict[str, Any]]] = None
    row_count: Optional[int] = None
    error: Optional[ErrorDetail] = None
    skip_reason: Optional[str] = None
    expect_rows: Optional[int] = None
    severity_if_unexpected: str = "vigilance"
    side: str = "source"
    applies_to: list[str] = field(default_factory=list)


@dataclass
class ConnectionInfo:
    host: str
    port: int
    user: str
    server_version: Optional[str] = None
    databases_targeted: list[str] = field(default_factory=list)


@dataclass
class SelectionInfo:
    tags: list[str] = field(default_factory=list)
    only: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    dry_run: bool = False


@dataclass
class RunSummary:
    total: int = 0
    success: int = 0
    skipped: int = 0
    error: int = 0


@dataclass
class RunMetadata:
    tool_version: str
    manifest_name: str
    started_at: str
    finished_at: Optional[str]
    source: ConnectionInfo
    selection: SelectionInfo
    summary: RunSummary
    target: Optional[ConnectionInfo] = None
    same_server: Optional[bool] = None  # dérivé de la topologie ; None = pas de cible
    target_error: Optional[str] = None  # motif si la connexion cible a échoué
    migration_method: Optional[str] = None  # override CLI facultatif : "pg_upgrade" | "dump_restore"


def to_json_dict(metadata: RunMetadata, results: list[QueryResult]) -> dict:
    return {
        "metadata": asdict(metadata),
        "results": [asdict(r) for r in results],
    }
