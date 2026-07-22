-- Adapté du calibrage pgAdmin (comptage par schéma) à la convention de l'outil :
-- une ligne = un objet fautif, pas un total agrégé, pour rester cohérent avec
-- "zéro ligne = sain" et permettre expect_rows. Regex plutôt que simple
-- détection de majuscules : couvre aussi les identifiants entre guillemets avec
-- espaces/tirets.
SELECT n.nspname  AS schema_,
       c.relname  AS objet,
       'relation' AS categorie
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'v', 'm', 'p', 'S')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND c.relname !~ '^[a-z_][a-z0-9_]*$'

UNION ALL

SELECT n.nspname, a.attname, 'colonne'
FROM pg_attribute a
JOIN pg_class c     ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p', 'v', 'm')
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND a.attname !~ '^[a-z_][a-z0-9_]*$'

ORDER BY 1, 3, 2
