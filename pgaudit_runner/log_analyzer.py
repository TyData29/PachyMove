from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Préfixe par défaut de PostgreSQL : '%m [%p] ' — %m = timestamp avec
# millisecondes + fuseau, %p = PID. À ajuster si le vrai log_line_prefix
# diverge (cf. note "lines_unparsed" en sortie : signal immédiat en cas
# d'écart plutôt qu'un échec silencieux).
_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} \S+)\s+"
    r"\[(?P<pid>\d+)\]\s+(?P<level>\w+):\s+(?P<message>.*)$"
)

_RECEIVED_RE = re.compile(r"^connection received:\s+host=(?P<host>\S+?)(?:\s+port=\d+)?$")
_RECEIVED_FR_RE = re.compile(r"^connexion reçue\s*:\s*hôte=(?P<host>\S+?)(?:\s+port=\d+)?$")

_AUTHORIZED_RE = re.compile(
    r"^connection authorized:\s+user=(?P<user>\S+)\s+database=(?P<database>\S+)"
    r"(?:\s+application_name=(?P<application>.*))?$"
)
# lc_messages=fr_FR (courant sur les instances Windows en mission) : mêmes
# informations, texte et ordre différents — "base de données" n'a pas de
# clé=valeur, la base suit directement.
_AUTHORIZED_FR_RE = re.compile(
    r"^connexion autorisée\s*:\s*utilisateur=(?P<user>\S+)\s+base de données\s+(?P<database>\S+)"
    r"(?:\s+application_name=(?P<application>.*))?$"
)


@dataclass
class RoleStats:
    connection_count: int = 0
    databases: dict[str, int] = field(default_factory=dict)
    source_hosts: dict[str, int] = field(default_factory=dict)
    applications: dict[str, int] = field(default_factory=dict)
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None


def _bump(counter: dict[str, int], key: Optional[str]) -> None:
    if not key:
        return
    counter[key] = counter.get(key, 0) + 1


def analyze_directory(
    input_dir: Path, pattern: str = "*", unparsed_sample_size: int = 20
) -> dict:
    """Parcourt tous les fichiers de `input_dir` (non récursif) correspondant à
    `pattern`, et construit une synthèse de connexions par rôle.

    Limite assumée (log_connections seul, sans log_disconnections ni
    log_statement/pgaudit) : ni durée de session, ni détail des actions
    (lecture/écriture, tables) — cf. metadata.note en sortie.
    """
    files = sorted(f for f in input_dir.glob(pattern) if f.is_file())

    roles: dict[str, RoleStats] = {}
    pending_host_by_pid: dict[str, str] = {}

    lines_total = 0
    lines_matched = 0
    lines_prefix_unrecognized = 0
    connections_total = 0
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    unparsed_sample: list[dict] = []

    for file in files:
        pending_host_by_pid.clear()
        raw = file.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            # Logs PostgreSQL sous Windows (mission CCPCAM) : encodage cp1252,
            # pas UTF-8 — décodés en UTF-8 ils ne produisent que des '�'
            # et aucune ligne ne matche plus jamais. errors="replace" en
            # dernier recours plutôt qu'un plantage sur un octet imprévu.
            text = raw.decode("cp1252", errors="replace")
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line
            if not line.strip():
                continue
            lines_total += 1

            m = _LINE_RE.match(line)
            if not m:
                lines_prefix_unrecognized += 1
                if len(unparsed_sample) < unparsed_sample_size:
                    unparsed_sample.append(
                        {"file": file.name, "line_number": line_number, "text": line[:300]}
                    )
                continue

            ts = m.group("ts")
            pid = m.group("pid")
            message = m.group("message")

            received = _RECEIVED_RE.match(message) or _RECEIVED_FR_RE.match(message)
            if received:
                pending_host_by_pid[pid] = received.group("host")
                lines_matched += 1
                continue

            authorized = _AUTHORIZED_RE.match(message) or _AUTHORIZED_FR_RE.match(message)
            if authorized:
                lines_matched += 1
                connections_total += 1
                user = authorized.group("user")
                database = authorized.group("database")
                application = authorized.group("application")
                host = pending_host_by_pid.pop(pid, None)

                if first_seen is None or ts < first_seen:
                    first_seen = ts
                if last_seen is None or ts > last_seen:
                    last_seen = ts

                stats = roles.setdefault(user, RoleStats())
                stats.connection_count += 1
                _bump(stats.databases, database)
                _bump(stats.source_hosts, host)
                _bump(stats.applications, application)
                if stats.first_seen is None or ts < stats.first_seen:
                    stats.first_seen = ts
                if stats.last_seen is None or ts > stats.last_seen:
                    stats.last_seen = ts
                continue

            # Ligne au bon format (préfixe reconnu) mais message non reconnu
            # (checkpoint, autovacuum, etc. — tout événement hors connexion) :
            # ignorée sans compter comme "non parsée", c'est le cas normal et
            # majoritaire d'un vrai fichier de log, pas une anomalie.

    return {
        "metadata": {
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "source_dir": str(input_dir),
            "files_processed": [f.name for f in files],
            "lines_total": lines_total,
            "lines_matched": lines_matched,
            "lines_other_events": lines_total - lines_matched - lines_prefix_unrecognized,
            "lines_unparsed": lines_prefix_unrecognized,
            "connections_total": connections_total,
            "period": {"first_seen": first_seen, "last_seen": last_seen},
            "note": (
                "Construit à partir de log_connections uniquement : ni durée de "
                "session (log_disconnections absent), ni détail des actions — "
                "lecture/écriture, schémas/tables (log_statement/pgaudit absent)."
            ),
        },
        "roles": {name: asdict(stats) for name, stats in sorted(roles.items())},
        "unparsed_sample": unparsed_sample,
    }
