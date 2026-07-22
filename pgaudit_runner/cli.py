from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from .collector import collect
from .reporter import generate_report, render_html


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()] if value else []


@click.group()
def cli():
    """pgaudit-runner — Pré-audit PostgreSQL avant migration majeure."""


@cli.command(name="collect")
@click.option("--host", default=None, help="Hôte PostgreSQL (obligatoire hors --dry-run)")
@click.option("--port", default=5432, show_default=True, type=int)
@click.option("--user", default=None, help="Utilisateur PostgreSQL (obligatoire hors --dry-run)")
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
    "--output", default=Path("output"), show_default=True, type=click.Path(path_type=Path),
    help="Dossier de sortie du JSON",
)
@click.option("--tags", default="", help="Filtrer par tags (virgule-séparés)")
@click.option("--only", default="", help="Exécuter uniquement ces ids (virgule-séparés)")
@click.option("--exclude", default="", help="Exclure ces ids (virgule-séparés)")
@click.option("--service", default=None, help="Nom de service pg_service.conf")
@click.option("--target-host", default=None, help="Hôte PostgreSQL cible")
@click.option("--target-port", default=None, type=int, help="Port cible")
@click.option("--target-user", default=None, help="Utilisateur cible")
@click.option("--target-service", default=None, help="Nom de service pg_service.conf cible")
@click.option("--target-maintenance-db", default=None, help="Base de connexion cible pour scope:instance")
@click.option("--target-dbnames", default=None, help="Bases ciblées côté cible (séparées par virgule)")
@click.option(
    "--migration-method", default=None,
    type=click.Choice(["pg_upgrade", "dump_restore"]),
    help="Force l'interprétation de la méthode de migration en cas d'ambiguïté (même serveur)",
)
@click.option("--dry-run", is_flag=True, help="Simule sans connexion réelle")
@click.option(
    "--with-report/--no-with-report", default=True, show_default=True,
    help="Génère aussi le rapport Markdown juste après la collecte",
)
@click.option(
    "--max-rows", default=100, show_default=True,
    help="Seuil de troncature des résultats (rapport auto, si --with-report)",
)
def collect_cmd(
    host: Optional[str],
    port: int,
    user: Optional[str],
    dbnames: str,
    maintenance_db: str,
    manifest: Path,
    output: Path,
    tags: str,
    only: str,
    exclude: str,
    service: Optional[str],
    target_host: Optional[str],
    target_port: Optional[int],
    target_user: Optional[str],
    target_service: Optional[str],
    target_maintenance_db: Optional[str],
    target_dbnames: Optional[str],
    migration_method: Optional[str],
    dry_run: bool,
    with_report: bool,
    max_rows: int,
) -> None:
    """Exécute les requêtes d'audit et produit un JSON horodaté."""
    if not dry_run and (not host or not user):
        raise click.UsageError(
            "--host et --user sont obligatoires hors --dry-run "
            "(ou ajoutez --dry-run pour valider le manifeste sans connexion réelle)."
        )
    host = host or "(dry-run)"
    user = user or "(dry-run)"

    queries_dir = manifest.parent.parent / "queries"
    if not queries_dir.exists():
        raise click.ClickException(f"Dossier queries introuvable : {queries_dir}")

    # Une cible n'existe que si au moins un --target-* a été passé explicitement
    # (tous par défaut None) — l'héritage ci-dessous ne doit jamais en créer une
    # qui n'a pas été demandée.
    target_defined = any(
        v is not None
        for v in (target_host, target_port, target_user, target_service,
                  target_maintenance_db, target_dbnames)
    )

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
            target_host=(target_host or host) if target_defined else None,
            target_port=(target_port or port) if target_defined else None,
            target_user=(target_user or user) if target_defined else None,
            target_service=target_service,
            target_maintenance_db=(target_maintenance_db or maintenance_db) if target_defined else None,
            target_dbnames=(_csv(target_dbnames) if target_dbnames else _csv(dbnames)) if target_defined else None,
            migration_method=migration_method,
        )
        click.echo(f"Audit sauvegardé : {output_file}")

        if with_report:
            report_path = output_file.with_name(
                output_file.name.replace("audit_", "rapport_", 1)
            ).with_suffix(".md")
            md = generate_report(output_file, max_rows=max_rows)
            report_path.write_text(md, encoding="utf-8")
            click.echo(f"Rapport généré : {report_path}")
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


@cli.command(name="html")
@click.option(
    "--input", "input_file", required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Fichier Markdown en entrée (rapport, éventuellement édité à la main)",
)
@click.option(
    "--output", "output_file", required=True,
    type=click.Path(path_type=Path),
    help="Fichier HTML en sortie",
)
def html_cmd(input_file: Path, output_file: Path) -> None:
    """Convertit un rapport Markdown en HTML autonome (CSS intégrée, sans dépendance externe)."""
    try:
        md = input_file.read_text(encoding="utf-8")
        html = render_html(md)
        output_file.write_text(html, encoding="utf-8")
        click.echo(f"HTML généré : {output_file}")
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
