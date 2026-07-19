-- Depuis PG15, le schéma public n'accorde plus le droit de création à tous par défaut.
-- Un applicatif qui créait des objets dans public sans droit explicite cassera après
-- migration. grantee = 0 désigne PUBLIC. Exception à la convention « zéro ligne = sain » :
-- une ligne ici est plutôt rassurante côté source (le droit existe encore).
SELECT n.nspname                AS schema_,
       pg_get_userbyid(n.nspowner) AS proprietaire,
       a.grantee::regrole::text AS beneficiaire,
       a.privilege_type
FROM pg_namespace n
CROSS JOIN LATERAL aclexplode(COALESCE(n.nspacl, acldefault('n', n.nspowner))) AS a
WHERE n.nspname = 'public'
  AND a.grantee = 0
  AND a.privilege_type = 'CREATE'
