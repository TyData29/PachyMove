SELECT datname,
       pg_size_pretty(pg_database_size(datname))  AS taille,
       pg_catalog.pg_get_userbyid(datdba)          AS proprietaire,
       pg_encoding_to_char(encoding)               AS encodage,
       datcollate                                   AS collation
FROM pg_database
WHERE datistemplate = false
ORDER BY pg_database_size(datname) DESC
