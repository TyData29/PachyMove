-- Gabarit exécuté une fois par colonne temporelle découverte
-- (discover_timestamp_columns.sql), composé par le moteur — jamais exécuté tel
-- quel. Filtre d'existence à 3 seuils, pas une agrégation (EXISTS court-circuite
-- dès le premier hit) ; regroupement par table en Python (collector.py), pas ici
-- — cf. specs_data_quality_on_tables.md §4.4.
SELECT EXISTS (SELECT 1 FROM {schema}.{table} WHERE {column} > now() - interval '6 months') AS recent_6_mois,
       EXISTS (SELECT 1 FROM {schema}.{table} WHERE {column} > now() - interval '1 year')   AS recent_1_an,
       EXISTS (SELECT 1 FROM {schema}.{table} WHERE {column} > now() - interval '3 years')  AS recent_3_ans
