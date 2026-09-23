def calculate_user_level_test(ship_data):
    """
    根据用户所有船只数据测试计算 user_level。

    ship_data:
        可迭代对象，每个元素为:
        [tier, battles, wins]

    返回:
        0 = 数据不足，无法评级
        1 = 低水平
        2 = 平台水平
        3 = 高水平
    """

    # ===== 测试参数 =====
    tier_weight = {
        5: 0.1,   # 5 级依然存在部分人机因素，因此系数很低
        6: 0.3,
        7: 0.5,
        8: 0.7,
        9: 0.9,
        10: 1.0,
        11: 1.1
    }

    # 测试阶段暂定 ±4%
    low_threshold = 0.04
    high_threshold = 0.04

    print("=" * 60)
    print("User Level Calculation Test")
    print("=" * 60)

    effective_battles = 0.0
    effective_wins = 0.0

    # Step 1: 处理每艘船
    print("\n[Step 1] Ship data calculation")

    for _, data in enumerate(ship_data, start=1):
        tier, battles, wins = data

        # Tier 1~4 不参与计算
        if tier < 5:
            continue

        if tier not in tier_weight:
            continue

        if battles <= 0:
            continue

        if wins < 0 or wins > battles:
            continue

        weight = tier_weight[tier]

        ship_effective_battles = battles * weight
        ship_effective_wins = wins * weight

        effective_battles += ship_effective_battles
        effective_wins += ship_effective_wins

    print(f"Effective Battles : {effective_battles:.2f}")
    print(f"Effective Wins    : {effective_wins:.2f}")

    # Step 2: 有效样本量检查
    print("\n[Step 2] Effective battle check")
    min_effective_battles = 100   # 最小有效场次样本量

    print(f"Minimum Effective Battles: {min_effective_battles}")
    print(f"Current Effective Battles: {effective_battles:.2f}")

    if effective_battles < min_effective_battles:
        print(
            f"Result: insufficient data "
            f"({effective_battles:.2f} < {min_effective_battles})"
        )
        print("Final User Level: 0")
        print("=" * 60)
        return 0

    # Step 3: 计算原始加权胜率
    print("\n[Step 3] Weighted win rate")

    weighted_wr = effective_wins / effective_battles

    print(f"Weighted WR = {weighted_wr:.4%}")

    # Step 4: 小样本修正
    print("\n[Step 4] Win rate shrinkage")

    reference_wr = 0.50       # 平台参考胜率
    prior_strength = 100      # 小样本修正强度
    prior_wins = prior_strength * reference_wr

    adjusted_wr = (
        effective_wins + prior_wins
    ) / (
        effective_battles + prior_strength
    )

    print(f"Reference WR       : {reference_wr:.2%}")
    print(f"Prior Strength      : {prior_strength}")
    print(f"Prior Wins          : {prior_wins:.2f}")

    print(
        f"Adjusted WR = "
        f"({effective_wins:.2f} + {prior_wins:.2f}) / "
        f"({effective_battles:.2f} + {prior_strength})"
    )
    print(f"Adjusted WR        : {adjusted_wr:.4%}")

    # Step 5: 根据阈值判断等级
    print("\n[Step 5] User level classification")

    low_limit = reference_wr - low_threshold
    high_limit = reference_wr + high_threshold

    print(f"Reference WR : {reference_wr:.2%}")
    print(f"Low Limit    : {low_limit:.2%}")
    print(f"High Limit   : {high_limit:.2%}")
    print(f"Adjusted WR  : {adjusted_wr:.2%}")

    if adjusted_wr < low_limit:
        user_level = 1
    elif adjusted_wr > high_limit:
        user_level = 3
    else:
        user_level = 2

    level_name = {
        1: "Low",
        2: "Average",
        3: "High",
    }

    print(
        f"\nFinal User Level: "
        f"{user_level} ({level_name[user_level]})"
    )

    print("=" * 60)

    return user_level

test_data = [
    # 0
    # 正常的平台偏上用户
    [
        [5, 100, 55],
        [8, 200, 120],
        [11, 50, 30],
    ],

    # 1
    # 明显低水平
    [
        [5, 100, 40],
        [7, 150, 60],
        [9, 200, 90],
    ],

    # 2
    # 明显高水平
    [
        [8, 300, 180],
        [10, 500, 300],
        [11, 200, 130],
    ],

    # 3
    # 明显低水平
    [
        [8, 300, 120],
        [10, 500, 220],
        [11, 200, 80],
    ],

    # 4
    # 高等级少量场次，但是胜率极高
    # 用于测试小样本 shrinkage
    [
        [11, 10, 8],
        [10, 20, 14],
    ],

    # 5
    # 只有 1~4 级船
    # 即使胜率极高，也应该无法评级
    [
        [1, 1000, 900],
        [3, 500, 450],
        [4, 300, 270],
    ],

    # 6
    # 5~8级为主，中高胜率
    [
        [5, 250, 150],
        [6, 300, 180],
        [7, 200, 120],
        [8, 100, 60],
    ],

    # 7
    # 大量5级场次 + 少量11级高胜率
    # 用于观察高等级数据的权重是否足够明显
    [
        [5, 2000, 1080],
        [11, 20, 15],
    ],

    # 8
    # 大量高等级船，但胜率略低于平台
    [
        [11, 1000, 450],
        [10, 1000, 440],
        [9, 500, 210],
    ],

    # 9
    # 大量高等级船 + 明显高胜率
    [
        [11, 1000, 650],
        [10, 1000, 620],
        [9, 1000, 590],
    ],
]

data = test_data[9]

level = calculate_user_level_test(data)

print("Returned level:", level)