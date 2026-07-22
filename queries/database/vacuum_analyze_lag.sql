-- Proxy de bloat sans dépendre de pgstattuple (souvent absente) : un ratio de
-- lignes mortes élevé et un dernier VACUUM ancien (ou jamais exécuté) signalent
-- le même risque par deux angles. Seuils illustratifs (20 %, 30 jours), non
-- calibrés — cf. specs_data_quality.md §3.
SELECT schemaname AS schema_,
       relname    AS relation,
       n_live_tup,
       n_dead_tup,
       ROUND(100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 1) AS pct_lignes_mortes,
       last_vacuum,
       last_autovacuum,
       last_analyze,
       last_autoanalyze
FROM pg_stat_user_tables
WHERE n_live_tup + n_dead_tup > 0
  AND (
        100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0) > 20
        OR GREATEST(last_vacuum, last_autovacuum) < now() - interval '30 days'
        OR (last_vacuum IS NULL AND last_autovacuum IS NULL)
      )
ORDER BY pct_lignes_mortes DESC NULLS LAST
