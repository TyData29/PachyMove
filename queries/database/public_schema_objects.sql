SELECT c.relname                                              AS nom,
       CASE c.relkind
           WHEN 'r' THEN 'table'
           WHEN 'v' THEN 'vue'
           WHEN 'm' THEN 'vue materialisee'
           WHEN 'f' THEN 'foreign table'
           WHEN 'p' THEN 'table partitionnee'
           ELSE c.relkind::text
       END                                                    AS type,
       pg_size_pretty(pg_total_relation_size(c.oid))         AS taille_totale,
       pg_catalog.pg_get_userbyid(c.relowner)                AS proprietaire
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'v', 'm', 'f', 'p')
ORDER BY c.relkind, c.relname
