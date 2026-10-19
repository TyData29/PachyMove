"""Projets QGIS stockés en base PostgreSQL : tables `qgis_projects` (stockage
PostgreSQL de QGIS), une ligne par projet, contenu .qgz dans la colonne
`content`. Lecture seule : la session est ouverte en
`default_transaction_read_only`.

psycopg n'est importé qu'ici, à l'appel : l'inventaire des seuls fichiers
n'en a pas besoin."""
from __future__ import annotations

import getpass
import sys
from typing import Iterator

_SCHEMAS_SQL = """
select table_schema
from information_schema.columns
where table_name = 'qgis_projects' and column_name in ('name', 'content')
group by table_schema
having count(*) = 2
order by table_schema
"""


def _parametres(conninfo: str) -> dict[str, str]:
    from psycopg.conninfo import conninfo_to_dict

    return {k: str(v) for k, v in conninfo_to_dict(conninfo).items()}


def chemin_projet(conninfo: str, schema: str, nom: str) -> str:
    """Chemin du projet au format d'URI de QGIS, sans utilisateur ni mot de
    passe : `postgresql:///?service=s&schema=x&project=nom`, ou
    `postgresql://hote:port/?dbname=d&schema=x&project=nom`."""
    p = _parametres(conninfo)
    if p.get("service"):
        return f"postgresql:///?service={p['service']}&schema={schema}&project={nom}"
    return (f"postgresql://{p.get('host', '')}:{p.get('port', '5432')}/"
            f"?dbname={p.get('dbname', '')}&schema={schema}&project={nom}")


def _connecter(conninfo: str):
    """Mot de passe demandé seulement si le serveur en exige un et qu'il n'est
    fourni ni par la chaîne, ni par pgpass, ni par le service. Le test porte
    sur le texte du message, en anglais ou en français selon la langue de
    libpq."""
    import psycopg

    try:
        return psycopg.connect(conninfo, autocommit=True)
    except psycopg.OperationalError as exc:
        message = str(exc).lower()
        if not sys.stdin.isatty() or ("password" not in message and "mot de passe" not in message):
            raise
    return psycopg.connect(conninfo, password=getpass.getpass(f"Mot de passe ({conninfo}) : "), autocommit=True)


def iter_projets_en_base(conninfo: str) -> Iterator[tuple[str, str, bytes]]:
    """(chemin, nom, contenu) de chaque projet de chaque table `qgis_projects`
    lisible avec cette connexion."""
    from psycopg import sql

    with _connecter(conninfo) as conn:
        conn.execute("set default_transaction_read_only = on")
        schemas = [r[0] for r in conn.execute(_SCHEMAS_SQL)]
        for schema in schemas:
            requete = sql.SQL("select name, content from {}.qgis_projects order by name").format(
                sql.Identifier(schema)
            )
            for nom, contenu in conn.execute(requete).fetchall():
                yield chemin_projet(conninfo, schema, nom), nom, bytes(contenu or b"")
