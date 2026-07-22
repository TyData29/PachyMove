-- Découverte pour la requête dérivée true_duplicate_tables : sous-ensemble de
-- la logique de duplicate_tables_across_schemas.sql (v1), restreint aux
-- candidats structurellement identiques entre schémas — seuls ceux-là peuvent
-- avoir un contenu identique. schema_/relation seules (pas de groupe/raison,
-- inutiles pour composer le gabarit de hachage).
WITH colonnes AS (
    SELECT c.oid,
           n.nspname AS schema_,
           c.relname AS relation,
           string_agg(a.attname || ':' || t.typname, ',' ORDER BY a.attnum) AS signature
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
    JOIN pg_type t      ON t.oid = a.atttypid
    WHERE c.relkind IN ('r', 'p')
      AND n.nspname NOT IN ('pg_catalog', 'information_schema')
    GROUP BY c.oid, n.nspname, c.relname
)
SELECT schema_, relation
FROM colonnes
WHERE signature IN (
    SELECT signature FROM colonnes GROUP BY signature HAVING count(DISTINCT schema_) > 1
)
ORDER BY schema_, relation
