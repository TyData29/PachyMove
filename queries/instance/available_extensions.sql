-- Ce que j'utilise existe-t-il côté cible, et en quelle version ? La comparaison
-- PostGIS est celle qui décide souvent de la faisabilité. installed_version reflète
-- uniquement le maintenance-db de connexion, pas les bases réellement migrées —
-- default_version (disponibilité à l'échelle de l'instance) est la colonne fiable
-- pour la comparaison source/cible.
SELECT name, default_version, installed_version, comment
FROM pg_available_extensions
ORDER BY name
