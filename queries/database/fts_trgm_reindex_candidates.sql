-- PG18 : la recherche plein texte (tsvector) et pg_trgm utilisent désormais
-- le fournisseur de collation par défaut du cluster au lieu de toujours
-- utiliser libc — un REINDEX peut être nécessaire après la migration pour
-- ces index précisément. Inventaire, pas un défaut en soi : ne s'applique
-- que si le fournisseur par défaut du cluster cible diffère de libc (à
-- confirmer via collation_versions.sql, side: both).
SELECT n.nspname AS schema_,
       t.relname AS relation,
       i.relname AS index_,
       am.amname AS type_index,
       oc.opcname AS classe_operateur
FROM pg_index x
JOIN pg_class i     ON i.oid = x.indexrelid
JOIN pg_class t     ON t.oid = x.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
JOIN pg_am am       ON am.oid = i.relam
CROSS JOIN LATERAL unnest(x.indclass) AS opclass_oid
JOIN pg_opclass oc  ON oc.oid = opclass_oid
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND (oc.opcname = 'tsvector_ops' OR oc.opcname LIKE '%trgm%')
ORDER BY 1, 2, 3
