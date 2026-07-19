-- Une transaction préparée en attente bloque pg_upgrade net — souvent le résidu
-- d'un applicatif transactionnel mal arrêté, à résoudre côté client avant migration.
SELECT gid, prepared, owner, database
FROM pg_prepared_xacts
