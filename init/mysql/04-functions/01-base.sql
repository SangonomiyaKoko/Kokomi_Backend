-- DELIMITER //

-- 船只PR值计算函数
-- 根据用户的实际与预期胜率、伤害、击杀数据，
-- 通过归一化与加权公式计算综合个人评级（Personal Rating）
CREATE FUNCTION F_calculate_ship_pr(
    actual_wins DOUBLE,
    actual_dmg DOUBLE,
    actual_frags DOUBLE,
    expected_wins DOUBLE,
    expected_dmg DOUBLE,
    expected_frags DOUBLE
)
RETURNS DECIMAL(10,2)
DETERMINISTIC
BEGIN
    DECLARE r_wins DOUBLE;
    DECLARE r_dmg DOUBLE;
    DECLARE r_frags DOUBLE;
    DECLARE n_wins DOUBLE;
    DECLARE n_dmg DOUBLE;
    DECLARE n_frags DOUBLE;
    DECLARE pr DOUBLE;
    IF IFNULL(expected_wins, 0) = 0
        OR IFNULL(expected_dmg, 0) = 0
        OR IFNULL(expected_frags, 0) = 0 THEN
            RETURN -1.00;
    END IF;
    -- ratios
    SET r_wins = actual_wins / expected_wins;
    SET r_dmg = actual_dmg / expected_dmg;
    SET r_frags = actual_frags / expected_frags;
    -- normalization
    SET n_wins = GREATEST(0, (r_wins - 0.7) / (1 - 0.7));
    SET n_dmg = GREATEST(0, (r_dmg - 0.4) / (1 - 0.4));
    SET n_frags = GREATEST(0, (r_frags - 0.1) / (1 - 0.1));
    -- final PR
    SET pr = 700 * n_dmg + 300 * n_frags + 150 * n_wins;
    RETURN ROUND(pr, 2);
END;