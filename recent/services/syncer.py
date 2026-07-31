from pymysql import Connection
from pymysql.cursors import Cursor

from db import mysql_transaction
from utils import TimeUtils
from settings import (
    REGION, 
    USER_ACTIVITY_THRESHOLDS,
    SPECIAL_ACTIVITY_STRATEGY,
    USER_ACTIVITY_STRATEGY
)

class UserStatsSyncer:
    """用户基础信息同步器

    从外部 API 返回的账号数据中提取用户基础信息、Dog Tag 标识和
    各模式战斗场次统计，并同步写入 MySQL 的 T_user_base 和 T_user_stats 表。
    """
    @staticmethod
    def _get_insignias(data: dict) -> str:
        """从 DogTag 数据中生成标识字符串"""
        if not data:
            return None
        
        keys = [
            "texture_id",
            "symbol_id",
            "border_color_id",
            "background_color_id",
            "background_id"
        ]

        if any(k not in data for k in keys):
            return None
        
        return "-".join(str(data[k]) for k in keys)
    
    @staticmethod
    def _get_activity_level(current_timestamp: int, last_battle_time: int | None) -> int:
        """根据最后战斗时间戳返回活跃等级（0-9）"""
        if not last_battle_time or last_battle_time <= 0:
            return 0

        diff = current_timestamp - last_battle_time

        for threshold, level in USER_ACTIVITY_THRESHOLDS:
            if diff <= threshold:
                return level

        return 9

    @classmethod
    def _extract_user_data(cls, account_id: int, current_timestamp: int, response: dict) -> dict:
        """从 API 响应中提取用户基础数据"""
        user_data = {
            'username': None,
            'register_time': None,
            'insignias': None,
            'is_enabled': 1,
            'is_public': 1,
            'activity_level': 0,
            'total_battles': 0,
            'pve_battles': 0,
            'pvp_battles': 0,
            'ranked_battles': 0,
            'rating_battles': 0,
            'karma': 0,
            'last_battle_at': None,
            'random_stats': {},
            'ranked_stats': {}
        }
        
        user_info = response.get(str(account_id))
        
        # 无有效数据
        if user_info is None:
            user_data['is_enabled'] = 0
            return user_data

        # 隐藏战绩
        if 'hidden_profile' in user_info:
            user_data['is_public'] = 0
            user_data['username'] = user_info['name']
            return user_data
        
        # 无有效数据
        if 'statistics' not in user_info:
            user_data['is_enabled'] = 0
            return user_data
        
        # 无数据账号
        if 'basic' not in user_info['statistics']:
            user_data['username'] = user_info['name']
            register_time = int(user_info.get('created_at', 0))
            user_data['register_time'] = register_time if register_time != 0 else None
            return user_data
        
        # 正常有数据用户
        statistics = user_info['statistics']
        basic_data = statistics.get('basic', {})
        leveling_points = basic_data.get('leveling_points', 0)
        
        # 中国服主播体验账号的特殊等级点数偏移量（1,000,000）
        # 国服 API 返回的 leveling_points 包含了此偏移，需减去以得到真实场次
        if leveling_points >= 1_000_000:
            leveling_points -= 1_000_000
        
        # 处理时间戳字段
        register_time = int(user_info.get('created_at', 0))
        last_battle_time = basic_data.get('last_battle_time', 0)
        if last_battle_time == 0:
            last_battle_time = None

        pve_battles = statistics.get('pve', {}).get('battles_count', 0)
        pvp_battles = statistics.get('pvp', {}).get('battles_count', 0)
        ranked_battles = statistics.get('rank_solo', {}).get('battles_count', 0)
        
        user_data.update({
            'username': user_info['name'],
            'register_time': register_time if register_time not in (0, None) else None,
            'insignias': cls._get_insignias(user_info.get('dog_tag')),
            'activity_level': cls._get_activity_level(current_timestamp, last_battle_time),
            'total_battles': leveling_points,
            'karma': basic_data.get('karma', 0),
            'last_battle_at': last_battle_time,
            'pve_battles': pve_battles,
            'pvp_battles': pvp_battles,
            'ranked_battles': ranked_battles
        })
        
        # 处理俄服的评分战数据
        if REGION == 'ru':
            rating_count = 0
            rating_count += statistics.get('rating_solo', {}).get('battles_count', 0)
            rating_count += statistics.get('rating_div', {}).get('battles_count', 0)
            user_data['rating_battles'] = rating_count

        if pvp_battles > 0:
            user_data['random_stats'] = {
                'battles': pvp_battles,
                'total_exp': statistics['pvp']['exp'],
                'win_rate': round(statistics['pvp']['wins']/pvp_battles*100, 2),
                'avg_damage': int(statistics['pvp']['damage_dealt']/pvp_battles),
                'avg_frags': round(statistics['pvp']['frags']/pvp_battles, 2),
                'avg_exp': int(statistics['pvp']['original_exp']/pvp_battles),
                'max_exp': statistics['pvp']['max_exp'],
                'max_frags': statistics['pvp']['max_frags'],
                'max_planes': statistics['pvp']['max_planes_killed'],
                'max_damage': statistics['pvp']['max_damage_dealt'],
                'max_scouting': statistics['pvp']['max_scouting_damage'],
                'max_potential': statistics['pvp']['max_total_agro']
            }
        
        if ranked_battles > 0:
            user_data['ranked_stats'] = {
                'battles': ranked_battles ,
                'total_exp': statistics['rank_solo']['exp'],
                'win_rate': round(statistics['rank_solo']['wins']/ranked_battles*100, 2),
                'avg_damage': int(statistics['rank_solo']['damage_dealt']/ranked_battles),
                'avg_frags': round(statistics['rank_solo']['frags']/ranked_battles, 2),
                'avg_exp': int(statistics['rank_solo']['original_exp']/ranked_battles),
                'max_exp': statistics['rank_solo']['max_exp'],
                'max_frags': statistics['rank_solo']['max_frags'],
                'max_planes': statistics['rank_solo']['max_planes_killed'],
                'max_damage': statistics['rank_solo']['max_damage_dealt'],
                'max_scouting': statistics['rank_solo']['max_scouting_damage'],
                'max_potential': statistics['rank_solo']['max_total_agro']
            }
        
        return user_data

    @staticmethod
    def _fetch_user_base_row(cursor: Cursor, account_id: int) -> tuple | None:
        """从 T_user_base 表查询用户基本信息行

        Args:
            cursor: 数据库游标
            account_id: 用户 ID
        """
        sql = """
            SELECT
                b.username,
                UNIX_TIMESTAMP(b.updated_at),
                s.pvp_battles,
                s.ranked_battles,
                IFNULL(c.user_level, 0)
            FROM T_user_base b
            LEFT JOIN T_user_stats s
              ON b.account_id = s.account_id
            LEFT JOIN T_user_config c
              ON b.account_id = c.account_id
            WHERE b.account_id = %s;
        """
        cursor.execute(sql, [account_id])
        return cursor.fetchone()

    @staticmethod
    def _update_user_base(cursor: Cursor, account_id: int, user_data: dict, old_username: str, old_timestamp: int) -> None:
        """更新 T_user_base 表"""
        if not user_data['username']:
            return
        
        if user_data['register_time'] is None:
            # 有名称但无注册时间 -> 隐藏战绩用户
            sql = """
                UPDATE T_user_base 
                SET 
                    username = %s, 
                    updated_at = NOW() 
                WHERE account_id = %s;
            """
            cursor.execute(sql, [user_data['username'], account_id])
        else:
            # 有名称和注册时间 -> 正常用户
            sql = """
                UPDATE T_user_base 
                SET 
                    username = %s, 
                    register_time = FROM_UNIXTIME(%s), 
                    insignias = %s, 
                    updated_at = NOW() 
                WHERE account_id = %s;
            """
            cursor.execute(
                sql, [user_data['username'], user_data['register_time'], user_data['insignias'], account_id]
            )
        
        # 检测昵称变更
        if old_timestamp and old_username != user_data['username']:
            sql = """
                INSERT INTO T_user_action (
                    account_id, 
                    username
                ) VALUES (
                    %s, %s
                );
            """
            cursor.execute(sql, [account_id, old_username])

    @staticmethod
    def _update_user_stats(cursor: Cursor, account_id: int, user_level: int, user_data: dict, current_timestamp: int, return_refresh_time: bool) -> int | None:
        """更新 T_user_stats 表"""
        if user_data['is_enabled'] == 0:
            # 账号不存在
            sql = """
                UPDATE T_user_stats 
                SET 
                    is_enabled = 0, 
                    activity_level = 0, 
                    next_refresh_at = NULL,
                    updated_at = NOW() 
                WHERE account_id = %s;
            """
            cursor.execute(sql, [account_id])
        elif user_data['is_public'] == 0:
            # 账号隐藏战绩
            sql = """
                UPDATE T_user_stats 
                SET 
                    is_enabled = 1, 
                    is_public = 0, 
                    activity_level = 0, 
                    next_refresh_at = DATE_ADD(NOW(), INTERVAL %s SECOND), 
                    updated_at = NOW() 
                WHERE account_id = %s;
            """
            cursor.execute(sql, [30*86400, account_id])
        else:
            if user_level == 2 and user_data['activity_level'] == 1:
                diff_timestamp = current_timestamp - user_data['last_battle_at']
                interval_seconds = 600  # 默认 10min
                for item in SPECIAL_ACTIVITY_STRATEGY:
                    if diff_timestamp < item[0]:
                        interval_seconds = item[1]
                        break
            else:
                interval_seconds = USER_ACTIVITY_STRATEGY.get(f"{user_level}-{user_data['activity_level']}", 30*86400)

            sql = """
                UPDATE T_user_stats 
                SET 
                    is_enabled = 1,  
                    is_public = 1, 
                    activity_level = %s,
                    total_battles = %s, 
                    pve_battles = %s, 
                    pvp_battles = %s, 
                    ranked_battles = %s, 
                    rating_battles = %s, 
                    karma = %s, 
                    last_battle_at = FROM_UNIXTIME(%s), 
                    next_refresh_at = DATE_ADD(NOW(), INTERVAL %s SECOND), 
                    updated_at = NOW() 
                WHERE account_id = %s;
            """

            cursor.execute(
                sql,
                [user_data['activity_level'], user_data['total_battles'], user_data['pve_battles'], 
                user_data['pvp_battles'], user_data['ranked_battles'], user_data['rating_battles'], 
                user_data['karma'], user_data['last_battle_at'], interval_seconds, account_id]
            )

        if return_refresh_time:
            sql = """
                SELECT 
                    UNIX_TIMESTAMP(updated_at) 
                FROM T_user_stats
                WHERE account_id = %s;
            """
            cursor.execute(sql, [account_id])
            return cursor.fetchone()[0]

    @staticmethod
    def _update_user_battles(cursor: Cursor, account_id: int, table_name: str, user_data: dict) -> None:
        """更新 T_user_random / T_user_ranked 表"""
        if user_data == {}:
            return
        
        sql = f"""
            UPDATE {table_name} 
            SET 
                battles = %s, 
                total_exp = %s, 
                win_rate = %s, 
                avg_damage = %s, 
                avg_frags = %s, 
                avg_exp = %s, 
                max_exp = %s, 
                max_frags = %s, 
                max_planes = %s, 
                max_damage = %s, 
                max_scouting = %s,  
                max_potential = %s, 
                updated_at = NOW() 
            WHERE account_id = %s;
        """
        cursor.execute(sql, [
            user_data['battles'], user_data['total_exp'], user_data['win_rate'], user_data['avg_damage'], 
            user_data['avg_frags'], user_data['avg_exp'], user_data['max_exp'], user_data['max_frags'], 
            user_data['max_planes'], user_data['max_damage'], user_data['max_scouting'], user_data['max_potential'], 
            account_id
        ])

    @staticmethod
    def _update_user_cache(cursor: Cursor, account_id: int, user_data: dict, old_pvp: int) -> None:
        """更新 T_user_cache 表"""
        if user_data['is_enabled'] and user_data['is_public']:
            if old_pvp != user_data['pvp_battles']:
                sql = """
                    UPDATE T_user_cache 
                    SET 
                        is_due = TRUE 
                    WHERE account_id = %s;
                """
                cursor.execute(sql, [account_id])
            else:
                sql = """
                    UPDATE T_user_cache 
                    SET 
                        updated_at = NOW() 
                    WHERE account_id = %s 
                      AND is_due = FALSE;
                """
                cursor.execute(sql, [account_id])
        else:
            sql = """
                UPDATE T_user_cache 
                SET 
                    is_due = FALSE 
                WHERE account_id = %s;
            """
            cursor.execute(sql, [account_id])

    @classmethod
    def refresh(cls, conn: Connection, account_id: int, api_result: dict, return_refresh_time: bool = False) -> int | str | None:
        """基于用户基本信息接口的数据，刷新数据库的用户数据表"""
        current_timestamp = TimeUtils.get_current_timestamp()
        user_data = cls._extract_user_data(account_id, current_timestamp, api_result)
            
        try:
            with mysql_transaction(conn, account_id) as cursor:
                # 从数据库中读取用户的username
                existing = cls._fetch_user_base_row(cursor, account_id)
                
                if existing is None:
                    return "UserNotInDB"
                
                old_username, old_timestamp, random, ranked, user_level = existing

                if random is None or ranked is None:
                    return "UserNotInDB"

                # 更新 T_user_base
                cls._update_user_base(cursor, account_id, user_data, old_username, old_timestamp)
                
                # 更新 T_user_stats
                update_timestamp = cls._update_user_stats(cursor, account_id, user_level, user_data, current_timestamp, return_refresh_time)

                # 更新 T_user_random / T_user_ranked
                cls._update_user_battles(cursor, account_id, 'T_user_random', user_data['random_stats'])
                cls._update_user_battles(cursor, account_id, 'T_user_ranked', user_data['ranked_stats'])

                # 更新 T_user_cache
                cls._update_user_cache(cursor, account_id, user_data, random)

                if return_refresh_time:
                    return update_timestamp
        except Exception:
            return 