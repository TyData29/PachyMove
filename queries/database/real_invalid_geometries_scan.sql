-- Gabarit exécuté une fois par colonne géométrie découverte
-- (geometry_columns_discovery.sql), composé par le moteur — jamais exécuté tel
-- quel. Pas d'échantillonnage : cf. specs_data_quality_on_tables.md §4.3.
SELECT count(*) FILTER (WHERE NOT ST_IsValid({column})) AS geometries_invalides,
       count({column}) AS geometries_non_nulles
FROM {schema}.{table}
HAVING count(*) FILTER (WHERE NOT ST_IsValid({column})) > 0
