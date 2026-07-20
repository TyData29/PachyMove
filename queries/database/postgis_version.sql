-- Échoue proprement si PostGIS n'est pas installée dans cette base (fonctions
-- inexistantes). Volontairement pas PostGIS_Full_Version() : si l'extension
-- postgis_raster est enregistrée au catalogue mais que sa bibliothèque
-- ($libdir/postgis_raster-X) est absente du serveur — vu en pratique après un
-- dump/restore vers un serveur au paquetage incomplet — cette fonction échoue en
-- interrogeant raster en interne. La version de raster est lue directement dans
-- pg_extension, sans appeler aucune fonction raster.
SELECT PostGIS_Lib_Version()   AS lib_version,
       PostGIS_GEOS_Version()  AS geos_version,
       PostGIS_PROJ_Version()  AS proj_version,
       (SELECT extversion FROM pg_extension WHERE extname = 'postgis_raster') AS raster_extversion
