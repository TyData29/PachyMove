-- Classement informatif (top 20), pas un contrôle bloquant : ratio tuples lus
-- (scan séquentiel + accès index) sur taille actuelle de la table. Un ratio
-- élevé signale une table "chaude", utile pour prioriser index/VACUUM/partitionnement.
-- Filtre sur la taille physique (pg_relation_size), pas sur n_live_tup : ce
-- dernier est une estimation du collecteur de stats qui peut rester à 0 sur
-- une table peu modifiée jamais passée par ANALYZE — une table réellement
-- pleine mais aux stats jamais rafraîchies était exclue à tort du classement
-- (constaté en pratique sur CCPCAM, cf. unused_indexes.sql).
SELECT schemaname AS schema_,
       relname    AS relation,
       seq_scan,
       idx_scan,
       seq_tup_read + COALESCE(idx_tup_fetch, 0) AS tuples_lus,
       n_live_tup AS tuples_total,
       ROUND(
           (seq_tup_read + COALESCE(idx_tup_fetch, 0))::numeric / NULLIF(n_live_tup, 0), 1
       ) AS ratio_lus_sur_total
FROM pg_stat_user_tables
WHERE pg_relation_size(relid) > 0
ORDER BY ratio_lus_sur_total DESC NULLS LAST
LIMIT 20
