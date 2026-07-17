"""Exporte chaque requête réussie d'un JSON d'audit pgaudit-runner en CSV.

La matrice de droits est pensée pour un filtrage en tableur (spec module
droits §6/§10) — le rapport Markdown, tronqué par défaut à 100 lignes, ne
convient pas à ce type d'inspection. Usage :

    python scripts/export_csv.py output/audit_20260617_211245.json --output-dir output/csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def export_csv(audit_json: Path, output_dir: Path) -> list[Path]:
    with open(audit_json, encoding="utf-8") as f:
        data = json.load(f)

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for r in data["results"]:
        if r["status"] != "success" or not r.get("columns"):
            continue
        target = r["target"].replace("/", "_")
        csv_path = output_dir / f"{r['id']}__{target}.csv"
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=r["columns"])
            writer.writeheader()
            writer.writerows(r.get("rows") or [])
        written.append(csv_path)

    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_json", type=Path, help="Fichier JSON produit par 'collect'")
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="Dossier de sortie des CSV"
    )
    args = parser.parse_args()

    written = export_csv(args.audit_json, args.output_dir)
    for path in written:
        print(f"Écrit : {path}")


if __name__ == "__main__":
    main()
