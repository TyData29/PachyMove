SELECT pubname,
       pubowner::regrole  AS proprietaire,
       puballtables,
       pubinsert,
       pubupdate,
       pubdelete,
       pubtruncate
FROM pg_publication
ORDER BY pubname
