-- Table sans clé primaire : pas d'identité de ligne fiable, réplication logique
-- impossible, tout outil de synchronisation/CDC bloqué. Note : une table
-- partitionnée porte parfois sa PK au niveau parent seulement — chaque
-- partition fille apparaît alors ici individuellement (faux positif connu).
SELECT n.nspname AS schema_,
       c.relname AS relation
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg\_temp\_%'
  AND n.nspname NOT LIKE 'pg\_toast\_temp\_%'
  AND NOT EXISTS (
      SELECT 1 FROM pg_constraint co
      WHERE co.conrelid = c.oid AND co.contype = 'p'
  )
ORDER BY 1, 2
