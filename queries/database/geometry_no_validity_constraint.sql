-- Indicateur indirect : l'absence de contrainte CHECK imposant ST_IsValid() ne
-- prouve pas qu'il existe des géométries cassées, seulement que rien n'empêche
-- d'en insérer. Un vrai scan de données par table sortirait du modèle "une
-- requête statique par contrôle" de l'outil (cf. specs_data_quality.md §7).
SELECT gc.f_table_schema    AS schema_,
       gc.f_table_name      AS relation,
       gc.f_geometry_column AS colonne
FROM geometry_columns gc
JOIN pg_namespace n ON n.nspname = gc.f_table_schema
JOIN pg_class c     ON c.relname = gc.f_table_name AND c.relnamespace = n.oid
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_constraint co
    WHERE co.conrelid = c.oid
      AND co.contype = 'c'
      AND pg_get_constraintdef(co.oid) ILIKE '%st_isvalid%'
)
ORDER BY 1, 2, 3
