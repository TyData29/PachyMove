-- Colonne géométrie sans index spatial (GIST/SP-GIST) : tout filtre ou jointure
-- spatiale (ST_Intersects, ST_DWithin...) dégénère en scan séquentiel, invisible
-- sur une petite table de test, bloquant en volume réel.
SELECT gc.f_table_schema    AS schema_,
       gc.f_table_name      AS relation,
       gc.f_geometry_column AS colonne
FROM geometry_columns gc
JOIN pg_namespace n ON n.nspname = gc.f_table_schema
JOIN pg_class c     ON c.relname = gc.f_table_name AND c.relnamespace = n.oid
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = gc.f_geometry_column
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_index x
    JOIN pg_class ic ON ic.oid = x.indexrelid
    JOIN pg_am am    ON am.oid = ic.relam
    WHERE x.indrelid = c.oid
      AND a.attnum = ANY(x.indkey)
      AND am.amname IN ('gist', 'spgist')
)
ORDER BY 1, 2, 3
