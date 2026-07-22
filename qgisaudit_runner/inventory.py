from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from .datasource import determine_mode_connexion
from .qgis_project import LayerInfo, ProjectParseError, parse_project

_LISTE_SEP = "; "

_PROJETS_COLUMNS = [
    "chemin", "nom_projet", "nb_couches_total", "nb_couches_pg", "nb_couches_fichier",
    "nb_couches_autres", "profil", "mdp_en_clair", "authcfg_utilise",
    "services_distincts", "hosts_distincts", "bases_distinctes",
]

_COUCHES_PG_COLUMNS = [
    "chemin_projet", "nom_couche", "mode_connexion", "service", "host", "port",
    "dbname", "user", "mdp_present", "authcfg", "schema", "table", "colonne_geom", "srid",
]


@dataclass
class ProjectResult:
    chemin: str
    nom_projet: str
    nb_couches_total: int = 0
    nb_couches_pg: int = 0
    nb_couches_fichier: int = 0
    nb_couches_autres: int = 0
    profil: str = "sans_pg"
    mdp_en_clair: bool = False
    authcfg_utilise: bool = False
    services_distincts: list[str] = field(default_factory=list)
    hosts_distincts: list[str] = field(default_factory=list)
    bases_distinctes: list[str] = field(default_factory=list)
    couches_pg: list[dict] = field(default_factory=list)


def _couche_pg_row(chemin_projet: str, layer: LayerInfo) -> dict:
    ds = layer.parsed
    assert ds is not None
    mode = determine_mode_connexion(ds)
    return {
        "chemin_projet": chemin_projet,
        "nom_couche": layer.nom_couche,
        "mode_connexion": mode,
        "service": ds.get("service") or "",
        "host": ds.get("host") or "",
        "port": ds.get("port") or "",
        "dbname": ds.get("dbname") or "",
        "user": ds.get("user") or "",
        "mdp_present": bool(ds.get("password")),
        "authcfg": ds.get("authcfg") or "",
        "schema": ds.schema or "",
        "table": ds.table or "",
        "colonne_geom": ds.geom_column or "",
        "srid": ds.get("srid") or "",
    }


def build_project_result(path: Path, layers: list[LayerInfo]) -> ProjectResult:
    result = ProjectResult(chemin=str(path), nom_projet=path.stem)
    result.nb_couches_total = len(layers)

    pg_layers = [l for l in layers if l.categorie == "pg"]
    result.nb_couches_pg = len(pg_layers)
    result.nb_couches_fichier = sum(1 for l in layers if l.categorie == "fichier")
    result.nb_couches_autres = sum(1 for l in layers if l.categorie == "autres")

    services: set[str] = set()
    hosts: set[str] = set()
    bases: set[str] = set()
    modes: set[str] = set()

    for layer in pg_layers:
        row = _couche_pg_row(result.chemin, layer)
        result.couches_pg.append(row)
        modes.add(row["mode_connexion"])
        if row["service"]:
            services.add(row["service"])
        if row["host"]:
            hosts.add(row["host"])
        if row["dbname"]:
            bases.add(row["dbname"])
        if row["mdp_present"]:
            result.mdp_en_clair = True
        if row["authcfg"]:
            result.authcfg_utilise = True

    result.services_distincts = sorted(services)
    result.hosts_distincts = sorted(hosts)
    result.bases_distinctes = sorted(bases)

    # Spec §5.6 : classement à deux voies (service vs pas service), authcfg et
    # embarquee comptent tous deux comme "pas service" à ce niveau — le détail
    # par mode reste visible couche par couche dans couches_pg.csv.
    if not pg_layers:
        result.profil = "sans_pg"
    elif modes == {"service"}:
        result.profil = "nommee"
    elif "service" not in modes:
        result.profil = "embarquee"
    else:
        result.profil = "mixte"

    return result


def _iter_project_files(racines: Iterable[Path], extensions: Iterable[str]) -> Iterator[Path]:
    """Génère les fichiers correspondant aux `extensions` trouvés récursivement
    dans `racines`, un à la fois (streaming). L'ordre de parcours dépend du
    système de fichiers (pas de tri global, ce qui évite de matérialiser la
    liste complète des chemins avant de commencer le traitement)."""
    exts = {e.lower() for e in extensions}
    for racine in racines:
        if not racine.exists():
            print(f"[avertissement] racine introuvable, ignorée : {racine}", file=sys.stderr)
            continue
        for path in racine.rglob("*"):
            if path.is_file() and path.suffix.lower() in exts:
                yield path


def run_inventory(
    racines: list[Path], extensions: list[str], dossier_sortie: Path
) -> tuple[Path, Path]:
    """Parcourt `racines` récursivement, inventorie les projets QGIS trouvés, et
    écrit projets.csv/couches_pg.csv dans `dossier_sortie`. Ne plante jamais sur
    un fichier individuel (spec §7) : erreurs logguées sur stderr, traitement
    des autres fichiers poursuivi.

    Les deux CSV sont écrits en flux continu (streaming) : chaque projet est
    traité et écrit dès sa découverte, sans accumuler l'ensemble des chemins ou
    des résultats en mémoire."""
    dossier_sortie.mkdir(parents=True, exist_ok=True)
    projets_csv = dossier_sortie / "projets.csv"
    couches_csv = dossier_sortie / "couches_pg.csv"

    nb_fichiers = 0
    nb_analyses = 0

    with (
        open(projets_csv, "w", newline="", encoding="utf-8") as fp,
        open(couches_csv, "w", newline="", encoding="utf-8") as fc,
    ):
        pw = csv.DictWriter(fp, fieldnames=_PROJETS_COLUMNS)
        pw.writeheader()
        cw = csv.DictWriter(fc, fieldnames=_COUCHES_PG_COLUMNS)
        cw.writeheader()

        for path in _iter_project_files(racines, extensions):
            nb_fichiers += 1
            try:
                layers = parse_project(path)
            except ProjectParseError as e:
                print(f"[ignoré] {e}", file=sys.stderr)
                continue
            except Exception as e:  # défense large : un fichier ne doit jamais arrêter le scan
                print(f"[ignoré] erreur inattendue sur {path} : {e}", file=sys.stderr)
                continue
            r = build_project_result(path, layers)
            nb_analyses += 1
            pw.writerow({
                "chemin": r.chemin,
                "nom_projet": r.nom_projet,
                "nb_couches_total": r.nb_couches_total,
                "nb_couches_pg": r.nb_couches_pg,
                "nb_couches_fichier": r.nb_couches_fichier,
                "nb_couches_autres": r.nb_couches_autres,
                "profil": r.profil,
                "mdp_en_clair": r.mdp_en_clair,
                "authcfg_utilise": r.authcfg_utilise,
                "services_distincts": _LISTE_SEP.join(r.services_distincts),
                "hosts_distincts": _LISTE_SEP.join(r.hosts_distincts),
                "bases_distinctes": _LISTE_SEP.join(r.bases_distinctes),
            })
            for row in r.couches_pg:
                cw.writerow(row)

    print(
        f"{nb_analyses} projet(s) analysé(s) sur {nb_fichiers} fichier(s) trouvé(s).",
        file=sys.stderr,
    )
    return projets_csv, couches_csv
