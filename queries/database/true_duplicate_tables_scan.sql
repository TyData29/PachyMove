-- Gabarit exécuté une fois par table candidate découverte
-- (duplicate_tables_structure_candidates.sql), composé par le moteur — jamais
-- exécuté tel quel. Empreinte de contenu, comparée en Python (deux tables du
-- même groupe structure avec la même empreinte ET le même nombre de lignes =
-- vrai doublon). Pas d'échantillonnage : un hash sur un échantillon ne prouve
-- rien. Cf. specs_data_quality_on_tables.md §4.5.
WITH bucketed AS (
    SELECT (hashtextextended(t::text, 0) % 1024) AS bucket,
           md5(t::text) AS row_hash
    FROM {schema}.{table} AS t
),
chunks AS (
    SELECT bucket,
           count(*) AS cnt,
           md5(coalesce(string_agg(row_hash, '' ORDER BY row_hash), '')) AS chunk_hash
    FROM bucketed
    GROUP BY bucket
)
SELECT sum(cnt) AS nb_lignes,
       md5(coalesce(string_agg(chunk_hash, '' ORDER BY chunk_hash), '')) AS empreinte
FROM chunks
