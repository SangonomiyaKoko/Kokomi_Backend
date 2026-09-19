from pymysql import Connection
from pymysql.cursors import Cursor
from shard import CommonConfig

from ..core import RunContext
from ..db_ops import mysql_transaction
from ..models import ClanRecord
from ..logger import logger


class ClanBaseSyncer:
    """把排行榜数据中的公会基础信息同步到 MySQL"""

    @staticmethod
    def _load_records(
        cursor: Cursor, clan_ids: list
    ) -> dict[int, ClanRecord]:
        """批量读取位于本地的公会赛季状态记录"""
        if not clan_ids:
            return {}

        placeholders = ','.join(['%s'] * len(clan_ids))
        sql = f"""
            SELECT
                clan_id,
                season,
                UNIX_TIMESTAMP(last_battle_at)
            FROM T_clan_stats
            WHERE clan_id IN ({placeholders});
        """
        cursor.execute(sql, clan_ids)

        return {
            row[0]: ClanRecord.from_row(row) for row in cursor.fetchall()
        }

    @staticmethod
    def _update_clan_bases(
        cursor: Cursor, entries: list
    ) -> None:
        """批量更新已存在公会的 tag 与 league"""
        if not entries:
            return

        sql = """
            UPDATE T_clan_base
            SET
                tag = %s,
                league = %s,
                updated_at = NOW()
            WHERE clan_id = %s;
        """
        params = [
            [entry.tag, entry.league, entry.clan_id] for entry in entries
        ]
        cursor.executemany(sql, params)

    @staticmethod
    def _insert_clans(
        cursor: Cursor, entries: list
    ) -> None:
        """为新公会初始化 T_clan_base 及各子表记录"""
        if not entries:
            return

        # 1. 批量插入 T_clan_base
        values_list = []
        params = []
        for entry in entries:
            values_list.append("(%s, %s, %s)")
            params.extend([entry.clan_id, entry.tag, entry.league])

        sql = f"INSERT INTO T_clan_base (clan_id, tag, league) VALUES {','.join(values_list)};"
        cursor.execute(sql, params)

        # 2. 批量插入所有子表
        for table_name in CommonConfig.CLAN_INIT_TABLE_LIST:
            values_list = []
            params = []
            for entry in entries:
                values_list.append("(%s)")
                params.append(entry.clan_id)

            sql = f"INSERT INTO {table_name} (clan_id) VALUES {','.join(values_list)};"
            cursor.execute(sql, params)

    @classmethod
    def main(
        cls, mysql_conn: Connection, run_ctx: RunContext
    ) -> list[int]:
        """同步公会基础数据，并筛选出需要刷新详情的公会"""
        with mysql_transaction(mysql_conn) as cursor:
            records = cls._load_records(
                cursor, [entry.clan_id for entry in run_ctx.clan_entries]
            )

            # 筛选出未查询到的工会，待后续插入数据库
            missing = [e for e in run_ctx.clan_entries if e.clan_id not in records]
            existing = [e for e in run_ctx.clan_entries if e.clan_id in records]

            cls._update_clan_bases(cursor, existing)
            if missing:
                cls._insert_clans(cursor, missing)
                logger.info(f'Insert new clans: {len(missing)}')

            update_ids = set()
            for entry in run_ctx.clan_entries:
                record = records.get(entry.clan_id)
                if record is None:
                    # 数据库中不存在的新公会必然需要刷新详情
                    update_ids.add(entry.clan_id)
                    continue

                if entry.last_battle_time is None:
                    # 跳过 LBT 为 None 的情况
                    continue

                if (
                    record.last_battle_time is None
                    or record.last_battle_time != entry.last_battle_time
                    or record.season != run_ctx.season_id
                ):
                    # SEASON_ID 发生更改或者 LBT 发生更改时触发刷新
                    update_ids.add(entry.clan_id)

            return list(update_ids)
