-- Extensions contrib supprimées entre PG14 et PG18. Liste à étendre au fil des
-- découvertes — volontairement séparée de extensions.sql (inventaire) pour un
-- verdict distinct.
SELECT e.extname,
       e.extversion,
       n.nspname AS schema_,
       CASE e.extname
           WHEN 'adminpack' THEN 'supprime en PG17'
       END AS remarque
FROM pg_extension e
JOIN pg_namespace n ON n.oid = e.extnamespace
WHERE e.extname IN ('adminpack')
