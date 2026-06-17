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
    connection: ConnectionInfo
    selection: SelectionInfo
    summary: RunSummary


def to_json_dict(metadata: RunMetadata, results: list[QueryResult]) -> dict:
    return {
        "metadata": asdict(metadata),
        "results": [asdict(r) for r in results],
    }
