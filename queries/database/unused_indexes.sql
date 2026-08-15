-- Index jamais scanné (idx_scan = 0), tous types confondus (généralise
-- geometry_no_spatial_index.sql : ici l'index existe mais ne sert à rien,
-- plutôt que d'être absent). Coûte en écriture/maintenance sans bénéfice de
-- lecture mesuré. Contexte de la table jointe (seq_scan, table_taille) pour
-- distinguer une table active où l'index est vraiment mort d'une table peu
-- sollicitée où l'absence d'usage n'est pas significative. Un index qui
-- backe une contrainte PK/UNIQUE/EXCLUDE est signalé (pas supprimable sans
-- supprimer la contrainte), jamais exclu silencieusement.
-- table_taille (pg_relation_size, lu sur disque) plutôt que n_live_tup :
-- n_live_tup est une estimation entretenue par le collecteur de stats,
-- mise à jour par ANALYZE/autovacuum — sur une petite table peu modifiée,
-- le seuil d'auto-analyze n'est jamais franchi et le compteur reste à 0
-- même quand la table contient réellement des lignes (constaté en pratique
-- sur CCPCAM, ex. assainissement.qgis_projects : n_live_tup=0, 5 lignes
-- réelles). La taille physique ne dépend pas du collecteur de stats.
-- Fenêtre d'observation pour idx_scan/seq_scan : ces compteurs sont remis à
-- zéro à pg_stat_reset()/redémarrage — à confirmer sur une période
-- d'activité représentative, pas juste après un restart récent.
SELECT n.nspname                              AS schema_,
       t.relname                              AS relation,
       i.relname                              AS index_,
       am.amname                              AS type_index,
       pg_size_pretty(pg_relation_size(i.oid)) AS taille_index,
       EXISTS (
           SELECT 1 FROM pg_constraint co
           WHERE co.conindid = s.indexrelid
       )                                       AS backe_une_contrainte,
       s.idx_scan,
       ts.seq_scan                            AS table_seq_scan,
       pg_size_pretty(pg_relation_size(t.oid)) AS table_taille
FROM pg_stat_user_indexes s
JOIN pg_class i          ON i.oid = s.indexrelid
JOIN pg_class t          ON t.oid = s.relid
JOIN pg_namespace n      ON n.oid = t.relnamespace
JOIN pg_am am             ON am.oid = i.relam
JOIN pg_stat_user_tables ts ON ts.relid = t.oid
WHERE s.idx_scan = 0
  AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'topology')
ORDER BY schema_, relation, index_
