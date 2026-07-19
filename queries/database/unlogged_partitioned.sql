-- PG18 interdit les tables partitionnées UNLOGGED — avant, la déclaration était
-- acceptée mais sans effet.
SELECT n.nspname AS schema_,
       c.relname AS relation,
       c.relpersistence
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'p'
  AND c.relpersistence = 'u'
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
