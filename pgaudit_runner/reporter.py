from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

_BADGES: dict[str, str] = {"success": "✅", "skipped": "⏭️", "error": "❌"}


def _badge(status: str) -> str:
    return _BADGES.get(status, "❓")


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
    errors = [r for r in all_results if r["status"] == "error"]
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
