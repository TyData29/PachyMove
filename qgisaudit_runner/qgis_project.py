from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .datasource import Datasource, parse_datasource

_FILE_PROVIDERS = {"ogr", "gdal"}


class ProjectParseError(Exception):
    """Fichier illisible/corrompu — à capturer par l'appelant (log + continuer)
    afin de respecter la spec §7 : ne jamais arrêter le scan sur un fichier."""


@dataclass
class LayerInfo:
    nom_couche: str
    provider: str
    datasource_raw: str
    parsed: Optional[Datasource] = None

    @property
    def categorie(self) -> str:
        if self.provider == "postgres":
            return "pg"
        if self.provider in _FILE_PROVIDERS:
            return "fichier"
        return "autres"


def _extract_qgs_text(path: Path) -> str:
    if path.suffix.lower() == ".qgz":
        try:
            with zipfile.ZipFile(path) as zf:
                names = [n for n in zf.namelist() if n.lower().endswith(".qgs")]
                if not names:
                    raise ProjectParseError(f"aucun .qgs dans l'archive : {path}")
                base = path.stem
                preferred = [n for n in names if Path(n).stem == base]
                chosen = preferred[0] if preferred else names[0]
                with zf.open(chosen) as f:
                    return f.read().decode("utf-8", errors="replace")
        except zipfile.BadZipFile as e:
            raise ProjectParseError(f"archive .qgz invalide : {path} ({e})") from e
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise ProjectParseError(f"fichier illisible : {path} ({e})") from e


def parse_project(path: Path) -> list[LayerInfo]:
    """Extrait les couches d'un projet .qgs/.qgz. Lève ProjectParseError sur
    tout fichier illisible/corrompu — à l'appelant de logguer et continuer
    (spec §7), jamais géré silencieusement ici."""
    text = _extract_qgs_text(path)

    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ProjectParseError(f"XML invalide : {path} ({e})") from e

    layers: list[LayerInfo] = []
    for maplayer in root.iter("maplayer"):
        datasource_el = maplayer.find("datasource")
        if datasource_el is None or not (datasource_el.text or "").strip():
            continue  # groupe/annotation sans datasource (spec §7)

        provider_el = maplayer.find("provider")
        name_el = maplayer.find("layername")
        provider = (provider_el.text or "").strip() if provider_el is not None else ""
        name = (name_el.text or "").strip() if name_el is not None else ""
        raw_ds = datasource_el.text or ""

        layer = LayerInfo(nom_couche=name, provider=provider, datasource_raw=raw_ds)
        if provider == "postgres":
            layer.parsed = parse_datasource(raw_ds)
        layers.append(layer)

    return layers
