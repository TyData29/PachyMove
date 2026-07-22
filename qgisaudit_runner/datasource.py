from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# table="schema"."table" (colonne_geom) — toujours entre guillemets doubles côté
# QGIS, peut contenir des espaces (ex. "Point de comptage"). Traité à part du
# tokenizer générique ci-dessous : ses valeurs sont entre guillemets doubles,
# pas simples, et sa forme (deux identifiants + parenthèse) ne rentre pas dans
# le patron clé=valeur des autres paramètres.
_TABLE_RE = re.compile(r'table="([^"]*)"\."([^"]*)"\s*\(([^)]*)\)')

# Valeur entre guillemets simples (peut contenir des espaces), entre guillemets
# doubles, ou non quotée (\S*, jamais \S+ : gère une clé sans valeur en fin de
# chaîne, ex. "sql=" en toute fin — cf. spec §6, exemple 1).
_KV_RE = re.compile(r"(\w+)=(?:'([^']*)'|\"([^\"]*)\"|(\S*))")


@dataclass
class Datasource:
    params: dict[str, str] = field(default_factory=dict)
    schema: Optional[str] = None
    table: Optional[str] = None
    geom_column: Optional[str] = None

    def get(self, key: str) -> Optional[str]:
        return self.params.get(key) or None


def parse_datasource(raw: str) -> Datasource:
    """Parse une chaîne <datasource> QGIS (spec §6) : paramètres clé=valeur
    (guillemets simples, doubles ou non quotés) + le champ table= à part
    (schéma/table entre guillemets doubles, colonne géométrique entre
    parenthèses). Ne casse jamais si une clé attendue est absente."""
    ds = Datasource()

    table_match = _TABLE_RE.search(raw)
    remainder = raw
    if table_match:
        ds.schema = table_match.group(1) or None
        ds.table = table_match.group(2) or None
        ds.geom_column = table_match.group(3).strip() or None
        remainder = raw[: table_match.start()] + raw[table_match.end() :]

    for m in _KV_RE.finditer(remainder):
        key = m.group(1)
        value = m.group(2)
        if value is None:
            value = m.group(3)
        if value is None:
            value = m.group(4) or ""
        ds.params[key] = value

    return ds


def determine_mode_connexion(ds: Datasource) -> str:
    """Spec §5.5 : service= présent -> "service" ; sinon authcfg= -> "authcfg" ;
    sinon (host=/dbname=) -> "embarquee"."""
    if ds.get("service"):
        return "service"
    if ds.get("authcfg"):
        return "authcfg"
    return "embarquee"
