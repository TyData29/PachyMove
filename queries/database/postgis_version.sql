-- Échoue proprement si PostGIS n'est pas installée dans cette base.
SELECT PostGIS_Full_Version()  AS version_complete,
       PostGIS_Lib_Version()   AS lib_version,
       PostGIS_GEOS_Version()  AS geos_version,
       PostGIS_PROJ_Version()  AS proj_version
