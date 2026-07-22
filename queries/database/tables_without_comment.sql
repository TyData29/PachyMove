-- Signal faible, purement informatif : utile pour prioriser la documentation
-- d'un schéma repris sans historique. Tag "info", jamais bloquant/vigilance.
SELECT n.nspname AS schema_,
       c.relname AS relation
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'v', 'm')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND obj_description(c.oid, 'pg_class') IS NULL
ORDER BY 1, 2
