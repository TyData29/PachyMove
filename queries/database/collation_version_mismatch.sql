-- Les index B-tree sur colonnes texte sont triés selon la collation système (glibc).
-- Si sa version a changé depuis la création, le tri peut différer silencieusement :
-- un SELECT WHERE peut ne rien renvoyer alors que la ligne existe, sans aucune erreur.
SELECT c.collname,
       c.collprovider,
       c.collversion                      AS version_enregistree,
       pg_collation_actual_version(c.oid) AS version_systeme
FROM pg_collation c
WHERE c.collversion IS NOT NULL
  AND c.collversion IS DISTINCT FROM pg_collation_actual_version(c.oid)
