-- Découverte pour la requête dérivée deprecated_tables_no_recent_timestamp.
-- Une table sans aucune colonne temporelle n'apparaît jamais ici — limite
-- assumée, documentée en specs_data_quality_on_tables.md §4.4.
SELECT n.nspname AS schema_,
       c.relname AS relation,
       a.attname AS colonne
FROM pg_attribute a
JOIN pg_class c     ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_type t      ON t.oid = a.atttypid
WHERE c.relkind IN ('r', 'p')
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND t.typname IN ('date', 'timestamp', 'timestamptz')
ORDER BY 1, 2, 3
