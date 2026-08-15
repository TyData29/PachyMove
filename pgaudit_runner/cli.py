from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

from .collector import collect
from .log_analyzer import analyze_directory
from .reporter import generate_dashboard, generate_report, render_html, report_stem


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
    help="Chemin d'un manifeste YAML, ou d'un dossier pour tous les lancer à la suite "
         "(ex. --manifest manifests/)",
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
@click.option(
    "--work-mem", default=None,
    help="SET work_mem en début de session (ex. 256MB) — utile pour les scans lourds "
         "(data_quality_on_tables) sur un serveur au réglage par défaut trop bas",
)
@click.option(
    "--quiet", is_flag=True,
    help="Supprime la progression en direct (utile en usage scripté)",
)
@click.option("--dry-run", is_flag=True, help="Simule sans connexion réelle")
@click.option(
    "--with-report/--no-with-report", default=True, show_default=True,
    help="Génère aussi le rapport Markdown juste après la collecte",
)
@click.option(
    "--max-rows", default=100, show_default=True,
    type=click.IntRange(min=1),
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
    work_mem: Optional[str],
    quiet: bool,
) -> None:
    """Exécute les requêtes d'audit et produit un JSON horodaté."""
    if not dry_run and (not host or not user):
        raise click.UsageError(
            "--host et --user sont obligatoires hors --dry-run "
            "(ou ajoutez --dry-run pour valider le manifeste sans connexion réelle)."
        )
    host = host or "(dry-run)"
    user = user or "(dry-run)"

    manifests_dir = manifest if manifest.is_dir() else manifest.parent
    queries_dir = manifests_dir.parent / "queries"
    if not queries_dir.exists():
        raise click.ClickException(f"Dossier queries introuvable : {queries_dir}")

    manifest_paths = sorted(manifest.glob("*.yaml")) if manifest.is_dir() else [manifest]
    if not manifest_paths:
        raise click.ClickException(f"Aucun manifeste .yaml trouvé dans {manifest}")

    # Une cible n'existe que si au moins un --target-* a été passé explicitement
    # (tous par défaut None) — l'héritage ci-dessous ne doit jamais en créer une
    # qui n'a pas été demandée.
    target_defined = any(
        v is not None
        for v in (target_host, target_port, target_user, target_service,
                  target_maintenance_db, target_dbnames)
    )

    for i, manifest_path in enumerate(manifest_paths, start=1):
        if len(manifest_paths) > 1:
            click.echo(f"=== Manifeste {i}/{len(manifest_paths)} : {manifest_path.name} ===")
        try:
            output_file = collect(
                host=host,
                port=port,
                user=user,
                dbnames=_csv(dbnames),
                maintenance_db=maintenance_db,
                manifest_path=manifest_path,
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
                work_mem=work_mem,
                quiet=quiet,
            )
            click.echo(f"Audit sauvegardé : {output_file}")

            if with_report:
                report_path = output_file.with_name(f"{report_stem(output_file)}.md")
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


@cli.command(name="dashboard")
@click.option(
    "--input-dir", "input_dir", required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Dossier contenant les JSON d'audit (audit_*.json, ex. output/)",
)
@click.option(
    "--output", "output_file", default=None, type=click.Path(path_type=Path),
    help="Fichier HTML en sortie (défaut : <input-dir>/index.html) — doit rester "
         "dans --input-dir, les liens vers les rapports sont relatifs",
)
@click.option(
    "--max-rows", default=100, show_default=True,
    help="Seuil de troncature des rapports HTML régénérés pour chaque run",
)
def dashboard_cmd(input_dir: Path, output_file: Optional[Path], max_rows: int) -> None:
    """Page HTML agrégeant bloquants/vigilance/erreurs de tous les runs d'un
    dossier, avec lien vers le rapport HTML complet de chacun (régénéré à
    chaque appel, pour rester à jour)."""
    try:
        json_paths = sorted(input_dir.glob("audit_*.json"))
        if not json_paths:
            raise click.ClickException(f"Aucun audit_*.json trouvé dans {input_dir}")

        for path in json_paths:
            data = json.loads(path.read_text(encoding="utf-8"))
            manifest_name = (data.get("metadata") or {}).get("manifest_name") or path.stem
            md = generate_report(path, max_rows=max_rows)
            stem = report_stem(path)
            (input_dir / f"{stem}.md").write_text(md, encoding="utf-8")
            html = render_html(md, title=manifest_name)
            (input_dir / f"{stem}.html").write_text(html, encoding="utf-8")

        dashboard_html = generate_dashboard(json_paths)
        out = output_file or (input_dir / "index.html")
        out.write_text(dashboard_html, encoding="utf-8")
        click.echo(f"Tableau de bord généré : {out}")
    except click.ClickException:
        raise
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command(name="analyze-logs")
@click.option(
    "--input-dir", "input_dir", required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Dossier contenant les fichiers de log PostgreSQL (log_connections)",
)
@click.option(
    "--pattern", default="*", show_default=True,
    help="Filtre de nom de fichier dans --input-dir (non récursif)",
)
@click.option(
    "--output", "output_file", default=None, type=click.Path(path_type=Path),
    help="Fichier JSON en sortie (défaut : output/connexions_<horodatage>.json)",
)
def analyze_logs_cmd(input_dir: Path, pattern: str, output_file: Optional[Path]) -> None:
    """Synthétise les connexions par rôle depuis des logs PostgreSQL (log_connections).

    Ne couvre ni la durée de session (nécessite log_disconnections) ni le détail
    des actions/tables (nécessite log_statement ou pgaudit) — ces réglages ne
    sont pas activés à la source. Sortie indexée par rôle, croisable avec
    role_membership_tree de rights_audit.json.
    """
    try:
        result = analyze_directory(input_dir, pattern=pattern)

        if output_file is None:
            ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
            output_file = Path("output") / f"connexions_{ts}.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        meta = result["metadata"]
        click.echo(f"Synthèse générée : {output_file}")
        click.echo(
            f"{meta['connections_total']} connexion(s) sur {len(meta['files_processed'])} "
            f"fichier(s), {meta['lines_unparsed']} ligne(s) non reconnue(s)."
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
