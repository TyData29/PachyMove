-- Classement informatif (top 25), pas un contrôle bloquant : les plus
-- grosses tables conditionnent la durée de dump/restore et de reconstruction
-- des index lors d'une migration — à surveiller en priorité pour le
-- dimensionnement de la fenêtre de bascule. Classement par taille physique
-- (MB), pas par n_live_tup : n_live_tup est affiché à titre indicatif
-- seulement, c'est une estimation du collecteur de stats qui peut rester à 0
-- sur une table peu modifiée jamais passée par ANALYZE (cf. unused_indexes.sql).
SELECT n.nspname AS schema_,
       c.relname AS relation,
       ROUND(pg_total_relation_size(c.oid) / 1024.0 / 1024.0, 1) AS taille_totale_mb,
       ROUND(pg_relation_size(c.oid) / 1024.0 / 1024.0, 1)       AS taille_table_mb,
       ROUND(
           (pg_total_relation_size(c.oid) - pg_relation_size(c.oid)) / 1024.0 / 1024.0, 1
       )                                                          AS taille_index_toast_mb,
       s.n_live_tup
FROM pg_class c
JOIN pg_namespace n         ON n.oid = c.relnamespace
LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg\_temp\_%'
  AND n.nspname NOT LIKE 'pg\_toast\_temp\_%'
ORDER BY pg_total_relation_size(c.oid) DESC
LIMIT 25
