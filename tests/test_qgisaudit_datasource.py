from __future__ import annotations

from qgisaudit_runner.datasource import determine_mode_connexion, parse_datasource


def test_parse_datasource_service_example_from_spec():
    raw = "service='sig_prod' key='id' srid=2154 type=Point table=\"urbanisme\".\"parcelles\" (geom) sql="
    ds = parse_datasource(raw)

    assert ds.get("service") == "sig_prod"
    assert ds.get("key") == "id"
    assert ds.get("srid") == "2154"
    assert ds.get("type") == "Point"
    assert ds.schema == "urbanisme"
    assert ds.table == "parcelles"
    assert ds.geom_column == "geom"
    assert determine_mode_connexion(ds) == "service"


def test_parse_datasource_embedded_example_from_spec():
    raw = (
        "host=192.168.0.12 port=5432 dbname='CCPCAM' user='chloe' password='xxx' "
        "key='id' table=\"aep\".\"conduites\" (geom)"
    )
    ds = parse_datasource(raw)

    assert ds.get("host") == "192.168.0.12"
    assert ds.get("port") == "5432"
    assert ds.get("dbname") == "CCPCAM"
    assert ds.get("user") == "chloe"
    assert ds.get("password") == "xxx"
    assert ds.schema == "aep"
    assert ds.table == "conduites"
    assert determine_mode_connexion(ds) == "embarquee"


def test_parse_datasource_authcfg_example_with_spaces_in_table_name():
    raw = 'host=192.168.0.12 dbname=\'CCPCAM\' authcfg=abc123 table="public"."Point de comptage" (geom)'
    ds = parse_datasource(raw)

    assert ds.get("authcfg") == "abc123"
    assert ds.schema == "public"
    assert ds.table == "Point de comptage"
    assert ds.geom_column == "geom"
    assert determine_mode_connexion(ds) == "authcfg"


def test_determine_mode_connexion_defaults_to_embarquee_without_recognized_keys():
    ds = parse_datasource("some=thing that has none of the usual keys")
    assert determine_mode_connexion(ds) == "embarquee"


def test_parse_datasource_missing_table_leaves_schema_table_none():
    ds = parse_datasource("service='sig_prod'")
    assert ds.schema is None
    assert ds.table is None
    assert ds.geom_column is None


def test_parse_datasource_empty_string_does_not_raise():
    ds = parse_datasource("")
    assert ds.params == {}
    assert ds.schema is None


def test_parse_datasource_get_returns_none_for_empty_value():
    ds = parse_datasource("password= host=10.0.0.1")
    assert ds.get("password") is None
    assert ds.get("host") == "10.0.0.1"
