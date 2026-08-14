"""Croise les exports de droits (rights_audit) avec les connexions observées
(analyze-logs) pour repérer les écarts droits <-> usage réel.

Charge dans DuckDB les CSV de droits (`role_membership_tree`,
`relation_privileges`, `schema_privileges`, `function_privileges`,
`rls_policies_presence` — export via `scripts/export_csv.py`, tous indexés
par `role`) et les CSV de connexions (`connexions.csv`/`connexions_detail.csv`
— export via `scripts/connexions_json_to_csv.py`), puis produit deux
croisements :

- droits_sans_connexion.csv : rôles ayant des droits mais jamais vus dans
  les logs de connexion sur la période couverte. Équivalent hors-ligne de la
  requête "role_login_jamais_vu" de `.tydata/specs/analyse_connexions.sql`.
- connexions_sans_droits_directs.csv : rôles connectés mais sans aucun droit
  `direct` (droits uniquement hérités d'un groupe, ou aucun droit trouvé).

Un dossier `--droits` doit correspondre à une seule mission/cible : le
script attend un seul fichier `<id>__*.csv` par requête de droits (convention
`scripts/export_csv.py`, `{id}__{side}__{target}.csv`).

Usage :
    python roles_analyses/main.py --droits output/csv --connexions output/csv --output-dir output/roles_analyses
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

_TABLES_DROITS = {
    "roles": "role_membership_tree",
    "fonctions": "function_privileges",
    "droits": "relation_privileges",
    "droits_avances": "rls_policies_presence",
    "schemas": "schema_privileges",
}


def _find_csv(directory: Path, query_id: str) -> Path:
    candidats = sorted(directory.glob(f"{query_id}__*.csv"))
    if not candidats:
        raise FileNotFoundError(f"Aucun CSV '{query_id}__*.csv' dans {directory}")
    if len(candidats) > 1:
        noms = ", ".join(c.name for c in candidats)
        raise FileNotFoundError(
            f"Plusieurs CSV '{query_id}__*.csv' dans {directory} ({noms}) — "
            "un dossier --droits doit correspondre à une seule mission/cible."
        )
    return candidats[0]


def charger_tables(
    con: duckdb.DuckDBPyConnection, droits_dir: Path, connexions_dir: Path
) -> None:
    for table, query_id in _TABLES_DROITS.items():
        csv_path = _find_csv(droits_dir, query_id)
        con.sql(
            f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM read_csv_auto(?)",
            params=[str(csv_path)],
        )

    con.sql(
        "CREATE OR REPLACE TABLE connexions_roles AS SELECT * FROM read_csv_auto(?)",
        params=[str(connexions_dir / "connexions.csv")],
    )
    con.sql(
        "CREATE OR REPLACE TABLE connexions_detail AS SELECT * FROM read_csv_auto(?)",
        params=[str(connexions_dir / "connexions_detail.csv")],
    )


def droits_sans_connexion(con: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyRelation:
    # role = '-' est la représentation PostgreSQL de PUBLIC (cast regrole de
    # l'oid 0 dans les requêtes de droits), pas un rôle réel — exclu ici.
    # Biais assumé : contrairement à analyse_connexions.sql (qui filtre sur
    # pg_roles.rolcanlogin en direct sur le serveur), cette version hors-ligne
    # ne peut pas distinguer les rôles de groupe (non connectables) des rôles
    # de login — rolcanlogin n'est pas exporté dans les CSV de droits. Les
    # rôles purement groupe (ex. grp_*) apparaissent donc aussi dans le
    # résultat, à filtrer manuellement si besoin.
    return con.sql("""
        WITH roles_avec_droits AS (
            SELECT DISTINCT role FROM droits    WHERE role <> '-'
            UNION SELECT DISTINCT role FROM schemas   WHERE role <> '-'
            UNION SELECT DISTINCT role FROM fonctions WHERE role <> '-'
            UNION SELECT DISTINCT role FROM roles
        )
        SELECT r.role
        FROM roles_avec_droits r
        LEFT JOIN connexions_roles c ON c.role = r.role
        WHERE c.role IS NULL
        ORDER BY r.role
    """)


def connexions_sans_droits_directs(
    con: duckdb.DuckDBPyConnection,
) -> duckdb.DuckDBPyRelation:
    return con.sql("""
        WITH roles_droits_directs AS (
            SELECT DISTINCT role FROM droits    WHERE source = 'direct'
            UNION SELECT DISTINCT role FROM schemas   WHERE source = 'direct'
            UNION SELECT DISTINCT role FROM fonctions WHERE source = 'direct'
        )
        SELECT c.role, c.connection_count, c.database_principale, c.host_principal,
               c.first_seen, c.last_seen
        FROM connexions_roles c
        LEFT JOIN roles_droits_directs d ON d.role = c.role
        WHERE d.role IS NULL
        ORDER BY c.connection_count DESC
    """)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--droits", type=Path, required=True, help="Dossier des CSV rights_audit"
    )
    parser.add_argument(
        "--connexions", type=Path, required=True, help="Dossier des CSV de connexions"
    )
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="Dossier de sortie des CSV croisés"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("analyse.duckdb"),
        help="Fichier DuckDB de travail (écrasé à chaque run, défaut analyse.duckdb)",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        with duckdb.connect(str(args.db)) as con:
            charger_tables(con, args.droits, args.connexions)

            sorties = {
                "droits_sans_connexion.csv": droits_sans_connexion(con),
                "connexions_sans_droits_directs.csv": connexions_sans_droits_directs(con),
            }
            for nom, relation in sorties.items():
                chemin = args.output_dir / nom
                relation.write_csv(str(chemin))
                print(f"Écrit : {chemin}")
    except FileNotFoundError as e:
        raise SystemExit(f"Erreur : {e}")


if __name__ == "__main__":
    main()
