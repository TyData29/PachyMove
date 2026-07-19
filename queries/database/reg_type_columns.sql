-- Une colonne de type regclass/regproc/regoper... stocke un OID de catalogue.
-- pg_dump ne peut pas le restituer de façon fiable : les OID changent d'instance à l'autre.
SELECT n.nspname AS schema_,
       c.relname AS relation,
       a.attname AS colonne,
       t.typname AS type_
FROM pg_attribute a
JOIN pg_class c     ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_type t      ON t.oid = a.atttypid
WHERE a.attnum > 0
  AND NOT a.attisdropped
  AND c.relkind IN ('r', 'p', 'm')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND t.typname IN ('regproc', 'regprocedure', 'regoper', 'regoperator',
                     'regclass', 'regcollation', 'regconfig', 'regdictionary',
                     'regnamespace', 'regrole')
