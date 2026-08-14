# Recent 功能设计文档

Recent 服务负责记录和处理用户近期战斗数据：通过**每日快照 + 差异计算**得出用户在某段时间内的战绩变化，并以**最小的空间**支撑**任意时间区间的近期战绩查询**。

---

## 一、设计目的

玩家的战舰数据有两个特征：**每天都在变，但大部分船每天不变**。

最朴素的做法是每天存一份完整副本，但一个玩家有几百艘船，每天一份会迅速膨胀，而且其中 99% 的数据是重复的。因此设计需要同时满足三个目标：

1. **只存变化**：不存每天的完整副本，空间随"实际变化量"增长，而非随"天数"增长；
2. **能回溯**：任意一天当时的快照都能还原出来；
3. **能算差**：任意两天快照相减，即可得到这段时间的战绩增量。

这三个目标共同催生了"**快照 + 索引复用**"的分层存储结构。

---

## 二、核心设计思想

> 记录每天一次快照。没变化的船只，新快照直接**引用**上一次的数据行，而不是复制一份。

这与 git 的存储思路一致：git 不重复存没改过的文件，只存变化，靠引用串起历史。

按此思想，快照数据被拆成三层，从上到下分别是"概览 → 索引 → 数据"：

```
user_daily_summary     顶层 · 每日概览
   │   每个模式一个索引（NULL=未记录 / 0=无数据 / 日期=有数据）
   ▼
ship_index_map         中层 · 某模式某天的「船只 → 数据位置」映射
   │   index_map 形如 { ship_id: data_index, ... }
   ▼
ship_index_data        底层 · 单艘船的真实战绩快照
```

- 顶层只记"今天的数据在哪"，本身不存船数据；
- 中层只记"每艘船的数据在哪一行"，没变化的船沿用旧索引；
- 底层只在数据真正变化时插入新行。

---

## 三、数据库设计

### 3.1 顶层：`user_daily_summary`（每日概览）

每天一行，记录当天的总览信息，以及**每个模式一个索引**指向中层数据。

```sql
CREATE TABLE IF NOT EXISTS user_daily_summary (
    id               INTEGER      PRIMARY KEY,
    snapshot_date    INT          UNIQUE,                -- 快照日期 YYYYMMDD

    is_public        BOOLEAN      NOT NULL,              -- 是否公开战绩

    total_battles    INT          NOT NULL DEFAULT 0,    -- 总战斗场次
    pve_battles      INT          NOT NULL DEFAULT 0,    -- PvE 场次
    pvp_battles      INT          NOT NULL DEFAULT 0,    -- PvP 场次
    rank_battles     INT          NOT NULL DEFAULT 0,    -- Rank 场次
    clan_battles     INT          NOT NULL DEFAULT 0,    -- Clan 场次

    karma            INT          NOT NULL DEFAULT 0,    -- 业力值

    pvp_index        INT          DEFAULT NULL,          -- PvP 数据索引
    rank_index       INT          DEFAULT NULL,          -- Rank 数据索引
    clan_index       INT          DEFAULT NULL,          -- Clan 数据索引

    update_time      INT          NOT NULL,              -- 快照更新时间戳
    created_at       DATETIME     DEFAULT CURRENT_TIMESTAMP
);
```

**索引三态语义**（全库统一约定）：

| 值 | 含义 |
| --- | --- |
| `NULL` | 该模式未记录（仅迁移/异常产生，代码对已知模式绝不写 NULL） |
| `0` | 该模式已检查但无数据（交叉校验：`index==0 ⟺ battles==0`） |
| `日期` | 该模式有数据，指向最近一次发生变动的 `ship_index_map` 行 |

无变动的日子，索引沿用上一个日期，只更新顶层一行，中底层完全不动。

### 3.2 中层：`ship_index_map`（模式索引映射）

`(模式, 日期)` 一行，记录该模式当天的聚合统计，以及一张"船只 → 数据位置"的映射清单。

```sql
CREATE TABLE IF NOT EXISTS ship_index_map (
    id               INTEGER      PRIMARY KEY,
    ship_mode        INT          NOT NULL,              -- 模式：1-pvp 2-rank 3-clan
    ship_index       INT          NOT NULL,              -- 快照索引 YYYYMMDD

    ships            INT          NOT NULL DEFAULT 0,    -- 总船只数
    battles          INT          NOT NULL DEFAULT 0,    -- 总战斗场次
    wins             INT          NOT NULL DEFAULT 0,    -- 总胜场
    damage           INT          NOT NULL DEFAULT 0,    -- 总伤害
    frags            INT          NOT NULL DEFAULT 0,    -- 总击毁数
    exp              INT          NOT NULL DEFAULT 0,    -- 总经验值

    index_map        TEXT         DEFAULT NULL,          -- 船只索引合集

    updated_at       DATETIME     DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ship_mode, ship_index)
);
```

`index_map` 字段形如 `4181669616:20260804,3761190192:20260801,...`，记录"每艘船的数据在底层哪一行"。**没变化的船，索引直接沿用昨天的行**——这是省空间的关键。

把索引拆到"模式"粒度（而非旧设计的"日期"粒度），是为了支持**按模式增量更新**：某天只有 PvP 数据变了，就只重建 PvP 的映射，Rank/Clan 的映射原样沿用。

### 3.3 底层：`ship_index_data`（船只数据）

`(模式, 船只, 日期)` 一行，是数据的最小粒度，存单艘船的真实战绩快照。

```sql
CREATE TABLE IF NOT EXISTS ship_index_data (
    id               INTEGER      PRIMARY KEY,
    ship_id          INT          NOT NULL,              -- 船只 ID
    ship_mode        INT          NOT NULL,              -- 模式：1-pvp 2-rank 3-clan
    ship_index       INT          NOT NULL,              -- 快照索引 YYYYMMDD

    data_type_1      TEXT         DEFAULT NULL,          -- solo
    data_type_2      TEXT         DEFAULT NULL,          -- div2 / div
    data_type_3      TEXT         DEFAULT NULL,          -- div3

    updated_at       DATETIME     DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ship_mode, ship_id, ship_index),
    CHECK(ship_mode IN (1, 2, 3))
);
```

`data_type_1/2/3` 分别对应 solo / div2 / div3 三种数据类型，每个类型是一串 12 字段的逗号分隔字符串：

```
battles,wins,losses,damage,frags,survived,scouting_damage,art_agro,original_exp,planes_killed,hits_by_main,shots_by_main
```

例如 `2,0,2,90573,1,0,7811,98800,1263,0,0,0`。

**只有数据变化时才插入新行**，因此底层空间随"变化量"增长，而不是随"天数"增长。

### 3.4 辅助表：`ship_latest_index`（最新缓存）

记录每艘船最新的场次和索引，更新时用来判断"这艘船变没变、该 insert 还是 update"。

```sql
CREATE TABLE IF NOT EXISTS ship_latest_index (
    id               INTEGER      PRIMARY KEY,
    ship_id          INT          UNIQUE,                -- 船只 ID

    pvp_battles      INT          NOT NULL DEFAULT 0,    -- 该船 PvP 场次
    rank_battles     INT          NOT NULL DEFAULT 0,    -- 该船 Rank 场次
    clan_battles     INT          NOT NULL DEFAULT 0,    -- 该船 Clan 场次

    pvp_index        INT          DEFAULT NULL,          -- 该船 PvP 数据索引
    rank_index       INT          DEFAULT NULL,          -- 该船 Rank 数据索引
    clan_index       INT          DEFAULT NULL,          -- 该船 Clan 数据索引

    updated_at       DATETIME     DEFAULT CURRENT_TIMESTAMP
);

-- 特殊行：记录各模式的最新索引，作为异常时的兜底来源
INSERT OR IGNORE INTO ship_latest_index (ship_id) VALUES (1000000000);
```

其中一行特殊行（`ship_id = 1000000000`，不可能与真实船只 ID 冲突）用于兜底记录"各模式最新索引"。当顶层 `user_daily_summary` 出现极低概率的数据不完整时，仍能从特殊行读到各模式的最新索引，保证更新逻辑不因脏数据中断。

> **引用层级注意**：特殊行的 `*_index` 指向 map 层；普通船只行的 `*_index` 指向 data 层。

### 3.5 辅助表：`user_recent_stats`（近期明细）

面向少量 Plus 用户，把"按天"的差异进一步细分到"按战斗"粒度。

```sql
CREATE TABLE IF NOT EXISTS user_recent_stats (
    id               INTEGER      PRIMARY KEY,
    ship_id          INT          NOT NULL,              -- 船只 ID
    data_mode        INT          NOT NULL,              -- 模式：1-pvp 2-rank 3-clan
    data_type        INT          NOT NULL,              -- 数据类型：1-solo 2-div2/div 3-div3

    battles          INT          DEFAULT 0,             -- 战斗场次变化
    wins             INT          DEFAULT 0,             -- 胜利场次变化
    losses           INT          DEFAULT 0,             -- 失败场次变化
    damage           INT          DEFAULT 0,             -- 伤害变化
    planes           INT          DEFAULT 0,             -- 击落飞机变化
    frags            INT          DEFAULT 0,             -- 击毁数变化
    exp              INT          DEFAULT 0,             -- 经验值变化
    survived         INT          DEFAULT 0,             -- 存活场次变化
    scout_damage     INT          DEFAULT 0,             -- 侦查伤害变化
    art_agro         INT          DEFAULT 0,             -- 潜在伤害变化
    hit_rate         REAL         DEFAULT 0,             -- 主炮命中率

    battle_time      INT          NOT NULL,              -- 战斗结束时间戳
    created_at       DATETIME     DEFAULT CURRENT_TIMESTAMP,
    CHECK(data_mode IN (1, 2, 3)),
    CHECK(data_type IN (1, 2, 3))
);
```

---

## 四、更新流程

### 4.1 更新发现（判断要不要更新）

Recent 服务读 MySQL 中由上游维护的 `T_user_stats` 表，拿到各模式最新战斗场次，与本地特殊行缓存的场次逐一比对，**找出哪些模式的数据发生了变化**。

- 某模式场次变了 → 该模式需要重新请求；
- 都没变 → 不请求，仅当缓存过期时更新一次顶层 summary。

### 4.2 更新策略

根据本地数据库的状态，分为三种策略：

| 策略 | 触发条件 | 处理方式 |
| --- | --- | --- |
| `NEW_USER` | 本地 summary 和缓存均无数据 | 全量初始化，所有表全量 insert（快照索引落在昨日，作为 diff 基线） |
| `NORMAL` | 本地数据正常 | 按模式 diff，只写变化的数据 |
| `MISSING_SUMMARY` | 今日+昨日 summary 缺失（服务崩溃）或均为隐藏战绩 | 同 NORMAL，但 summary 同时写昨日+今日，避免丢失今日近期数据 |

### 4.3 单用户更新流程

1. 读 MySQL `T_user_stats` 最新场次 + SQLite 特殊行缓存，**比对哪些模式变了**；
2. 只请求**变化模式**的接口（account 基础接口恒请求，一次并发）；
3. 同步 MySQL 用户基础数据（`T_user_stats` 等）；
4. 逐船 diff：变化的船写新快照（底层 insert），没变化的船索引复用（中层沿用旧索引）；
5. 合并新索引写入中层 `ship_index_map`，刷新 `ship_latest_index`（普通船 + 特殊行）；
6. 顶层 `user_daily_summary` 更新为"今天"，指向新的映射；
7. 若是 Plus 用户，顺带计算 `user_recent_stats` 近期明细差值。

### 4.4 代码分层

```
recent/
├── models/        # 数据结构与领域模型
├── clients/       # API 接入：endpoints(端点注册) / requester(请求) / validator(校验) / parser(解析)
├── services/      # 业务编排：coordinator(判定) / pipeline(取数) / planner(diff) / refresher(写库) / initializer(初始化)
├── repository/    # 数据访问：summary / cache / index_map / index_data / recent
└── db/            # MySQL / SQLite 连接与事务
```

---

## 五、读取与清理流程

### 5.1 读取流程

1. 执行一次刷新流程，确保本地快照为最新；
2. 从 `user_daily_summary` 读取两个时间端点日期对应的各模式索引；
3. 通过索引定位到两个 `ship_index_map`，比对 `index_map` 找出有差异的船只及各自的数据位置；
4. 从 `ship_index_data` 中取出新旧数据，相减即得该时间区间的近期战绩。

### 5.2 清理流程（数据裁剪）

按引用图从顶层向底层逐层清理，防止悬空引用——复用索引会让旧数据行仍被近期行引用，因此**不能按日期直接删除**，只能按"是否仍被引用"来判断：

1. 删除顶层超期的 `user_daily_summary` 行（按日期 cutoff，这是保留策略的唯一锚点）；
2. 收集仍被引用的 map 行 = 剩余 summary 的各模式索引 ∪ 特殊行的各模式索引，删除其余 `ship_index_map` 行；
3. 收集仍被引用的 data 行 = 剩余 map 的 `index_map` 解析结果 ∪ 普通船只行的各模式索引，删除其余 `ship_index_data` 行。

> **引用层级注意**：特殊行引用 map 层（计入步骤 2）；普通 `ship_latest_index` 行引用 data 层（计入步骤 3）。
