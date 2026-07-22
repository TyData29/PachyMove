from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from .inventory import run_inventory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qgisaudit-runner",
        description="Inventaire des projets QGIS et de leurs connexions PostgreSQL (lecture seule).",
    )
    parser.add_argument(
        "--config", type=Path, default=Path("config_qgis.yml"),
        help="Chemin du fichier de configuration YAML (défaut : config_qgis.yml)",
    )
    args = parser.parse_args(argv)

    if not args.config.exists():
        print(f"Fichier de configuration introuvable : {args.config}", file=sys.stderr)
        return 1

    try:
        with open(args.config, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(f"Configuration YAML invalide : {args.config} ({e})", file=sys.stderr)
        return 1

    if not isinstance(config, dict):
        print(
            f"Configuration invalide : le YAML doit contenir un mapping (dict), pas {type(config).__name__}.",
            file=sys.stderr,
        )
        return 1

    racines_raw = config.get("racines", [])
    if isinstance(racines_raw, (str, Path)):
        racines_raw = [racines_raw]
    if not isinstance(racines_raw, list):
        print("Configuration invalide : 'racines' doit être une liste de chemins.", file=sys.stderr)
        return 1
    racines = [Path(p) for p in racines_raw]
    if not racines:
        print("Aucune racine déclarée dans la configuration (clé 'racines').", file=sys.stderr)
        return 1

    extensions_raw = config.get("extensions", [".qgs", ".qgz"])
    if isinstance(extensions_raw, str):
        extensions = [extensions_raw]
    elif isinstance(extensions_raw, list):
        extensions = extensions_raw
    else:
        print("Configuration invalide : 'extensions' doit être une liste de suffixes.", file=sys.stderr)
        return 1

    dossier_sortie = Path(config.get("dossier_sortie", "output"))
    run_inventory(racines, extensions, dossier_sortie)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
