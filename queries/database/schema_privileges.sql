-- ACL explicites sur les schémas (USAGE et droit de créer des objets) — direct et hérité via groupes.
-- Mêmes exclusions techniques que droits_objets_relations.sql.
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
           (aclexplode(n.nspacl)).grantee          AS role_oid,
           (aclexplode(n.nspacl)).privilege_type   AS privilege,
           (aclexplode(n.nspacl)).grantor::regrole AS accorde_par
    FROM pg_namespace n
    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
      AND n.nspname NOT LIKE 'pg\_temp\_%'
      AND n.nspname NOT LIKE 'pg\_toast\_temp\_%'
      AND n.nspacl IS NOT NULL
)
SELECT schema,
       role_oid::regrole AS role,
       privilege,
       'direct'::text    AS source,
       accorde_par
FROM acl_directs

UNION ALL

SELECT a.schema,
       m.role_oid::regrole                    AS role,
       a.privilege,
       'groupe:' || a.role_oid::regrole::text AS source,
       a.accorde_par
FROM acl_directs a
JOIN membership m ON m.groupe_oid = a.role_oid
JOIN pg_roles r ON r.oid = m.role_oid AND r.rolcanlogin

ORDER BY schema, role, privilege
