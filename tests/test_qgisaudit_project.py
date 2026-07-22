from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from qgisaudit_runner.qgis_project import ProjectParseError, parse_project

_QGS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<qgis version="3.28">
  <projectlayers>
    <maplayer type="vector">
      <id>layer1</id>
      <datasource>service='sig_prod' key='id' table="urbanisme"."parcelles" (geom)</datasource>
      <layername>Parcelles</layername>
      <provider encoding="UTF-8">postgres</provider>
    </maplayer>
    <maplayer type="vector">
      <id>layer2</id>
      <datasource>/data/shapefile.shp</datasource>
      <layername>Shapefile Layer</layername>
      <provider encoding="UTF-8">ogr</provider>
    </maplayer>
    <maplayer type="raster">
      <id>layer3</id>
      <datasource>crs=EPSG:3857&amp;url=https://example.com/wms&amp;layers=x</datasource>
      <layername>WMS Layer</layername>
      <provider>wms</provider>
    </maplayer>
    <maplayer type="group">
      <id>group1</id>
      <layername>Groupe sans datasource</layername>
    </maplayer>
  </projectlayers>
</qgis>
"""


def test_parse_project_qgs_categorizes_layers(tmp_path: Path):
    qgs = tmp_path / "projet.qgs"
    qgs.write_text(_QGS_XML, encoding="utf-8")

    layers = parse_project(qgs)

    assert len(layers) == 3  # le groupe sans datasource est ignoré
    categories = {l.nom_couche: l.categorie for l in layers}
    assert categories == {"Parcelles": "pg", "Shapefile Layer": "fichier", "WMS Layer": "autres"}

    pg_layer = next(l for l in layers if l.categorie == "pg")
    assert pg_layer.parsed is not None
    assert pg_layer.parsed.get("service") == "sig_prod"
    assert pg_layer.parsed.table == "parcelles"


def test_parse_project_qgz_extracts_inner_qgs_same_basename(tmp_path: Path):
    qgz = tmp_path / "projet.qgz"
    with zipfile.ZipFile(qgz, "w") as zf:
        zf.writestr("projet.qgs", _QGS_XML)
        zf.writestr("autre.qgs", "<qgis></qgis>")  # ne doit pas être choisi

    layers = parse_project(qgz)

    assert len(layers) == 3


def test_parse_project_qgz_falls_back_to_first_qgs_if_no_matching_basename(tmp_path: Path):
    qgz = tmp_path / "monprojet.qgz"
    with zipfile.ZipFile(qgz, "w") as zf:
        zf.writestr("interne.qgs", _QGS_XML)

    layers = parse_project(qgz)

    assert len(layers) == 3


def test_parse_project_qgz_without_inner_qgs_raises_project_parse_error(tmp_path: Path):
    qgz = tmp_path / "vide.qgz"
    with zipfile.ZipFile(qgz, "w") as zf:
        zf.writestr("readme.txt", "rien ici")

    with pytest.raises(ProjectParseError):
        parse_project(qgz)


def test_parse_project_invalid_zip_raises_project_parse_error(tmp_path: Path):
    qgz = tmp_path / "corrompu.qgz"
    qgz.write_bytes(b"not a zip file at all")

    with pytest.raises(ProjectParseError):
        parse_project(qgz)


def test_parse_project_invalid_xml_raises_project_parse_error(tmp_path: Path):
    qgs = tmp_path / "corrompu.qgs"
    qgs.write_text("<qgis><projectlayers><maplayer>", encoding="utf-8")  # non fermé

    with pytest.raises(ProjectParseError):
        parse_project(qgs)


def test_parse_project_layer_without_provider_element_is_not_pg(tmp_path: Path):
    xml = """<?xml version="1.0"?>
<qgis>
  <projectlayers>
    <maplayer>
      <datasource>/data/x.gpkg</datasource>
      <layername>Sans provider</layername>
    </maplayer>
  </projectlayers>
</qgis>
"""
    qgs = tmp_path / "p.qgs"
    qgs.write_text(xml, encoding="utf-8")

    layers = parse_project(qgs)

    assert len(layers) == 1
    assert layers[0].categorie == "autres"
    assert layers[0].parsed is None
