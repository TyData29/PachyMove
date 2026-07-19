-- PG18 active les sommes de contrôle par défaut à l'initialisation. pg_upgrade exige
-- que les deux clusters aient le même réglage — sans objet en dump/restore.
SELECT name, setting
FROM pg_settings
WHERE name = 'data_checksums'
  AND setting = 'off'
