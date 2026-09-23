from pymysql.cursors import Cursor
from sqlite3 import Cursor as SQLiteCursor

from .settings import MAX_DISPATCH_PER_ROUND


class BasicDataRepository:

    @staticmethod
    def get_pending_count(cursor: Cursor) -> int:
        """获取待更新用户总数"""
        sql = """
            SELECT COUNT(*)
            FROM T_user_ships
            WHERE pending_at > 0;
        """
        cursor.execute(sql)
        return cursor.fetchone()[0]

    @staticmethod
    def get_update_ids(cursor: Cursor) -> list:
        """按待更新时间从早到晚获取本轮待更新的用户 ID 列表"""
        sql = """
            SELECT account_id
            FROM T_user_ships
            WHERE pending_at > 0
            ORDER BY pending_at ASC
            LIMIT %s;
        """
        cursor.execute(sql, [MAX_DISPATCH_PER_ROUND])
        return [row[0] for row in cursor.fetchall()]

    @staticmethod
    def get_ship_records(cursor: Cursor) -> tuple:
        """读取启用船只的记录值，无记录行的船只按 0 补齐"""
        sql = """
            SELECT
                b.ship_id,
                COALESCE(r.exp, 0),
                COALESCE(r.frags, 0),
                COALESCE(r.planes, 0),
                COALESCE(r.damage, 0),
                COALESCE(r.scouting, 0),
                COALESCE(r.potential, 0)
            FROM T_ship_base b
            LEFT JOIN T_ship_record r
              ON b.ship_id = r.ship_id
            WHERE b.is_enabled = 1;
        """
        cursor.execute(sql)
        return cursor.fetchall()

    @staticmethod
    def get_ship_benchmarks(cursor: Cursor) -> tuple:
        """读取启用船只的等级与服务端均值，无统计行的船只均值为 0"""
        sql = """
            SELECT
                b.ship_id,
                b.tier,
                COALESCE(s.battles, 0),
                COALESCE(s.win_rate, 0),
                COALESCE(s.avg_damage, 0),
                COALESCE(s.avg_frags, 0)
            FROM T_ship_base b
            LEFT JOIN T_ship_stats_by_battles s
              ON b.ship_id = s.ship_id
            WHERE b.is_enabled = 1;
        """
        cursor.execute(sql)
        return cursor.fetchall()

    @staticmethod
    def get_game_version(cursor: Cursor) -> tuple:
        """读取最新游戏版本的名称与版本开始时间"""
        sql = """
            SELECT
                short_name,
                UNIX_TIMESTAMP(created_at)
            FROM T_game_version
            WHERE is_latest = TRUE
            LIMIT 1;
        """
        cursor.execute(sql)
        version = cursor.fetchone()
        if not version:
            return None, None

        return version[0], version[1]

    @staticmethod
    def get_user_ships(cursor: Cursor, account_id: int) -> tuple:
        """读取用户本地储存的船只缓存数据与更新时间戳"""
        sql = """
            SELECT
                payload,
                UNIX_TIMESTAMP(updated_at)
            FROM T_user_ships
            WHERE account_id = %s;
        """
        cursor.execute(sql, [account_id])
        return cursor.fetchone()

    @staticmethod
    def upsert_ship_leaderboard(cursor: Cursor, rows: list) -> None:
        """批量写入船只排行榜数据"""
        if not rows:
            return

        sql = """
            INSERT INTO T_ship_leaderboard (
                account_id, ship_id, battles, rating, win_rate, solo_rate,
                avg_damage, avg_frags, avg_exp, hit_ratio, max_exp, max_damage,
                updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
            )
            ON DUPLICATE KEY UPDATE
                battles = VALUES(battles),
                rating = VALUES(rating),
                win_rate = VALUES(win_rate),
                solo_rate = VALUES(solo_rate),
                avg_damage = VALUES(avg_damage),
                avg_frags = VALUES(avg_frags),
                avg_exp = VALUES(avg_exp),
                hit_ratio = VALUES(hit_ratio),
                max_exp = VALUES(max_exp),
                max_damage = VALUES(max_damage),
                updated_at = NOW();
        """
        cursor.executemany(sql, rows)

    @staticmethod
    def update_user_ships(
        cursor: Cursor,
        account_id: int,
        ship_count: int,
        user_level: int,
        payload: bytes
    ) -> None:
        """更新用户船只缓存数据并清除待更新标记"""
        sql = """
            UPDATE T_user_ships
            SET
                ship_count = %s,
                user_level = %s,
                payload = %s,
                pending_at = 0,
                updated_at = NOW()
            WHERE account_id = %s;
        """
        cursor.execute(sql, [ship_count, user_level, payload, account_id])

    @staticmethod
    def update_ship_records(cursor: Cursor, rows: list) -> None:
        """批量刷新船只记录值"""
        if not rows:
            return

        sql = """
            INSERT INTO T_ship_record (
                exp, frags, planes, damage, scouting, potential, ship_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s
            )
            ON DUPLICATE KEY UPDATE
                exp = VALUES(exp),
                frags = VALUES(frags),
                planes = VALUES(planes),
                damage = VALUES(damage),
                scouting = VALUES(scouting),
                potential = VALUES(potential),
                updated_at = NOW();
        """
        cursor.executemany(sql, rows)


class VersionRepository:
    """版本 SQLite 数据库的写入操作

    每个游戏版本一个文件（data/version/{version}.db），按船只累加本版本的战斗增量。
    """

    @staticmethod
    def add_recent_stats(
        cursor: SQLiteCursor, ship_id: int, diff: list
    ) -> None:
        """累加单个船只的本版本近期数据"""
        sql = """
            INSERT INTO ship_recent_stats (
                ship_id, battles, wins, damage, frags,
                exp, survived, scouting_damage, potential_damage, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP
            )
            ON CONFLICT (ship_id) DO UPDATE SET
                battles = battles + excluded.battles,
                wins = wins + excluded.wins,
                damage = damage + excluded.damage,
                frags = frags + excluded.frags,
                exp = exp + excluded.exp,
                survived = survived + excluded.survived,
                scouting_damage = scouting_damage + excluded.scouting_damage,
                potential_damage = potential_damage + excluded.potential_damage,
                updated_at = CURRENT_TIMESTAMP;
        """
        cursor.execute(sql, [ship_id] + list(diff))
