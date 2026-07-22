-- Séquence proche de sa valeur maximale : panne applicative certaine au premier
-- INSERT suivant l'épuisement. Seuil illustratif (80 %), non calibré.
SELECT schemaname   AS schema_,
       sequencename AS sequence_,
       last_value,
       max_value,
       ROUND(100.0 * last_value / NULLIF(max_value, 0), 1) AS pct_consomme
FROM pg_sequences
WHERE last_value IS NOT NULL
  AND last_value > 0.8 * max_value
ORDER BY pct_consomme DESC NULLS LAST
