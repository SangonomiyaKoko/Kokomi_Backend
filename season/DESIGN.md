# ClanSeason 公会战赛季服务设计文档

ClanSeason 服务负责公会战赛季数据的采集与还原：轮询官方 Clan API 获取公会排行榜与公会详情，把 API 只提供的**累计快照**还原成**单场对战明细**，并维护**实时公会排行榜**。

---

## 一、设计目的

### 1.1 数据源的能力边界

官方 Clan API（`clans.korabli.su` / `clans.worldofwarships.com` 等，按 `REGION` 选域名）提供两类数据：

- **排行榜接口** `/api/ladder/structure/?realm={realm}&league={league}&division={division}&limit=1000`
  按「联赛-分段」返回该分段的公会列表（`id` / `tag` / `last_battle_at` / `season_number`）；
- **公会详情接口** `/api/clanbase/{clan_id}/claninfo/`
  返回公会在本赛季的**累计统计**（总场次、胜场、公开评分、分段评分、最长连胜、晋级赛进度）以及**两支队伍各自的累计快照**。

关键限制是：**API 不提供单场战斗记录**。它只会告诉你"这个公会打了 57 场、赢了 33 场、公开评分 1234"，而不会告诉你"第 57 场赢了、加了几分、当时是不是晋级赛"。

### 1.2 由此推导出的三个设计目标

1. **能还原单场**：把两次采集之间的累计值变化，还原成一条条可读的对战记录；
2. **能出榜**：维护一份实时的公会排行榜，供前台查询与主节点同步；
3. **能归档**：按赛季独立归档对战明细，赛季结束后可独立保留或清理。

---

## 二、核心设计思想

> **累计快照 + 差分还原**：缓存上一轮的队伍快照，与本次拉取的新快照逐字段相减；差值恰好为 1 场时，才能确定这一场战斗的胜负与分差。

这是整个服务的核心，它决定了两件事：

- `T_clan_team` 表**不是为了展示而存在**，它是下一轮做差分的**基线（baseline）**；
- 只有"两次采集之间恰好打了 1 场"才能还原。差值为 `0`（没打）或 `>1`（漏采——服务宕机、活跃窗口外、单轮内打了多场）都无法还原，后者计入 `discard` 指标。

### 2.1 数据流

```
官方 Clan API
   │  ① 排行榜接口（遍历 13 个「联赛-分段」）
   ▼
LeagueClanEntry ──────────────► T_clan_base        公会基础信息
   │
   │  ② 公会详情接口（逐公会，仅对筛出的公会）
   ▼
ClanSeasonStats ──────────────► T_clan_stats       最新累计值（排行榜数据源）
   │                          ├► T_clan_team      本轮快照（下一轮的差分基线）
   │                          └► BattleRecord     与基线相减还原出的单场明细
   │                                   │
   │                                   ▼
   │                          SQLite season_{id}.db / clan_battle
   ▼
clan_rating ──────────────────► Redis leaderboard:clan（实时排行榜）
                                       │
                                       ▼
                              clan_ranking.msgpack（前 50 名快照，供外部同步）
```

### 2.2 两个关键约定

**① 基线 `SEASON_BASELINE`**

公会尚未参加本赛季时，API 不返回队伍数据。此时以下列 8 元组作为差分起点：

```
(0, 0, 1100, 4, 2, 50, None, None)
 场次 胜场 评分 联赛 分段 分段评分 阶段 进度
```

它的意义是：即便公会"一场没打"，首场战斗也能算出正确的分差（`1100` 是赛季初始公开评分）。

落库时以 `NULL` 表示基线状态（`ClanSeasonStats.team_json(n)` 在 `TeamStats.is_baseline` 为真时返回 `None`），读取时再由 `TeamStats.from_list([])` 还原——避免为绝大多数未参战的公会写冗余 JSON。

> 但**初始分不为基线的公会，即便尚未开战也必须落库**，否则首场战斗统计不出正确的分差。这是 `is_baseline` 判定同时要求 `battles_count == 0` **且** `public_rating == 1100` 的原因。

**② 丢弃计数 `discard`**

差值不为 1 的场次无法还原，计入 SQLite `database_meta` 的 `discard` 键，与 `record`（成功还原）、`total`（两者之和）一起构成本轮的数据质量指标：

```
clan_battle（SQLite）
database_meta: total   = record + discard
               record    本轮成功还原的场次
               discard   本轮无法还原的场次
```

---

## 三、运行架构

### 3.1 进程模型

`python -m season.main` 启动一个**常驻单进程轮询循环**（docker-compose 中的 `season` 服务，容器名 `backend-season`）。每轮：

```
start_scheduler
   └─ while True:
        start = time.monotonic()
        await run_once()             # 建连 → run_worker() → 清连
        gc.collect()
        打印内存占用（MEM_MONITOR 开启时）
        sleep_time = max(1, round(REFRESH_INTERVAL - elapsed, 2))
        await asyncio.sleep(sleep_time)
```

设计要点：

- **每轮重建全部连接**（Redis / MySQL / `requests.Session`），轮末统一关闭。避免长连接在数小时空转后失效；
- 休眠时间按**上一轮耗时扣减**，使循环周期对齐 `REFRESH_INTERVAL`；耗时超出一整个周期时，`max(1, ...)` 保证至少休眠 1 秒，不会空转打满 CPU；
- 进程存活通过 Redis 键 `status:ClanSeason` 对外暴露（TTL = `REFRESH_INTERVAL + 100`），正常建连后写入、异常退出前主动删除；
- 仅注册 `SIGTERM`（Windows 下跳过），退出走 `os._exit(0)`——不展开栈、不跑清理，见第七章。

> `REFRESH_INTERVAL` 是**轮询间隔**，不是**更新间隔**。真正的更新频率由活跃窗口与公会自身的 `last_battle_at` 是否变化决定——绝大多数轮次会在触发判定阶段直接返回。

**俄服（`REGION == 'ru'`）特殊处理**：俄服官方以 Rating（评分战）替代了 CLAN 模式，本服务不适用。`run_once` 在首轮建连后**不执行任何更新**，直接把 `status:ClanSeason` 改写为一个**无 TTL 的永久键**，随后 `start_scheduler` 立即 `return`，`main` 返回，**进程自行退出**。因此俄服环境下本服务只是"亮个灯"后结束，不参与轮询。

### 3.2 代码分层

```
season/
├── main.py          # 进程入口：打印启动参数、注册信号、启动调度器
├── settings.py      # 配置装载：环境变量 / data 下的 JSON / init 下的 SQL
├── logger.py        # 日志与异常落盘（封装 shard 的 logger 与 exception_writer）
├── core/            # 调度与上下文
│   ├── context.py   #   RunContext（整轮）/ UpdateContext（单公会）
│   ├── scheduler.py #   轮循环：建资源 → 跑一轮 → 清资源 → 休眠
│   └── worker.py    #   单轮编排：串起各 service
├── services/        # 业务编排（无状态类方法，按需调用）
├── clients/         # 外部 API 接入（端点注册 + 请求 + 指标上报）
├── repository/      # 数据访问（纯 SQL，不感知业务）
├── models/          # 领域模型（frozen dataclass）
└── db_ops/          # MySQL / SQLite 连接与事务上下文管理器
```

分层职责边界：

| 层 | 只做 | 不做 |
| --- | --- | --- |
| `core` | 流程编排、资源生命周期、异常兜底 | 业务规则、SQL |
| `services` | 业务规则、数据加工、事务边界（调用 db_ops） | 直接拼 SQL |
| `repository` | SQL 语句与行 → 模型转换 | 业务判断、事务控制 |
| `models` | 数据结构、序列化、派生属性 | IO |
| `clients` | 拼 URL、发请求、错误分类、指标上报 | 业务语义 |
| `db_ops` | 连接与事务的上下文管理 | 任何业务 SQL |

**依赖方向单向向下**，且 `services` 之间只允许一条依赖：`updater → parser`（流水线需要用解析器）。其余 service 互不调用，由 `core/worker.py` 统一编排。

### 3.3 services 层职责一览

| 模块 | 类 / 函数 | 职责 |
| --- | --- | --- |
| `collector` | `LeagueCollector` | 遍历 13 个「联赛-分段」，收集全部活跃公会条目 + 赛季切换检测 |
| `collector` | `read_season_data` / `refresh_season_data` | 读写本地赛季配置 `data/json/clan_season.json` |
| `syncer` | `ClanBaseSyncer` | 同步公会基础信息，并筛选出本轮需要刷详情的公会 |
| `updater` | `ClanSeasonUpdater` | 单公会流水线：拉详情 → 解析 → 差分 → 提交 → 刷榜 |
| `parser` | `ClanStatsParser` | 公会详情响应 → `ClanSeasonStats`（含晋级赛解析） |
| `ranking` | `ClanRankingWriter` | 生成排行榜 msgpack 快照 |

> 历史上曾有一个独立的 `planner.py`（`BattleRecordPlanner`）负责差分，现已并入 `updater` 的 `_plan_record` / `_plan_team`。

### 3.4 上下文对象

两个 `dataclass` 分别承载两种粒度的状态，避免层层传参：

**`RunContext`** — 整轮循环的状态

| 字段 | 说明 |
| --- | --- |
| `session` / `redis_client` / `mysql_connection` | 本轮中间件连接（`create_resources` 后填充） |
| `season_id` | 当前赛季 ID |
| `clan_entries` | 本轮收集到的全部公会条目 |
| `league_counts` | 各联赛的公会数量分布（仅用于日志） |
| `record_match` / `discard_match` | 本轮成功还原 / 无法还原的场次计数 |

另提供 `set_status_key()` / `del_status_key()` 维护服务状态键。

**`UpdateContext`** — 单个公会更新的状态

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `clan_id` / `season_id` | `int` | 目标公会与赛季（构造时传入） |
| `stats` | `ClanSeasonStats \| None` | 本次拉取并解析出的最新统计 |
| `cache` | `ClanTeamCache \| None` | 从 `T_clan_team` 读出的旧队伍快照（差分基线） |
| `record` | `BattleRecord \| None` | 差分还原出的待写入对战明细 |

> 三个可选字段均为 `field(init=False, default=None)`：由流水线按阶段逐步填充，`None` 即代表"该阶段未产出"。

---

## 四、数据模型

`models/clan.py` 中的领域模型全部为 `@dataclass(frozen=True, slots=True)`——不可变、无 `__dict__`，保证单轮内大量实例的构造与比较开销可控。

### 4.1 `TeamStats` — 单支队伍的累计快照

```python
battles_count, wins_count, public_rating, league, division,
division_rating, stage_type, stage_progress
```

固定 8 字段，是**差分的原子单位**。

- `from_list(data)`：由 8 元素数组创建，数组为空时返回 `SEASON_BASELINE`。API 响应中的队伍数组与 `T_clan_team` 中缓存的 JSON 数组结构完全一致，因此两条读取路径共用本方法，**下标映射只在此处定义一次**；
- `is_baseline`：`battles_count == 0 and public_rating == 1100`，用于决定落库时写 JSON 还是 `NULL`；
- `to_list()`：序列化回数组。

> `battle_time` 不在队伍快照中——一场战斗的时间由公会级的 `last_battle_at` 提供，因为 API 不区分两支队伍各自的最后战斗时间。

### 4.2 `ClanSeasonStats` — 单公会的赛季统计

由 API 响应解析而来，是写入 MySQL 与生成明细的唯一输入：

| 字段 | 来源 |
| --- | --- |
| `clan_id` / `season_id` | 入参 |
| `leading_team_number` | `ladder.leading_team_number` |
| `battles_count` / `wins_count` | `ladder.*` |
| `public_rating` / `league` / `division` / `division_rating` | `ladder.*` |
| `longest_winning_streak` | `ladder.longest_winning_streak` |
| `stage_type` / `stage_battles` / `stage_victories` / `stage_progress` | 由**主力队伍**的晋级赛数据解析 |
| `last_battle_time` | `ladder.last_battle_at` 转时间戳 |
| `team_alpha` / `team_bravo` | 两支队伍各自的 `TeamStats` |

派生属性：

- `win_rate` — `wins / battles * 100`，保留两位小数，`battles <= 0` 时返回 `0.0`；
- **`clan_rating` — 综合评分**：

  ```python
  public_rating + stage_battles * 0.1 + stage_victories * 0.01
  ```

  写入 `T_clan_stats.public_rating`，同时用作 Redis 排行榜的排序分数。

> **为什么需要综合评分？** 晋级赛期间公开评分不再变化，若纯按 `public_rating` 排序，正在打晋级赛的公会排名会整段停滞，看不出进展。由于一个晋级赛阶段的场次是个位数（即进度串长度），`stage_battles * 0.1 + stage_victories * 0.01` 的取值恒小于 1，因此综合评分的作用是**在公开评分相同时，按晋级赛进度做次级排序**——它不改变任何跨分档的排名，只在同分档内部区分先后。

- `team_json(n)` — 取第 n 支队伍的序列化结果，**基线状态返回 `None`**（即写库时的 `NULL`）。

### 4.3 `BattleRecord` — 一条对战明细

字段顺序**与 SQLite `clan_battle` 表列序严格一致**（除自增主键与 `created_at`），`to_list()` 的结果可直接作为 `execute` 的参数：

```python
battle_time, clan_id, team_number, victory, result, rating,
league, division, division_rating, stage_type, stage_progress
```

其中展示型字段 `result` 由 `_plan_team` 按**优先级链**格式化：

| 优先级 | 条件 | `result` 取值 |
| --- | --- | --- |
| ① | 该队伍正处于晋级赛 / 保级赛 | `'+' + 进度串末位`，如 `'+★'` |
| ② | 联赛等级发生变化 | `▲`（晋级）/ `▼`（降级） |
| ③ | 公开评分发生变化 | `'+N'` / `'-N'`（如 `'+5'`） |
| ④ | 都不满足（评分未动） | `'—'` |

`victory` 为胜场差，`rating` 为该队伍当前的公开评分。

> **联赛编号方向**：`0=紫金 1=白金 2=黄金 3=白银 4=青铜 5=无`，**数字越小段位越高**（见 `app/constants/clan.py` 的颜色映射与两张表的列注释）。当前 `_plan_team` 中写的是 `new.league > old.league → PROMOTION`，与上述约定相反，**待确认**。

### 4.4 其余模型

| 模型 | 用途 |
| --- | --- |
| `LeagueClanEntry` | 排行榜接口的单个公会条目：`clan_id` / `tag` / `league` / `last_battle_time` / `season_id` |
| `ClanRecord` | `T_clan_stats` 中的赛季状态：`clan_id` / `season` / `last_battle_time`，用于判断"这个公会变没变" |
| `ClanTeamCache` | `T_clan_team` 中缓存的 `season` / `team_alpha` / `team_bravo`，由 `from_row` 把 `NULL` 还原为基线 |
| `StageInfo` | 单支队伍晋级赛的解析中间态：`stage_type` / `battles` / `victories` / `progress`（定义在 `parser.py`） |

---

## 五、数据库设计

### 5.1 MySQL（主库，跨赛季共用）

#### `T_clan_base` — 公会基础信息

```sql
clan_id          BIGINT       NOT NULL   -- 10 位非连续数字，UNIQUE
tag              VARCHAR(10)  NOT NULL   -- 公会标签
league           TINYINT      DEFAULT 5  -- 段位 0紫金 1白金 2黄金 3白银 4青铜 5无
created_at / updated_at
```

由 `ClanBaseSyncer` 维护：排行榜接口即可拿到 `tag` 与 `league`，**无需请求详情**。

#### `T_clan_stats` — 公会赛季统计

```sql
clan_id          BIGINT       NOT NULL   -- UNIQUE
season           TINYINT      DEFAULT 0  -- 赛季 ID
leading_team     TINYINT                 -- 主力队伍编号
battles          INT                      -- 战斗总数
win_rate         FLOAT                    -- 胜率
public_rating    FLOAT        DEFAULT 1100  -- 综合评分（含晋级赛加成）
league           TINYINT                 -- 段位
division         TINYINT                 -- 分段
division_rating  INT                     -- 分段评分
max_streak       INT                      -- 最长连胜
stage_type       TINYINT                 -- 晋级赛类型 1=晋级 2=保级
stage_progress   VARCHAR(5)              -- 晋级赛进度（★☆ 串）
last_battle_at   TIMESTAMP               -- 最后战斗时间，INDEX
```

本表承担两个职责：

1. 前台公会详情页与排行榜的直接数据源；
2. **本轮的"变没变"判定依据**——`ClanBaseSyncer` 用 `last_battle_at` 与 `season` 筛出需要刷详情的公会。

#### `T_clan_team` — 队伍快照缓存（差分基线）

```sql
clan_id          BIGINT   NOT NULL   -- UNIQUE
season           TINYINT  DEFAULT 0  -- 赛季 ID
team_alpha       JSON     DEFAULT NULL  -- 队伍 1 数据
team_bravo       JSON     DEFAULT NULL  -- 队伍 2 数据
```

**本表是差分还原的核心**：每轮更新后覆盖写入本轮快照，下一轮读出来与新快照相减。`NULL` 表示该队伍处于赛季基线状态。

`season` 字段用于**检测跨赛季**：若缓存中的 `season` 与当前赛季不符，说明本赛季首轮数据尚无可比基线，此时不做差分，直接把该公会的全部场次计入 `discard`。

#### `T_tracking_meta` — 任务追踪

```sql
tracking_key     VARCHAR(50)  -- 'clan_season'
tracking_type    VARCHAR(20)  -- 'refresh_time'
tracking_value   TIMESTAMP    -- 上次成功完成整轮更新的时间
UNIQUE KEY uk_key_type (tracking_key, tracking_type)
```

提供两个操作：

- `is_need_update` — 追踪值为 `NULL`，或距上次更新已超过 `FALLBACK_REFRESH_SECONDS`（配置项，默认 86400 秒）时返回 `True`；追踪行整行缺失时返回 `False`，该情况由初始化种子数据（`('clan_season', 'refresh_time')`）兜底；
- `update_tracking_key` — 写为 `NOW()`。

两者共同实现**保底每日刷新一次**。

#### 初始化联动

新公会首次出现时，`ClanBaseSyncer` 除插入 `T_clan_base` 外，还会按 `CommonConfig.CLAN_INIT_TABLE_LIST` 为 `T_clan_users` / `T_clan_stats` / `T_clan_team` 各插入一条仅含 `clan_id` 的占位行，保证后续所有 `UPDATE` 都有命中行。`T_clan_stats` 的行同时也是"已建档"的判定依据。

> `T_clan_users` 的其余字段（成员数、活跃等级、下次刷新时间等）由 ClanMember 服务（`scripts/member/`）维护，本服务只负责建行；`is_enabled` 另可由后台接口 `app/models/clan.py` 手动切换。

### 5.2 SQLite（赛季库，每赛季一个文件）

文件路径 `data/local/season_{season_id}.db`，由 `ensure_database()` 按 `init/sqlite/clan_battle.sql` 建表。

> 对战明细放在 SQLite 而非 MySQL，是因为它是**纯追加、只增不减、按赛季隔离**的时序数据：单赛季可达数百万行，用独立文件承载既便于整体归档/清理，也不给主库带来写入压力。

#### `clan_battle` — 对战明细

```sql
id               INTEGER  PRIMARY KEY AUTOINCREMENT
clan_id          INTEGER  NOT NULL   -- INDEX
team_number      INTEGER  NOT NULL   -- 队伍编号（1 或 2）
victory          INTEGER  NOT NULL   -- 胜场差（增量恰为 1 时恒为 1 或 0）
result           TEXT     NOT NULL   -- 战斗结果（'+5' / '▲' / '▼' / '+★' / '—'）
rating           INTEGER  NOT NULL   -- 战斗结束时的公开评分
league           INTEGER  NOT NULL   -- 联赛等级
division         INTEGER  NOT NULL   -- 分段
division_rating  INTEGER  NOT NULL   -- 分段评分
stage_type       INTEGER  DEFAULT NULL  -- 1=晋级 2=保级
stage_progress   TEXT     DEFAULT NULL  -- 晋级赛进度（★☆ 串）
battle_time      INTEGER  NOT NULL   -- INDEX
created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
```

#### `database_meta` — 数据质量指标

```sql
metric_key   TEXT UNIQUE      -- total / record / discard
metric_value INTEGER DEFAULT 0
```

建表时预置三行，`ClanBattleRepository.update_meta` 以**累加**方式写入本轮计数（一轮一次，不是一行一次）。

### 5.3 Redis

| 键 | 类型 | 用途 | 生命周期 |
| --- | --- | --- | --- |
| `leaderboard:clan` | ZSET | 公会排行榜，score = `clan_rating` | 长期；赛季切换时整体删除 |
| `status:ClanSeason` | STRING | 服务存活心跳 | TTL = `REFRESH_INTERVAL + 100`；俄服为永久键 |
| `metrics:http:{annual\|monthly\|daily:total\|daily:error}:{date}` | STRING | HTTP 调用量与错误数 | 由上游统一维护 |

---

## 六、更新流程

### 6.1 触发判定（三层闸门）

`run_worker` 在真正开始采集前，依次通过三道判断，任意一道不满足即整轮跳过：

| 闸门 | 判断 | 不满足时 |
| --- | --- | --- |
| ① 赛季已配置 | `clan_season.json` 的 `id != 0` | 记 warning 后返回 |
| ② 保底每日一次 | `is_need_update('clan_season', 'refresh_time')` | **进入闸门 ③** |
| ③ 处于活跃窗口 | `GameUtils.is_cb_active(REGION, start, finish)` | 记日志后返回 |

闸门 ② 与 ③ 是**或**的关系：`is_need_update` 表示"距上次成功更新已超过 `FALLBACK_REFRESH_SECONDS`"，一旦成立就**绕过**窗口判断强制刷新，保证哪怕活跃窗口配置有误、或长期无战斗，数据也能每天至少同步一次。

`is_cb_active` 的判定逻辑（`shard/game_utils.py`）：

1. 若 `season_start` 与 `season_finish` **都已填写**，且当前时间不在 `[start, finish]` 内 → 直接返回 `False`；
   （两者任一为空时跳过此检查——新赛季起止时间未知，需人工补录，期间退化为纯窗口判断）
2. 取当前 UTC 时间的**星期**，查 `CLAN_BATTLE_WINDOWS[weekday]` 的各时间窗口；
3. 窗口需同时满足：当前时间落在 `[start, end + 29min)` 内，且窗口的 `regions` 列表包含当前 `REGION`。

窗口的结束时刻按 `end[1] + 29` 放宽（如 `04:30 → 04:59`、`22:00 → 22:29`），用于覆盖"窗口关闭瞬间开打、结果稍后才结算"的战斗。

> 各服窗口差异集中在**周三、周四、周六、周日**；`cn` 服只参与其中的 UTC `[11,30]-[15,30]` 窗口（北京时间 19:30–23:30），不参与凌晨与晚间那两个窗口；`ru` 服不参与任何窗口（服务本身也不运行）。

### 6.2 全量收集排行榜

`LeagueCollector.main` 遍历 `ClanPolicy.LEAGUE_LIST` 的 13 个「联赛-分段」组合（`0-1`，`1-1` … `4-3`），逐个请求排行榜接口。

- `realm` 由 `GameUtils.CLAN_REALM_MAP[REGION]` 映射（如 `asia → sg`、`na → us`、`cn → cn360`）；
- 单个分段请求失败只记日志并 `continue`，**不中断整轮**；
- 每段 `limit=1000`，累加得到 `clan_entries` 与 `league_counts`（后者仅用于日志）。

**赛季切换处理**是这里最需要小心的分支。取该分段第一条数据的 `season_id` 与 `run_ctx.season_id` 比对：

| 情形 | 处理 |
| --- | --- |
| `entries` 已非空（本轮已收集到旧赛季数据） | 直接 `return False`，**放弃本轮**，等下轮从干净状态重来 |
| `entries` 为空（本轮首次发现新赛季） | 更新 `run_ctx.season_id`；`refresh_season_data` 写入新赛季 ID 并把 `start`/`finish` 重置为 `None`；删除 Redis `leaderboard:clan` |

之所以对第一种情形选择放弃整轮，是因为此时 `clan_entries` 中混有新旧两个赛季的公会，继续处理会产生错误的差分基线。而 `start`/`finish` 置空是刻意的——新赛季的起止时间未知，置空后 `is_cb_active` 会退化为纯窗口判断，服务得以继续工作，等待人工补录准确时间。

### 6.3 同步基础数据并筛选待刷新公会

`ClanBaseSyncer.main` 在**一个 MySQL 事务**内完成：

1. **批量读取** `T_clan_stats` 中已建档公会的 `(clan_id, season, last_battle_at)`；
2. **已存在的公会**：批量 `UPDATE T_clan_base` 的 `tag` 与 `league`（`executemany`）；
3. **新出现的公会**：批量 `INSERT T_clan_base`，并按 `CLAN_INIT_TABLE_LIST` 为三张子表插入占位行；
4. **筛选 `update_ids`**，规则如下：

| 条件 | 是否需刷详情 | 原因 |
| --- | --- | --- |
| 数据库中不存在该公会 | ✅ | 新公会必然需要首轮数据 |
| `entry.last_battle_time is None` | ❌ | 排行榜未给出最后战斗时间，无从判断变化 |
| `record.last_battle_time is None` | ✅ | 库中没有基线时间，需要补齐 |
| `record.last_battle_time != entry.last_battle_time` | ✅ | 打过新战斗 |
| `record.season != run_ctx.season_id` | ✅ | 跨赛季，需要重置基线 |

> **这是整个服务最关键的降本设计**：排行榜接口只能告诉你"这个公会的 `last_battle_at` 变了"，详情接口才能告诉你"具体变成什么"。用前者做粗筛，只为真正有新战斗的公会请求详情，使绝大多数轮次的详情请求量与实际参战公会的数量同阶，而不是与在榜公会总数同阶。
>
> 同一公会可能同时出现在多个分段中，`update_ids` 以 `set` 去重（不保证顺序）。

### 6.4 逐公会更新流水线

`ClanSeasonUpdater.main` 是服务里分支最多的函数，流程被刻意划成**三个阶段**，以"拉取 + 解析"作为**唯一的分水岭**：

```
阶段一  _fetch_stats
   ① 请求详情 fetch_clan_info          失败 → 返回 False
   ② 解析 ClanStatsParser.main         异常 → 返回 False
   ③ 读取差分基线 load_team_cache
   → 成功则 ctx.stats / ctx.cache 就位

        ↓ 阶段一失败：整轮放弃该公会（不写库、不刷榜）

阶段二  _plan_record   （异常仅记日志）
   ④ 逐队算场次差（负数截断为 0）
   ⑤ 按差值决定是否生成 BattleRecord，并给出 (record_inc, discard_inc)
   → 所有提前退出都用「返回值」表达，不用 return

        ↓ 阶段二失败：只意味着本轮没有明细，统计照常写入

阶段三  提交
   ⑥ _commit：MySQL 事务（T_clan_stats + T_clan_team）
              有明细时再开 SQLite 事务（clan_battle）
   ⑦ Redis ZADD leaderboard:clan
   ⑧ 累加 record_match / discard_match
```

**第 ④ 步的差分**对 `team_number ∈ {1, 2}` 各做一次：

```python
battles_diff = max(new.battles_count - old.battles_count, 0)
```

| 情形 | 处理 |
| --- | --- |
| `cache.season != 当前赛季` | 无有效基线，两队场次全部计入 `discard`，不生成明细 |
| `battles_diff == 0`（两队之和） | 无新增场次，不生成明细 |
| `battles_diff > 1`（两队之和） | 漏采，无法逐场还原，全部计入 `discard` |
| `battles_diff == 1` | **生成一条 `BattleRecord`**，`record_inc = 1`；差值必来自其中一支队伍，据此确定 `team_number` |

> **注意"恰好为 1"这个硬约束的代价**：若某个公会在一轮轮询间隔内连打 3 场，这 3 场都会被丢弃。因此 `discard / total` 是衡量数据完整性的核心指标——活跃窗口内 `REFRESH_INTERVAL`（默认 60 秒）需要足够小，才能让"一轮一场"成为常态。

**为什么阶段二必须用返回值而不是 `return`**：阶段二内部的多个提前退出（无新增场次、增量 > 1、赛季不一致）意味着**"本轮没有明细要记"，而不是"这个公会更新失败"**——它新拉到的统计依然是有效的、更新的。若把这些早退写成 `return`，这些公会就会**只写 MySQL 不刷 Redis**，导致排行榜分数长期停在旧值。

**写库顺序**上，MySQL 事务（`T_clan_stats` + `T_clan_team`）与 SQLite 事务（`clan_battle`）是**分开的两次事务**，且 MySQL 在前：前者写入基线，后者写入由基线推出的明细。若 SQLite 写入失败，基线已经更新，该场次将永久丢失——这是为了不让 SQLite 的故障阻塞主库数据的更新。

**先落库、再刷缓存**：`ZADD` 排在 `_commit` 之后。因为排行榜快照是以 MySQL 为准去 join 的（见 6.5），缓存先行会制造出"Redis 里有、MySQL 里没有"的公会，恰好触发 6.5 的放弃逻辑。

**阶段三的异常不吞**：`_commit` 与 `ZADD` 的异常直接向上抛出，中断整轮。理由见第七章。

### 6.5 生成排行榜快照

全部公会更新完毕后，`ClanRankingWriter.main` 生成本轮快照：

1. `zcard leaderboard:clan` 取在榜公会总数（为 0 则跳过）；
2. `zrevrange 0, 49` 取**前 50 名**（`TOP_CLAN_LIMIT`）；
3. 从 MySQL 批量读取这 50 个公会的展示字段（`T_clan_stats` LEFT JOIN `T_clan_base` 取 `tag`），并叠加 `RatingUtils.get_metric_level` 计算出的胜率等级；
4. 组装 payload 写入 `data/local/clan_ranking.msgpack`：

```python
{
    'time':   当前时间戳,
    'season': 赛季 ID,
    'clans':  在榜公会总数,      # 注意：是总数，不是快照条数
    'data':   [[名次, clan_id, tag, leading_team, battles, win_rate,
                win_rate_level, league, division, public_rating,
                max_streak, stage_type, stage_progress, last_battle_at], ...]
}
```

名次按**实际写入的行数**连续编排（`len(data) + 1`），而非 ZSET 中的原始 rank——即使中间有公会因数据缺失被跳过，快照里的名次也是连续的。

若某个在榜公会查不到 `T_clan_stats` 行，说明 ZSET 中存在脏数据：代码会 `zrem` 剔除该成员并**放弃本次快照**，在下轮重建。

> 取舍：宁可本轮不出快照，也不出一份含缺失行的快照。

### 6.6 写回追踪时间

`run_worker` 用 `try / except / finally` 包裹整个流程，`finally` 中**仅当本轮未失败时**才写回追踪时间：

```python
failed = False
try:
    ...
    return              # 提前返回（无活跃公会 / 无需更新）时 failed 仍为 False
except Exception:
    failed = True
    raise
finally:
    if not failed:
        BasicDataRepository.update_tracking_key(...)
```

这一设计把"本轮任务的完成"与"数据的正确"绑定在一起：

- **提前返回**（无活跃公会、无待刷新公会）视为**已完成**，追踪时间照常写回——没有可做的工作本身就是一种完成；
- **失败**（SQLite 异常、排行榜收集失败、单公会写库失败）不写回，于是保底计时不会重置，下轮会继续重试。

### 6.7 完整时序

```
start_scheduler
  └─ run_once
       ├─ create_resources        建连 + 置 status:ClanSeason
       ├─ [REGION == 'ru']        改永久键 → 返回 → start_scheduler 退出
       └─ run_worker
            ├─ read_season_data                    ← 闸门 ①
            ├─ is_need_update / is_cb_active       ← 闸门 ②③
            ├─ ensure_database                     ← 建/校验赛季 SQLite
            ├─ LeagueCollector.main                ← 收集 13 段排行榜（含赛季切换检测）
            ├─ ClanBaseSyncer.main (MySQL 事务)    ← 同步基础信息 + 筛选
            ├─ for clan_id in update_ids:
            │     ClanSeasonUpdater.main           ← 逐公会流水线（三阶段）
            ├─ update_meta (SQLite 事务)           ← 写 record / discard
            ├─ ClanRankingWriter.main              ← 生成 msgpack 快照
            └─ update_tracking_key (MySQL 事务)    ← 仅当未失败
```

---

## 七、关键设计与边界处理

| 设计点 | 处理方式 | 目的 |
| --- | --- | --- |
| **差分必须为 1** | 两队差值之和 `!= 1` 时不生成明细，`> 1` 计入 `discard` | 只有恰好一场才能确定胜负与分差，宁缺毋滥 |
| **早退用返回值** | `_plan_record` 的所有分支返回 `(record_inc, discard_inc)` | 保证"无明细"的分支仍会刷榜与写库 |
| **阶段二异常只记日志** | 由 `main` 捕获后按 `(0, 0)` 继续 | 统计已解析成功，不应因为算不出明细而丢弃 |
| **阶段三异常向上抛** | `_commit` / `ZADD` 不捕获 | 能失败通常意味着数据库或 Redis 整体不可用；若逐个吞掉会产生数千条重复异常日志（fail-fast） |
| **跨赛季双层防护** | 收集阶段发现新赛季→放弃本轮并重置配置；单公会 `season` 不符→全场次计入 `discard` | 避免用上赛季基线差分出错误明细 |
| **新赛季起止时间未知** | `refresh_season_data` 把 `start`/`finish` 置 `None` | 退化为纯窗口判断，服务不中断，等待人工补录 |
| **新公会建档** | `T_clan_base` + 三张子表同时插入占位行 | 保证后续所有 `UPDATE` 都有命中行 |
| **未参战公会不写冗余** | `is_baseline` 时 `T_clan_team` 写 `NULL` | 绝大多数公会未参战，避免 JSON 冗余 |
| **初始分非基线必须落库** | `is_baseline` 同时要求场次为 0 且评分为 1100 | 否则首场战斗算不出正确分差 |
| **失败不写追踪时间** | `finally` 中 `if not failed` 才写回 | 保留保底重试的机会 |
| **提前返回视为完成** | `return` 路径 `failed` 仍为 `False` | 无工作可做时正常推进保底计时 |
| **连接每轮重建** | `run_once` 建连、`finally` 清理 | 规避长连接在数小时空转后失效 |
| **单分段请求失败不中断** | 记日志后 `continue` | 13 个分段中个别失败不损失其余数据 |
| **单公会拉取/解析失败隔离** | `_fetch_stats` 返回 `False`，循环继续 | 一个公会的数据问题不拖垮整轮 |
| **ZSET 脏数据自愈** | 快照时查不到 `T_clan_stats` 则 `zrem` 并放弃本次快照 | 下轮自动重建，避免脏数据长期驻留 |
| **比对前只做粗筛** | 用排行榜的 `last_battle_at` 变化筛选，再拉详情 | 详情请求量与"实际参战公会数"同阶，而非"在榜总数"同阶 |
| **先落库再刷缓存** | `ZADD` 排在 `_commit` 之后 | 避免制造"Redis 有、MySQL 无"的公会 |
| **建库失败删残留** | `ensure_database` 失败时 `unlink` 残缺文件 | 空库文件存在会让后续写入全部失败 |
| **退出不展开栈** | `SIGTERM` / `KeyboardInterrupt` 走 `os._exit(0)` | 主线程通常阻塞在同步 IO 上，优雅退出可能挂住容器 |
| **俄服自退** | `REGION == 'ru'` 置永久键后结束进程 | 该服无 CLAN 模式，服务不应参与轮询 |

---

## 八、对外读取

### 8.1 实时排行榜（Redis）

前台直接读 `leaderboard:clan` ZSET：

- `zcard` 取总数；`zrevrange` 取分页；`zrevrank` 取单个公会的名次；
- score 为 `clan_rating`（含晋级赛加成的综合评分）。

对应接口：`app/apis/ranking/clan.py`、`app/apis/external/clan.py`。

### 8.2 排行榜快照（msgpack）

`data/local/clan_ranking.msgpack` 由 `app/routers/external_urls.py` 的 `download_clan_ranking_msgpack` 以附件形式对外提供，供**主节点**同步本节点的榜单数据。

### 8.3 对战明细（SQLite）

`data/local/season_{season_id}.db` 为按赛季隔离的独立文件，可整体归档或清理；`database_meta` 中的 `record` / `discard` / `total` 用于监控数据还原的完整度。

### 8.4 公会赛季统计（MySQL）

`T_clan_stats` 与 `T_clan_team` 由 ClanMember / 排行等前台服务直接读取。

---

## 九、配置项

### 9.1 服务配置 `data/json/services_config.json`

```json
"ClanSeason": {
    "REFRESH_INTERVAL": 60,             // 轮询间隔（秒），同时也是 status 键 TTL 的基数
    "REQUEST_TIMEOUT": 5,               // 单次 HTTP 请求超时（秒）
    "FALLBACK_REFRESH_SECONDS": 86400,  // 保底刷新间隔：距上次成功更新超过该值则强制刷新
    "MEM_MONITOR": true                 // 是否每轮打印进程内存占用
}
```

### 9.2 赛季配置 `data/json/clan_season.json`

```json
{"id": 35, "start": null, "finish": null}
```

| 字段 | 说明 |
| --- | --- |
| `id` | 当前赛季 ID，`0` 表示未配置（服务空转）；由服务在检测到赛季切换时自动更新 |
| `start` / `finish` | 赛季起止时间戳；**为 `null` 时跳过赛季区间校验**，退化为纯窗口判断 |

### 9.3 环境与标记

| 配置 | 来源 | 说明 |
| --- | --- | --- |
| `REGION` | `data/json/init_marker.json` | 决定 Clan API 域名、`realm` 映射与活跃窗口的服务器判定 |
| `MYSQL_*` / `REDIS_*` | 环境变量（`env.dev` / `env.prod`） | 中间件连接 |
| `LOG_LEVEL` | 环境变量 | 日志级别 |
| `SSL_CA_BUNDLE` | 环境变量 | 俄服接口证书校验（设置后 `session.verify` 指向该证书） |
| `PLATFORM` | 环境变量 | 以 `KokomiAPI` 开头判定为生产环境，从而加载 `env.prod` |

> `settings.py` 启动时会以项目根目录下的 `README.md` 是否存在来**校验工作目录**，不满足则直接退出——服务必须从项目根目录启动（`python -m season.main`）。

---

## 十、已知约束

| 约束 | 位置 | 说明 |
| --- | --- | --- |
| 排行榜快照只取前 50 名 | `ranking.TOP_CLAN_LIMIT` | `data` 最多 50 行；`clans` 字段是全量基数，两者语义不同（有意为之） |
| 每个分段最多 1000 条 | `endpoints.league_ranking` | 接口 `limit=1000`；单分段公会数超过该值时会有公会收集不到 |
| 快照在部分分支下不生成 | `worker.run_worker` | "无活跃公会"与"无待刷新公会"两处提前返回会跳过快照生成，此时快照的 `time` 字段不推进（有意为之） |
| `stage_progress` 上限 5 字符 | `T_clan_stats.stage_progress VARCHAR(5)` | 与晋级赛最多 5 场的赛制对应；超出会写入失败 |
| `season` 列为 `TINYINT` | `T_clan_stats.season` | 赛季 ID 上限 127 |
| 每赛季一个 SQLite 文件 | `sqlite_ops` | 明细不与汇总同库，避免主库随赛季膨胀 |
| 明细增量 > 1 时丢弃 | `updater._plan_record` | LBT 只有一个时间戳，无法还原每场 |
| 联赛升降级方向待确认 | `updater._plan_team` | 见 4.3 末尾的说明 |

---

## 十一、相关文件

| 文件 | 说明 |
| --- | --- |
| `init/mysql/01-schemas/03-clan.sql` | MySQL 侧表结构（本服务涉及的 4 张表） |
| `init/mysql/02-data/01-base.sql` | `T_tracking_meta` 种子行 |
| `init/sqlite/clan_battle.sql` | SQLite 侧表结构与统计表种子数据 |
| `shard/game_utils.py` | `CLAN_BATTLE_WINDOWS`、`is_cb_active`、`CLAN_REALM_MAP` |
| `shard/constants.py` | `LEAGUE_LIST`、`CLAN_INIT_TABLE_LIST` |
| `shard/endpoints.py` | 各服 Clan API 域名 |
| `shard/redis_keys.py` | Redis 键名生成 |
| `app/routers/external_urls.py` | 快照 msgpack 的下载路由 |
| `temp/season.md` | 本服务早期版本的设计文档（结构参考） |
