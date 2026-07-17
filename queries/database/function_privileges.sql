-- ACL explicites sur les fonctions/procédures — direct et hérité via groupes.
-- Exclusions techniques : schémas système + schémas temporaires (voir clause WHERE ci-dessous).
WITH RECURSIVE membership AS (
    SELECT am.member AS role_oid,
           am.roleid AS groupe_oid,
           1         AS niveau
    FROM pg_auth_members am
    UNION ALL
    SELECT m.role_oid,
           am.roleid,
           m.niveau + 1
    FROM membership m
    JOIN pg_auth_members am ON am.member = m.groupe_oid
),
acl_directs AS (
    SELECT n.nspname                               AS schema,
           p.oid::regprocedure::text               AS objet,
           acl.grantee                            AS role_oid,
           acl.privilege_type                     AS privilege,
           acl.grantor::regrole                   AS accorde_par
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    CROSS JOIN LATERAL aclexplode(p.proacl) AS acl(grantor, grantee, privilege_type, is_grantable)
    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
      AND n.nspname NOT LIKE 'pg\_temp\_%'
      AND n.nspname NOT LIKE 'pg\_toast\_temp\_%'
      AND p.proacl IS NOT NULL
)
SELECT schema, objet,
       role_oid::regrole AS role,
       privilege,
       'direct'::text    AS source,
       accorde_par
FROM acl_directs

UNION ALL

SELECT a.schema, a.objet,
       m.role_oid::regrole                    AS role,
       a.privilege,
       'groupe:' || a.role_oid::regrole::text AS source,
       a.accorde_par
FROM acl_directs a
JOIN membership m ON m.groupe_oid = a.role_oid
JOIN pg_roles r ON r.oid = m.role_oid AND r.rolcanlogin

ORDER BY schema, objet, role, privilege
