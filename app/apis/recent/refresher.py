import sqlite3
from pathlib import Path
from sqlite3 import Cursor
from typing import Optional
from typing_extensions import TypedDict
from contextlib import asynccontextmanager

from app.core import EnvConfig
from app.utils import TimeUtils
from app.response import JSONResponse
from app.middlewares import RedisClient

class UserStats(TypedDict):
    is_public: bool
    total_battles: int
    pve_battles: int
    pvp_battles: int
    ranked_battles: int
    karma: int

@asynccontextmanager
async def recent_refresh_lock(account_id: str):
    """分布式锁上下文管理器"""
    lock_key = f"refresh_lock:recent:{account_id}"
    
    # 尝试获取锁
    error, acquired = JSONResponse.extract_data(
        response=await RedisClient.setnx(lock_key, 1, nx=True, ex=60)
    )
    if error:
        acquired = False
    
    if not acquired:
        yield False
        return
    
    # 获取锁成功
    try:
        yield True
    finally:
        await RedisClient.drop(lock_key)

class UserUpdater:
    """负责维护用户的近期数据库文件，并检查用户是否需要更新"""
    @staticmethod
    def _init_new_database(db_path: Path):
        """初始化数据库文件"""
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()

                # 初始化数据库
                cursor.executescript(EnvConfig.SQLITE_SQL)

                conn.commit()
        except:
            db_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _read_daily_summary(cursor: Cursor, reset_date: tuple[int, int]) -> tuple:
        """读取今日和昨日的数据"""
        sql = """
            SELECT 
                is_public, 
                total_battles, 
                pve_battles, 
                pvp_battles, 
                ranked_battles, 
                karma, 
                index_table, 
                updated_at
            FROM user_daily_summary 
            WHERE snapshot_date = ?;
        """
        cursor.execute(sql, [reset_date[0]])
        data1 = cursor.fetchone()
        cursor.execute(sql, [reset_date[1]])
        data2 = cursor.fetchone()
        return (data1, data2)

    @staticmethod
    def _read_ship_cache(cursor: Cursor):
        sql = """
            SELECT 
                ship_id, 
                battles, 
                snapshot_date
            FROM ship_latest_cache;
        """
        cursor.execute(sql)
        data = {}
        for row in cursor.fetchall():
            data[str(row[0])] = [row[1], row[2]]
        return data

    @staticmethod
    def _insert_daily_summary(
        cursor: Cursor, 
        snapshot_date: int, 
        summary_data: Optional[UserStats], 
        index_table: Optional[str], 
        update_time: int
    ):
        sql = """
            INSERT INTO user_daily_summary (
                snapshot_date,
                is_public,
                total_battles,
                pve_battles,
                pvp_battles,
                ranked_battles,
                karma,
                index_table,
                updated_at
            ) VALUES (
                ?,?,?,?,?,?,?,?,?
            );
        """
        cursor.execute(sql, [
            snapshot_date, 
            summary_data['is_public'], 
            summary_data['total_battles'], 
            summary_data['pve_battles'],
            summary_data['pvp_battles'],
            summary_data['ranked_battles'],
            summary_data['karma'],
            index_table, 
            update_time
        ])
    
    @staticmethod
    def _update_daily_summary(
        cursor: Cursor, 
        snapshot_date: int, 
        summary_data: UserStats, 
        index_table: Optional[str], 
        update_time: int
    ):
        if index_table:
            sql = """
                UPDATE user_daily_summary 
                SET
                    is_public = ?,
                    total_battles = ?,
                    pve_battles = ?, 
                    pvp_battles = ?, 
                    ranked_battles = ?, 
                    karma = ?, 
                    index_table = ?,
                    updated_at = ?
                WHERE snapshot_date = ?;
            """
            cursor.execute(sql, [
                summary_data['is_public'],
                summary_data['total_battles'],
                summary_data['pve_battles'],
                summary_data['pvp_battles'],
                summary_data['ranked_battles'],
                summary_data['karma'],
                index_table,
                update_time,
                snapshot_date
            ])
        else:
            sql = """
                UPDATE user_daily_summary 
                SET
                    is_public = ?,
                    total_battles = ?,
                    pve_battles = ?, 
                    pvp_battles = ?, 
                    ranked_battles = ?, 
                    karma = ?, 
                    updated_at = ?
                WHERE snapshot_date = ?;
            """
            cursor.execute(sql, [
                summary_data['is_public'],
                summary_data['total_battles'],
                summary_data['pve_battles'],
                summary_data['pvp_battles'],
                summary_data['ranked_battles'],
                summary_data['karma'],
                update_time,
                snapshot_date
            ])

    @staticmethod
    def _ship_snapshot_encode(data: list):
        parts = []
        for item in data:
            if item is None:
                parts.append('')
            else:
                parts.append(str(item).replace(' ', ''))
        return ';'.join(parts)
    
    @staticmethod
    def _ship_snapshot_decode(data: str):
        fields = data.split(';')
        result = []
        for f in fields:
            if f == '':
                result.append(None)
            else:
                result.append(eval(f))
        return result

    @staticmethod
    def _ship_map_encode(data: dict):
        parts = []
        for key, value in data.items():
            parts.append(str(key) + ':' + str(value))
        return ','.join(parts)

    @staticmethod
    def _ship_map_decode(data: str):
        fields = data.split('1')
        result = {}
        for f in fields:
            k, v = f.split(':', 1)
            result[int(k)] = int(v)
        return result

    @staticmethod
    def _process_responeses(responses: list):
        statis_dict = {}
        type_list = ['pvp_solo', 'pvp_div2', 'pvp_div3', 'rank_solo']
        for i in range(4):
            for ship_id, ship_data in responses[i].items():
                battle_type = type_list[i]
                if ship_data[battle_type] == {}:
                    continue
                if ship_data[battle_type]['battles_count'] == 0:
                    continue
                if ship_id not in statis_dict:
                    statis_dict[ship_id] = {
                        'battles': 0,
                        'values': [
                            None, None, None, None
                        ]
                    }
                statis_dict[ship_id]['battles'] += ship_data[battle_type]['battles_count']
                statis_dict[ship_id]['values'][i] = [
                    ship_data[battle_type]['battles_count'],
                    ship_data[battle_type]['wins'],
                    ship_data[battle_type]['losses'],
                    ship_data[battle_type]['damage_dealt'],
                    ship_data[battle_type]['frags'],
                    ship_data[battle_type]['survived'],
                    max(
                        ship_data[battle_type].get('assist_damage', 0), 
                        ship_data[battle_type].get('scouting_damage', 0)
                    ),
                    ship_data[battle_type]['art_agro'],
                    ship_data[battle_type]['original_exp'],
                    ship_data[battle_type]['planes_killed'],
                    ship_data[battle_type]['hits_by_main'],
                    ship_data[battle_type]['shots_by_main']
                ]
        return statis_dict

    @staticmethod
    def _insert_snapshot_index(cursor: Cursor, snapshot_date: int, ship_count: int, ship_map: dict):
        sql = """
            INSERT INTO daily_snapshot_index (
                snapshot_date, ship_count, ship_map
            ) VALUES (
                ?,?,?
            );
        """
        cursor.execute(sql, [snapshot_date, ship_count, ship_map])

    @staticmethod
    def _update_snapshot_index(cursor: Cursor, snapshot_date: int, ship_count: int, ship_map: dict):
        sql = """
            UPDATE daily_snapshot_index 
            SET 
                ship_count = ?, 
                ship_map = ?
            WHERE snapshot_date = ?;
        """
        cursor.execute(sql, [ship_count, ship_map, snapshot_date])

    @staticmethod
    def _calc_recent_diff(ship_id: int, new_list: list, old_list: list) -> list:
        modes = ['pvp_solo', 'pvp_div2', 'pvp_div3', 'rank_solo']
        params = []

        for idx, mode in enumerate(modes):
            new_data = new_list[idx]
            old_data = old_list[idx]

            # 只有两者都存在时才计算差值
            if new_data is None:
                continue

            if old_data is None:
                old_data = [0] * 12

            # 计算各字段差值（新 - 旧）
            delta_battles = new_data[0] - old_data[0]
            if delta_battles <= 0:
                continue

            delta_wins = new_data[1] - old_data[1]
            delta_losses = new_data[2] - old_data[2]
            delta_damage = new_data[3] - old_data[3]
            delta_frags = new_data[4] - old_data[4]
            delta_original_exp = new_data[8] - old_data[8]
            delta_scouting_damage = new_data[6] - old_data[6]
            delta_art_agro = new_data[7] - old_data[7]
            delta_planes_killed = new_data[9] - old_data[9]
            delta_survived = new_data[5] - old_data[5]

            delta_hits = new_data[10] - old_data[10]
            delta_shots = new_data[11] - old_data[11]
            hit_rate = round(delta_hits / delta_shots * 100, 2) if delta_shots != 0 else 0.0

            params.append((
                ship_id, mode,
                delta_battles, delta_wins, delta_losses, delta_damage,
                delta_frags, delta_original_exp, delta_scouting_damage,
                delta_art_agro, delta_planes_killed, delta_survived, hit_rate
            ))

        return params

    @staticmethod
    def _read_ship_snapshot(cursor: Cursor, ship_id: int, snapshot_date: int):
        sql = """
            SELECT snapshot_data 
            FROM ship_daily_snapshot 
            WHERE ship_id = ? 
              AND snapshot_date = ?;
        """
        cursor.execute(sql, [ship_id, snapshot_date])
        return cursor.fetchone()

    @staticmethod
    def _refresh_latest_cache(cursor: Cursor, params: dict):
        if len(params['insert']) > 0:
            sql = """
                INSERT INTO ship_latest_cache (
                    ship_id, battles, snapshot_date
                ) VALUES (
                    ?,?,?
                );
            """
            cursor.executemany(sql, params['insert'])
        
        if len(params['update']) > 0:
            sql = """
                UPDATE ship_latest_cache 
                SET 
                    battles = ?, 
                    snapshot_date = ?, 
                    updated_at = CURRENT_TIMESTAMP 
                WHERE ship_id = ?;
            """
            cursor.executemany(sql, params['update'])
        
        if len(params['delete']) > 0:
            sql = """
                DELETE FROM ship_latest_cache WHERE ship_id = ?;
            """
            cursor.executemany(sql, params['update'])

    @staticmethod
    def _refresh_daily_snapshot(cursor: Cursor, params: dict):
        if len(params['insert']) > 0:
            sql = """
                INSERT INTO ship_daily_snapshot (
                    ship_id, snapshot_date, snapshot_data
                ) VALUES (
                    ?,?,?
                );
            """
            cursor.executemany(sql, params['insert'])
        
        if len(params['update']) > 0:
            sql = """
                UPDATE ship_daily_snapshot 
                SET 
                    snapshot_data = ?, 
                    updated_at = CURRENT_TIMESTAMP 
                WHERE ship_id = ? 
                    AND snapshot_date = ?;
            """
            cursor.executemany(sql, params['update'])

    @staticmethod
    def _insert_user_recent_stats(cursor: Cursor, rows: list):
        if len(rows) > 0:
            sql = """
                INSERT INTO user_recent_stats (
                    ship_id, mode, battles, wins, losses, damage, frags,
                    original_exp, scouting_damage, art_agro, planes_killed,
                    survived, hit_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """
            cursor.executemany(sql, rows)

    @classmethod
    async def main(
        cls, 
        account_id: int,
        user_level: int,
        responses: list,
        current_timestamp: int,
        update_timestamp: int
    ) -> str:
        # 数据库文件地址
        db_path = EnvConfig.SQLITE_DIR / f'{account_id}.db'

        # 如果文件不存在则初始化文件
        if not db_path.exists():
            cls._init_new_database(account_id, db_path)

        # 格式化今日和昨日日期
        reset_date = (
            TimeUtils.get_reset_date(current_timestamp), 
            TimeUtils.get_reset_date(current_timestamp - 86400)
        )

        basic_data = responses[0].get(str(account_id))
        # 用户隐藏战绩情况，但是这里不存在
        if 'hidden_profile' in basic_data:
            return
        
        # 读取用户的战绩数据
        statistics = basic_data.get('statistics', {})
        user_info = statistics.get('basic', {})
        leveling_points = user_info.get('leveling_points', 0)
        if leveling_points >= 1_000_000:
            leveling_points = leveling_points - 1_000_000
        user_latest_stats = UserStats(
            is_public=1,
            total_battles=leveling_points,
            pve_battles=statistics.get('pve', {}).get('battles_count', 0),
            pvp_battles=statistics.get('pvp', {}).get('battles_count', 0),
            ranked_battles=statistics.get('rank_solo', {}).get('battles_count', 0),
            karma=user_info.get('karma', 0)
        )
        
        # 无随机或排位数据情况，只需要更新daily summary表
        if user_latest_stats['pvp_battles'] + user_latest_stats['ranked_battles'] == 0:
            with sqlite3.connect(db_path) as conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute("BEGIN IMMEDIATE")

                    now_daily_summary = cls._read_daily_summary(cursor, reset_date)
                    if now_daily_summary[0] is None and now_daily_summary[1] is None:
                        cls._insert_daily_summary(cursor, reset_date[1], user_latest_stats, None, update_timestamp)
                        cls._insert_daily_summary(cursor, reset_date[0], user_latest_stats, None, update_timestamp)
                    elif now_daily_summary[0] is None:
                        cls._insert_daily_summary(cursor, reset_date[0], user_latest_stats, None, update_timestamp)
                    else:
                        cls._update_daily_summary(cursor, reset_date[0], user_latest_stats, None, update_timestamp)

                    cursor.execute("COMMIT")
                except:
                    cursor.execute("ROLLBACK")
                    raise
                finally:
                    cursor.close()
                return

        latest_ship_count = 0
        latest_ship_map = {}
        latest_ship_cache = {
            'insert': [],
            'update': [],
            'delete': []
        }
        latest_shapshot = {
            'insert': [],
            'update': []
        }
            
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            # 本地数据库中船只的缓存数据
            now_daily_summary = cls._read_daily_summary(cursor, reset_date)
            now_ship_cache = cls._read_ship_cache(cursor)
            
            # 处理船只数据
            latest_dict = cls._process_responeses([
                responses[1][str(account_id)]['statistics'],
                responses[2][str(account_id)]['statistics'],
                responses[3][str(account_id)]['statistics'],
                responses[4][str(account_id)]['statistics']
            ])
            
            # 数据库中没有用户数据
            if now_daily_summary[0] is None and now_daily_summary[1] is None:
                for ship_id, ship_data in latest_dict.items():
                    if ship_id not in now_ship_cache:
                        latest_ship_cache['insert'].append([
                            ship_id, ship_data['battles'], reset_date[1]
                        ])
                        latest_shapshot['insert'].append([
                            ship_id, reset_date[1], cls._ship_snapshot_encode(ship_data['values'])
                        ])
                        latest_ship_map[ship_id] = reset_date[1]
                    else:
                        latest_ship_cache['update'].append([
                            ship_id, ship_data['battles'], reset_date[1]
                        ])
                        if ship_data['battles'] == now_ship_cache[ship_id][0]:
                            latest_ship_map[ship_id] = now_ship_cache[ship_id][1]
                        else:
                            latest_shapshot['insert'].append([
                                ship_id, reset_date[1], cls._ship_snapshot_encode(ship_data['values'])
                            ])
                            latest_ship_map[ship_id] = reset_date[1]
                    latest_ship_count += 1

                try:
                    cursor.execute("BEGIN IMMEDIATE")

                    cls._insert_daily_summary(cursor, reset_date[1], user_latest_stats, reset_date[1], update_timestamp)
                    cls._insert_daily_summary(cursor, reset_date[0], user_latest_stats, reset_date[1], update_timestamp)
                    cls._insert_snapshot_index(cursor, reset_date[1], latest_ship_count, cls._ship_map_encode(latest_ship_map))
                    cls._refresh_latest_cache(cursor, latest_ship_cache)
                    cls._refresh_daily_snapshot(cursor, latest_shapshot)

                    cursor.execute("COMMIT")
                except:
                    cursor.execute("ROLLBACK")
                    raise
                finally:
                    cursor.close()

                return
            
            # 有昨日数据但是没有今日数据，先复制一份昨日数据到今日下
            if now_daily_summary[0] is None and now_daily_summary[1]:
                user_latest_stats = UserStats(
                    is_public=now_daily_summary[1][0],
                    total_battles=now_daily_summary[1][1],
                    pve_battles=now_daily_summary[1][2],
                    pvp_battles=now_daily_summary[1][3],
                    ranked_battles=now_daily_summary[1][4],
                    karma=now_daily_summary[1][5]
                )
                cls._insert_daily_summary(cursor, reset_date[0], user_latest_stats, now_daily_summary[1][6], now_daily_summary[1][7])
                now_daily_summary[0] = now_daily_summary[1].copy()
                conn.commit()
            
            # 正常用户
            changed_count = 0
            changed_list = {}
            insert_recent_list = []

            if (
                user_level == 2 and 
                current_timestamp - now_daily_summary[0][7] <= 3600
            ):
                is_pro = True
            else:
                is_pro = False

            for ship_id, ship_data in latest_dict.items():
                # 基于数据库中本地的ship_cache来分类数据
                # 1. ship_id不在本地缓存中，插入新船只
                # 2. 船只的数据和本地缓存中存在差异，更新船只信息
                # 3. 数据没有修改，沿用旧数据索引
                if ship_id not in now_ship_cache:
                    latest_ship_cache['insert'].append([
                        ship_id, ship_data['battles'], reset_date[0]
                    ])
                    latest_shapshot['insert'].append([
                        ship_id, reset_date[0], cls._ship_snapshot_encode(ship_data['values'])
                    ])

                    # 处理pro权限用户
                    if is_pro:
                        changed_list[ship_id] = [ship_data['values'], [None] * 4]

                    changed_count += 1
                    latest_ship_count += 1
                    latest_ship_map[ship_id] = reset_date[0]
                elif ship_data['battles'] != now_ship_cache[ship_id][0]:
                    latest_ship_cache['update'].append([
                        ship_data['battles'], reset_date[0], int(ship_id)
                    ])
                    if now_ship_cache[ship_id][1] == reset_date[0]:
                        latest_shapshot['update'].append([
                            cls._ship_snapshot_encode(ship_data['values']), ship_id, reset_date[0]
                        ])
                    else:
                        latest_shapshot['insert'].append([
                            ship_id, reset_date[0], cls._ship_snapshot_encode(ship_data['values'])
                        ])
                        
                    # 处理pro权限用户
                    if is_pro and ship_data['battles'] > now_ship_cache[ship_id][0]:
                        local_snapshot = cls._read_ship_snapshot(cursor, ship_id, now_ship_cache[ship_id][1])
                        if local_snapshot:
                            local_snapshot = cls._ship_snapshot_decode(local_snapshot[0])
                            changed_list[ship_id] = [ship_data['values'], local_snapshot]

                    changed_count += 1
                    latest_ship_count += 1
                    latest_ship_map[ship_id] = reset_date[0]
                else:
                    # 本地数据和最新数据间没有修改
                    latest_ship_count += 1
                    latest_ship_map[ship_id] = now_ship_cache[ship_id][1]

            # 在本地缓存中但是不在用户的最新数据中，删除
            for ship_id, _ in now_ship_cache.items():
                if ship_id not in latest_dict:
                    changed_count += 1
                    latest_ship_cache['delete'].append(ship_id)

            # 存在近期数据
            if changed_list != {}:
                for ship_id, ship_data in changed_list.items():
                    diff_params = cls._calc_recent_diff(ship_id, ship_data[0], ship_data[1])
                    insert_recent_list.extend(diff_params)

            try:
                cursor.execute("BEGIN IMMEDIATE")
                if changed_count == 0:
                    cls._update_daily_summary(cursor, reset_date[0], user_latest_stats, None, update_timestamp)
                else:
                    cls._update_daily_summary(cursor, reset_date[0], user_latest_stats, reset_date[0], update_timestamp)
                    if now_daily_summary[0][6] == str(reset_date[0]):
                        cls._update_snapshot_index(cursor, reset_date[0], latest_ship_count, cls._ship_map_encode(latest_ship_map))
                    else:
                        cls._insert_snapshot_index(cursor, reset_date[0], latest_ship_count, cls._ship_map_encode(latest_ship_map))
                cls._refresh_latest_cache(cursor, latest_ship_cache)
                cls._refresh_daily_snapshot(cursor, latest_shapshot)
                cls._insert_user_recent_stats(cursor, insert_recent_list)

                cursor.execute("COMMIT")
            except:
                cursor.execute("ROLLBACK")
                raise
            return