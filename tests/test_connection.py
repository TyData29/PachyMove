from __future__ import annotations

from unittest.mock import MagicMock, patch

import psycopg
import pytest

from pgaudit_runner.connection import get_server_version_num, open_connection, resolve_password


@pytest.fixture(autouse=True)
def _no_pgpassword(monkeypatch):
    monkeypatch.delenv("PGPASSWORD", raising=False)


def _auth_failure():
    return psycopg.OperationalError("FATAL: password authentication failed for user")


def test_resolve_password_prompt_has_no_label_by_default():
    with patch("psycopg.connect", side_effect=_auth_failure()), \
         patch("getpass.getpass", return_value="secret") as mock_getpass:
        result = resolve_password("h", 5432, "u", "d")

    assert result == "secret"
    prompt = mock_getpass.call_args[0][0]
    assert prompt == "Mot de passe PostgreSQL (u@h:5432) : "


def test_resolve_password_prompt_uses_source_label():
    with patch("psycopg.connect", side_effect=_auth_failure()), \
         patch("getpass.getpass", return_value="secret") as mock_getpass:
        resolve_password("h", 5432, "u", "d", label="source")

    prompt = mock_getpass.call_args[0][0]
    assert prompt.startswith("Mot de passe source ")


def test_resolve_password_prompt_uses_cible_label():
    with patch("psycopg.connect", side_effect=_auth_failure()), \
         patch("getpass.getpass", return_value="secret") as mock_getpass:
        resolve_password("h", 5432, "u", "d", label="cible")

    prompt = mock_getpass.call_args[0][0]
    assert prompt.startswith("Mot de passe cible ")


def test_resolve_password_returns_none_on_successful_connection():
    with patch("psycopg.connect", return_value=MagicMock()) as mock_connect:
        result = resolve_password("h", 5432, "u", "d")

    assert result is None
    mock_connect.assert_called_once()


def test_get_server_version_num_parses_show_result():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = ("140011",)

    assert get_server_version_num(conn) == 140011
    conn.execute.assert_called_once_with("SHOW server_version_num")


def test_get_server_version_num_defaults_to_zero_without_row():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = None

    assert get_server_version_num(conn) == 0


def test_open_connection_passes_keepalive_params():
    with patch("psycopg.connect", return_value=MagicMock()) as mock_connect:
        with open_connection("h", 5432, "u", "d"):
            pass

    kwargs = mock_connect.call_args.kwargs
    assert kwargs["keepalives"] == 1
    assert kwargs["keepalives_idle"] == 30
    assert kwargs["keepalives_interval"] == 10
    assert kwargs["keepalives_count"] == 3


def test_open_connection_forces_utf8_client_encoding():
    # Nos requetes ont des commentaires accentues en francais : sur une base
    # SQL_ASCII (ou toute base non-UTF8), psycopg encoderait sinon le texte
    # envoye au serveur avec un codec restreint et planterait des le premier
    # commentaire accentue (constate en pratique sur un serveur PG18).
    mock_conn = MagicMock()
    mock_conn.info.parameter_status.return_value = "SQL_ASCII"
    with patch("psycopg.connect", return_value=mock_conn):
        with open_connection("h", 5432, "u", "d"):
            pass

    mock_conn.execute.assert_called_once_with("SET client_encoding TO 'UTF8'")


def test_open_connection_sets_work_mem_when_provided():
    mock_conn = MagicMock()
    with patch("psycopg.connect", return_value=mock_conn):
        with open_connection("h", 5432, "u", "d", work_mem="256MB"):
            pass

    executed_sql = mock_conn.execute.call_args[0][0]
    assert executed_sql.as_string(None) == "SET work_mem = '256MB'"


def test_open_connection_skips_work_mem_when_not_provided():
    mock_conn = MagicMock()
    with patch("psycopg.connect", return_value=mock_conn):
        with open_connection("h", 5432, "u", "d"):
            pass

    mock_conn.execute.assert_not_called()
