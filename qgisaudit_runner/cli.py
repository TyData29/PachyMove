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

    with open(args.config, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    racines = [Path(p) for p in config.get("racines", [])]
    if not racines:
        print("Aucune racine déclarée dans la configuration (clé 'racines').", file=sys.stderr)
        return 1
    extensions = config.get("extensions", [".qgs", ".qgz"])
    dossier_sortie = Path(config.get("dossier_sortie", "output"))

    run_inventory(racines, extensions, dossier_sortie)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
