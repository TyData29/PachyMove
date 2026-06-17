-- Nécessite superuser (accès à pg_authid).
-- L'authentification MD5 est dépréciée depuis PG14 et supprimée en PG17+.
SELECT rolname,
       left(rolpassword, 3) AS methode_stockage
FROM pg_authid
WHERE rolpassword IS NOT NULL
  AND rolpassword LIKE 'md5%'
ORDER BY rolname
