-- Seul moyen de voir un problème de collation *entre deux serveurs* avant de
-- migrer (contrairement à collation_version_mismatch.sql, qui compare un serveur
-- à lui-même). Exécutée des deux côtés sur le maintenance-db : la comparer révèle
-- un changement de fournisseur de collation (ex. Windows source vs glibc cible).
SELECT c.collname,
       c.collprovider,
       c.collversion                      AS version_enregistree,
       pg_collation_actual_version(c.oid) AS version_systeme
FROM pg_collation c
WHERE c.collversion IS NOT NULL
ORDER BY 1
