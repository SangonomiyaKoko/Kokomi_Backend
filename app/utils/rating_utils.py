class RatingUtils:
    """API 侧专用的评分计算

    指标等级换算等通用能力由 shard.RatingAlgo 提供，
    此处仅保留需要区分模式系数的评分计算。
    """

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
