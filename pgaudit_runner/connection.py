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
) -> Optional[str]:
    """
    Tente une connexion sans mot de passe explicite (libpq gère PGPASSWORD et ~/.pgpass).
    Si l'authentification échoue, demande le mot de passe interactivement.
    Retourne le mot de passe saisi, ou None si libpq le gère lui-même.
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
            return getpass.getpass(f"Mot de passe PostgreSQL ({user}@{host}:{port}) : ")
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
