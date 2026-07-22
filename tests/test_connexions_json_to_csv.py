from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.connexions_json_to_csv import convert


def _write_json(tmp_path: Path, roles: dict) -> Path:
    path = tmp_path / "connexions.json"
    path.write_text(json.dumps({"metadata": {}, "roles": roles}), encoding="utf-8")
    return path


def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_convert_writes_one_row_per_role_in_connexions_csv(tmp_path: Path):
    json_path = _write_json(tmp_path, {
        "alice": {
            "connection_count": 5,
            "databases": {"mydb": 4, "postgres": 1},
            "source_hosts": {"10.0.0.5": 5},
            "applications": {"psql": 5},
            "first_seen": "2026-07-01 08:00:00.000 UTC",
            "last_seen": "2026-07-23 09:00:00.000 UTC",
        },
    })

    connexions_csv, _detail_csv = convert(json_path, tmp_path / "out")

    rows = _read_csv(connexions_csv)
    assert len(rows) == 1
    assert rows[0]["role"] == "alice"
    assert rows[0]["connection_count"] == "5"
    assert rows[0]["nb_databases"] == "2"
    assert rows[0]["database_principale"] == "mydb"
    assert rows[0]["host_principal"] == "10.0.0.5"
    assert rows[0]["first_seen"] == "2026-07-01 08:00:00.000 UTC"


def test_convert_writes_long_format_detail_csv(tmp_path: Path):
    json_path = _write_json(tmp_path, {
        "bob": {
            "connection_count": 2,
            "databases": {"mydb": 2},
            "source_hosts": {"10.0.0.6": 1, "10.0.0.7": 1},
            "applications": {},
            "first_seen": None,
            "last_seen": None,
        },
    })

    _connexions_csv, detail_csv = convert(json_path, tmp_path / "out")

    rows = _read_csv(detail_csv)
    dimensions = {(r["dimension"], r["valeur"], r["nb"]) for r in rows}
    assert ("database", "mydb", "2") in dimensions
    assert ("host", "10.0.0.6", "1") in dimensions
    assert ("host", "10.0.0.7", "1") in dimensions


def test_convert_no_top_value_when_no_databases_or_hosts(tmp_path: Path):
    json_path = _write_json(tmp_path, {
        "svc": {
            "connection_count": 1,
            "databases": {},
            "source_hosts": {},
            "applications": {},
            "first_seen": None,
            "last_seen": None,
        },
    })

    connexions_csv, _ = convert(json_path, tmp_path / "out")

    rows = _read_csv(connexions_csv)
    assert rows[0]["database_principale"] == ""
    assert rows[0]["host_principal"] == ""


def test_convert_empty_roles_yields_header_only(tmp_path: Path):
    json_path = _write_json(tmp_path, {})

    connexions_csv, detail_csv = convert(json_path, tmp_path / "out")

    assert _read_csv(connexions_csv) == []
    assert _read_csv(detail_csv) == []
