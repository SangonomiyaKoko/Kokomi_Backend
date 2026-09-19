from typing import Optional


class RatingUtils:
    # 计算评分等级所用的区间
    _METRIC_RATING_THRESHOLDS = {
        "rating":   [750,1100,1350,1550,1750,2100,2450],
        "damage":   [0.8,0.95,1.0,1.1,1.2,1.4,1.7],
        "frags":    [0.2,0.3,0.6,1.0,1.3,1.5,2.0],
        "win_rate": [40,45,50,52.5,55,60,67]
    }

    @staticmethod
    def get_metric_level(value: float, metric_name: str) -> int:
        """根据指标值计算对应的 Rating 等级

        将指标值与预设阈值列表对比，返回 1-8 的等级
        """
        thresholds = RatingUtils._METRIC_RATING_THRESHOLDS.get(metric_name)
        if not thresholds:
            return 1

        # 遍历阈值，找到第一个大于 value 的阈值位置
        for i, threshold in enumerate(thresholds):
            if value < threshold:
                return i + 1

        # value 大于等于所有阈值时返回最高等级
        return 8

    @staticmethod
    def calc_ship_rating(
        ship_data: list, server_data: Optional[list] = None
    ) -> tuple:
        """计算玩家在单艘船上的综合 Rating

        以服务器均值为基准，将玩家的胜率、场均伤害、场均击毁换算为
        比值后归一化，加权得到个人 Rating，同时给出伤害与击毁的等级
        """
        # 无服务器基准数据时无法计算 Rating
        if not server_data:
            return -1, -1, -1

        # 玩家指标与服务器均值的比值
        r_wins = ship_data[0] / server_data[0]
        r_dmg = ship_data[1] / server_data[1]
        r_frags = ship_data[2] / server_data[2]

        # 归一化处理，低于基准下限的指标统一按 0 计
        n_wins = max(0, (r_wins - 0.7) / (1 - 0.7))
        n_dmg = max(0, (r_dmg - 0.4) / (1 - 0.4))
        n_frags = max(0, (r_frags - 0.1) / (1 - 0.1))

        return (
            round(700 * n_dmg + 300 * n_frags + 150 * n_wins, 2),
            RatingUtils.get_metric_level(r_dmg, 'damage'),
            RatingUtils.get_metric_level(r_frags, 'frags')
        )
