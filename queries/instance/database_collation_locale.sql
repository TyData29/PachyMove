-- Équivalent pour PostgreSQL < 15 de database_collation_version.sql : le suivi de
-- version de la collation par défaut d'une base (datcollversion,
-- pg_database_collation_actual_version()) n'existe qu'à partir de PG15 — sur une
-- source plus ancienne, aucune détection automatique de dérive n'est possible.
-- Seul un inventaire l'est : à comparer manuellement à la locale système si le
-- serveur a changé d'OS/glibc entre-temps (cf. le cas dump/restore Windows→Debian).
SELECT d.datname,
       d.datcollate,
       d.datctype
FROM pg_database d
WHERE d.datallowconn
  AND NOT d.datistemplate
ORDER BY d.datname
