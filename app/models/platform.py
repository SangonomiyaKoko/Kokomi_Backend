from app.database import MySQLManager
from app.loggers import ExceptionLogger
from app.response import JSONResponse


class PlatformModel:
    @ExceptionLogger.handle_database_exception_async
    async def read_table_meta():
        """读取数据库元信息（T_table_meta 表）"""
        async with MySQLManager.read_only_cursor() as cur:
            sql = """
                SELECT
                    metric_key,
                    metric_value
                FROM T_table_meta;
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
            data = {row[0]: row[1] for row in rows}
            return JSONResponse.success(data)
        
    @ExceptionLogger.handle_database_exception_async
    async def read_database_meta():
        """读取数据库元信息（T_database_meta 表）"""
        async with MySQLManager.read_only_cursor() as cur:
            sql = """
                SELECT
                    metric_key,
                    metric_value
                FROM T_database_meta;
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
            data = {row[0]: row[1] for row in rows}
            return JSONResponse.success(data)
        
    @ExceptionLogger.handle_database_exception_async
    async def read_latest_version():
        async with MySQLManager.read_only_cursor() as cur:
            sql = """
                SELECT 
                    short_name 
                FROM T_game_version 
                WHERE is_latest = TRUE 
                LIMIT 1;
            """
            await cur.execute(sql)
            data = await cur.fetchone()

            return JSONResponse.success(data[0] if data else None)
        
    @ExceptionLogger.handle_database_exception_async
    async def read_table_meta():
        async with MySQLManager.read_only_cursor() as cur:
            sql = """
                SELECT 
                    metric_key, 
                    metric_value 
                FROM T_table_meta;
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
            data = {}
            for row in rows:
                data[row[0]] = row[1]
            return JSONResponse.success(data)

    @ExceptionLogger.handle_database_exception_async
    async def read_archive_base_count():
        """读取 ARCH_base_count 归档表的实体总数每日变化

        Returns:
            success → {code: 1000, data: [(stat_date, total_count), ...]}
        """
        async with MySQLManager.read_only_cursor() as cur:
            sql = """   
                SELECT
                    stat_date,
                    total_count
                FROM ARCH_base_count
                ORDER BY stat_date ASC;
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
            data = [(row[0].isoformat() if hasattr(row[0], 'isoformat') else str(row[0]), row[1]) for row in rows]
            return JSONResponse.success(data)

    @ExceptionLogger.handle_database_exception_async
    async def read_user_refresh_stats():
        """读取用户刷新计划分布

        Returns:
            success → {code: 1000, data: [(status, user_count, clan_count), ...]}
        """
        async with MySQLManager.read_only_cursor() as cur:
            sql = """
                SELECT
                    status,
                    user_count,
                    clan_count
                FROM T_refresh_stats
                ORDER BY
                    CASE status
                        WHEN 'overdue' THEN 1
                        WHEN 'within_24h' THEN 2
                        WHEN 'within_week' THEN 3
                        WHEN 'within_month' THEN 4
                        WHEN 'within_quarter' THEN 5
                    END;
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
            data = [(row[0], row[1], row[2]) for row in rows]
            return JSONResponse.success(data)

    @ExceptionLogger.handle_database_exception_async
    async def read_clan_activity_distribution():
        """读取用户活跃度分布 (0-3) 从 T_clan_activity

        Returns:
            success → {code: 1000, data: [(activity_level, cnt), ...]}
        """
        async with MySQLManager.read_only_cursor() as cur:
            sql = """
                SELECT
                    clan_level,
                    clan_count
                FROM T_clan_activity
                ORDER BY clan_level;
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
            data = [(row[0], row[1]) for row in rows]
            return JSONResponse.success(data)

    @ExceptionLogger.handle_database_exception_async
    async def read_user_activity_distribution():
        """读取用户活跃度分布 (0-9) 从 T_user_activity

        Returns:
            success → {code: 1000, data: [(activity_level, cnt), ...]}
        """
        async with MySQLManager.read_only_cursor() as cur:
            sql = """
                SELECT
                    user_level,
                    user_count
                FROM T_user_activity
                ORDER BY user_level;
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
            data = [(row[0], row[1]) for row in rows]
            return JSONResponse.success(data)

    @ExceptionLogger.handle_database_exception_async
    async def read_user_refresh_hourly_stats():
        """读取未来24h刷新计划每小时分布

        Returns:
            success → {code: 1000, data: [(planned_hour, planned_users, planned_clans), ...]}
        """
        async with MySQLManager.read_only_cursor() as cur:
            sql = """
                SELECT
                    planned_hour,
                    planned_users,
                    planned_clans
                FROM T_refresh_hourly_stats
                ORDER BY planned_hour;
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
            data = [(row[0], row[1], row[2]) for row in rows]
            return JSONResponse.success(data)

    @ExceptionLogger.handle_database_exception_async
    async def reset_tracking_time(tracking_key: str, tracking_type: str):
        """将指定追踪键和类型的记录置为 NULL，触发服务立即刷新"""
        async with MySQLManager.auto_transaction_cursor() as cur:
            sql = """
                UPDATE T_tracking_meta 
                SET 
                    tracking_value = NULL 
                WHERE tracking_key = %s 
                  AND tracking_type = %s;
            """
            await cur.execute(sql, [tracking_key, tracking_type])
            
            return JSONResponse.API_1000_Success