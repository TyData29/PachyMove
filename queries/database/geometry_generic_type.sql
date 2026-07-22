-- Colonne déclarée en type géométrique générique (GEOMETRY, GEOMETRYCOLLECTION)
-- plutôt qu'un type précis : aucune contrainte de forme à l'insertion, source
-- classique de mélange de géométries hétérogènes dans une même colonne.
SELECT f_table_schema    AS schema_,
       f_table_name      AS relation,
       f_geometry_column AS colonne,
       type,
       coord_dimension,
       srid
FROM geometry_columns
WHERE type IN ('GEOMETRY', 'GEOMETRYCOLLECTION')
  AND f_table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1, 2, 3
