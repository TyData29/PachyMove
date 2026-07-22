-- Gabarit exécuté une fois par table candidate découverte
-- (duplicate_tables_structure_candidates.sql), composé par le moteur — jamais
-- exécuté tel quel. Empreinte de contenu, comparée en Python (deux tables du
-- même groupe structure avec la même empreinte ET le même nombre de lignes =
-- vrai doublon). Pas d'échantillonnage : un hash sur un échantillon ne prouve
-- rien. Cf. specs_data_quality_on_tables.md §4.5.
SELECT count(*) AS nb_lignes,
       md5(coalesce(string_agg(md5(t::text), '' ORDER BY md5(t::text)), '')) AS empreinte
FROM {schema}.{table} AS t
