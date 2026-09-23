
# 各舰种等级的权重
SHIP_TIER_WEIGHT = {
    5: 0.1,
    6: 0.3,
    7: 0.5,
    8: 0.7,
    9: 0.9,
    10: 1.0,
    11: 1.1
}

# 参与计算的最低舰种等级，1~4 级不参与
MIN_SHIP_TIER = 5

# 有效场次门槛，低于该值判为数据不足
MIN_EFFECTIVE_BATTLES = 100

# 平台参考胜率，以及小样本收缩的先验强度
REFERENCE_WIN_RATE = 0.50
PRIOR_STRENGTH = 100

# 分档阈值：相对参考胜率的偏移量
LOW_THRESHOLD = 0.04
HIGH_THRESHOLD = 0.04

# 评级结果
LEVEL_INSUFFICIENT = 0  # 数据不足，无法评级
LEVEL_LOW = 1           # 低水平
LEVEL_AVERAGE = 2       # 平台水平
LEVEL_HIGH = 3          # 高水平


class LevelAlgo:
    """用户水平评级相关公用算法"""

    @staticmethod
    def calculate_user_level(ship_data: list) -> int:
        """根据用户的全部船只数据计算水平等级

        ship_data 的每个元素为 [tier, battles, wins]，
        依次为舰种等级、战斗场次、胜利场次

        返回 LEVEL_INSUFFICIENT / LEVEL_LOW / LEVEL_AVERAGE / LEVEL_HIGH
        """
        effective_battles = 0.0
        effective_wins = 0.0

        for entry in ship_data:
            tier, battles, wins = entry

            # 低等级船只不参与计算
            if tier < MIN_SHIP_TIER:
                continue

            weight = SHIP_TIER_WEIGHT.get(tier)
            if weight is None:
                continue

            # 剔除明显异常的数据行
            if battles <= 0 or wins < 0 or wins > battles:
                continue

            effective_battles += battles * weight
            effective_wins += wins * weight

        # 有效样本量不足，判为无法评级
        if effective_battles < MIN_EFFECTIVE_BATTLES:
            return LEVEL_INSUFFICIENT

        # 小样本收缩：以平台胜率为先验，按先验强度把观测胜率向参考值拉
        prior_wins = PRIOR_STRENGTH * REFERENCE_WIN_RATE
        adjusted_wr = (
            (effective_wins + prior_wins) / (effective_battles + PRIOR_STRENGTH)
        )

        if adjusted_wr < REFERENCE_WIN_RATE - LOW_THRESHOLD:
            return LEVEL_LOW

        if adjusted_wr > REFERENCE_WIN_RATE + HIGH_THRESHOLD:
            return LEVEL_HIGH

        return LEVEL_AVERAGE
