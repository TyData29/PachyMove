-- Découverte pour la requête dérivée real_invalid_geometries (vrai scan des
-- données, à distinguer de geometry_srid_missing.sql/geometry_generic_type.sql
-- en v1 qui lisent geometry_columns comme un contrôle catalogue en soi).
SELECT f_table_schema    AS schema_,
       f_table_name      AS relation,
       f_geometry_column AS colonne
FROM geometry_columns
WHERE f_table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1, 2, 3
