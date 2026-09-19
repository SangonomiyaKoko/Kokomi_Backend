import uuid
import json
from pymysql.cursors import Cursor
from collections import defaultdict

from .logger import logger


def get_agg_rows(cursor: Cursor):
    """从暂存表中读取待处理数据条数
    
    Args:
        cursor: 数据库游标
    """
    sql = """
        SELECT 
            count(*)
        FROM STAGING_ship_recent_data
        WHERE status = 'pending';
    """
    cursor.execute(sql)
    return cursor.fetchone()[0]

def read_recent_data(cursor, last_uuid, batch_size):
    """从 STAGING_ship_recent_data 中读取一批 pending 数据"""
    if last_uuid is None:
        sql = """
            SELECT uuid, game_version, account_id, payload
            FROM STAGING_ship_recent_data
            WHERE status = 'pending'
            ORDER BY uuid
            LIMIT %s
        """
        cursor.execute(sql, [batch_size])
    else:
        sql = """
            SELECT uuid, game_version, account_id, payload
            FROM STAGING_ship_recent_data
            WHERE status = 'pending' AND uuid > %s
            ORDER BY uuid
            LIMIT %s
        """
        cursor.execute(sql, [last_uuid, batch_size])
    return cursor.fetchall()

def verify_ship_exist(cursor: Cursor, version: str, ship_ids: list) -> None:
    """确保近期数据存档表包含最新版本下所有船只的记录

    读取全量 ship_id 和最新版本号，检查归档表中是否已有该版本的数据条目，
    若不存在则插入一条空数据记录

    Args:
        cursor: 数据库游标
        version: 游戏版本
        ship_ids: 船只ID列表
    """
    # 查询已归档的 ship_id + version 组合
    sql = """
        SELECT 
            ship_id 
        FROM ARCH_ship_stats_by_recent 
        WHERE game_version = %s;
    """
    cursor.execute(sql, [version])
    archived_ids = {row[0] for row in cursor.fetchall()}
    
    # 找出未归档的 ship_id
    missing_ids = [sid for sid in ship_ids if sid not in archived_ids]
    if not missing_ids:
        return 
    
    # 补全归档表
    for ship_id in missing_ids:
        sql = """
            INSERT INTO ARCH_ship_stats_by_recent (
                ship_id, game_version
            )
            VALUES (
                %s, %s
            );
        """
        cursor.execute(sql, [ship_id, version])

    logger.info(f'Table ARCH_ship_stats_by_recent inserted: {len(missing_ids)}')

def cleanup_done_rows(cursor: Cursor) -> int:
    """删除暂存表中已处理完成的旧数据

    Args:
        cursor: 数据库游标

    Returns:
        删除的行数
    """
    sql = """
        DELETE FROM STAGING_ship_recent_data 
        WHERE status = 'done';
    """
    cursor.execute(sql)

    return cursor.rowcount

def aggregate_recent(cursor: Cursor, ship_aggregator: dict) -> None:
    sql = """
        UPDATE ARCH_ship_stats_by_recent
        SET
            battles = battles + %s,
            wins = wins + %s,
            damage = damage + %s,
            frags = frags + %s,
            exp = exp + %s,
            survived = survived + %s,
            scouting_damage = scouting_damage + %s,
            potential_damage = potential_damage + %s
        WHERE ship_id = %s 
          AND game_version = %s;
    """
    for game_ver, ship_dict in ship_aggregator.items():
        for ship_id, vals in ship_dict.items():
            cursor.execute(sql, (
                vals[0], vals[1], vals[2], vals[3], vals[4], vals[5], vals[6], vals[7],
                ship_id, game_ver
            ))

def update_status(cursor: Cursor, update_status_params: list) -> None:
    if len(update_status_params) > 0:
        sql = """
            UPDATE STAGING_ship_recent_data
            SET 
                status = %s, 
                payload = %s, 
                processed_at = NOW() 
            WHERE uuid = %s;
        """
        cursor.executemany(sql, update_status_params)
    
def insert_error(cursor: Cursor, insert_error_params: list) -> None:
    if len(insert_error_params) > 0:
        sql = """
            INSERT INTO STAGING_ship_recent_data (
                uuid, game_version, account_id, payload, status
            ) VALUES (
                %s, %s, %s, %s, 'error'
            );
        """
        cursor.executemany(sql, insert_error_params)

class ShipRecentAggregator:
    """舰船近期数据聚合类"""
    def __init__(self, ship_ids: list):
        """
        初始化舰船统计数据聚合器
        """
        self.ship_ids = ship_ids
        # 按版本分组累加，结构: {game_version: {ship_id: [8 vals]}}
        self.ship_aggregator = defaultdict(lambda: defaultdict(lambda: [0] * 8))
        self.update_status_params = []       # (new_status, new_payload, uuid)
        self.insert_error_params = []        # (uuid, game_version, account_id, error_payload)

    def add_batch(self, rows: list[tuple]) -> None:
        """处理一批原始缓存数据，并累加到服务器统计与用户 Rating 分布中
        
        Args:
            rows: 数据库查询结果列表
        """
        for uuid_val, game_version, account_id, payload_str in rows:
            try:
                payload = json.loads(payload_str)
            except (json.JSONDecodeError, TypeError):
                self.update_status_params.append(('error', payload_str, uuid_val))
                continue
            known = {}
            unknown = {}

            for ship_id_str, stats in payload.items():
                ship_id = int(ship_id_str) if ship_id_str.isdigit() else None
                if ship_id is None or ship_id not in self.ship_ids:
                    unknown[ship_id_str] = stats
                else:
                    known[ship_id_str] = stats

            if not known:
                self.update_status_params.append(('error', payload_str, uuid_val))
                continue

            for ship_id_str, stats in known.items():
                ship_id = int(ship_id_str)
                safe = (list(stats) + [0] * 8)[:8]
                agg = self.ship_aggregator[game_version][ship_id]
                agg[0] += safe[0]
                agg[1] += safe[1]
                agg[2] += safe[2]
                agg[3] += safe[3]
                agg[4] += safe[4]
                agg[5] += safe[5]
                agg[6] += safe[6]
                agg[7] += safe[7]

            known_payload = json.dumps(known)
            self.update_status_params.append(('done', known_payload, uuid_val))

            if unknown:
                unknown_payload = json.dumps(unknown)
                self.insert_error_params.append(
                    (str(uuid.uuid4()), game_version, account_id, unknown_payload)
                )

    def get_ship_aggregator(self):
        return self.ship_aggregator
    
    def get_error_params(self):
        return self.insert_error_params
    
    def get_status_params(self):
        return self.update_status_params