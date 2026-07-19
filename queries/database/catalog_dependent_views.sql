-- Une vue lisant pg_stat_activity, pg_shadow ou toute autre table système peut casser :
-- les colonnes des catalogues changent entre versions majeures.
SELECT DISTINCT
       n.nspname  AS schema_,
       c.relname  AS vue,
       c.relkind,
       dn.nspname AS catalogue_reference,
       dc.relname AS objet_reference
FROM pg_depend d
JOIN pg_rewrite r    ON r.oid = d.objid
JOIN pg_class c      ON c.oid = r.ev_class
JOIN pg_namespace n  ON n.oid = c.relnamespace
JOIN pg_class dc     ON dc.oid = d.refobjid
JOIN pg_namespace dn ON dn.oid = dc.relnamespace
WHERE d.classid = 'pg_rewrite'::regclass
  AND d.refclassid = 'pg_class'::regclass
  AND dn.nspname = 'pg_catalog'
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND c.relkind IN ('v', 'm')
ORDER BY 1, 2
