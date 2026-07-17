-- ACL explicites (aclexplode) + héritage via groupes + propriété. has_*_privilege()
-- ne donne qu'un effectif (oui/non), pas l'origine du droit (spec module droits §2-4).
-- Exclusions techniques uniquement (schémas système) — pas d'exclusion de rôles
-- système : la matrice reste exhaustive, le filtrage est la responsabilité du diff.
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
    SELECT n.nspname                             AS schema,
           c.relname                             AS objet,
           c.relkind                             AS type_objet,
           (aclexplode(c.relacl)).grantee        AS role_oid,
           (aclexplode(c.relacl)).privilege_type AS privilege,
           (aclexplode(c.relacl)).grantor::regrole AS accorde_par
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind IN ('r', 'v', 'm', 'f', 'S')
      AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
      AND n.nspname NOT LIKE 'pg\_temp\_%'
      AND n.nspname NOT LIKE 'pg\_toast\_temp\_%'
      AND c.relacl IS NOT NULL
),
proprietaires AS (
    SELECT n.nspname       AS schema,
           c.relname       AS objet,
           c.relkind       AS type_objet,
           c.relowner      AS role_oid,
           '(owner)'::text AS privilege
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind IN ('r', 'v', 'm', 'f', 'S')
      AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
      AND n.nspname NOT LIKE 'pg\_temp\_%'
      AND n.nspname NOT LIKE 'pg\_toast\_temp\_%'
)
SELECT schema, objet, type_objet,
       role_oid::regrole    AS role,
       privilege,
       'direct'::text       AS source,
       accorde_par
FROM acl_directs

UNION ALL

SELECT a.schema, a.objet, a.type_objet,
       m.role_oid::regrole                    AS role,
       a.privilege,
       'groupe:' || a.role_oid::regrole::text AS source,
       a.accorde_par
FROM acl_directs a
JOIN membership m ON m.groupe_oid = a.role_oid
JOIN pg_roles r ON r.oid = m.role_oid AND r.rolcanlogin

UNION ALL

SELECT schema, objet, type_objet,
       role_oid::regrole    AS role,
       privilege,
       'proprietaire'::text AS source,
       NULL::regrole        AS accorde_par
FROM proprietaires

ORDER BY schema, objet, role, privilege
