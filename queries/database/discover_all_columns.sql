-- Découverte pour les requêtes dérivées low_fill_rate_columns/constant_value_columns
-- (specs_data_quality_on_tables.md §4.1-4.2). reltuples (catalogue, approximatif,
-- aucun scan) alimente le calcul de l'échantillonnage TABLESAMPLE côté moteur.
SELECT n.nspname    AS schema_,
       c.relname    AS relation,
       a.attname    AS colonne,
       t.typname    AS type_,
       c.reltuples  AS lignes_estimees
FROM pg_attribute a
JOIN pg_class c     ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_type t      ON t.oid = a.atttypid
WHERE c.relkind IN ('r', 'p')
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1, 2, 3
