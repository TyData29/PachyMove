from __future__ import annotations

import html as _html
import json
from collections import OrderedDict
from pathlib import Path
from typing import Optional

import markdown as _markdown_lib

_BADGES: dict[str, str] = {"success": "✅", "skipped": "⏭️", "error": "❌"}
_VALID_SEVERITIES = {"bloquant", "vigilance", "info"}
_SYNTHESE_MAX_PAR_CONTROLE = 10


def _badge(status: str) -> str:
    return _BADGES.get(status, "❓")


def _normalize_severity(value: object) -> str:
    v = str(value or "").strip().lower()
    return v if v in _VALID_SEVERITIES else "info"


def _synthese_engagee(results: list[dict]) -> bool:
    """Le mécanisme de synthèse est-il utilisé par au moins une requête du run ?

    Distingue « rien à signaler » (section affichée, all-clear explicite) de
    « aucune requête n'utilise encore severite/expect_rows » (section absente,
    comportement identique à avant cette fonctionnalité — pas de régression, et
    pas de faux sentiment de sécurité tant que rien n'a été calibré, cf. spec §8).
    """
    for r in results:
        if r.get("status") != "success":
            continue
        columns = r.get("columns") or []
        if "severite" in columns and "constat" in columns:
            return True
        if r.get("expect_rows") is not None:
            return True
    return False


def _topology_excludes(
    applies_to: list[str],
    same_server: Optional[bool],
    migration_method: Optional[str],
) -> Optional[str]:
    """Une requête liée à une méthode de migration précise est-elle sans objet
    ici, compte tenu de la topologie source/cible ?

    `same_server` est dérivé (jamais déclaré) : `False` exclut catégoriquement
    pg_upgrade (contrainte physique, vraie pour n'importe quelle mission).
    `True`/`None` (même serveur, ou pas de cible) restent ambigus — seul un
    override explicite (`migration_method`) permet alors de trancher.
    """
    if not applies_to:
        return None
    if same_server is False and "pg_upgrade" in applies_to:
        return "sans objet pour dump/restore — la topologie exclut pg_upgrade"
    if same_server is not False and migration_method and migration_method not in applies_to:
        return f"sans objet pour {migration_method} — applicable seulement à : {', '.join(applies_to)}"
    return None


def extraire_synthese(
    results: list[dict],
    same_server: Optional[bool] = None,
    migration_method: Optional[str] = None,
) -> list[dict]:
    """Retourne les constats de gravité, tous résultats confondus.

    Deux sources :
      - convention de colonnes : le résultat expose 'severite' et 'constat'
      - expect_rows : le manifeste déclare un nombre de lignes attendu
    La convention de colonnes prime si les deux sont présentes.

    Une requête exclue par la topologie (`_topology_excludes`) n'alimente pas
    la synthèse, mais reste visible — annotée — dans le détail par requête.
    """
    entries: list[dict] = []

    for r in results:
        if r.get("status") != "success":
            continue
        if _topology_excludes(r.get("applies_to") or [], same_server, migration_method):
            continue

        columns = r.get("columns") or []
        rows = r.get("rows") or []
        if r.get("scope") == "instance":
            base = "cible" if r.get("side") == "target" else "—"
        else:
            base = r.get("target", "—")
        ancre = r["id"].replace("_", "-")

        if "severite" in columns and "constat" in columns:
            for row in rows:
                constat_value = row.get("constat")
                constat = str(constat_value) if constat_value is not None else f"{r['id']} : {len(rows)} ligne(s)"
                entries.append({
                    "severite": _normalize_severity(row.get("severite")),
                    "constat": constat,
                    "id": r["id"],
                    "base": base,
                    "ancre": ancre,
                })
            continue

        expect_rows = r.get("expect_rows")
        if expect_rows is not None:
            row_count = r.get("row_count")
            if row_count is None:
                row_count = len(rows)
            if row_count != expect_rows:
                entries.append({
                    "severite": _normalize_severity(r.get("severity_if_unexpected")),
                    "constat": f"{row_count} ligne(s) trouvée(s), {expect_rows} attendue(s).",
                    "id": r["id"],
                    "base": base,
                    "ancre": ancre,
                })

    return entries


def _synthese_table(entries: list[dict], severite: str) -> list[str]:
    filtered = [e for e in entries if e["severite"] == severite]
    if not filtered:
        return []

    by_id: OrderedDict[str, list[dict]] = OrderedDict()
    for e in filtered:
        by_id.setdefault(e["id"], []).append(e)

    lines = ["| Base | Contrôle | Constat |", "|---|---|---|"]
    for qid, group in by_id.items():
        for e in group[:_SYNTHESE_MAX_PAR_CONTROLE]:
            constat = e["constat"].replace("|", "\\|")
            lines.append(f"| {e['base']} | [{qid}](#{e['ancre']}) | {constat} |")
        reste = len(group) - _SYNTHESE_MAX_PAR_CONTROLE
        if reste > 0:
            lines.append(f"| | | _… et {reste} autre(s) pour \\`{qid}\\` — voir la section détaillée._ |")
    return lines + [""]


def _md_table(columns: list[str], rows: list[dict]) -> str:
    if not rows:
        return "_Aucun résultat._\n"
    escaped_cols = [_html.escape(str(c), quote=False) for c in columns]
    header = "| " + " | ".join(escaped_cols) + " |"
    sep = "|" + "|".join(" --- " for _ in columns) + "|"
    body_lines = [
        "| "
        + " | ".join(
            _html.escape(str(row.get(c, "")), quote=False).replace("|", "\\|")
            for c in columns
        )
        + " |"
        for row in rows
    ]
    return "\n".join([header, sep, *body_lines]) + "\n"


def _sql_block(sql: str) -> str:
    return f"<details>\n<summary>SQL exécuté</summary>\n\n```sql\n{sql}\n```\n\n</details>\n"


def _render_result_body(r: dict, max_rows: int, annotation: Optional[str] = None) -> list[str]:
    lines: list[str] = []
    status = r["status"]

    if annotation:
        lines.append(f"_{annotation}._\n")

    if status == "success":
        columns = r.get("columns") or []
        rows = r.get("rows") or []
        total = r.get("row_count") or 0
        lines.append(_md_table(columns, rows[:max_rows]))
        if total > max_rows:
            lines.append(
                f"_… {total - max_rows} ligne(s) supplémentaire(s) non affichée(s) "
                f"— total : {total}._\n"
            )
    elif status == "skipped":
        lines.append(f"**Ignorée.** {r.get('skip_reason', '')}\n")
    elif status == "error":
        err = r.get("error") or {}
        msg = err.get("message", "Erreur inconnue")
        sqlstate = err.get("sqlstate")
        suffix = f" _(SQLSTATE : {sqlstate})_" if sqlstate else ""
        lines.append(f"**Erreur.** {msg}{suffix}\n")

    if r.get("sql"):
        lines.append(_sql_block(r["sql"]))

    return lines


def _overall_status(group: list[dict]) -> str:
    statuses = {r["status"] for r in group}
    if "error" in statuses:
        return "error"
    if "success" in statuses:
        return "success"
    return "skipped"


def generate_report(audit_json: Path, max_rows: int = 100) -> str:
    with open(audit_json, encoding="utf-8") as f:
        data = json.load(f)

    meta = data["metadata"]
    all_results: list[dict] = data["results"]
    summary = meta["summary"]
    conn = meta.get("source") or meta["connection"]  # repli JSON pré-spec-3
    target_meta = meta.get("target")
    same_server = meta.get("same_server")
    migration_method = meta.get("migration_method")
    target_error = meta.get("target_error")

    # Groupement par id, ordre de première apparition
    by_id: OrderedDict[str, list[dict]] = OrderedDict()
    for r in all_results:
        by_id.setdefault(r["id"], []).append(r)

    lines: list[str] = []

    # ── En-tête ──────────────────────────────────────────────────────────────
    started = meta["started_at"][:19].replace("T", " ")
    targets = ", ".join(conn.get("databases_targeted") or []) or "—"
    version = conn.get("server_version") or "inconnu"

    if target_meta is None:
        lines += [
            "# Rapport de pré-audit PostgreSQL\n",
            f"**Manifeste :** {meta['manifest_name']}  ",
            f"**Date :** {started}  ",
            f"**Serveur :** {version}  ",
            f"**Bases ciblées :** {targets}  ",
        ]
    else:
        target_version = target_meta.get("server_version") or "inconnu"
        lines += [
            "# Rapport de pré-audit PostgreSQL\n",
            f"**Manifeste :** {meta['manifest_name']}  ",
            f"**Date :** {started}  ",
            f"**Source :** {conn.get('host')}:{conn.get('port')} ({version})  ",
            f"**Cible :** {target_meta.get('host')}:{target_meta.get('port')} ({target_version})  ",
            f"**Bases ciblées :** {targets}  ",
        ]

    lines.append(
        f"**Résumé :** {summary['total']} requêtes — "
        f"✅ {summary['success']} succès / "
        f"⏭️ {summary['skipped']} ignorées / "
        f"❌ {summary['error']} erreurs"
    )
    lines.append("\n---\n")

    if target_error:
        n_target_errors = sum(
            1 for r in all_results if r.get("side") == "target" and r["status"] == "error"
        )
        lines.append(
            f"⚠️ Cible {target_meta.get('host')}:{target_meta.get('port')} injoignable — "
            f"{n_target_errors} contrôle(s) n'ont pas pu s'exécuter. "
            "La comparaison source/cible est absente de ce rapport.\n"
        )

    # ── Synthèse ─────────────────────────────────────────────────────────────
    errors = [r for r in all_results if r["status"] == "error"]

    if _synthese_engagee(all_results):
        entries = extraire_synthese(all_results, same_server=same_server, migration_method=migration_method)
        bloquants = [e for e in entries if e["severite"] == "bloquant"]
        vigilances = [e for e in entries if e["severite"] == "vigilance"]

        lines.append("## Synthèse\n")
        if errors:
            lines.append(
                f"⚠️ {len(errors)} contrôle(s) n'ont pas pu s'exécuter — voir Points d'attention. "
                "La synthèse est incomplète.\n"
            )
        if not bloquants and not vigilances:
            lines.append("_Aucun bloquant ni point de vigilance détecté._\n")
        else:
            lines.append(f"**{len(bloquants)} bloquant(s) · {len(vigilances)} point(s) de vigilance**\n")
            if bloquants:
                lines.append("### Bloquants\n")
                lines += _synthese_table(bloquants, "bloquant")
            if vigilances:
                lines.append("### Points de vigilance\n")
                lines += _synthese_table(vigilances, "vigilance")
        lines.append("---\n")

    # ── Sommaire ─────────────────────────────────────────────────────────────
    lines.append("## Sommaire\n")
    for qid, group in by_id.items():
        anchor = qid.replace("_", "-")
        overall = _overall_status(group)
        lines.append(f"- {_badge(overall)} [{group[0]['title']}](#{anchor})")
    lines += ["", "---\n"]

    # ── Sections par requête ─────────────────────────────────────────────────
    def _render_group(rows: list[dict], scope: str) -> list[str]:
        out: list[str] = []
        for r in rows:
            annotation = _topology_excludes(r.get("applies_to") or [], same_server, migration_method)
            if scope == "database":
                out.append(f"### {_badge(r['status'])} `{r['target']}`\n")
            else:
                out.append(f"{_badge(r['status'])}\n")
            out += _render_result_body(r, max_rows, annotation)
        return out

    for qid, group in by_id.items():
        first = group[0]
        anchor = qid.replace("_", "-")
        superuser_note = " _(superuser requis)_" if first.get("requires_superuser") else ""

        lines += [
            f'<a id="{anchor}"></a>',
            f"## {first['title']}",
            f"**id :** `{qid}` | **scope :** `{first['scope']}`{superuser_note}\n",
        ]
        if first.get("description"):
            # Préfixe chaque ligne avec "> " : une description multi-lignes non
            # préfixée casserait le rendu blockquote Markdown après la première ligne.
            quoted = "\n".join(f"> {ln}" for ln in first["description"].strip().splitlines())
            lines.append(f"{quoted}\n")

        target_group = [r for r in group if r.get("side") == "target"]

        if not target_group:
            # Rétrocompat/mono-serveur : rendu inchangé, group ne contient que
            # des résultats "source" (ou sans champ side du tout, JSON pré-spec-3).
            lines += _render_group(group, first["scope"])
        else:
            source_group = [r for r in group if r.get("side", "source") == "source"]
            if source_group:
                lines.append("**Source**\n")
                lines += _render_group(source_group, first["scope"])
            lines.append("**Cible**\n")
            lines += _render_group(target_group, first["scope"])

        lines.append("---\n")

    # ── Points d'attention ───────────────────────────────────────────────────
    su_skipped = [
        r for r in all_results
        if r["status"] == "skipped" and r.get("requires_superuser")
    ]

    if errors or su_skipped:
        lines.append("## Points d'attention\n")
        if errors:
            lines.append("### Requêtes en erreur\n")
            for r in errors:
                err = r.get("error") or {}
                lines.append(
                    f"- **`{r['id']}`** sur `{r['target']}` : {err.get('message', '?')}"
                )
            lines.append("")
        if su_skipped:
            lines.append("### À relancer avec superuser\n")
            for r in su_skipped:
                lines.append(f"- **`{r['id']}`** : {r.get('skip_reason', '')}")
            lines.append("")

    return "\n".join(lines) + "\n"


_HTML_CSS = """
:root { color-scheme: light; }
body {
    font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.5;
    color: #1a1a1a;
    max-width: 60rem;
    margin: 2rem auto;
    padding: 0 1.5rem;
}
h1, h2, h3 { line-height: 1.25; }
h1 { border-bottom: 2px solid #ddd; padding-bottom: .3rem; }
h2 { border-bottom: 1px solid #eee; padding-bottom: .2rem; margin-top: 2.5rem; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .9rem; }
th, td { border: 1px solid #ddd; padding: .4rem .6rem; text-align: left; vertical-align: top; }
th { background: #f5f5f5; }
tr:nth-child(even) td { background: #fafafa; }
code { background: #f2f2f2; padding: .1rem .3rem; border-radius: 3px; font-size: .9em; }
pre { background: #f2f2f2; padding: .8rem 1rem; overflow-x: auto; border-radius: 4px; }
pre code { background: none; padding: 0; }
details { margin: .5rem 0; }
summary { cursor: pointer; color: #555; }
blockquote { border-left: 3px solid #ccc; margin: 1rem 0; padding: .2rem 1rem; color: #444; }
hr { border: none; border-top: 1px solid #ddd; margin: 2rem 0; }
@media print {
    body { max-width: none; margin: 0; }
    table { page-break-inside: avoid; }
    details { page-break-inside: avoid; }
}
"""


def render_html(markdown_text: str, title: str = "Rapport de pré-audit PostgreSQL") -> str:
    """Convertit un rapport Markdown en HTML autonome (CSS intégrée, aucun asset externe).

    `md_in_html` est nécessaire : le rapport imbrique des blocs ```sql fenced à
    l'intérieur de `<details>` (HTML brut) pour le repli du SQL exécuté — sans
    cette extension, Python-Markdown laisse ce contenu tel quel (texte brut, pas
    de coloration/mise en forme de bloc de code).
    """
    body = _markdown_lib.markdown(
        markdown_text,
        extensions=["tables", "fenced_code", "md_in_html"],
    )
    safe_title = _html.escape(title, quote=True)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="fr">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{safe_title}</title>\n<style>{_HTML_CSS}</style>\n</head>\n<body>\n"
        f"{body}\n</body>\n</html>\n"
    )
