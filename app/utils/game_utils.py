from .time_utils import TimeUtils


class GameUtils:
    """存放和游戏相关的工具函数"""
    def get_user_default_name(account_id: int):
        "获取用户的默认名称"
        return f'User_{account_id}'
    
    def get_clan_default_name():
        "获取工会的默认名称"
        return f'N/A'
    
    @staticmethod
    def get_region_id(region: str) -> int:
        region_id_dict = {
            'asia': 1,
            'eu': 2,
            'na': 3,
            'ru': 4,
            'cn': 5
        }
        return region_id_dict[region]
    
    @staticmethod
    def get_region(region_id: int) -> int:
        region_dict = {
            1: 'asia',
            2: 'eu',
            3: 'na',
            4: 'ru',
            5: 'cn'
        }
        return region_dict[region_id]
    
    @staticmethod
    def get_platform_id(platform: str) -> int:
        platform_id_dict = {
            'qq_bot': 1,
            'qq_group': 2,
            'qq_guild': 3,
            'discord': 4
        }
        return platform_id_dict[platform]
    
    @staticmethod
    def get_insignias(data: dict):
        if data is None or data == {}:
            return None
        else:
            return f"{data['texture_id']}-{data['symbol_id']}-{data['border_color_id']}-{data['background_color_id']}-{data['background_id']}"
    
    @staticmethod
    def get_dog_tag(data: str):
        if data is None or data == "":
            return {}
        data = data.split('-')
        return {
            "texture_id": data[0],
            "symbol_id": data[1],
            "border_color_id": data[2],
            "background_color_id": data[3],
            "background_id": data[4]
        }

    @staticmethod
    def check_aid_and_rid(region: str, account_id: int) -> bool:
        "检查account_id是否合法"
        account_id_len = len(str(account_id))
        if account_id_len > 10:
            return False
        # 由于不知道后续会使用什么字段
        # 目前的检查逻辑是判断aid不在其他的字段内

        # 俄服 1-9 [~5字段]
        if region == 'ru' and account_id_len < 9:
            return True
        elif (
            region == 'ru' and 
            account_id_len == 9 and 
            int(account_id/100000000) not in [5,6,7,8,9]
        ):
            return True
        # 欧服 9 [5~字段] 
        if (
            region == 'eu' and
            account_id_len == 9 and
            int(account_id/100000000) not in [1,2,3,4]
        ):
            return True
        # 亚服 10 [2-3字段]
        if (
            region == 'asia' and 
            account_id_len == 10 and
            int(account_id/1000000000) not in [1,7]
        ):
            return True
        # 美服 10 [1字段]
        if (
            region == 'na' and
            account_id_len == 10 and
            int(account_id/1000000000) not in [2,3,7]
        ):
            return True
        # 国服 10 [7字段]
        if (
            region == 'cn' and
            account_id_len == 10 and
            int(account_id/1000000000) not in [1,2,3]
        ):
            return True
        return False
    
    @staticmethod
    def check_cid_and_rid(region: str, clan_id: int) -> bool:
        "检查clan_id和region_id是否合法"
        clan_id_len = len(str(clan_id))
        # 亚服 10 [2字端]
        if (
            region == 'asia' and 
            clan_id_len == 10 and
            int(clan_id/1000000000) == 2
        ):
            return True
        # 欧服 9 [5字段]
        if (
            region == 'eu' and 
            clan_id_len == 9 and
            int(clan_id/100000000) == 5
        ):
            return True
        # 美服 10 [1字段]
        if (
            region == 'na' and 
            clan_id_len == 10 and
            int(clan_id/1000000000) == 1
        ):
            return True
        # 俄服 6 [4字段]
        if (
            region == 'ru' and 
            clan_id_len == 6 and
            int(clan_id/100000) == 4
        ):
            return True
        # 国服 10 [7字段]
        if (
            region == 'cn' and 
            clan_id_len == 10 and
            int(clan_id/1000000000) == 7
        ):
            return True
        return False
    
    @staticmethod
    def get_activity_level(is_public: bool, total_battles: int = 0, last_battle_time: int = 0):
        "获取activity_level"
        # 具体对应关系的表格
        # | is_public | total_battles | last_battle_time | activity_level | decs    |
        # | --------- | ------------- | ---------------- | -------------- | ------- |
        # | 0         | -             | -                | 0              | 隐藏战绩 |
        # | 1         | 0             | 0                | 1              | 无数据   |
        # | 1         | -             | [0, 1d]          | 2              | 活跃    |
        # | 1         | -             | [1d, 3d]         | 3              | -       |
        # | 1         | -             | [3d, 7d]         | 4              | -       |
        # | 1         | -             | [7d, 1m]         | 5              | -       |
        # | 1         | -             | [1m, 3m]         | 6              | -       |
        # | 1         | -             | [3m, 6m]         | 7              | -       |
        # | 1         | -             | [6m, 1y]         | 8              | -       |
        # | 1         | -             | [1y, + ]         | 9              | 不活跃  |
        if not is_public:
            return 0
        if total_battles == 0 or last_battle_time == 0:
            return 1
        current_timestamp = TimeUtils.timestamp()
        time_differences = [
            (1 * 24 * 60 * 60, 2),
            (3 * 24 * 60 * 60, 3),
            (7 * 24 * 60 * 60, 4),
            (30 * 24 * 60 * 60, 5),
            (90 * 24 * 60 * 60, 6),
            (180 * 24 * 60 * 60, 7),
            (360 * 24 * 60 * 60, 8),
        ]
        time_since_last_battle = current_timestamp - last_battle_time
        for time_limit, return_value in time_differences:
            if time_since_last_battle <= time_limit:
                return return_value
        return 9