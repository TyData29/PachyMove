-- Colonnes géométrie sans SRID déclaré (srid = 0) : source classique de bugs de
-- reprojection silencieux, ou de comparaisons spatiales dont le référentiel
-- n'est en réalité pas garanti identique.
SELECT f_table_schema    AS schema_,
       f_table_name      AS relation,
       f_geometry_column AS colonne,
       coord_dimension,
       srid,
       type
FROM geometry_columns
WHERE srid = 0
  AND f_table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1, 2, 3
