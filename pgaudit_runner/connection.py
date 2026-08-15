from __future__ import annotations

import getpass
import os
from contextlib import contextmanager
from typing import Generator, Optional

import psycopg
from psycopg import sql as pgsql


def resolve_password(
    host: str,
    port: int,
    user: str,
    dbname: str,
    service: Optional[str] = None,
    label: Optional[str] = None,
) -> Optional[str]:
    """
    Tente une connexion sans mot de passe explicite (libpq gère PGPASSWORD et ~/.pgpass).
    Si l'authentification échoue, demande le mot de passe interactivement.
    Retourne le mot de passe saisi, ou None si libpq le gère lui-même.

    `label` (ex. "source"/"cible") distingue les deux prompts quand une cible est
    définie ; laissé à None, le prompt est identique à avant (mono-serveur).
    """
    if os.environ.get("PGPASSWORD"):
        return None

    params: dict = dict(host=host, port=port, user=user, dbname=dbname, connect_timeout=5)
    if service:
        params["service"] = service

    try:
        psycopg.connect(**params, autocommit=True).close()
        return None
    except psycopg.OperationalError as e:
        msg = str(e).lower()
        if "password" in msg or "authentication" in msg:
            prefix = f"Mot de passe {label} " if label else "Mot de passe "
            return getpass.getpass(f"{prefix}PostgreSQL ({user}@{host}:{port}) : ")
        raise


@contextmanager
def open_connection(
    host: str,
    port: int,
    user: str,
    dbname: str,
    service: Optional[str] = None,
    password: Optional[str] = None,
    work_mem: Optional[str] = None,
) -> Generator[psycopg.Connection, None, None]:
    # Keepalives : un scan long (ex. iterate_over sur beaucoup de tables) est
    # peu bavard sur le fil pendant le calcul côté serveur — un VPN/pare-feu
    # d'entreprise peut couper silencieusement une connexion TCP dans cet état
    # même si elle est toujours active côté application. Valeurs prudentes
    # (probe dès 30s d'inactivité réseau) plutôt que le défaut OS (souvent 2h).
    params: dict = dict(
        host=host, port=port, user=user, dbname=dbname, connect_timeout=10,
        keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3,
    )
    if service:
        params["service"] = service
    if password:
        params["password"] = password

    conn = psycopg.connect(**params, autocommit=True)
    try:
        if work_mem:
            conn.execute(pgsql.SQL("SET work_mem = {}").format(pgsql.Literal(work_mem)))
        yield conn
    finally:
        conn.close()


def get_server_version(conn: psycopg.Connection) -> str:
    row = conn.execute("SELECT version()").fetchone()
    return row[0] if row else "unknown"


def get_server_version_num(conn: psycopg.Connection) -> int:
    """Version numérique (format server_version_num, ex. 150003 pour PG 15.3) —
    utilisée pour décider si une requête nécessitant une version minimale
    (`min_server_version`) peut s'exécuter sur ce serveur."""
    row = conn.execute("SHOW server_version_num").fetchone()
    return int(row[0]) if row else 0
