from __future__ import annotations

import csv
from pathlib import Path

from qgisaudit_runner.inventory import run_inventory


def _qgs(nom_couche_ds: list[tuple[str, str, str]]) -> str:
    """Construit un .qgs minimal à partir de (nom_couche, provider, datasource)."""
    layers_xml = "\n".join(
        f"""<maplayer>
      <datasource>{ds}</datasource>
      <layername>{nom}</layername>
      <provider>{provider}</provider>
    </maplayer>"""
        for nom, provider, ds in nom_couche_ds
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<qgis version="3.28">
  <projectlayers>
    {layers_xml}
  </projectlayers>
</qgis>
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_run_inventory_classifies_all_four_profiles(tmp_path: Path):
    racine = tmp_path / "sig"

    _write(racine / "nommee.qgs", _qgs([
        ("c1", "postgres", "service='sig_prod' table=\"public\".\"t1\" (geom)"),
        ("c2", "postgres", "service='sig_prod' table=\"public\".\"t2\" (geom)"),
    ]))
    _write(racine / "embarquee.qgs", _qgs([
        ("c1", "postgres", "host=10.0.0.1 dbname='db1' table=\"public\".\"t1\" (geom)"),
    ]))
    _write(racine / "mixte.qgs", _qgs([
        ("c1", "postgres", "service='sig_prod' table=\"public\".\"t1\" (geom)"),
        ("c2", "postgres", "host=10.0.0.1 dbname='db1' table=\"public\".\"t2\" (geom)"),
    ]))
    _write(racine / "sans_pg.qgs", _qgs([
        ("c1", "ogr", "/data/x.shp"),
    ]))

    sortie = tmp_path / "out"
    run_inventory([racine], [".qgs", ".qgz"], sortie)

    projets = {r["nom_projet"]: r for r in _read_csv(sortie / "projets.csv")}
    assert projets["nommee"]["profil"] == "nommee"
    assert projets["embarquee"]["profil"] == "embarquee"
    assert projets["mixte"]["profil"] == "mixte"
    assert projets["sans_pg"]["profil"] == "sans_pg"
    assert projets["sans_pg"]["nb_couches_pg"] == "0"
    assert projets["nommee"]["nb_couches_pg"] == "2"


def test_run_inventory_detects_password_and_authcfg_flags(tmp_path: Path):
    racine = tmp_path / "sig"
    _write(racine / "p.qgs", _qgs([
        ("c1", "postgres", "host=10.0.0.1 dbname='db1' user='u' password='secret' table=\"public\".\"t1\" (geom)"),
    ]))

    sortie = tmp_path / "out"
    run_inventory([racine], [".qgs"], sortie)

    projets = _read_csv(sortie / "projets.csv")
    assert projets[0]["mdp_en_clair"] == "True"
    assert projets[0]["authcfg_utilise"] == "False"

    couches = _read_csv(sortie / "couches_pg.csv")
    assert couches[0]["mdp_present"] == "True"
    assert couches[0]["mode_connexion"] == "embarquee"


def test_run_inventory_couches_pg_extracts_schema_table_geom_srid(tmp_path: Path):
    racine = tmp_path / "sig"
    _write(racine / "p.qgs", _qgs([
        ("Point de comptage", "postgres",
         "host=10.0.0.1 dbname='db1' srid=2154 authcfg=abc123 table=\"public\".\"Point de comptage\" (geom)"),
    ]))

    sortie = tmp_path / "out"
    run_inventory([racine], [".qgs"], sortie)

    couches = _read_csv(sortie / "couches_pg.csv")
    row = couches[0]
    assert row["schema"] == "public"
    assert row["table"] == "Point de comptage"
    assert row["colonne_geom"] == "geom"
    assert row["srid"] == "2154"
    assert row["authcfg"] == "abc123"
    assert row["mode_connexion"] == "authcfg"


def test_run_inventory_aggregates_distinct_services_hosts_bases(tmp_path: Path):
    racine = tmp_path / "sig"
    _write(racine / "p.qgs", _qgs([
        ("c1", "postgres", "service='svc_a' table=\"public\".\"t1\" (geom)"),
        ("c2", "postgres", "service='svc_b' table=\"public\".\"t2\" (geom)"),
        ("c3", "postgres", "service='svc_a' table=\"public\".\"t3\" (geom)"),
    ]))

    sortie = tmp_path / "out"
    run_inventory([racine], [".qgs"], sortie)

    projets = _read_csv(sortie / "projets.csv")
    assert projets[0]["services_distincts"] == "svc_a; svc_b"


def test_run_inventory_continues_after_corrupted_file(tmp_path: Path):
    racine = tmp_path / "sig"
    _write(racine / "corrompu.qgs", "<qgis><projectlayers><maplayer>")  # XML non fermé
    _write(racine / "valide.qgs", _qgs([("c1", "ogr", "/data/x.shp")]))

    sortie = tmp_path / "out"
    projets_csv, _ = run_inventory([racine], [".qgs"], sortie)

    projets = _read_csv(projets_csv)
    assert len(projets) == 1
    assert projets[0]["nom_projet"] == "valide"


def test_run_inventory_recurses_into_subdirectories(tmp_path: Path):
    racine = tmp_path / "sig"
    _write(racine / "sous_dossier" / "profond.qgs", _qgs([("c1", "ogr", "/data/x.shp")]))

    sortie = tmp_path / "out"
    run_inventory([racine], [".qgs"], sortie)

    projets = _read_csv(sortie / "projets.csv")
    assert len(projets) == 1
    assert projets[0]["nom_projet"] == "profond"


def test_run_inventory_ignores_non_matching_extensions(tmp_path: Path):
    racine = tmp_path / "sig"
    _write(racine / "ignore.txt", "pas un projet QGIS")
    _write(racine / "vrai.qgs", _qgs([("c1", "ogr", "/data/x.shp")]))

    sortie = tmp_path / "out"
    run_inventory([racine], [".qgs"], sortie)

    projets = _read_csv(sortie / "projets.csv")
    assert len(projets) == 1


def test_run_inventory_missing_root_does_not_crash(tmp_path: Path):
    racine_absente = tmp_path / "inexistant"
    sortie = tmp_path / "out"

    projets_csv, couches_csv = run_inventory([racine_absente], [".qgs"], sortie)

    assert _read_csv(projets_csv) == []
