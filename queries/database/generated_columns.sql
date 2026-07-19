-- PG18 introduit les colonnes générées virtuelles et en fait le défaut ; les colonnes
-- stockées existantes le restent après migration, mais tout DDL rejoué (dump/restore)
-- change de sémantique par défaut. attgenerated distingue stocké ('s') de virtuel ('v').
SELECT n.nspname   AS schema_,
       c.relname   AS relation,
       a.attname   AS colonne,
       t.typname   AS type_,
       a.attgenerated
FROM pg_attribute a
JOIN pg_class c     ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_type t      ON t.oid = a.atttypid
WHERE a.attnum > 0
  AND NOT a.attisdropped
  AND a.attgenerated <> ''
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schema_, relation, colonne
