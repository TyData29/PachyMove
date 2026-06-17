from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from .collector import collect
from .reporter import generate_report


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()] if value else []


@click.group()
def cli():
    """pgaudit-runner — Pré-audit PostgreSQL avant migration majeure."""


@cli.command(name="collect")
@click.option("--host", required=True, help="Hôte PostgreSQL")
@click.option("--port", default=5432, show_default=True, type=int)
@click.option("--user", required=True, help="Utilisateur PostgreSQL")
@click.option("--dbnames", default="", help="Bases ciblées (séparées par virgule)")
@click.option(
    "--maintenance-db", default="postgres", show_default=True,
    help="Base de connexion pour les requêtes scope:instance",
)
@click.option(
    "--manifest", required=True, type=click.Path(exists=True, path_type=Path),
    help="Chemin du manifeste YAML",
)
@click.option(
    "--output", required=True, type=click.Path(path_type=Path),
    help="Dossier de sortie du JSON",
)
@click.option("--tags", default="", help="Filtrer par tags (virgule-séparés)")
@click.option("--only", default="", help="Exécuter uniquement ces ids (virgule-séparés)")
@click.option("--exclude", default="", help="Exclure ces ids (virgule-séparés)")
@click.option("--service", default=None, help="Nom de service pg_service.conf")
@click.option("--dry-run", is_flag=True, help="Simule sans connexion réelle")
def collect_cmd(
    host: str,
    port: int,
    user: str,
    dbnames: str,
    maintenance_db: str,
    manifest: Path,
    output: Path,
    tags: str,
    only: str,
    exclude: str,
    service: Optional[str],
    dry_run: bool,
) -> None:
    """Exécute les requêtes d'audit et produit un JSON horodaté."""
    queries_dir = manifest.parent.parent / "queries"
    if not queries_dir.exists():
        raise click.ClickException(f"Dossier queries introuvable : {queries_dir}")

    try:
        output_file = collect(
            host=host,
            port=port,
            user=user,
            dbnames=_csv(dbnames),
            maintenance_db=maintenance_db,
            manifest_path=manifest,
            queries_dir=queries_dir,
            output_dir=output,
            tags=_csv(tags),
            only=_csv(only),
            exclude=_csv(exclude),
            dry_run=dry_run,
            service=service,
        )
        click.echo(f"Audit sauvegardé : {output_file}")
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command(name="report")
@click.option(
    "--input", "input_file", required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Fichier JSON d'audit en entrée",
)
@click.option(
    "--output", "output_file", required=True,
    type=click.Path(path_type=Path),
    help="Fichier Markdown en sortie",
)
@click.option(
    "--max-rows", default=100, show_default=True,
    help="Seuil de troncature des résultats",
)
def report_cmd(input_file: Path, output_file: Path, max_rows: int) -> None:
    """Génère le rapport Markdown depuis un JSON d'audit."""
    try:
        md = generate_report(input_file, max_rows=max_rows)
        output_file.write_text(md, encoding="utf-8")
        click.echo(f"Rapport généré : {output_file}")
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
