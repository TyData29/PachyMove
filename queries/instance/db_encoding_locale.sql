-- SQL_ASCII = aucune validation d'encodage (bombe à retardement), datconnlimit = -2
-- = base marquée invalide (résidu d'un DROP DATABASE interrompu), ou base non connectable.
SELECT d.datname,
       pg_encoding_to_char(d.encoding) AS encodage,
       d.datcollate,
       d.datctype,
       d.datconnlimit,
       d.datallowconn
FROM pg_database d
WHERE NOT d.datistemplate
  AND (pg_encoding_to_char(d.encoding) = 'SQL_ASCII'
       OR d.datconnlimit = -2
       OR NOT d.datallowconn)
