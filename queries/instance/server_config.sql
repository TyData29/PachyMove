SELECT name,
       setting,
       unit,
       category,
       short_desc
FROM pg_settings
WHERE name IN (
    'max_connections',
    'shared_buffers',
    'effective_cache_size',
    'work_mem',
    'maintenance_work_mem',
    'wal_level',
    'max_wal_size',
    'checkpoint_completion_target',
    'default_statistics_target',
    'log_min_duration_statement',
    'autovacuum',
    'timezone',
    'lc_messages',
    'lc_monetary',
    'lc_numeric',
    'lc_time',
    'client_encoding',
    'standard_conforming_strings',
    'escape_string_warning',
    'search_path'
)
ORDER BY category, name
