-- PG18 marque le MD5 comme déprécié (avertissement au réglage du mot de passe) ; le
-- support sera retiré dans une version future. Migrer vers SCRAM avant est le bon
-- réflexe — faisable dès PG14. Nécessite superuser (pg_authid).
SELECT rolname,
       rolcanlogin,
       rolvaliduntil::text
FROM pg_authid
WHERE rolpassword LIKE 'md5%'
