-- Pendant de collation_version_mismatch.sql pour la collation par défaut de la base,
-- qui n'apparaît pas dans pg_collation. Cette requête compare la source à elle-même ;
-- elle ne dit rien de la glibc du serveur cible.
SELECT d.datname,
       d.datcollate,
       d.datctype,
       d.datcollversion                            AS version_enregistree,
       pg_database_collation_actual_version(d.oid) AS version_systeme
FROM pg_database d
WHERE d.datallowconn
  AND NOT d.datistemplate
  AND d.datcollversion IS DISTINCT FROM pg_database_collation_actual_version(d.oid)
