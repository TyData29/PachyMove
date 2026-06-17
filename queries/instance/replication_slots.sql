-- Un slot logique actif avec wal_level=replica bloque pg_upgrade.
-- Tout slot non consommé retient les WAL et gonfle pg_wal.
SELECT slot_name,
       slot_type,
       database,
       active,
       active_pid,
       xmin,
       catalog_xmin,
       restart_lsn,
       confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name
