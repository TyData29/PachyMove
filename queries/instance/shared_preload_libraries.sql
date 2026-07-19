-- Renvoie des lignes même quand tout va bien : c'est un inventaire, pas une détection.
-- Sa valeur est comparative — ces bibliothèques doivent exister côté serveur cible.
SELECT unnest(string_to_array(setting, ',')) AS bibliotheque
FROM pg_settings
WHERE name = 'shared_preload_libraries'
  AND setting <> ''
