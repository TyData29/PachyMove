-- pg_auth_members ne donne que l'appartenance directe (niveau 1) : un rôle
-- membre d'un groupe lui-même membre d'un autre groupe hérite des droits sans
-- apparaître explicitement — la récursion reconstitue la chaîne complète.
WITH RECURSIVE membership AS (
    SELECT am.member::regrole AS role,
           am.roleid::regrole AS groupe,
           1                  AS niveau
    FROM pg_auth_members am
    UNION ALL
    SELECT m.role,
           am.roleid::regrole,
           m.niveau + 1
    FROM membership m
    JOIN pg_auth_members am ON am.member = m.groupe
)
SELECT DISTINCT role, groupe, niveau
FROM membership
ORDER BY role, niveau
