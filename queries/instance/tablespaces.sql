-- Un tablespace hors du répertoire de données complique pg_upgrade et impose que
-- le chemin existe à l'identique côté cible.
SELECT spcname,
       pg_get_userbyid(spcowner)   AS proprietaire,
       pg_tablespace_location(oid) AS emplacement
FROM pg_tablespace
WHERE spcname NOT IN ('pg_default', 'pg_global')
