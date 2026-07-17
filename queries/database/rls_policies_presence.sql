-- Signale la présence de RLS sans en auditer le détail : une ligne SELECT dans
-- la matrice de droits ne garantit pas un accès à toutes les lignes si des
-- politiques RLS existent sur la table (spec module droits §9).
SELECT n.nspname                                                       AS schema,
       c.relname                                                       AS objet,
       c.relrowsecurity                                                AS rls_active,
       c.relforcerowsecurity                                           AS rls_forcee,
       COUNT(p.policyname)                                             AS nb_politiques,
       ARRAY_AGG(p.policyname) FILTER (WHERE p.policyname IS NOT NULL) AS politiques
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_policies p ON p.schemaname = n.nspname AND p.tablename = c.relname
WHERE c.relkind = 'r'
  AND (c.relrowsecurity OR c.relforcerowsecurity OR p.policyname IS NOT NULL)
  AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
  AND n.nspname NOT LIKE 'pg\_temp\_%'
  AND n.nspname NOT LIKE 'pg\_toast\_temp\_%'
GROUP BY n.nspname, c.relname, c.relrowsecurity, c.relforcerowsecurity
ORDER BY schema, objet
