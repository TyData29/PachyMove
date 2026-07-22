-- Heuristique de nommage, pas une preuve : signale les candidats à vérifier
-- manuellement. Une colonne *_id sans FK déclarée peut légitimement stocker un
-- identifiant externe (autre système, autre base). Détecter de vraies lignes
-- orphelines nécessiterait de lire les données (cf. specs_data_quality.md §7).
SELECT n.nspname AS schema_,
       c.relname AS relation,
       a.attname AS colonne
FROM pg_attribute a
JOIN pg_class c     ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND a.attname ~ '_id$'
  AND a.attname <> 'id'
  AND NOT EXISTS (
      SELECT 1 FROM pg_constraint co
      WHERE co.conrelid = c.oid
        AND co.contype = 'f'
        AND a.attnum = ANY(co.conkey)
  )
ORDER BY 1, 2, 3
