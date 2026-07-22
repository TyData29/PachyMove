-- Gabarit exécuté une fois par colonne découverte (discover_all_columns.sql),
-- composé par le moteur — jamais exécuté tel quel. Cf. specs_data_quality_on_tables.md §4.2.
SELECT count(DISTINCT {column}) AS valeurs_distinctes,
       count(*) AS total
FROM {schema}.{table} {sample}
HAVING count(*) > 0
   AND count(DISTINCT {column}) = 1
