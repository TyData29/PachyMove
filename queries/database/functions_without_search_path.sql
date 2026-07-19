-- Depuis PG17, ANALYZE/CLUSTER/REINDEX/VACUUM et le rafraîchissement de vue matérialisée
-- s'exécutent avec un search_path restreint. Une fonction appelée par un index
-- d'expression ou une vue matérialisée qui ne fixe pas son search_path échouera à ce
-- moment-là — la migration et le restore passent, le premier VACUUM casse en prod.
WITH fonctions_indexees AS (
    SELECT DISTINCT d.refobjid AS oid_fonction
    FROM pg_depend d
    JOIN pg_index x ON x.indexrelid = d.objid
    WHERE d.classid = 'pg_class'::regclass
      AND d.refclassid = 'pg_proc'::regclass
      AND x.indexprs IS NOT NULL
    UNION
    SELECT DISTINCT d.refobjid
    FROM pg_depend d
    JOIN pg_rewrite r ON r.oid = d.objid
    JOIN pg_class c   ON c.oid = r.ev_class
    WHERE d.classid = 'pg_rewrite'::regclass
      AND d.refclassid = 'pg_proc'::regclass
      AND c.relkind = 'm'
)
SELECT n.nspname AS schema_,
       p.proname AS fonction,
       pg_get_function_identity_arguments(p.oid) AS arguments,
       p.prosecdef AS security_definer,
       p.proconfig
FROM fonctions_indexees f
JOIN pg_proc p      ON p.oid = f.oid_fonction
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND (p.proconfig IS NULL
       OR NOT EXISTS (
            SELECT 1 FROM unnest(p.proconfig) AS cfg
            WHERE cfg LIKE 'search\_path=%'
       ))
ORDER BY 1, 2
