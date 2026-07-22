-- Gabarit exécuté une fois par colonne découverte (discover_all_columns.sql),
-- composé par le moteur (schéma/table/colonne + échantillon éventuel) — jamais
-- exécuté tel quel. Cf. specs_data_quality_on_tables.md §3-4.1.
SELECT count(*) AS total,
       count({column}) AS non_nuls,
       ROUND(100.0 * count({column}) / NULLIF(count(*), 0), 1) AS pct_remplissage
FROM {schema}.{table} {sample}
HAVING count(*) > 0
   AND 100.0 * count({column}) / NULLIF(count(*), 0) < 10
