INSERT INTO D_ranking_battles_limit 
    (tier, battles_limit) 
VALUES
    (6, 40),
    (7, 40),
    (8, 40),
    (9, 50),
    (10, 60),
    (11, 60);

INSERT INTO D_metric_name
    (name)
VALUES
    ('battles'),
    ('wins'),
    ('damage'),
    ('frags'),
    ('exp'),
    ('survived'),
    ('scouting_dmg'),
    ('potential_dmg'),
    ('planes'),
    ('rating');

INSERT INTO T_base_id
    (meta)
VALUES
    ('user'),
    ('clan'),
    ('ship');

INSERT INTO T_metric_level_thresholds 
    (metric_id, threshold)
VALUES
    (3, 0.8), (3, 0.95), (3, 1.0), (3, 1.1), (3, 1.2), (3, 1.4), (3, 1.7),
    (4, 0.2), (4, 0.3), (4, 0.6), (4, 1.0), (4, 1.3), (4, 1.5), (4, 2.0);

INSERT INTO T_tracking_meta 
    (tracking_key, tracking_type) 
VALUES
    ('base_table', 'archive_time'),
    ('ship_stats', 'update_time'),
    ('clan_season', 'refresh_time');

INSERT INTO T_database_meta 
    (metric_key) 
VALUES
    ('mysql_tables'),
    ('mysql_rows'),
    ('mysql_size_kb'),
    ('sqlite_files'),
    ('sqlite_size_kb');

INSERT INTO T_table_meta 
    (metric_key, table_name) 
VALUES
    ('base_users', 'user_base'),
    ('base_clans', 'clan_base'),
    ('base_ships', 'ship_base'),
    ('recent_lv1', 'user_config'),
    ('recent_lv2', 'user_config'),
    ('planned_users', 'user_stats'),
    ('planned_clans', 'clan_users'),
    ('total_users', 'user_pvp'),
    ('ship_entries', 'user_pvp'),
    ('total_battles', 'user_pvp'),
    ('leaderboard_rows', 'ship_pvp_leaderboard');

INSERT INTO T_refresh_stats 
    (status)
VALUES
    ('overdue'),
    ('within_24h'),
    ('within_week'),
    ('within_month'),
    ('within_quarter');

INSERT INTO T_refresh_hourly_stats
    (planned_hour)
VALUES
    (1),(2),(3),(4),(5),(6),(7),(8),(9),(10),
    (11),(12),(13),(14),(15),(16),(17),(18),(19),(20),
    (21),(22),(23),(24);

INSERT INTO T_user_activity 
    (user_level)
VALUES
    (0),(1),(2),(3),(4),(5),(6),(7),(8),(9);

INSERT INTO T_clan_activity 
    (clan_level)
VALUES
    (0),(1),(2),(3);