-- Catalogue seul : signale un même nom de table et/ou une même signature de
-- colonnes (nom+type, ordonnée) répétés dans des schémas différents. Ne
-- compare aucune donnée — un vrai doublon (données identiques) nécessite un
-- scan par table, hors périmètre de ce manifeste (cf. specs_data_quality.md §7
-- et le manifeste séparé data_quality_on_tables).
WITH colonnes AS (
    SELECT c.oid,
           n.nspname AS schema_,
           c.relname AS relation,
           string_agg(a.attname || ':' || t.typname, ',' ORDER BY a.attnum) AS signature
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
    JOIN pg_type t      ON t.oid = a.atttypid
    WHERE c.relkind IN ('r', 'p')
      AND n.nspname NOT IN ('pg_catalog', 'information_schema')
    GROUP BY c.oid, n.nspname, c.relname
),
doublons_nom AS (
    SELECT relation AS groupe, 'meme_nom' AS raison, schema_, relation
    FROM colonnes
    WHERE relation IN (
        SELECT relation FROM colonnes GROUP BY relation HAVING count(DISTINCT schema_) > 1
    )
),
doublons_structure AS (
    SELECT signature AS groupe, 'meme_structure' AS raison, schema_, relation
    FROM colonnes
    WHERE signature IN (
        SELECT signature FROM colonnes GROUP BY signature HAVING count(DISTINCT schema_) > 1
    )
)
SELECT * FROM doublons_nom
UNION
SELECT * FROM doublons_structure
ORDER BY raison, groupe, schema_, relation
