"""Convertit le JSON produit par `pgaudit-runner analyze-logs` en deux CSV.

Le JSON source est agrégé **par rôle** (une entrée par rôle, pas par
connexion) — cf. `pgaudit_runner/log_analyzer.py`. Il ne contient ni durée de
session (`log_disconnections` non activé côté source) ni détail des requêtes
exécutées. Ces deux CSV n'inventent aucune de ces deux informations :

- connexions.csv : une ligne par rôle (comptage, principaux hôte/base, bornes
  temporelles).
- connexions_detail.csv : format long, une ligne par (rôle, dimension,
  valeur, nb) où dimension ∈ {database, host, application} — pour la
  provenance détaillée et tout croisement par la suite.

Usage :
    python scripts/connexions_json_to_csv.py output/connexions_20260723_101500.json --output-dir output/csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def _top(counter: dict[str, int]) -> str:
    return max(counter, key=counter.get) if counter else ""


def convert(json_path: Path, output_dir: Path) -> tuple[Path, Path]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    roles: dict[str, dict] = data.get("roles", {})

    output_dir.mkdir(parents=True, exist_ok=True)
    connexions_csv = output_dir / "connexions.csv"
    detail_csv = output_dir / "connexions_detail.csv"

    with open(connexions_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "role", "connection_count", "nb_databases", "nb_hosts", "nb_applications",
            "database_principale", "host_principal", "first_seen", "last_seen",
        ])
        for role, stats in roles.items():
            writer.writerow([
                role,
                stats.get("connection_count", 0),
                len(stats.get("databases") or {}),
                len(stats.get("source_hosts") or {}),
                len(stats.get("applications") or {}),
                _top(stats.get("databases") or {}),
                _top(stats.get("source_hosts") or {}),
                stats.get("first_seen") or "",
                stats.get("last_seen") or "",
            ])

    with open(detail_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["role", "dimension", "valeur", "nb"])
        for role, stats in roles.items():
            for dimension, counter in (
                ("database", stats.get("databases") or {}),
                ("host", stats.get("source_hosts") or {}),
                ("application", stats.get("applications") or {}),
            ):
                for valeur, nb in counter.items():
                    writer.writerow([role, dimension, valeur, nb])

    return connexions_csv, detail_csv


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path", type=Path, help="Fichier JSON produit par 'analyze-logs'")
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="Dossier de sortie des 2 CSV"
    )
    args = parser.parse_args()

    connexions_csv, detail_csv = convert(args.json_path, args.output_dir)
    print(f"Écrit : {connexions_csv}")
    print(f"Écrit : {detail_csv}")


if __name__ == "__main__":
    main()
