from __future__ import annotations

import getpass
import os
from contextlib import contextmanager
from typing import Generator, Optional

import psycopg


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
) -> Generator[psycopg.Connection, None, None]:
    params: dict = dict(host=host, port=port, user=user, dbname=dbname, connect_timeout=10)
    if service:
        params["service"] = service
    if password:
        params["password"] = password

    conn = psycopg.connect(**params, autocommit=True)
    try:
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
