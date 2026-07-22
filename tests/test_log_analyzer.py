from __future__ import annotations

from pathlib import Path

from pgaudit_runner.log_analyzer import analyze_directory


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_analyze_directory_correlates_received_and_authorized_by_pid(tmp_path: Path):
    _write(tmp_path, "postgresql.log", """\
2026-07-23 08:00:00.100 UTC [1001] LOG:  connection received: host=10.0.0.5 port=54321
2026-07-23 08:00:00.150 UTC [1001] LOG:  connection authorized: user=alice database=mydb application_name=psql
""")

    result = analyze_directory(tmp_path)

    assert result["metadata"]["connections_total"] == 1
    alice = result["roles"]["alice"]
    assert alice["connection_count"] == 1
    assert alice["databases"] == {"mydb": 1}
    assert alice["source_hosts"] == {"10.0.0.5": 1}
    assert alice["applications"] == {"psql": 1}


def test_analyze_directory_handles_local_socket_host(tmp_path: Path):
    _write(tmp_path, "postgresql.log", """\
2026-07-23 08:05:00.200 UTC [1002] LOG:  connection received: host=[local]
2026-07-23 08:05:00.250 UTC [1002] LOG:  connection authorized: user=bob database=postgres
""")

    result = analyze_directory(tmp_path)

    assert result["roles"]["bob"]["source_hosts"] == {"[local]": 1}


def test_analyze_directory_authorized_without_prior_received_has_no_host(tmp_path: Path):
    # Rotation de log ou ligne "received" tronquée : l'hôte reste inconnu,
    # mais la connexion est quand même comptabilisée.
    _write(tmp_path, "postgresql.log", """\
2026-07-23 08:10:00.300 UTC [1003] LOG:  connection authorized: user=alice database=otherdb
""")

    result = analyze_directory(tmp_path)

    assert result["metadata"]["connections_total"] == 1
    assert result["roles"]["alice"]["source_hosts"] == {}


def test_analyze_directory_application_name_with_spaces_captured_whole(tmp_path: Path):
    _write(tmp_path, "postgresql.log", """\
2026-07-23 08:10:00.300 UTC [1003] LOG:  connection authorized: user=alice database=db application_name=DBeaver 24.1.1
""")

    result = analyze_directory(tmp_path)

    assert result["roles"]["alice"]["applications"] == {"DBeaver 24.1.1": 1}


def test_analyze_directory_counts_unparsed_lines_without_crashing(tmp_path: Path):
    _write(tmp_path, "postgresql.log", """\
2026-07-23 08:00:00.100 UTC [1001] LOG:  connection received: host=10.0.0.5 port=54321
this line matches nothing at all
2026-07-23 08:00:00.150 UTC [1001] LOG:  connection authorized: user=alice database=mydb
another garbage line
""")

    result = analyze_directory(tmp_path)

    meta = result["metadata"]
    assert meta["lines_unparsed"] == 2
    assert len(result["unparsed_sample"]) == 2
    assert meta["connections_total"] == 1


def test_analyze_directory_aggregates_multiple_connections_same_role(tmp_path: Path):
    _write(tmp_path, "postgresql.log", """\
2026-07-23 08:00:00.100 UTC [1001] LOG:  connection received: host=10.0.0.5 port=1
2026-07-23 08:00:00.150 UTC [1001] LOG:  connection authorized: user=alice database=mydb application_name=psql
2026-07-23 09:00:00.100 UTC [1002] LOG:  connection received: host=10.0.0.6 port=2
2026-07-23 09:00:00.150 UTC [1002] LOG:  connection authorized: user=alice database=mydb application_name=psql
""")

    result = analyze_directory(tmp_path)

    alice = result["roles"]["alice"]
    assert alice["connection_count"] == 2
    assert alice["source_hosts"] == {"10.0.0.5": 1, "10.0.0.6": 1}
    assert alice["first_seen"] == "2026-07-23 08:00:00.150 UTC"
    assert alice["last_seen"] == "2026-07-23 09:00:00.150 UTC"


def test_analyze_directory_processes_multiple_files(tmp_path: Path):
    _write(tmp_path, "postgresql-1.log", """\
2026-07-23 08:00:00.100 UTC [1001] LOG:  connection received: host=10.0.0.5 port=1
2026-07-23 08:00:00.150 UTC [1001] LOG:  connection authorized: user=alice database=mydb
""")
    _write(tmp_path, "postgresql-2.log", """\
2026-07-23 09:00:00.100 UTC [1002] LOG:  connection received: host=10.0.0.6 port=2
2026-07-23 09:00:00.150 UTC [1002] LOG:  connection authorized: user=bob database=mydb
""")

    result = analyze_directory(tmp_path)

    assert set(result["metadata"]["files_processed"]) == {"postgresql-1.log", "postgresql-2.log"}
    assert result["metadata"]["connections_total"] == 2
    assert "alice" in result["roles"]
    assert "bob" in result["roles"]


def test_analyze_directory_pattern_filters_files(tmp_path: Path):
    _write(tmp_path, "keep.log", """\
2026-07-23 08:00:00.100 UTC [1001] LOG:  connection authorized: user=alice database=mydb
""")
    _write(tmp_path, "ignore.txt", """\
2026-07-23 08:00:00.100 UTC [1002] LOG:  connection authorized: user=bob database=mydb
""")

    result = analyze_directory(tmp_path, pattern="*.log")

    assert result["metadata"]["files_processed"] == ["keep.log"]
    assert "alice" in result["roles"]
    assert "bob" not in result["roles"]


def test_analyze_directory_does_not_flag_routine_events_as_unparsed(tmp_path: Path):
    # Un checkpoint (ou autovacuum, etc.) a un préfixe PostgreSQL valide mais un
    # message hors connexion : ne doit pas gonfler lines_unparsed (sur un vrai
    # fichier, ces lignes sont majoritaires — un faux "non reconnu" alarmerait
    # à tort). Distinct de lines_other_events, qui les compte séparément.
    _write(tmp_path, "postgresql.log", """\
2026-07-23 08:00:00.100 UTC [1001] LOG:  connection authorized: user=alice database=mydb
2026-07-23 09:00:00.000 UTC [1004] LOG:  checkpoint starting: time
""")

    result = analyze_directory(tmp_path)

    assert result["metadata"]["lines_unparsed"] == 0
    assert result["metadata"]["lines_other_events"] == 1
    assert result["unparsed_sample"] == []


def test_analyze_directory_empty_directory_yields_zero_counts(tmp_path: Path):
    result = analyze_directory(tmp_path)

    assert result["metadata"]["connections_total"] == 0
    assert result["metadata"]["lines_total"] == 0
    assert result["roles"] == {}
    assert result["metadata"]["period"] == {"first_seen": None, "last_seen": None}
