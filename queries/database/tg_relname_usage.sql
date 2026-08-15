-- TG_RELNAME est la variable spéciale historique des fonctions trigger
-- PL/pgSQL, documentée comme dépréciée (remplacée par TG_TABLE_NAME,
-- disponible depuis longtemps) et pouvant disparaître dans une future
-- version majeure. Heuristique de scan du texte source (comme
-- fk_like_columns_without_constraint.sql) : ne prouve pas qu'un remplacement
-- est nécessaire (le mot pourrait apparaître en commentaire), mais signal
-- fiable vu la spécificité du nom.
SELECT n.nspname                                   AS schema_,
       p.proname                                   AS fonction,
       pg_get_function_identity_arguments(p.oid)    AS arguments,
       l.lanname                                    AS langage
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
JOIN pg_language l  ON l.oid = p.prolang
WHERE p.prorettype = 'trigger'::regtype
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND p.prosrc ILIKE '%TG_RELNAME%'
ORDER BY 1, 2
