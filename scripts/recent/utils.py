from datetime import datetime, timezone

from settings import (
    DATE_FMT,
    TIMEZOEN, 
    SERVER_RESET_OFFSET
)

ACHIEVEMENTS = [
    'PCH001_DoubleKill', 'PCH002_OneSoldierInTheField', 'PCH003_MainCaliber', 
    'PCH004_Dreadnought', 'PCH005_Support', 'PCH006_Withering', 
    'PCH010_Retribution', 'PCH011_InstantKill', 'PCH012_Arsonist', 
    'PCH014_Headbutt', 'PCH016_FirstBlood', 'PCH017_Fireproof', 
    'PCH018_Unsinkable', 'PCH019_Detonated', 'PCH020_ATBACaliber', 
    'PCH023_Warrior', 'PCH174_AirDefenseExpert', 'PCH364_MainCaliber_Squad', 
    'PCH365_ClassDestroy_Squad', 'PCH366_Warrior_Squad', 'PCH367_Support_Squad', 
    'PCH368_Frag_Squad', 'PCH395_CombatRecon'
]

def get_formatted_date() -> str:
    """获取当前日期格式化字符串，用于日志输出"""
    return datetime.now().strftime(DATE_FMT)

def get_current_timestamp() -> int:
    """获取当前 UTC 时间的 int 类型时间戳（秒）"""
    return int(datetime.now(timezone.utc).timestamp())

def get_current_iso_time() -> str:
    """获取当前 UTC 时间的 ISO 格式字符串"""
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def get_reset_date(current_timestamp: int) -> int:
    """获取服务器重置日期（基于当地凌晨5点更新）"""
    reset_timestamp = current_timestamp + TIMEZOEN * 3600 - SERVER_RESET_OFFSET * 3600
    strftime = datetime.fromtimestamp(reset_timestamp, timezone.utc).strftime("%Y%m%d")
    return int(strftime)

def get_reset_date_list(current_timestamp: int, start_date: int) -> list:
    result = []
    for _ in range(1000):
        reset_timestamp = current_timestamp + TIMEZOEN * 3600 - SERVER_RESET_OFFSET * 3600
        strftime = int(datetime.fromtimestamp(reset_timestamp, timezone.utc).strftime("%Y%m%d"))
        result.append(strftime)
        if strftime == start_date:
            break
        current_timestamp -= 86400
    result.reverse()
    return result   