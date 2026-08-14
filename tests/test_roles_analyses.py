from __future__ import annotations

import csv
from pathlib import Path

import duckdb
import pytest

from roles_analyses.main import (
    _find_csv,
    charger_tables,
    connexions_sans_droits_directs,
    droits_sans_connexion,
)


def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def _make_droits_dir(tmp_path: Path) -> Path:
    droits_dir = tmp_path / "droits"
    droits_dir.mkdir()
    _write_csv(
        droits_dir / "role_membership_tree__instance.csv",
        ["role", "groupe", "niveau"],
        [["grp_vide", "grp_racine", 1]],
    )
    _write_csv(
        droits_dir / "relation_privileges__CCPI.csv",
        ["schema", "objet", "type_objet", "role", "privilege", "source", "accorde_par"],
        [
            ["public", "table1", "r", "alice", "SELECT", "direct", "postgres"],
            ["public", "table1", "r", "-", "SELECT", "direct", "postgres"],
            ["public", "table1", "r", "bob", "SELECT", "groupe:lecteurs", "postgres"],
        ],
    )
    _write_csv(
        droits_dir / "schema_privileges__CCPI.csv",
        ["schema", "role", "privilege", "source", "accorde_par"],
        [["public", "carol", "USAGE", "direct", "postgres"]],
    )
    _write_csv(
        droits_dir / "function_privileges__CCPI.csv",
        ["schema", "objet", "role", "privilege", "source", "accorde_par"],
        [],
    )
    _write_csv(
        droits_dir / "rls_policies_presence__CCPI.csv",
        ["schema", "objet", "rls_active", "rls_forcee", "nb_politiques", "politiques"],
        [],
    )
    return droits_dir


def _make_connexions_dir(tmp_path: Path, roles: list[str]) -> Path:
    connexions_dir = tmp_path / "connexions"
    connexions_dir.mkdir()
    _write_csv(
        connexions_dir / "connexions.csv",
        [
            "role", "connection_count", "nb_databases", "nb_hosts", "nb_applications",
            "database_principale", "host_principal", "first_seen", "last_seen",
        ],
        [[role, 3, 1, 1, 1, "mydb", "10.0.0.1", "2026-07-01", "2026-07-20"] for role in roles],
    )
    _write_csv(
        connexions_dir / "connexions_detail.csv",
        ["role", "dimension", "valeur", "nb"],
        [[role, "database", "mydb", 3] for role in roles],
    )
    return connexions_dir


def _connect(tmp_path: Path, droits_dir: Path, connexions_dir: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(tmp_path / "analyse.duckdb"))
    charger_tables(con, droits_dir, connexions_dir)
    return con


def test_droits_sans_connexion_excludes_public_and_connected_roles(tmp_path: Path):
    droits_dir = _make_droits_dir(tmp_path)
    connexions_dir = _make_connexions_dir(tmp_path, roles=["alice"])
    con = _connect(tmp_path, droits_dir, connexions_dir)

    roles = [r[0] for r in droits_sans_connexion(con).fetchall()]

    assert "alice" not in roles
    assert "-" not in roles
    assert "bob" in roles
    assert "carol" in roles
    assert "grp_vide" in roles


def test_connexions_sans_droits_directs_excludes_direct_grantees(tmp_path: Path):
    droits_dir = _make_droits_dir(tmp_path)
    connexions_dir = _make_connexions_dir(tmp_path, roles=["alice", "bob", "carol", "dave"])
    con = _connect(tmp_path, droits_dir, connexions_dir)

    roles = [r[0] for r in connexions_sans_droits_directs(con).fetchall()]

    assert "alice" not in roles
    assert "carol" not in roles
    assert "bob" in roles
    assert "dave" in roles


def test_find_csv_raises_when_no_match(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="Aucun CSV"):
        _find_csv(tmp_path, "relation_privileges")


def test_find_csv_raises_when_ambiguous(tmp_path: Path):
    (tmp_path / "relation_privileges__CCPI.csv").touch()
    (tmp_path / "relation_privileges__CCPCAM.csv").touch()

    with pytest.raises(FileNotFoundError, match="Plusieurs CSV"):
        _find_csv(tmp_path, "relation_privileges")
