SELECT n.nspname       AS schema,
       c.relname       AS table_name,
       fs.srvname      AS foreign_server,
       ft.ftoptions    AS options
FROM pg_foreign_table ft
JOIN pg_class c           ON c.oid = ft.ftrelid
JOIN pg_namespace n       ON n.oid = c.relnamespace
JOIN pg_foreign_server fs ON fs.oid = ft.ftserver
ORDER BY n.nspname, c.relname
