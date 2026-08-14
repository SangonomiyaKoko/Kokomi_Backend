import json
import traceback
from redis import Redis
from requests import Session
from pymysql import Connection
from typing import Optional

from loggers import logger, write_exception
from clients import fetch_clan_season
from utils import formtime_to_timestamp
from db import (
    read_clan_cache,
    update_clan_stats,
    insert_clan_battles
)
from settings import REGION

def format_clan_data(data: list) -> Optional[dict]:
    """将公会队伍原始数据列表转换为结构化字典

    Args:
        data: 原始数据列表，按固定顺序包含 battles/wins/rating/league/division 等字段

    Returns:
        格式化后的字典，输入为空列表时返回 None
    """
    if not data:
        return None
    return {
        'battles_count': data[0],
        'wins_count': data[1],
        'public_rating': data[2],
        'league': data[3],
        'division': data[4],
        'division_rating': data[5],
        'stage_type': data[6],
        'stage_progress': data[7],
    }

def _build_clan_result(raw_data: dict, clan_id: int, season_id: int) -> dict:
    """从 API 原始响应构建标准化的公会结果字典"""
    ladder_name = 'mk_ladder' if REGION == 'ru' else 'wows_ladder'
    ladder = raw_data['clanview'][ladder_name]

    clan_result = {
        'clan_id': clan_id,
        'leading_team_number': ladder['leading_team_number'],
        'battles_count': ladder['battles_count'],
        'wins_count': ladder['wins_count'],
        'public_rating': ladder['public_rating'],
        'league': ladder['league'],
        'division': ladder['division'],
        'division_rating': ladder['division_rating'],
        'longest_winning_streak': ladder['longest_winning_streak'],
        'stage_type': None,
        'stage_battles': 0,
        'stage_victories': 0,
        'stage_progress': None,
        'last_battle_time': formtime_to_timestamp(ladder['last_battle_at']),
        'team_data': {1: [], 2: []},
    }

    leading_team = clan_result['leading_team_number']

    for team_data in ladder['ratings']:
        if team_data['season_number'] != season_id:
            continue

        team_number = team_data['team_number']
        team_result = [
            team_data['battles_count'],
            team_data['wins_count'],
            team_data['public_rating'],
            team_data['league'],
            team_data['division'],
            team_data['division_rating'],
            None,  # stage_type
            None,  # stage_progress
        ]

        if team_data.get('stage'):
            stage = team_data['stage']
            team_result[6] = 1 if stage['type'] == 'promotion' else 2

            stage_battles = 0
            stage_victories = 0
            stage_progress_parts = []
            for progress in stage['progress']:
                stage_battles += 1
                if progress == 'victory':
                    stage_victories += 1
                    stage_progress_parts.append('★')  # ★
                else:
                    stage_progress_parts.append('☆')  # ☆

            team_result[7] = ''.join(stage_progress_parts)

            if team_number == leading_team:
                clan_result['stage_type'] = team_result[6]
                clan_result['stage_battles'] = stage_battles
                clan_result['stage_victories'] = stage_victories
                clan_result['stage_progress'] = team_result[7]

        if team_result[0] > 0:
            clan_result['team_data'][team_number] = team_result

    return clan_result

def _build_insert_data(
    new_team_data: dict,
    old_team_data: dict,
    clan_id: int,
    last_battle_time: int,
) -> list[list]:
    """对比新旧队伍数据，生成需要插入的对战记录列表

    Args:
        new_team_data: 新队伍数据 {1: dict|None, 2: dict|None}
        old_team_data: 旧队伍数据 {1: dict|None, 2: dict|None}
        clan_id: 公会 ID
        last_battle_time: 最后战斗时间戳

    Returns:
        待插入的对战记录列表。
    """
    insert_data_list = []

    for team_number in [1, 2]:
        new_data = new_team_data.get(team_number)
        if new_data is None:
            continue

        old_data = old_team_data.get(team_number)

        if old_data is not None:
            battles_diff = new_data['battles_count'] - old_data['battles_count']
            wins_diff = new_data['wins_count'] - old_data['wins_count']
        else:
            battles_diff = new_data['battles_count']
            wins_diff = new_data['wins_count']

        # 只处理恰好 1 场新战斗的情况
        if battles_diff != 1:
            continue

        temp_list = [last_battle_time, clan_id, team_number]

        # 战斗结果
        temp_list.append(1 if wins_diff == 1 else 0)

        # 战斗评分变化
        if old_data is not None:
            rating_diff = new_data['public_rating'] - old_data['public_rating']
        else:
            rating_diff = new_data['public_rating']

        if rating_diff > 0:
            temp_list.append(f'+{rating_diff}')
        elif rating_diff < 0:
            temp_list.append(str(rating_diff))
        else:
            temp_list.append(None)

        # 晋级赛阶段标识
        if (
            new_data.get('stage_type')
            and new_data.get('stage_progress')
        ):
            temp_list.append('+' + new_data['stage_progress'][-1])
        else:
            temp_list.append(None)

        temp_list.extend([
            new_data['league'],
            new_data['division'],
            new_data['division_rating'],
            new_data['public_rating'],
            new_data['stage_type'],
            new_data['stage_progress'],
        ])

        insert_data_list.append(temp_list)

    return insert_data_list

def update_clan_season(
    session: Session,
    redis_client: Redis,
    conn: Connection,
    season_id: int,
    clan_id: int
) -> None:
    """更新单个公会的赛季数据，并同步更新 Redis 排行榜缓存

    Args:
        redis_client: Redis 客户端
        conn: 数据库连接
        season_id: 当前赛季 ID
        clan_id: 公会 ID
    """
    try:
        # 请求公会详情
        result = fetch_clan_season(session, redis_client, clan_id)
        if not result:
            logger.info(f'{clan_id} | Failed to obtain data')
            return

        # 解析并构建标准化数据
        clan_result = _build_clan_result(result, clan_id, season_id)
        team_data_1 = clan_result['team_data'][1]
        team_data_2 = clan_result['team_data'][2]

        # 加载最新数据
        new_team_data = {
            1: format_clan_data(team_data_1),
            2: format_clan_data(team_data_2),
        }

        # 加载本地缓存数据
        clan = read_clan_cache(conn, clan_id)
        if not clan:
            return

        if clan[0] == season_id:
            # 已有本赛季记录：对比新旧数据
            original_team = json.loads(clan[1])
            old_team_data = {
                1: format_clan_data(original_team[0]),
                2: format_clan_data(original_team[1]),
            }
        else:
            # 新赛季或新公会：使用空旧数据
            old_team_data = {1: None, 2: None}

        # 构建插入数据
        insert_data_list = _build_insert_data(
            new_team_data,
            old_team_data,
            clan_id,
            clan_result['last_battle_time'],
        )

        # 计算胜率
        battles = clan_result.get('battles_count', 0)
        wins = clan_result.get('wins_count', 0)
        win_rate = round((wins / battles) * 100, 2) if battles > 0 else 0.0

        # 准备更新参数
        update_params = [
            season_id,
            clan_result['leading_team_number'],
            battles,
            win_rate,
            clan_result['public_rating'],
            clan_result['league'],
            clan_result['division'],
            clan_result['division_rating'],
            clan_result['longest_winning_streak'],
            clan_result['stage_type'],
            clan_result['stage_battles'],
            clan_result['stage_victories'],
            clan_result['stage_progress'],
            json.dumps([team_data_1, team_data_2]),
            clan_result['last_battle_time'],
            clan_id,
        ]

        # 更新 MySQL 公会统计表，并将对战明细写入赛季 SQLite 数据库
        update_clan_stats(conn, update_params)
        insert_clan_battles(season_id, insert_data_list)

        # 更新 Redis 排行榜缓存
        clan_rating = round(
            clan_result['public_rating']
            + clan_result['stage_battles'] * 0.1
            + clan_result['stage_victories'] * 0.01,
            2,
        )
        redis_client.zadd(
            'leaderboard:clan', {str(clan_id): float(clan_rating)}
        )

    except Exception as e:
        error_name = type(e).__name__
        logger.error(f"{clan_id} | Update clan season failed: {error_name}")
        write_exception(
            error_type="DatabaseError",
            error_name=error_name,
            error_info=traceback.format_exc()
        )
