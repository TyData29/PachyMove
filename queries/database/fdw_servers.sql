SELECT s.srvname,
       fdw.fdwname,
       s.srvoptions
FROM pg_foreign_server s
JOIN pg_foreign_data_wrapper fdw ON fdw.oid = s.srvfdw
ORDER BY s.srvname
