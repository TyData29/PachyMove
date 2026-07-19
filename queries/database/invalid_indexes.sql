-- Un index invalide/non prêt est en général le résidu d'un REINDEX CONCURRENTLY
-- interrompu — à reconstruire ou supprimer avant migration.
SELECT n.nspname AS schema_,
       t.relname AS relation,
       i.relname AS index_,
       x.indisvalid,
       x.indisready,
       x.indislive
FROM pg_index x
JOIN pg_class i     ON i.oid = x.indexrelid
JOIN pg_class t     ON t.oid = x.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE NOT (x.indisvalid AND x.indisready AND x.indislive)
