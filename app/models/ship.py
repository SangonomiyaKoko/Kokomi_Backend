from app.core import EnvConfig
from app.constants import GameData
from app.database import MySQLManager
from app.loggers import ExceptionLogger
from app.response import JSONResponse


class ShipModel:
    @ExceptionLogger.handle_database_exception_async
    async def get_version_battles():
        async with MySQLManager.read_only_cursor() as cur:
            result = {}
            sql = """
                SELECT game_version, total_battles 
                FROM V_version_battles_total;
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
            for row in rows:
                result[row[0]] = row[1]
            return JSONResponse.success(result)

    @ExceptionLogger.handle_program_exception_async
    async def get_ship_staging_overview():
        async with MySQLManager.read_only_cursor() as cur:
            result = {
                'pending': 0,
                'done': 0,
                'error': 0
            }
            sql = """
                SELECT 
                    status,
                    COUNT(*) as count
                FROM STAGING_ship_recent_data
                GROUP BY status;
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
            for row in rows:
                if row[0] in result:
                    result[row[0]] = row[1]

            return JSONResponse.success(result)

    @ExceptionLogger.handle_database_exception_async
    async def get_ranking_ship_ids():
        async with MySQLManager.read_only_cursor() as cur:
            result = {}
            sql = """
                SELECT 
                    ship_id, 
                    min_battles 
                FROM V_ship_ranking_stats;
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
            for row in rows:
                result[row[0]] = row[1]
            return JSONResponse.success(result)
        
    @ExceptionLogger.handle_database_exception_async
    async def get_ranking_ship_stats():
        async with MySQLManager.read_only_cursor() as cur:
            result = {}
            sql = """
                SELECT 
                    ship_id, 
                    min_battles,
                    stats_battles, 
                    win_rate, 
                    avg_damage, 
                    avg_frags 
                FROM V_ship_ranking_stats;
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
            for row in rows:
                if row[2] < 1000:
                    continue
                result[row[0]] = [row[1], [row[3], row[4], row[5]]]
            return JSONResponse.success(result)
            
    @ExceptionLogger.handle_database_exception_async
    async def get_ship_base():
        async with MySQLManager.read_only_cursor() as cur:
            sql = """
                SELECT
                    ship_id, 
                    is_old,
                    tier,
                    type_id,
                    nation_id
                FROM
                    T_ship_base 
                WHERE is_enabled = 1;
            """
            await cur.execute(sql)
            rows = await cur.fetchall()

            result = {} 
            for row in rows:
                result[str(row[0])] = [
                    row[1],
                    row[2],
                    GameData.SHIP_TYPE_MAP.get(row[3], 'Destroyer'), 
                    GameData.SHIP_NATION_MAP.get(row[4], 'usa')
                ]
            return JSONResponse.success(result)

    @ExceptionLogger.handle_database_exception_async
    async def get_ship_stats():
        async with MySQLManager.read_only_cursor() as cur:
            sql = """
                SELECT 
                    b.ship_id, 
                    s.battles,
                    s.win_rate, 
                    s.avg_damage, 
                    s.avg_frags
                FROM T_ship_base b
                LEFT JOIN T_ship_stats_by_battles s 
                  ON b.ship_id = s.ship_id
                WHERE b.is_enabled = 1; 
            """
            await cur.execute(sql)
            rows = await cur.fetchall()

            result = {}
            for row in rows:
                if row[1] and row[1] >= 1000:
                    result[str(row[0])] = [
                        row[2],
                        row[3],
                        row[4]
                    ]
        
        return JSONResponse.success(result)
        
    @ExceptionLogger.handle_database_exception_async
    async def get_all_ship_stats():
        async with MySQLManager.read_only_cursor() as cur:
            result = {}
            sql = """
                SELECT 
                    ship_id, 
                    battles, 
                    win_rate,
                    avg_damage, 
                    avg_frags 
                FROM T_ship_stats_by_battles;
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
            for row in rows:
                if row[1] > 0:
                    result[row[0]] = [row[1], row[2], row[3], row[4]]
            return JSONResponse.success(result)
        
    @ExceptionLogger.handle_database_exception_async
    async def refresh_ship_base(ships: dict):
        async with MySQLManager.auto_transaction_cursor() as cur:
            result = {
                'insert': 0,
                'update': 0,
                'disable': 0
            }

            constant = EnvConfig.get_constants()
            sql = """
                SELECT
                    ship_id, 
                    is_enabled
                FROM T_ship_base;
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
            existing_ship_ids = []
            enabled_ship_ids = []
            for row in rows:
                existing_ship_ids.append(row[0])
                if row[1]:
                    enabled_ship_ids.append(row[0])

            for ship_id, ship_row in ships.items():
                ship_id = int(ship_id)
                if ship_id not in existing_ship_ids:
                    sql = """
                        INSERT INTO T_ship_base (
                            ship_id, is_enabled, is_old, tier, type_id,
                            nation_id, rarity_id, premium, special, index_code, ship_name
                        ) VALUES (%s, TRUE, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """
                    await cur.execute(sql, [ship_id] + ship_row)

                    for table_name in constant.SHIP_INIT_TABLE_LIST:
                        sql = f"INSERT INTO {table_name} (ship_id) VALUES (%s);"
                        cur.execute(sql, [ship_id])
                    
                    pvp_data = []
                    for metric_id in [3, 4, 5, 7, 8, 9]:
                        pvp_data.append((ship_id, metric_id))
                    sql = """
                        INSERT INTO T_ship_pvp_record (ship_id, metric_id) VALUES (%s, %s);
                    """
                    await cur.executemany(sql, pvp_data)
                    result['insert'] += 1
                else:
                    sql = """
                        UPDATE T_ship_base
                        SET 
                            is_enabled = TRUE, 
                            is_old = %s, 
                            rarity_id = %s, 
                            premium = %s, 
                            special = %s 
                        WHERE ship_id = %s;
                    """
                    await cur.execute(sql, [ship_id, ship_row[0], ship_row[4], ship_row[5], ship_row[6]])
                    result['update'] += 1

            for ship_id in enabled_ship_ids:
                if str(ship_id) not in ships:
                    sql = """
                        UPDATE T_ship_base SET is_enabled = FALSE WHERE ship_id = %s;
                    """
                    await cur.execute(sql, [ship_id])
                    result['disable'] += 1

        return JSONResponse.success(result)