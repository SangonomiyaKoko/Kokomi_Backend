import json
import uuid
import traceback
from redis import Redis
from requests import Session
from pymysql import Connection
from pymysql.cursors import Cursor
from typing import Optional

from logger import logger
from exception import write_exception
from api import fetch_user_pvp_data
from utils import calc_ship_rating


class UserCacheUpdater:
    """用户 PvP 缓存数据更新器

    负责从 API 获取用户数据，提取并计算各项统计指标，
    更新 MySQL 中的用户 PvP 缓存、最高记录、船只极值记录和排行榜，
    同时将近期增量数据写入暂存表并同步 Redis 排行榜

    Attributes:
        ship_record: 船只极值记录缓存，来自 read_ship_record()
        ship_info: 船只排行榜基准数据，来自 read_ship_data()
    """
    def __init__(
        self, 
        ship_record: dict, 
        ship_info: dict, 
        game_version: Optional[str], 
        version_start: Optional[str]
    ):
        """初始化更新器

        Args:
            ship_record: 船只极值记录数据
            ship_info: 船只排行榜基准数据
        """
        self.ship_record = ship_record
        self.ship_info = ship_info
        self.game_version = game_version
        self.version_start = version_start

    @staticmethod
    def _build_ship_pvp_cache(pvp_data: dict) -> dict:
        """构建船只 PvP 缓存数据

        将 API 返回的按船分组的 PvP 数据转换为缓存格式，
        其中侦查伤害和潜在伤害需要做单位转换

        Args:
            pvp_data: API 返回的船只 PvP 数据

        Returns:
            ship_id -> [battles, wins, damage, frags, exp, survived, scout_dmg, potential_dmg]
        """
        ship_pvp_cache = {}
        for ship_id, ship_data in pvp_data.items():
            pvp = ship_data.get('pvp', {})
            if not pvp:
                continue
            
            ship_pvp_cache[ship_id] = [
                pvp.get('battles_count', 0),
                pvp.get('wins', 0),
                pvp.get('damage_dealt', 0),
                pvp.get('frags', 0),
                pvp.get('original_exp', 0),
                pvp.get('survived', 0),
                max(pvp.get('assist_damage', 0), pvp.get('scouting_damage', 0)) // 100,  # 注意单位
                pvp.get('art_agro', 0) // 1000  # 注意单位
            ]
        return ship_pvp_cache
    
    @staticmethod
    def _build_ship_pvp_record(pvp_data: dict) -> dict:
        """构建船只 PvP 极值缓存数据

        将 API 返回的按船只分组的 PvP 数据提取出所需字段，
        按固定顺序组装为列表，供后续与记录比较使用

        Args:
            pvp_data: API 返回的船只 PvP 数据

        Returns:
            ship_id -> [max_exp, max_frags, max_planes_killed, max_damage_dealt,
            max_scouting_damage, max_total_agro]
        """
        ship_pvp_record = {}
        for ship_id, ship_data in pvp_data.items():
            pvp = ship_data.get('pvp', {})
            if not pvp:
                continue
            
            ship_pvp_record[ship_id] = [
                pvp.get('max_exp', 0),
                pvp.get('max_frags', 0),
                pvp.get('max_planes_killed', 0),
                pvp.get('max_damage_dealt', 0),
                pvp.get('max_scouting_damage', 0),
                pvp.get('max_total_agro', 0)
            ]
        return ship_pvp_record

    @staticmethod
    def _calc_recent_diff(old_cache: dict, latest_data: dict):
        """计算每艘船的近期数据增量

        将最新数据与本地缓存对比，差值经过精度修正后返回，
        跳过有负增量或无战斗变化的船只

        Args:
            old_cache: 本地缓存的船只数据
            latest_data: 最新的船只数据

        Returns:
            ship_id -> [battles_diff, wins_diff, ...] 的差值字典
        """
        diff_data = {}
        for ship_id, new_values in latest_data.items():
            old_values = old_cache.get(ship_id, [0]*len(new_values))
            ship_diff = [new_val - old_val for new_val, old_val in zip(new_values, old_values)]
            ship_diff[-2] = ship_diff[-2] * 100
            ship_diff[-1] = ship_diff[-1] * 1000
            if any(d < 0 for d in ship_diff):
                continue
            if ship_diff[0] == 0:
                continue
            diff_data[ship_id] = ship_diff
        return diff_data

    def _get_local_cache(self, cursor: Cursor, account_id: int) -> Optional[dict]:
        """获取用户本地的船只缓存数据

        Args:
            cursor: 数据库游标
            account_id: 用户 ID

        Returns:
            船只缓存字典，无缓存时返回 None
        """
        if not self.game_version:
            return None
        
        sql = """
            SELECT 
                cache, 
                UNIX_TIMESTAMP(updated_at)
            FROM T_user_cache 
            WHERE account_id = %s;
        """
        cursor.execute(
            sql,
            [account_id]
        )
        data = cursor.fetchone()

        if data and data[1] and self.version_start < data[1]:
            if data[0]:
                return json.loads(data[0])
            
        return None

    def _update_ship_records(self, ship_pvp_record: dict, account_id: int) -> None:
        """更新船只极值记录

        遍历用户各船只的数据列表，与当前服务器最高记录比较：
        - 超过：设为新记录，用户集合仅含当前用户
        - 平记录：若用户尚未在集合中，则加入集合并增加计数
        - 相同用户重复平记录：忽略

        Args:
            ship_pvp_record: {ship_id: [exp, planes, damage, scouting, potential]}
            account_id: 当前用户 ID
        """
        for ship_id, user_values_list in ship_pvp_record.items():
            if ship_id not in self.ship_record:
                continue

            # ship_record[ship_id] 是按 METRIC_ID_TO_INDEX 顺序的列表
            # 每个元素为 [metric_value, users_count, top_user_ids_set]
            for idx, user_value in enumerate(user_values_list):
                current_value, _, current_set = self.ship_record[ship_id][idx]

                # 超过当前最高值 → 新记录
                if user_value > current_value:
                    new_set = {account_id}
                    self.ship_record[ship_id][idx] = [user_value, 1, new_set]

                # 平记录且数值大于0，且用户尚未在集合中 → 增加达成者
                elif user_value == current_value and user_value > 0 and account_id not in current_set:
                    current_set.add(account_id)
                    new_count = len(current_set)
                    self.ship_record[ship_id][idx] = [user_value, new_count, current_set]

                # 用户已在集合中或数值为0 → 无变化，跳过

    def _build_ranking_cache(
        self,
        pvp_data: dict
    ) -> dict:
        """构建船只排行榜缓存数据

        计算每艘船的 Rating、solo 比例、命中率和各项指标等级，
        仅处理达到场次要求的船只

        Args:
            pvp_data: 按船分组的 PvP 数据

        Returns:
            ship_id -> [battles, rating, win_rate, avg_damage, damage_level, 
                        avg_frags, frags_level, avg_exp, hit_ratio,max_exp, max_damage]
        """
        ship_ranking_cache = {}
        
        for ship_id, ship_data in pvp_data.items():
            pvp = ship_data.get('pvp', {})
            if not pvp:
                continue
            
            if ship_id not in self.ship_info:
                continue
            
            battles_limit = self.ship_info[ship_id][0]
            if pvp.get('battles_count', 0) < battles_limit:
                continue
            
            # 计算命中率
            shots = pvp.get('shots_by_main', 0)
            hits = pvp.get('hits_by_main', 0)
            hit_ratio = round(hits / shots * 100, 2) if shots != 0 else 0
            
            # 计算评分
            personal_rating, damage_rating, frags_rating = calc_ship_rating(
                ship_data=[
                    round(pvp['wins'] / pvp['battles_count'] * 100, 4),
                    int(pvp['damage_dealt'] / pvp['battles_count']),
                    round(pvp['frags'] / pvp['battles_count'], 2)
                ],
                server_data=self.ship_info[ship_id][1]
            )
            
            ship_ranking_cache[ship_id] = [
                pvp['battles_count'],
                personal_rating,
                round(pvp['wins'] / pvp['battles_count'] * 100, 4),
                int(pvp['damage_dealt'] / pvp['battles_count']),
                damage_rating,
                round(pvp['frags'] / pvp['battles_count'], 2),
                frags_rating,
                int(pvp['original_exp'] / pvp['battles_count']),
                hit_ratio,
                pvp.get('max_exp', 0),
                pvp.get('max_damage_dealt', 0)
            ]
        
        return ship_ranking_cache

    @staticmethod
    def _upsert_leaderboard(
        cursor: Cursor, 
        ship_ranking_cache: dict, 
        account_id: int
    ) -> None:
        """批量插入或更新船只排行榜数据

        Args:
            cursor: 数据库游标
            ship_ranking_cache: 排行榜缓存数据
            account_id: 用户 ID
        """
        if not ship_ranking_cache:
            return
        
        values_to_insert = []
        for ship_id, data in ship_ranking_cache.items():
            values_to_insert.append((
                account_id,
                ship_id,
                data[0],     # battles
                data[1],     # rating
                data[2],     # win_rate
                data[3],     # avg_damage
                data[4],     # avg_damage_level
                data[5],     # avg_frags
                data[6],     # avg_frags_level
                data[7],     # avg_exp
                data[8],     # hit_ratio
                data[9],    # max_exp
                data[10]     # max_damage
            ))
        
        sql = """
            INSERT INTO T_ship_pvp_leaderboard (
                account_id, ship_id, battles, rating, win_rate, avg_damage, avg_damage_level, 
                avg_frags, avg_frags_level, avg_exp, hit_ratio, max_exp, max_damage, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
            )
            ON DUPLICATE KEY UPDATE 
                rating = VALUES(rating),
                battles = VALUES(battles),
                win_rate = VALUES(win_rate),
                avg_damage = VALUES(avg_damage),
                avg_damage_level = VALUES(avg_damage_level),
                avg_frags = VALUES(avg_frags),
                avg_frags_level = VALUES(avg_frags_level),
                avg_exp = VALUES(avg_exp),
                hit_ratio = VALUES(hit_ratio),
                max_exp = VALUES(max_exp),
                max_damage = VALUES(max_damage),
                updated_at = NOW();
        """
        cursor.executemany(sql, values_to_insert)

    def _insert_recent_diff_data(
        self,
        cursor: Cursor, 
        account_id: int,
        diff_data: dict
    ) -> None:
        """将船只近期数据变化写入暂存表

        Args:
            cursor: 数据库游标
            diff_data: 近期增量数据
            account_id: 用户 ID
        """
        if not diff_data:
            return
        
        sql = """
            INSERT INTO STAGING_ship_recent_data (
                uuid, game_version, account_id, payload
            ) VALUES (
                %s, %s, %s, %s
            );
        """
        cursor.execute(sql, [str(uuid.uuid4()), self.game_version, account_id, json.dumps(diff_data)])
        return

    @staticmethod
    def _update_user_cache(
        cursor: Cursor, 
        account_id: int,
        pvp_cache: dict = None
    ) -> None:
        """标记用户已更新

        Args:
            cursor: 数据库游标
        """
        if not pvp_cache:
            sql = """
                UPDATE T_user_cache
                SET
                    is_due = FALSE
                WHERE account_id = %s;
            """
            cursor.execute(sql, [account_id])
        else:
            sql = """
                UPDATE T_user_cache
                SET
                    is_due = FALSE, 
                    ships = %s,
                    cache = %s, 
                    updated_at = NOW() 
                WHERE account_id = %s;
            """
            cursor.execute(sql, [len(pvp_cache.keys()), json.dumps(pvp_cache), account_id])

    def main(
        self,
        mysql_connection: Connection,
        redis_client: Redis,
        session: Session,
        account_id: int
    ) -> None:
        """更新用户缓存数据 - 主入口函数

        完整流程：
            1. 调用 API 获取用户 PvP 数据
            2. 刷新用户基础信息
            3. 处理隐藏战绩 / 无效用户
            4. 提取总体统计、最高记录和船只缓存
            5. 更新船只极值记录和排行榜缓存
            6. 写入 MySQL 各表
            7. 计算近期增量并写入暂存表
            8. 同步 Redis 排行榜

        Args:
            mysql_connection: MySQL 数据库连接
            redis_client: Redis 客户端
            async_client: HTTP 异步客户端
            account_id: 用户 ID
        """
        # 获取用户PVP数据
        try:
            response = fetch_user_pvp_data(session, redis_client, account_id)
            if response == {}:
                try:
                    with mysql_connection.cursor() as cursor:
                        self._update_user_cache(cursor, account_id, None)
                    
                    mysql_connection.commit()
                except Exception as e:
                    mysql_connection.rollback()
                    error_name = type(e).__name__
                    logger.error(f'{account_id} | Update database failed: {error_name}')
                    write_exception(
                        error_type="DatabaseError",
                        error_name=error_name,
                        error_info=traceback.format_exc()
                    )

                logger.info(f'{account_id} | User not exist')
                return

            if not response:
                logger.info(f'{account_id} | Failed to obtain data')
                return
            
            ship_pvp_cache = {}
            ship_ranking_cache = {}
            
            # 构建船只PVP缓存
            pvp_data = response.get(str(account_id), {}).get('statistics')

            if pvp_data:
                ship_pvp_cache = self._build_ship_pvp_cache(pvp_data)
                ship_pvp_record = self._build_ship_pvp_record(pvp_data)
                
                # 更新船只记录
                self._update_ship_records(ship_pvp_record, account_id)
                
                # 构建排行榜缓存
                ship_ranking_cache = self._build_ranking_cache(pvp_data)
        except Exception as e:
            error_name = type(e).__name__
            logger.error(f'{account_id} | Data processing error: {error_name}')
            write_exception(
                error_type="ProgramError",
                error_name=error_name,
                error_info=traceback.format_exc()
            )
            return

        # 数据库更新或者写入操作
        try:
            with mysql_connection.cursor() as cursor:
                if ship_pvp_cache == {}:
                    self._update_user_cache(cursor, account_id, None)
                else:
                    # 获取本地缓存
                    local_cache = self._get_local_cache(cursor, account_id)
                    
                    # 更新各项数据
                    self._update_user_cache(cursor, account_id, ship_pvp_cache)
                    self._upsert_leaderboard(cursor, ship_ranking_cache, account_id)
                    
                    # 处理近期数据变化
                    if local_cache:
                        diff_data = self._calc_recent_diff(local_cache, ship_pvp_cache)
                        self._insert_recent_diff_data(cursor, account_id, diff_data)
            
            mysql_connection.commit()
        except Exception as e:
            mysql_connection.rollback()
            error_name = type(e).__name__
            logger.error(f'{account_id} | Update database failed: {error_name}')
            write_exception(
                error_type="DatabaseError",
                error_name=error_name,
                error_info=traceback.format_exc()
            )
            return
        
        # 更新 Redis
        try:
            # 更新Redis中的排行榜数据
            if ship_ranking_cache == {}:
                return
            
            pipe = redis_client.pipeline()
            for ship_id, values in ship_ranking_cache.items():
                if values[1] == -1:
                    continue
                key = f"leaderboard:ship:{ship_id}"
                pipe.zadd(key, {str(account_id): values[1]})
            pipe.execute()
        except Exception as e:
            error_name = type(e).__name__
            logger.error(f'{account_id} | Refresh redis failed: {error_name}')
            write_exception(
                error_type="DatabaseError",
                error_name=error_name,
                error_info=traceback.format_exc()
            )