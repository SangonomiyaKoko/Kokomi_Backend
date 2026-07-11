from app.database import MySQLManager
from app.loggers import ExceptionLogger
from app.response import JSONResponse
from app.utils import TimeUtils


class DemoClanModel:
    @ExceptionLogger.handle_database_exception_async
    async def read_base(clan_id: int):
        '''
        从数据库中获取工会的基本数据
        '''
        async with MySQLManager.read_only_cursor() as cur:
            data = {
                'clan_id': clan_id,
                'clan_tag': None,
                'league': 5,
                'is_enabled': False
            }
            sql = """
                SELECT
                    tag,
                    league
                FROM T_clan_base
                WHERE clan_id = %s;
            """
            await cur.execute(sql, [clan_id])
            row = await cur.fetchone()
            if not row:
                return JSONResponse.API_1000_Success
            data['clan_tag'] = row[0]
            data['league'] = row[1]

            sql = """
                SELECT
                    is_enabled,
                    member_count, 
                    UNIX_TIMESTAMP(next_refresh_at) 
                FROM T_clan_users
                WHERE clan_id = %s;
            """
            await cur.execute(sql, [clan_id])
            row = await cur.fetchone()
            data['is_enabled'] = row[0]
            data['member_count'] = row[1]
            data['next_refresh_at'] = TimeUtils.fromtimestamp(row[2])
            data['now_iso_time'] = TimeUtils.now_iso()[:19].replace('T', ' ')
            return JSONResponse.success(data)
    
    @ExceptionLogger.handle_program_exception_async
    async def get_season_rows(season_id: int):
        async with MySQLManager.read_only_cursor() as cur:
            sql = f"""
                SELECT COUNT(*) FROM S_clan_battle_{season_id};
            """
            await cur.execute(sql)
            data = await cur.fetchone()
            return JSONResponse.success(data[0])

    @ExceptionLogger.handle_database_exception_async
    async def set_clan_status(clan_id: int, status: int):
        async with MySQLManager.auto_transaction_cursor() as cur:
            sql = """
                UPDATE T_clan_users 
                SET is_enabled = %s 
                WHERE clan_id = %s;
            """
            await cur.execute(sql, [status, clan_id])
            data = cur.rowcount
            return JSONResponse.success(data)

class ClanModel:
    @ExceptionLogger.handle_database_exception_async
    async def get_latest_season():
        async with MySQLManager.read_only_cursor() as cur:
            sql = """
                SELECT MAX(season) FROM T_clan_stats;
            """
            await cur.execute(sql)
            data = await cur.fetchone()
            return JSONResponse.success(data[0] if data else 0)