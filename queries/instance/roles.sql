SELECT r.rolname,
       r.rolsuper,
       r.rolinherit,
       r.rolcreaterole,
       r.rolcreatedb,
       r.rolcanlogin,
       r.rolreplication,
       r.rolbypassrls,
       r.rolconnlimit,
       r.rolvaliduntil::text AS rolvaliduntil,
       ARRAY(
           SELECT m.rolname
           FROM pg_auth_members am
           JOIN pg_roles m ON m.oid = am.roleid
           WHERE am.member = r.oid
       ) AS membre_de
FROM pg_roles r
WHERE r.rolname NOT LIKE 'pg_%'
ORDER BY r.rolname
