SELECT e.extname,
       e.extversion,
       n.nspname       AS schema,
       e.extrelocatable
FROM pg_extension e
JOIN pg_namespace n ON n.oid = e.extnamespace
ORDER BY e.extname
