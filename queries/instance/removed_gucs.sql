-- Paramètres présents en PG14, supprimés ou renommés d'ici PG18. Limite : pg_settings
-- ne voit que ce que le serveur a chargé (un paramètre commenté dans postgresql.conf
-- n'apparaît pas) — un relevé du fichier de config reste nécessaire hors de cet outil.
SELECT name, setting, source, boot_val,
       CASE name
           WHEN 'promote_trigger_file'     THEN 'supprime en PG16'
           WHEN 'vacuum_defer_cleanup_age' THEN 'supprime en PG16'
           WHEN 'force_parallel_mode'      THEN 'renomme debug_parallel_query en PG16'
           WHEN 'old_snapshot_threshold'   THEN 'supprime en PG17'
           WHEN 'db_user_namespace'        THEN 'supprime en PG17'
           WHEN 'stats_temp_directory'     THEN 'supprime en PG15'
       END AS remarque
FROM pg_settings
WHERE name IN ('promote_trigger_file', 'vacuum_defer_cleanup_age',
               'force_parallel_mode', 'old_snapshot_threshold',
               'db_user_namespace', 'stats_temp_directory')
  AND source <> 'default'
