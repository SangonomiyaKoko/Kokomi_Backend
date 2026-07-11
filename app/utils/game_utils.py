from typing import Optional

from app.core import EnvConfig


class GameUtils:
    """存放和游戏相关的工具函数"""
    
    @staticmethod
    def get_user_default_name(account_id: int) -> str:
        """根据账号 ID 生成用户的默认名称"""
        return f'User_{account_id}'
    
    @staticmethod
    def get_clan_default_name() -> str:
        """获取公会的默认名称"""
        return 'N/A'

    @staticmethod
    def check_uid(uid: int) -> bool:
        """检查 UID 是否在合法的 UID 范围内"""
        uid_rule = EnvConfig.UID_RULE
        if uid_rule[0] <= uid <= uid_rule[1]:
            return True
        return False
    
    @staticmethod
    def format_nation(nation: str) -> str:
        """将国家代码格式化为完整显示名称，未找到时返回首字母大写的原始值"""
        NATION_DISPLAY = {
            "commonwealth": "Commonwealth",
            "europe": "Europe",
            "france": "France",
            "germany": "Germany",
            "italy": "Italy",
            "japan": "Japan",
            "netherlands": "Netherlands",
            "pan_america": "Pan America",
            "pan_asia": "Pan Asia",
            "spain": "Spain",
            "uk": "UK",
            "usa": "USA",
            "ussr": "USSR",
        }

        return NATION_DISPLAY.get(nation, nation.capitalize())
    
    @staticmethod
    def format_tier(tier: int) -> str:
        """将等级数字格式化为罗马数字显示"""
        ROMAN_MAP = {
            1: 'Ⅰ',
            2: 'Ⅱ',
            3: 'Ⅲ',
            4: 'Ⅳ',
            5: 'Ⅴ',
            6: 'Ⅵ',
            7: 'Ⅶ',
            8: 'Ⅷ',
            9: 'Ⅸ',
            10: 'Ⅹ',
            11: '★',
        }

        return ROMAN_MAP.get(tier, str(tier))