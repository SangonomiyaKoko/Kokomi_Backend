# 用户活跃等级系统设计文档

Activity_Level 是标识用户活跃度的核心数据，它与用户平台等级共同决定每个用户的**数据刷新间隔**，是整个 Recent 服务调度的心脏。

---

## 一、活跃等级（activity_level）计算

活跃等级由**最后战斗时间（last_battle_time）距今的时间差**唯一决定，共 10 个等级（0–9）。等级越高，表示用户越久没有战斗。

```python
def _get_activity_level(current_timestamp, last_battle_time):
    if not last_battle_time or last_battle_time <= 0:
        return 0
    diff = current_timestamp - last_battle_time
    for threshold, level in USER_ACTIVITY_THRESHOLDS:
        if diff <= threshold:
            return level
    return 9
```

| 等级 | 时间差区间（秒） | 区间说明 | 活跃度 |
| --- | --- | --- | --- |
| 0 | — | 无战斗数据（last_battle_time 为空） | NoData |
| 1 | `(0, 86400]` | 1 天内 | ++++++++ |
| 2 | `(86400, 259200]` | 1–3 天 | +++++++ |
| 3 | `(259200, 604800]` | 3–7 天 | ++++++ |
| 4 | `(604800, 2592000]` | 7–30 天 | +++++ |
| 5 | `(2592000, 7776000]` | 30–90 天 | ++++ |
| 6 | `(7776000, 15552000]` | 90–180 天 | +++ |
| 7 | `(15552000, 31536000]` | 180–365 天 | ++ |
| 8 | `(31536000, 63072000]` | 1–2 年 | + |
| 9 | `(63072000, ∞)` | 超过 2 年 | - |

> 对应配置：`USER_ACTIVITY_THRESHOLDS`。

---

## 二、刷新间隔策略

刷新间隔由 **user_level（平台等级）× activity_level（活跃等级）** 共同决定：用户越重要、越活跃，刷新越频繁。

### 2.1 平台等级（user_level）

| user_level | 含义 | 说明 |
| --- | --- | --- |
| 0 | 普通用户 | 未启用 Recent 功能，刷新最慢 |
| 1 | Recent 用户 | 启用近期战绩查询，刷新中等 |
| 2 | Recent Pro 用户 | 启用详细近期数据（Plus），刷新最快 |

### 2.2 常规刷新策略

对应配置 `USER_ACTIVITY_STRATEGY`，key 为 `"{user_level}-{activity_level}"`。下表为换算后的刷新间隔：

**普通用户（user_level = 0）**

| activity_level | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 间隔 | 26h | 2d | 3d | 5d | 7d | 15d | 20d | 30d | 90d |

**Recent 用户（user_level = 1）**

| activity_level | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 间隔 | 1h | 2h | 3h | 4h | 6h | 8h | 12h | 30d | 60d |

**Recent Pro 用户（user_level = 2）**

| activity_level | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 间隔 | 10m | 20m | 25m | 30m | 1h | 15d | 20d | 30d | 60d |

> `activity_level = 0`（无战斗数据）未配置专属键，统一回落到默认 30 天。

### 2.3 特殊活跃策略（SPECIAL_ACTIVITY_STRATEGY）

仅针对 **Recent Pro 用户且 activity_level = 1**（最近 1 天内战斗过）的情况，按"距今战斗时间差"做更细粒度的分钟级刷新：

| 距今战斗时间差 | 刷新间隔 |
| --- | --- |
| `< 1h` | 1min |
| `< 3h` | 3min |
| `< 12h` | 5min |
| `< 19h` | 7min |
| 其余（19h–1d） | 10min |

即：Pro 用户刚打完一局，服务会在 1 分钟内跟进刷新，保证"近期数据"近乎实时。

### 2.4 特殊状态

| 状态 | 判定 | 刷新处理 |
| --- | --- | --- |
| 账号不存在 | `is_enabled = 0` | `activity_level = 0`，`next_refresh_at = NULL`，停止刷新 |
| 隐藏战绩 | `is_public = 0` | `activity_level = 0`；启用用户 1 天刷新一次，普通用户 30 天 |

---

## 三、刷新超时兜底（USER_REFRESH_TIMEOUT）

正常情况下由上游（Celery / Maintenance）按 `next_refresh_at` 触发刷新；若上游未按时触发，Recent 服务在 `next_refresh_at + timeout` 之后兜底强制刷新，避免数据长期不更新。

| user_level | 兜底容忍时间 |
| --- | --- |
| 1 | 1 天 |
| 2 | 1 小时 |

> `user_level = 0` 无兜底配置，普通用户不参与 Recent 兜底刷新。

---

## 四、用户停用策略

长期不活跃或异常的用户会被停用（`is_enabled` 相关标记），停用后不再刷新：

| 策略 | 配置 | 触发条件 | 含义 |
| --- | --- | --- | --- |
| 不活跃停用 | `USER_INACTIVE_DAYS = 30` | 距上次调用超过 30 天 | 用户已不再查询，停止服务 |
| 无战斗停用 | `USER_NO_BATTLE_DAYS = 180` | 距上次战斗超过 180 天 | 长期不打，数据无意义 |
| 隐藏停用 | `USER_HIDDEN_PROFILE_DAYS = 30` | 连续隐藏战绩达 30 天 | 长期隐藏，无法获取数据 |

---

## 五、刷新间隔决策流程

综合上述规则，更新用户 `next_refresh_at` 的完整决策顺序如下：

```
读 API 用户数据
  ├─ 账号不存在（is_enabled=0）
  │     → activity_level=0, next_refresh_at=NULL（停止刷新）
  ├─ 隐藏战绩（is_public=0）
  │     → activity_level=0
  │         user_level>0 → 1 天刷新一次
  │         user_level=0 → 30 天刷新一次
  └─ 正常公开
        ├─ Pro 用户(level=2) 且 activity_level=1
        │     → 按 SPECIAL_ACTIVITY_STRATEGY（分钟级）
        └─ 其余
              → 按 USER_ACTIVITY_STRATEGY["level-activity"]（默认 30 天）
