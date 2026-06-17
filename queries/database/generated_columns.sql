-- Les colonnes GENERATED ALWAYS ont une syntaxe incompatible avec pg_dump < PG12.
-- À vérifier avant migration vers PG16+ (changements de comportement).
SELECT table_schema,
       table_name,
       column_name,
       data_type,
       generation_expression
FROM information_schema.columns
WHERE is_generated = 'ALWAYS'
  AND table_schema NOT IN ('information_schema', 'pg_catalog')
ORDER BY table_schema, table_name, column_name
