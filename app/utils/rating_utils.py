class RatingUtils:
    _RATING_THRESHOLDS = None
    _DAMAGE_THRESHOLDS = None
    _FRAGS_THRESHOLDS = None
    _WIN_RATE_THRESHOLDS = None

    @classmethod
    def init(cls, data: dict):
        """应用启动时加载配置数据"""
        cls._RATING_THRESHOLDS = data['rating']
        cls._DAMAGE_THRESHOLDS = data['damage']
        cls._FRAGS_THRESHOLDS = data['frags']
        cls._WIN_RATE_THRESHOLDS = data['win_rate']

    @staticmethod
    def calculate_rating(game_type: str, ship_data: dict, server_data: list):
        """根据用户数据和服务器数据计算个人评分及各项子评分"""
        if server_data is None or server_data == []:
            return
        
        if ship_data is None or ship_data == {}:
            return
        
        battles_count = ship_data['battles_count']
        if battles_count <= 0:
            ship_data['personal_rating'] = -1
            ship_data['damage_rating'] = -1
            ship_data['frags_rating'] = -1
            return
        
        # 用户数据
        actual_wins = ship_data['wins'] / battles_count * 100
        actual_dmg = ship_data['damage_dealt'] / battles_count
        actual_frags = ship_data['frags'] / battles_count

        # 服务器数据
        expected_wins = server_data[0]
        expected_dmg = server_data[1]
        expected_frags = server_data[2]

        # 计算PR
        # Step 1 - ratios:
        r_wins = actual_wins / expected_wins
        r_dmg = actual_dmg / expected_dmg
        r_frags = actual_frags / expected_frags

        # Step 2 - normalization:
        n_wins = max(0, (r_wins - 0.7) / (1 - 0.7))
        n_dmg = max(0, (r_dmg - 0.4) / (1 - 0.4))
        n_frags = max(0, (r_frags - 0.1) / (1 - 0.1))

        # Step 3 - PR value:
        if game_type in ['rank', 'rank_solo', 'rating_solo', 'rating_div']:
            personal_rating = 600 * n_dmg + 350 * n_frags + 400 * n_wins
        else:
            personal_rating = 700 * n_dmg + 300 * n_frags + 150 * n_wins

        ship_data['personal_rating'] = round(personal_rating, 2)
        ship_data['damage_rating'] = round(actual_dmg / expected_dmg, 2)
        ship_data['frags_rating'] = round(actual_frags / expected_frags, 2)
        return
    
    @classmethod
    def get_rating_level(cls, rating: int | float, show_eggshell: bool = False) -> int:
        """根据评分值获取对应的等级"""
        if rating is None or rating == -1:
            return 0
        
        for i in range(len(cls._RATING_THRESHOLDS)):
            if rating < cls._RATING_THRESHOLDS[i]:
                return i + 1
        
        # 特殊彩蛋功能
        if show_eggshell and rating >= 3250:
            return 9
        
        return 8
    
    @classmethod
    def get_win_rate_level(cls, win_rate: int | float, show_eggshell: bool = False) -> int:
        """根据胜率值获取对应的等级"""
        if win_rate is None or win_rate == -1:
            return 0
        
        for i in range(len(cls._WIN_RATE_THRESHOLDS)):
            if win_rate < cls._WIN_RATE_THRESHOLDS[i]:
                return i + 1
        
        # 特殊彩蛋功能
        if show_eggshell and win_rate >= 75:
            return 9
        
        return 8
    
    @classmethod
    def get_metric_level(cls, metric_id: int, value: float) -> int:
        """根据指标ID和数值获取对应的等级
        
        metric_id: 0-win_rate, 1-avg_damage, 2-avg_frags, 3-rating
        """
        thresholds_map = {
            0: cls._WIN_RATE_THRESHOLDS,      # win_rate 等级阈值
            1: cls._DAMAGE_THRESHOLDS,        # avg_damage 等级阈值
            2: cls._FRAGS_THRESHOLDS,         # avg_frags 等级阈值
            3: cls._RATING_THRESHOLDS         # rating 等级阈值
        }

        thresholds = thresholds_map.get(metric_id)
        if thresholds is None:
            return 0

        # 计算满足 value >= threshold 的数量
        count = sum(1 for th in thresholds if value >= th)
        return 1 + count