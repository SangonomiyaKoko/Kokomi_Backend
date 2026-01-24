import requests
import pymysql
import traceback
from datetime import datetime, time
from logger import logger
from settings import SEASON_ID, SEASON_FINISH, SEASON_START
from middlewares import db_pool, redis_client


CLAN_API_URL_LIST = {
    1: 'https://clans.worldofwarships.asia',
    2: 'https://clans.worldofwarships.eu',
    3: 'https://clans.worldofwarships.com',
    4: 'https://clans.korabli.su',
    5: 'https://clans.wowsgame.cn'
}
CLAN_COLOR_INDEX = {
    13477119: 0,
    12511165: 1,
    14931616: 2,
    13427940: 3,
    13408614: 4,
    11776947: 5,
}

# weekday: 周一=0 ... 周日=6
WEEKLY_WINDOWS = {
    0: [  # 周一
        (time(2, 0), time(6, 29)),
        (time(8, 30), time(12, 59)),
    ],
    2: [  # 周三
        (time(19, 30), time(23, 59)),
    ],
    3: [  # 周四
        (time(2, 0), time(6, 29)),
        (time(8, 30), time(12, 59)),
        (time(19, 30), time(23, 59)),
    ],
    4: [  # 周五
        (time(2, 0), time(6, 29)),
        (time(8, 30), time(12, 59)),
    ],
    5: [  # 周六
        (time(19, 30), time(23, 59)),
    ],
    6: [  # 周日
        (time(2, 0), time(6, 29)),
        (time(8, 30), time(12, 59)),
        (time(19, 30), time(23, 59)),
    ]
}

def is_cb_active() -> bool:
    now_ts = int(datetime.timestamp())
    if not (SEASON_START <= now_ts <= SEASON_FINISH):
        return False
    now = datetime.fromtimestamp(now_ts)
    weekday = now.weekday()
    current_time = now.time()
    for start, end in WEEKLY_WINDOWS.get(weekday, []):
        if start <= current_time < end:
            return True
    return False

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def formtime2timestamp(formtime: str):
    return int(datetime.fromisoformat(formtime).timestamp())

def fetch_data(url):
    try:
        resp = requests.get(url,timeout=5)
        if resp.status_code == 200:
            result = resp.json()
            logger.debug(f'200 {url}')
            return result
        logger.warning(f'Code_{resp.status_code} {url}')
    except Exception as e:
        logger.warning(f"{type(e).__name__} {url}")

def get_clan_rank_data(region_id: int):
    if region_id == 5:
        base_url = CLAN_API_URL_LIST[region_id]
    else:
        base_url = CLAN_API_URL_LIST[1]
    region_dict = {1: 'asia',2: 'eu',3: 'na',4: 'ru',5: 'cn'}
    region = region_dict[region_id]
    league_list = [
        [0,1], [1,1], [1,2], [1,3],
        [2,1], [2,2], [2,3], [3,1],
        [3,2], [3,3], [4,1], [4,2],
        [4,3]
    ]
    realm_list = {
        1: 'sg', 2: 'eu', 3: 'us',
        4: 'ru', 5: 'cn360'
    }
    clan_data_list = []
    realm = realm_list[region_id]
    now_time = now_iso()
    for i in range(13):
        league=league_list[i][0]
        division=league_list[i][1]
        url = f'{base_url}/api/ladder/structure/?realm={realm}&league={league}&division={division}&limit=1000'
        result = fetch_data(url)
        key = f"metrics:http:{now_time[:10]}:{region}_total"
        redis_client.incrby(key, 1)
        if result is None:
            key = f"metrics:http:{now_time[:10]}:{region}_error"
            redis_client.incrby(key, 1)
        if result is None:
            continue
        for temp_data in result:
            # clan_data_list.append({
            #     region_id,
            #     temp_data['id'],
            #     temp_data['tag'],
            #     temp_data['public_rating'],
            #     temp_data['league'],
            #     temp_data['division'],
            #     temp_data['division_rating'],
            #     int(datetime.fromisoformat(temp_data['last_battle_at']).timestamp())
            # })
            clan_data_list.append([
                region_id,
                temp_data['id'],
                temp_data['tag'],
                formtime2timestamp(temp_data['last_battle_at'])
            ])
    return clan_data_list

def get_clan_cvc_data(region_id: int, clan_id: int):
    api_url = CLAN_API_URL_LIST.get(region_id)
    region_dict = {1: 'asia',2: 'eu',3: 'na',4: 'ru',5: 'cn'}
    region = region_dict[region_id]
    url = f'{api_url}/api/clanbase/{clan_id}/claninfo/'
    result = fetch_data(url)
    now_time = now_iso()
    key = f"metrics:http:{now_time[:10]}:{region}_total"
    redis_client.incrby(key, 1)
    if result is None:
        key = f"metrics:http:{now_time[:10]}:{region}_error"
        redis_client.incrby(key, 1)
        return "RequestFailed"
    last_battle_at = result['clanview']['wows_ladder']['last_battle_at']
    clan_result = {
        'clan_id': clan_id,
        'region_id': region_id,
        'tag': result['clanview']['clan']['tag'],
        'color': result['clanview']['wows_ladder']['color'], 
        'public_rating': result['clanview']['wows_ladder']['public_rating'], 
        'league': result['clanview']['wows_ladder']['league'], 
        'division': result['clanview']['wows_ladder']['division'], 
        'division_rating': result['clanview']['wows_ladder']['division_rating'], 
        'last_battle_time': formtime2timestamp(last_battle_at),
        'team_data': {
            1: [],
            2: []
        }
    }
    for team_data in result['clanview']['wows_ladder']['ratings']:
        if team_data['season_number'] != SEASON_ID:
            continue
        team_number = team_data['team_number']
        team_result = [
            team_data['battles_count'],
            team_data['wins_count'],
            team_data['public_rating'],
            team_data['league'],
            team_data['division'],
            team_data['division_rating'],
            None,
            None
        ]
        if team_data['stage']:
            if team_data['stage']['type'] == 'promotion':
                team_result[6] = '1'
            else:
                team_result[6] = '2'
            stage_progress = []
            for progress in team_data['stage']['progress']:
                if progress == 'victory':
                    stage_progress.append(1)
                else:
                    stage_progress.append(0)
            team_result[7] = stage_progress
        clan_result['team_data'][team_number] = team_result
    return clan_result

def check_clan_stats(clan_data_list: list):
    update_ids = []
    conn = db_pool.connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        for clan_data in clan_data_list:
            sql = """
                SELECT 
                    clan_id, 
                    season, 
                    UNIX_TIMESTAMP(last_battle_at) AS last_battle_at 
                FROM clan_stats 
                WHERE clan_id = %s;
            """
            cursor.execute(sql, [clan_data[1]])
            clan = cursor.fetchone()
            if clan is None:
                sql = """
                    INSERT INTO clan_base (region_id, clan_id, tag) VALUES (%s, %s, %s);
                """
                cursor.execute(sql, [clan_data[0],clan_data[1],clan_data[2]])
                sql = """
                    INSERT INTO clan_stats (clan_id) VALUES (%s);
                """
                cursor.execute(sql, [clan_data[1]])
                conn.commit()
                update_ids.append([clan_data[0],clan_data[1]])
            else:
                if clan_data[3] is None:
                    continue
                if (
                    clan['last_battle_at'] is None or 
                    clan['last_battle_at'] != clan_data[3] or 
                    clan['season'] != SEASON_ID
                ):
                    update_ids.append([clan_data[0],clan_data[1]])
    except Exception as e:
        logger.error((f"{traceback.format_exc()}"))
    finally:
        cursor.close()
        conn.close()
    return update_ids

def format_clan_data(data: list):
    if data != []:
        return {
            'battles_count': data[0], 
            'wins_count': data[1], 
            'public_rating': data[2], 
            'league': data[3], 
            'division': data[4], 
            'division_rating': data[5], 
            'stage_type': data[6], 
            'stage_progress': data[7]
        }
    else:
        return None

def update_clan_season(clan_season: dict):
    conn = db_pool.connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        result = None
        clan_id = clan_season['clan_id']
        region_id = clan_season['region_id']
        last_battle_time = clan_season['last_battle_time']
        team_data_1 = clan_season['team_data'][1]
        team_data_2 = clan_season['team_data'][2]
        sql = """
            SELECT season, team_data FROM clan_stats WHERE clan_id = %s;
        """
        cursor.execute(sql, [clan_id])
        clan = cursor.fetchone()
        insert_data_list = []
        if clan and clan['season'] == SEASON_ID:
            original_team_data = eval(clan['team_data']) 
            old_team_data = {
                1: format_clan_data(original_team_data[0]),
                2: format_clan_data(original_team_data[1])
            }
            new_team_data = {
                1: format_clan_data(team_data_1),
                2: format_clan_data(team_data_2)
            }
            for team_number in [1, 2]:
                if new_team_data[team_number] == None:
                    continue
                if old_team_data[team_number]:
                    battles = new_team_data[team_number]['battles_count'] - old_team_data[team_number]['battles_count']
                    wins = new_team_data[team_number]['wins_count'] - old_team_data[team_number]['wins_count']
                    if battles > 2 or battles <= 0:
                        continue
                    battle_time = last_battle_time
                    if battles == 1:
                        temp_list = None
                        temp_list = [battle_time, region_id, clan_id, team_number]
                        if wins == 1:
                            temp_list += ['victory']
                        else:
                            temp_list += ['defeat']
                        battle_rating = new_team_data[team_number]['public_rating'] - old_team_data[team_number]['public_rating']
                        if battle_rating > 0:
                            temp_list += ['+'+str(battle_rating)]
                        elif battle_rating < 0:
                            temp_list += [str(battle_rating)]
                        else:
                            temp_list += [None]
                        if (
                            new_team_data[team_number]['stage_type'] and 
                            new_team_data[team_number]['stage_progress'] != None and 
                            new_team_data[team_number]['stage_progress'] != []
                        ):
                            stage_progress = new_team_data[team_number]['stage_progress']
                            if stage_progress[len(stage_progress) - 1] == 1:
                                temp_list += ['+★']
                            else:
                                temp_list += ['+☆']
                        else:
                            temp_list += [None]
                        temp_list += [
                            new_team_data[team_number]['league'],
                            new_team_data[team_number]['division'],
                            new_team_data[team_number]['division_rating'],
                            new_team_data[team_number]['public_rating'],
                            new_team_data[team_number]['stage_type'],
                            str(new_team_data[team_number]['stage_progress']) if new_team_data[team_number]['stage_progress'] else None
                        ]
                        insert_data_list.append(temp_list)
                    else:
                        temp_list = [battle_time, region_id, clan_id, team_number]
                        if wins == 2:
                            insert_data_list.append(temp_list+['victory'])
                            insert_data_list.append(temp_list+['victory'])
                        elif wins == 1:
                            insert_data_list.append(temp_list+['victory'])
                            insert_data_list.append(temp_list+['defeat'])
                        else:
                            insert_data_list.append(temp_list+['defeat'])
                            insert_data_list.append(temp_list+['defeat'])
                else:
                    battles = new_team_data[team_number]['battles_count']
                    wins = new_team_data[team_number]['wins_count']
                    if battles > 2 and battles <= 0:
                        continue
                    battle_time = last_battle_time
                    if battles == 1:
                        temp_list = None
                        temp_list = [battle_time, region_id, clan_id, team_number]
                        if wins == 1:
                            temp_list += ['victory']
                        else:
                            temp_list += ['defeat']
                        temp_list += [
                            None, None,
                            new_team_data[team_number]['league'],
                            new_team_data[team_number]['division'],
                            new_team_data[team_number]['division_rating'],
                            new_team_data[team_number]['public_rating'],
                            new_team_data[team_number]['stage_type'],
                            str(new_team_data[team_number]['stage_progress']) if new_team_data[team_number]['stage_progress'] else None
                        ]
                        insert_data_list.append(temp_list)
                    else:
                        temp_list = [battle_time, region_id, clan_id, team_number]
                        if wins == 2:
                            insert_data_list.append(temp_list+['victory'])
                            insert_data_list.append(temp_list+['victory'])
                        elif wins == 1:
                            insert_data_list.append(temp_list+['victory'])
                            insert_data_list.append(temp_list+['defeat'])
                        else:
                            insert_data_list.append(temp_list+['defeat'])
                            insert_data_list.append(temp_list+['defeat'])
            result = f'Add {len(insert_data_list)} CW records'
        else:
            result = 'FullChanged'
        sql = """
            UPDATE clan_base 
            SET 
                tag = %s, 
                league = %s, 
                touch_at = CURRENT_TIMESTAMP 
            WHERE region_id = %s 
                AND clan_id = %s;
        """
        cursor.execute(sql,[
            clan_season['tag'],
            CLAN_COLOR_INDEX.get(clan_season['color'],5),
            region_id,
            clan_id
        ])
        sql = """
            UPDATE clan_stats 
            SET 
                season = %s, 
                public_rating = %s, 
                league = %s, 
                division = %s, 
                division_rating = %s, 
                last_battle_at = FROM_UNIXTIME(%s), 
                team_data = %s 
            WHERE clan_id = %s;
        """
        cursor.execute(sql,[
            SEASON_ID,
            clan_season['public_rating'],
            clan_season['league'],
            clan_season['division'],
            clan_season['division_rating'],
            clan_season['last_battle_time'],
            str([team_data_1,team_data_2]),
            clan_id
        ])
        for insert_data in insert_data_list:
            if len(insert_data) == 13:
                sql = f"""
                    INSERT INTO clan_battle_s{SEASON_ID} (
                        battle_time, 
                        region_id, 
                        clan_id, 
                        team_number, 
                        battle_result, 
                        battle_rating, 
                        battle_stage, 
                        league, 
                        division, 
                        division_rating, 
                        public_rating, 
                        stage_type, 
                        stage_progress
                    ) VALUES (
                        FROM_UNIXTIME(%s),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                    );
                """
                cursor.execute(sql, insert_data)
            else:
                sql = f"""
                    INSERT INTO clan_battle_s{SEASON_ID} (
                        battle_time, 
                        region_id, 
                        clan_id, 
                        team_number, 
                        battle_result 
                    ) VALUES (
                        FROM_UNIXTIME(%s),%s,%s,%s,%s
                    );
                """
                cursor.execute(sql,insert_data)
        conn.commit()
        return result
    except Exception as e:
        conn.rollback()
        logger.error((f"{traceback.format_exc()}"))
        return type(e).__name__
    finally:
        cursor.close()
        conn.close()