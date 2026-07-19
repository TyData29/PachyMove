from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

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


def extraire_synthese(results: list[dict]) -> list[dict]:
    """Retourne les constats de gravité, tous résultats confondus.

    Deux sources :
      - convention de colonnes : le résultat expose 'severite' et 'constat'
      - expect_rows : le manifeste déclare un nombre de lignes attendu
    La convention de colonnes prime si les deux sont présentes.
    """
    entries: list[dict] = []

    for r in results:
        if r.get("status") != "success":
            continue

        columns = r.get("columns") or []
        rows = r.get("rows") or []
        base = "—" if r.get("scope") == "instance" else r.get("target", "—")
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
            row_count = r.get("row_count") or 0
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
    header = "| " + " | ".join(columns) + " |"
    sep = "|" + "|".join(" --- " for _ in columns) + "|"
    body_lines = [
        "| " + " | ".join(str(row.get(c, "")).replace("|", "\\|") for c in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, sep, *body_lines]) + "\n"


def _sql_block(sql: str) -> str:
    return f"<details>\n<summary>SQL exécuté</summary>\n\n```sql\n{sql}\n```\n\n</details>\n"


def _render_result_body(r: dict, max_rows: int) -> list[str]:
    lines: list[str] = []
    status = r["status"]

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
    conn = meta["connection"]

    # Groupement par id, ordre de première apparition
    by_id: OrderedDict[str, list[dict]] = OrderedDict()
    for r in all_results:
        by_id.setdefault(r["id"], []).append(r)

    lines: list[str] = []

    # ── En-tête ──────────────────────────────────────────────────────────────
    started = meta["started_at"][:19].replace("T", " ")
    targets = ", ".join(conn.get("databases_targeted") or []) or "—"
    version = conn.get("server_version") or "inconnu"

    lines += [
        "# Rapport de pré-audit PostgreSQL\n",
        f"**Manifeste :** {meta['manifest_name']}  ",
        f"**Date :** {started}  ",
        f"**Serveur :** {version}  ",
        f"**Bases ciblées :** {targets}  ",
        (
            f"**Résumé :** {summary['total']} requêtes — "
            f"✅ {summary['success']} succès / "
            f"⏭️ {summary['skipped']} ignorées / "
            f"❌ {summary['error']} erreurs"
        ),
        "\n---\n",
    ]

    # ── Synthèse ─────────────────────────────────────────────────────────────
    errors = [r for r in all_results if r["status"] == "error"]

    if _synthese_engagee(all_results):
        entries = extraire_synthese(all_results)
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
    for qid, group in by_id.items():
        first = group[0]
        anchor = qid.replace("_", "-")
        superuser_note = " _(superuser requis)_" if first.get("requires_superuser") else ""

        lines += [
            f'<a id="{anchor}"></a>',
            f"## {first['title']}",
            f"**id :** `{qid}` | **scope :** `{first['scope']}`{superuser_note}\n",
        ]

        if first["scope"] == "database":
            for r in group:
                lines.append(f"### {_badge(r['status'])} `{r['target']}`\n")
                lines += _render_result_body(r, max_rows)
        else:
            r = first
            lines.append(f"{_badge(r['status'])}\n")
            lines += _render_result_body(r, max_rows)

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
