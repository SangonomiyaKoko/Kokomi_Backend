# Recent 用户近期数据服务设计文档

Recent 服务负责**为用户保留长期的每日战绩快照**，并据此推导"近期战斗数据"：定时轮询游戏接口，把只提供**累计值**的战绩还原成**按日切分的快照**，再通过相邻快照的差分得到"最近这一小时打了什么船、打得怎么样"。

前台 `/recent/` 与 `/recent/plus/` 接口读取的正是本服务写下的 SQLite 文件（两者共用同一把用户锁）；本服务是整个 Recent 功能的数据生产端。

---

## 一、设计目的

### 1.1 数据源的能力边界

游戏接口（Vortex API / Official API）对用户战绩只提供**累计值**：

- **账号总览** `/api/accounts/{account_id}/`（Vortex）：`statistics.basic` / `pvp` / `rank_solo` / `rating_solo` / `rating_div` 各模式的累计场次、胜场、伤害、击杀、经验，以及 `last_battle_time`（LBT）、`karma`、`leveling_points`；
- **船只明细** `/api/accounts/{account_id}/ships/{pvp_solo|pvp_div2|pvp_div3|rank_solo|rating_solo|rating_div}/`（Vortex）：该模式下**每艘船**的累计统计（场次、胜/负、伤害、击杀、存活、侦查伤害、潜在伤害、经验、击落飞机、主炮命中/射击）；
- **公会战船只明细** `/wows/ships/stats/?extra=clan`（Official，仅直营服）：以 `clan` 键返回每艘船的公会战累计数据。

关键限制是：**接口不提供单场战斗记录，也不提供"昨天打了多少"**。你只能拿到"这条船一共打了 120 场、赢了 63 场"，拿不到"昨天打了 5 场"。

同时还有两个现实约束：

- 累计值会被**回档**（账号数据回退）；
- 用户随时可能**隐藏战绩**（`hidden_profile`），隐藏期间拿不到任何数值。

### 1.2 由此推导出的四个设计目标

1. **能留存**：把"某条船在某模式下截至某天的累计值"落盘，形成可回溯的历史快照；
2. **能定位**：快照不能只存数值，还要能回答"这条船今天的数据和哪一天的数据是一样的"——即**索引**，否则每次都要全表扫描比对；
3. **能差分**：相邻两次快照相减，得到"这段时间内的增量"，供前台换算成近期战斗数据；
4. **能自治**：不依赖上游队列，自己轮询全量用户；同时对长期不活跃、长期隐藏、数据损坏的账号主动停用，避免无限膨胀。

---

## 二、核心设计思想

> **每日快照 + 索引指针 + 增量差分**：不为每艘船每天写一行明细，而是把"某个模式下某一天的全部船只数据"打包成一行（`ship_index_map`），再用船只各自的 `data_index` 指向它；数据没变的船复用旧索引，只有变了的船才产生新快照。差分时拿新旧两个索引读两次快照相减即可。

它决定了两件事：

- `user_daily_summary` 与 `mode_latest_index` / `ship_latest_index` **不是为了展示而存在**，它们是"今天该写什么、该和谁比"的**定位表**；
- **索引复用是省空间的核心手段**。一艘船 1000 场里今天只打了 2 场，它的新快照仍然要写整行累计值，因此同一天内多条船共享同一份 `ship_index_map` 行，绝大多数船在各天之间共享旧索引，只有真正变动过的船才在当天产生新 `ship_index_data` 行。

### 2.1 数据流

```
游戏接口（Vortex / Official）
   │  ① 账号总览接口（恒发，1 次）
   ▼
UserStats ─────────────────────► MySQL T_user_base / T_user_stats /
   │                             T_user_random / T_user_ranked / T_user_cache
   │  ② 各模式船只明细接口（按需，N 次）
   ▼
ShipDataCollection
   │
   ├─ 与本地 latest 索引比对 ──► ShipDataUpdateParams / ShipLatestUpdateParams
   │                                    │
   │                                    ▼
   │                            SQLite {account_id}.db
   │                            ├ ship_index_data   变动船只的当日快照
   │                            ├ ship_index_map    当日模式索引行
   │                            ├ ship_latest_index 每船最新索引（下轮比对基线）
   │                            ├ mode_latest_index 每模式最新索引
   │                            └ user_daily_summary 每日摘要（索引指针在此）
   │
   └─ 新旧快照相减 ─────────────► user_recent_stats  近期战斗增量行
                                          │
                                          ▼
                                  app/apis/recent/  前台读取
```

### 2.2 两级数据组织：摘要行与快照行

SQLite 侧的数据由三层构成，**指针全部收敛在 `user_daily_summary` 一行里**：

| 层级 | 表 | 粒度 | 角色 |
| --- | --- | --- | --- |
| 定位层 | `user_daily_summary` | 用户 × 日期 | 当日各模式的累计值 + 指向快照的索引（`pvp_index` / `rank_index` / `clan_index`） |
| 打包层 | `ship_index_map` | 模式 × 索引日期 | 该日该模式**全部船只**的 `ship_id:index` 映射，以及汇总值 |
| 明细层 | `ship_index_data` | 船 × 模式 × 索引日期 | 单船当日快照（3 个数据类型的 12 字段统计） |

索引的取值约定：

| 取值 | 含义 |
| --- | --- |
| `NULL` | 未记录。该模式本次没有数据来源（如直营服配置了 AC 后拿不到 CLAN） |
| `YYYYMMDD` | 指向 `ship_index_map` 中 `(ship_mode, ship_index)` 对应的那一行 |

> `init/sqlite/recent.sql` 的注释里还写了「`0` = 无统计数据」，但当前写回路径（`UserSummaryUpdateEntry.from_stats`）只会写 `NULL` 或日期，`0` 不会出现。

### 2.3 四种更新策略 `UpdateStrategy`

本地数据库的状态决定了这次要写哪些行（`services/loader.py` 判定，`services/planner.py` 消费）：

| 策略 | 触发条件 | 写回动作 |
| --- | --- | --- |
| `NEW_USER` | `user_daily_summary` 与 `mode_latest_index` **同时为空** | 全量初始化：写入昨日与今日两条 summary，并为所有变动船只建快照 |
| `NORMAL` | 本地既有 summary 又有 latest 索引（绝大多数场景） | 只 `UPDATE` 今日一条 summary |
| `MISSING_SUMMARY` | 今日与昨日 summary 均缺失，或均为隐藏；或本地最新快照的更新时间超过 48 小时 | 需要 `UPDATE` 今日与昨日两条 summary，避免今日增量被算进昨日 |
| `SPECIAL_CLAN_UPDATE` | 今日与昨日均为公开战绩，但两者的 `clan_index` 都是 `NULL`（用户此前配置了 AC，CLAN 数据缺失） | `UPDATE` 今日 summary，同时把 CLAN 场次补写进昨日 summary |

`MISSING_SUMMARY` 的存在理由：正常情况下"昨日 summary"一定存在（昨日也跑过服务）。它缺失只有两种可能——**服务崩溃**或**服务长时间离线**。若只更新今日，则"从昨日到今日"的增量会被整段抹掉，因此必须同时回补昨日。

`SPECIAL_CLAN_UPDATE` 的存在理由：直营服在用户配置 AC 之后拿不到 CLAN 数据，此前的 summary 里 `clan_index` 一直为 `NULL`。当用户取消 AC（或服务重新拿到 TOKEN）后，CLAN 数据第一次可用，这部分场次实际上是**昨日发生的**，只能补写进昨日。

### 2.4 两级分布式锁

| 锁键 | 位置 | 作用 |
| --- | --- | --- |
| `refresh_lock:recent:{account_id}` | `core/worker.py` 的 `run_worker` | **整条用户流水线**的互斥。前台 `/recent/` 接口在按需刷新时使用**同一个键**（`app/apis/recent/refresher.py`），保证服务与前台不会同时操作同一个用户的 SQLite |
| `refresh_lock:user:{account_id}` | `services/pipeline.py` 的 `UserDataProcessor` | **MySQL 同步**的互斥。与 Celery 刷任务（`tasks/`）共用，保证 `T_user_*` 系列表不会并发写入 |

两把锁的粒度不同：外层锁覆盖"拉取 → 同步 → 写回"全流程，内层锁只覆盖"同步 MySQL"这一段。未获取到外层锁时该用户记为 `FAILED`（原因为 `AcquireLockFailed`），未获取到内层锁时返回 `FailedReason.ACQUIRE_LOCK_FAILED`。

---

## 三、运行架构

### 3.1 进程模型

`python -m recent.main`（docker-compose 中的 `recent` 服务，容器名 `backend-recent`）启动一个**常驻单进程轮询循环**：

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

- **每轮重建全部连接**（Redis / MySQL / `httpx.AsyncClient`），轮末统一关闭。避免长连接在长时间空转后失效；
- 休眠时间按**上一轮耗时扣减**，使循环周期对齐 `REFRESH_INTERVAL`（默认 60 秒）；耗时超出一整个周期时 `max(1, ...)` 保证至少休眠 1 秒；
- 进程存活通过 Redis 键 `status:Recent` 对外暴露，TTL = `REFRESH_INTERVAL + 10`，异常退出前主动删除；
- 仅注册 `SIGTERM`（Windows 下跳过），退出走 `os._exit(0)`——不展开栈、不跑清理。

> `REFRESH_INTERVAL` 是**轮询间隔**，不是**用户更新间隔**。真正的更新频率由 `T_user_stats.next_refresh_at`（活跃等级推导，见 [core/activity.md](../core/activity.md)）+ 保底超时共同决定——绝大多数用户在绝大多数轮次里会在评估阶段直接 `SKIPPED`。

**单轮内的用户遍历**（`core/worker.py`）：

1. 从 `T_user_config` 读取 `user_level > 0` 的全部 `account_id`，**打乱顺序**（`random.shuffle`，仅一个用户时跳过）——保证低频用户不会永远排在队尾；
2. 逐用户：维护状态键 → 校验挂载点 → 计数 → 取锁 → 执行 `UserUpdateRunner.run()`；
3. 状态键续期：每 60 个用户检查一次"剩余有效期 < 10 秒"则续期，避免单轮用户过多导致键提前过期；
4. **挂载点校验**：每个用户都检查 `SQLITE_DIR/_MOUNT_POINT` 是否存在，缺失则抛 `RuntimeError` 中断整轮。挂载点文件的用途是防止外挂云硬盘掉盘后目录仍存在、程序误判为首次初始化而把数据库写到系统盘。

### 3.2 代码分层

```
recent/
├── main.py          # 进程入口：打印启动参数、注册信号、启动调度器
├── settings.py      # 配置装载：环境变量 / data 下的 JSON / init 下的 SQL
├── logger.py        # 日志与异常落盘（封装 shard 的 logger 与 exception_writer）
├── core/            # 调度与上下文
│   ├── context.py   #   RunContext（整轮）/ UpdateContext（单用户）
│   ├── scheduler.py #   轮循环：建资源 → 跑一轮 → 清资源 → 休眠
│   └── worker.py    #   单轮编排：读用户列表、取锁、逐用户调度
├── services/        # 业务编排（无状态类方法，按需调用）
│   ├── runner.py    #   单用户流水线总控
│   ├── loader.py    #   阶段一：加载本地库 + 判定更新策略
│   ├── updater.py   #   阶段二：评估是否需要拉取、要拉哪些模式
│   ├── pipeline.py  #   阶段三：请求接口 + 同步 MySQL + 构建领域模型
│   ├── planner.py   #   阶段四：生成写回计划（含近期数据差分）
│   ├── policy.py    #   各阶段的数据校验策略合集
│   └── syncer.py    #   用户基础信息的 MySQL 同步器
├── clients/         # 外部 API 接入（端点注册 + 并发请求 + 指标上报）
├── repository/      # 数据访问（纯 SQL，不感知业务）
├── params/          # 写回参数与本地读取结果（dataclass）
└── models/          # 领域模型（frozen dataclass）与枚举
```

MySQL / SQLite / Redis 的连接与事务上下文管理器由 `shard.db` 提供，本模块不再自持。

### 3.3 各模块职责一览

| 模块 | 类 / 函数 | 职责 |
| --- | --- | --- |
| `core` | `start_scheduler` | 轮循环、资源生命周期、状态键维护、内存监控 |
| `core` | `run_worker` | 读用户列表、打乱、逐用户取锁调度、进度条 |
| `core` | `RunContext` | 整轮上下文：连接、计数器、CLAN 活跃期与配额 |
| `core` | `UpdateContext` | 单用户上下文：时间参数、本地数据、拉取数据、写回计划 |
| `services` | `UserUpdateRunner` | 四阶段流水线总控、异常落盘、计划提交 |
| `services` | `UserDataLoader` | 读本地库、完整性校验、判定 `UpdateStrategy`、补全 summary 缺口 |
| `services` | `UpdateEvaluate` | 判定是否需要拉取、需要拉取哪些模式、兜底刷新 |
| `services` | `UserDataProcessor` | 构建请求目标、并发请求、同步 MySQL、解析为领域模型 |
| `services` | `UpdatePlanner` | 生成各表写回参数、计算近期差分 |
| `services` | `ValidationPolicy` | 库前校验 / 响应前校验 / 库后校验 / 响应后校验 |
| `services` | `UserStatsSyncer` | 单事务写 MySQL 6 张表、计算活跃等级与更新间隔 |
| `clients` | `EndpointRegistry` | 模式 → 接口路径注册表、请求目标构建 |
| `clients` | `APIRequester` | 并发请求全部目标、错误标记、HTTP 指标上报 |
| `repository` | `*Repository` | 各表的纯 SQL 读写（`load_user_ids` / `refresh` / `read` 等） |

### 3.4 上下文对象

两个 `dataclass` 分别承载两种粒度的状态，避免层层传参。

**`RunContext`** — 整轮循环的状态（`core/context.py`）

| 字段 | 说明 |
| --- | --- |
| `redis_client` / `async_client` / `mysql_connection` | 本轮中间件连接（`create_resources` 后填充） |
| `run_counter` | 单轮计数器 `RunCounter`：`total` / `updated` / `skipped` / `disabled` / `failed` |
| `clan_update_count` | 本轮已处理的直营服 CLAN 更新数量（配额 60） |
| `key_expired_ts` | 状态键的过期时间戳，用于续期判断 |
| `period_start_ts` | CLAN 模式更新活跃时间段的开始时间戳（非活跃期为 `None`） |

另提供 `set_status_key()` / `del_status_key()` 维护服务状态键，`is_key_expiring()` 判断是否需要续期。

**`UpdateContext`** — 单个用户更新的状态

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `account_id` | `int` | 目标用户（构造时传入） |
| `now_date` / `yesterday_date` | `int` | 重置日期（`YYYYMMDD`），构造时计算 |
| `current_timestamp` | `int` | 本轮开始的 Unix 时间戳 |
| `access_token` | `str \| None` | 用户 AC，从 Redis `token:ac:{id}` 解码 |
| `user_record` / `user_stats` | `UserRecord` / `UserStats` | 从 MySQL 读出的配置与战绩快照 |
| `local_data` | `Dict[BattleMode, LocalDataEntry]` | 本地 SQLite 的每模式最新索引与船只缓存 |
| `daily_summary` | `Dict[int, UserSummaryLocalEntry]` | 本地每日摘要，缺失日期以 `None` 占位 |
| `date_list` | `List[int]` | 从最早 summary 日期到今日的连续日期列表 |
| `latest_summary` | `UserSummaryLocalEntry \| None` | 本地最新一条有效 summary |
| `update_strategy` | `UpdateStrategy` | 本次的更新策略 |
| `fetch_modes` | `Set[BattleMode]` | 本次需要拉取的模式合集 |
| `latest_data` | `Dict[BattleMode, LatestDataEntry]` | 本次拉取并解析后的数据 |
| `update_timestamp` | `int` | MySQL `T_user_stats.updated_at` 的新值，作为快照的更新时间 |
| `update_plan` | `UpdatePlan` | 本次的写回计划，构造时即创建 |

派生属性：`dates_desc` / `dates_asc`（日期排序）、`query_interval`（距上次被查询的秒数）、`battle_interval`（距上次战斗的秒数）、`is_pro`（是否 Plus 用户且今日摘要足够新）。

> `is_pro` 的判定为：`user_level == 2` 且**今日 summary 存在**且 `updated_at` 距今不超过 **3600 秒**。它是"能否计算近期差分"的开关。

---

## 四、数据模型

`models/stats.py` / `models/user.py` 中的模型全部为 `@dataclass(frozen=True, slots=True)`——不可变、无 `__dict__`，保证单轮内大量实例的构造与比较开销可控。

### 4.1 `ModeBattleStats` — 模式级简略统计

```python
battles, wins, damage, frags, exp
```

固定 5 字段，是**模式汇总的原子单位**，也是 `ship_index_map` / `mode_latest_index` 的落地形态。

- `from_api(dict)`：兼容三种字段名（`battles_count` / `wins` / `damage_dealt` / `frags` / `original_exp`），空字典得到全 0；
- `rates()`：返回 `(胜率%, 场均伤害, 场均击杀, 场均经验)`，场次为 0 时返回全 0（避免除零）；
- `to_list()`：序列化为 5 元素数组。

### 4.2 `ShipBattleStats` — 单船单数据类型的统计

```python
battles, wins, losses, damage, frags, survived, scouting_damage,
art_agro, original_exp, planes_killed, hits_by_main, shots_by_main
```

固定 12 字段，是**快照的最小单位**（`ship_index_data.data_type_N` 存的就是这 12 个数的逗号分隔串）。

两个来源的构造器，差异集中在字段名与两处推算：

| | `from_api`（Vortex） | `from_api2`（Official） |
| --- | --- | --- |
| 场次 | `battles_count` | `battles` |
| 存活 | `survived` | `survived_battles` |
| 侦查伤害 | `max(assist_damage, scouting_damage)` | `damage_scouting` |
| 经验 | `original_exp` | **按场次推算**：`胜 × 2500 + 负 × 250 + 平 × 250` |
| 主炮 | `hits_by_main` / `shots_by_main` | `main_battery.hits` / `main_battery.shots` |

> Official 接口返回的经验是**加成后**数值，无法直接使用；而胜利 2500、非胜利 250 是公会战的经验结算规则，因此按胜负场次反推原始经验。

### 4.3 `ShipDataEntry` / `ShipDataCollection` — 船只集合

`ShipDataEntry` 是一艘船在一个模式下的三个数据类型槽位（`solo` / `div2` / `div3`，均为 `Optional[ShipBattleStats]`）：

- `battles`：三个槽位场次之和；
- `aggregate()`：三个槽位汇总为一个 `ModeBattleStats`——这是写入 `ship_latest_index` 与 `ship_index_map` 的形态；
- `set_type_stats` / `get_type_stats`：按 `DataType` 存取。

`ShipDataCollection` 是 `{ship_id: ShipDataEntry}` 的包装，提供 `count` / `is_exists` / `setdefault` / `set_type_data` / `aggregate()`，并可直接迭代出 `(ship_id, entry)` 元组。**「模式」与「数据类型」的合法组合由接口决定**：

| 模式 | Vortex 路径 | 数据类型 | Official（直营服 CLAN） |
| --- | --- | --- | --- |
| PVP | `pvp_solo` / `pvp_div2` / `pvp_div3` | solo / div2 / div3 | — |
| RANK | `rank_solo` | solo | — |
| CLAN（俄服） | `rating_solo` / `rating_div` | solo / div2 | — |
| CLAN（直营服） | — | — | 仅 div2，响应键为 `clan` |

### 4.4 `UserStats` / `UserRecord` — 用户状态

`UserStats` 是**从 MySQL 读出的战绩快照**（同时也是写回 MySQL 的数据形态）：

```python
is_enabled, is_public, total_battles, pve_battles, pvp_battles,
ranked_battles, rating_battles, karma, last_battle_at, updated_at
```

- `is_hidden` = `not is_public`；`is_valid` = `is_enabled`；
- `battles_for(mode)`：按模式取场次，是"是否变化"的判据；
- `is_cache_outdated(updated_at)`：判断 MySQL 数据是否比本地缓存更新。

`UserRecord` 是从 `T_user_config` 读出的配置：`user_level` / `storage_limit` / `last_query_at` / `next_refresh_at`，其中 `is_configured` = `user_level > 0 and storage_limit > 0`。

### 4.5 `UpdatePlan` — 写回计划

`UpdatePlan`（`params/__init__.py`）聚合六类写回参数 + 一个异常标记：

| 字段 | 目标表 | 支持的写回方式 |
| --- | --- | --- |
| `user_summary` | `user_daily_summary` | insert / update |
| `mode_latest` | `mode_latest_index` | update（另有 CLAN 专用的 `special_update`） |
| `ship_latest` | `ship_latest_index` | insert / update |
| `ship_map` | `ship_index_map` | insert / update |
| `ship_data` | `ship_index_data` | insert / update |
| `user_recent` | `user_recent_stats` | insert（只追加） |
| `exception_raised` | — | 流程中是否发生过异常 |

两个关键属性：

- `planned_count`：六类参数的行数之和；
- `can_execute`：`not exception_raised and planned_count > 0`——**只有"没出异常"且"确实有计划"时才提交**。

> `mode_latest` 的 `special_update`（`set_special_params`）不产生新行，只把 CLAN 行的 `update_time` 刷成当前时间戳。用途见 6.3 的"无战斗则只刷时间戳"分支。

### 4.6 结果与原因枚举

流水线各阶段统一返回 `ValidationResult` / `UpdateResult`（`models/reason.py`），四类动作 + 一个原因字符串：

| 动作 | 含义 | 后续 |
| --- | --- | --- |
| `CONTINUE` | 继续下一阶段 | — |
| `SKIPPED` | 跳过本轮（不写数据） | 计入 `skipped` |
| `FAILED` | 本轮失败（网络/数据库/锁） | 计入 `failed` |
| `DISABLED` | 停用用户 | 计入 `disabled`，并执行停用动作 |

原因枚举同时是**日志词汇表**（`UpdateResult.reason_text` 会拼进日志）：

| 枚举 | 取值 |
| --- | --- |
| `FailedReason` | `ObtainDataFailed`、`AcquireLockFailed`、`DbOperationFailed`、`MySQLRefreshFailed` |
| `SkippedReason` | `UserHidden`、`NotConfigured`、`StatsUnchanged`、`HiddenProfile`、`NoFetchModes` |
| `UpdatedReason` | `Continue`、`FirstUpdate`、`StatsChanged`、`FallbackRefresh` |
| `DisabledReason` | `UserHidden`、`AccountInvalid`、`AccountNoStats`、`DataIntegrityError`、`UserInactiveTooLong`、`AccountHiddenTooLong`、`AccountInactiveTooLong` |

> `UserHidden` 在 `SkippedReason` 与 `DisabledReason` 中同名：前者表示"本次跳过"，后者表示"首次更新就是隐藏战绩，直接停用"。

---

## 五、数据库设计

### 5.1 MySQL（跨服务共用）

本服务读写的表在 `init/mysql/01-schemas/02-user.sql`。

| 表 | 本服务的动作 | 说明 |
| --- | --- | --- |
| `T_user_config` | 读 `user_level > 0` 的用户列表；读单个用户的 `user_level` / `storage_limit` / `last_query_at`；**停用时置 `user_level = 0`、`storage_limit = 0`** | 用户是否启用 Recent 的唯一开关 |
| `T_user_stats` | 读战绩快照与 `next_refresh_at`；写回 `is_enabled` / `is_public` / `activity_level` / 各模式场次 / `karma` / `last_battle_at` / `next_refresh_at` / `updated_at` | 同时是"下次该不该刷"的调度依据 |
| `T_user_base` | 写 `username` / `register_time` / `insignias` / `updated_at`；改名时向 `T_user_action` 追加上一条旧名 | 隐藏战绩时只更新 `username` 与 `updated_at` |
| `T_user_random` / `T_user_ranked` | 写 `battles` / `total_exp` / 胜率 / 场均 / 各类最高纪录 / `updated_at` | 由 `ParseUtils.user_basic_data` 解析出的战绩 |
| `T_user_cache` | 写 `is_due` 与 `updated_at` | **跨服务契约**：PvP 场次变化即置 `is_due = TRUE`，通知 `scripts/cache` 重算该用户的船只缓存 |
| `T_user_action` | 昵称变更时插入一条旧名 | 只追加 |

`T_user_cache` 的三条分支（`services/syncer.py`）：

| 用户状态 | 动作 |
| --- | --- |
| 有效且公开，且 PvP 场次**变化** | `is_due = TRUE` |
| 有效且公开，PvP 场次未变 | `updated_at = NOW()`（限 `is_due = FALSE` 的行） |
| 无效或隐藏 | `is_due = FALSE` |

### 5.2 SQLite（每用户一个文件）

路径由 `shard.db.SQLiteOPS.user_db_path(SQLITE_DIR, account_id)` 推导，即 `{SQLITE_DIR}/{account_id}.db`。建表 SQL 来自 `init/sqlite/recent.sql`，在 `ensure_database` 中于文件不存在时执行。

| 表 | 唯一键 | 说明 |
| --- | --- | --- |
| `user_daily_summary` | `snapshot_date` | 每日一行：公开标记、各模式场次与 `karma`、三个模式的索引、`update_time` |
| `mode_latest_index` | `ship_mode` | 每模式一行（建表时预插 1/2/3 三行）：模式汇总 + `mode_index` + `update_time` |
| `ship_latest_index` | `(ship_mode, ship_id)` | 每船每模式一行：汇总 + `data_index`——**下一轮比对的基线** |
| `ship_index_map` | `(ship_mode, ship_index)` | 一条快照映射：`ships` 船只数、汇总值、`index_map` 字符串（`ship_id:index,...`） |
| `ship_index_data` | `(ship_mode, ship_id, ship_index)` | 单船快照：`data_type_1/2/3` 各存 12 个统计值的逗号分隔串 |
| `user_recent_stats` | 无（只追加） | 近期战斗增量行，含 `battle_time` 与 `idx_battle_time` 索引 |

序列化由 `shard.utils.data.StringUtils` 承担（`index_map_encode` / `index_data_encode` 等），**空值统一编码为 `NULL`**——`data_type_1/2/3` 为 `NULL` 表示该数据类型无数据。

> 隐藏战绩的 summary 行只写 `is_public = FALSE` 与 `update_time`，其余字段全部为 0——语义是"这一天没有可用的公开数据"，而非"这一天数据为零"。

### 5.3 Redis

| 键 | 类型 | 用途 |
| --- | --- | --- |
| `status:Recent` | String (TTL = `REFRESH_INTERVAL + 10`) | 服务存活标记，异常退出前删除 |
| `refresh_lock:recent:{account_id}` | String (NX, 60s) | 单用户流水线互斥（与前台共用） |
| `refresh_lock:user:{account_id}` | String (NX, 60s) | MySQL 同步互斥（与 Celery 共用） |
| `token:ac:{account_id}` | String | 读取用户 AC（`TOKEN:ID1,ID2` 格式，`StringUtils.token_decode` 解析） |
| `metrics:http:annual:{yyyy}` 等 | String | HTTP 调用量与错误量统计（年 / 月 / 日） |

---

## 六、更新流程

单用户的完整流程由 `services/runner.py` 的 `UserUpdateRunner.run()` 编排，共四个阶段，**每个阶段返回 `SKIPPED` / `FAILED` / `DISABLED` 时立即短路并返回**。

### 6.1 加载阶段 `UserDataLoader`（`services/loader.py`）

```
validate_database_pre  →  ensure_database  →  _load_data  →  _repair  →  validate_database_post
```

1. **库前校验**（`ValidationPolicy.validate_database_pre`）：

   | 条件 | 结果 |
   | --- | --- |
   | `user_stats` 或 `user_record` 为 `None` | `SKIPPED / NotConfigured` |
   | `not user_record.is_configured` | `SKIPPED / NotConfigured` |
   | `not user_stats.is_valid` | `DISABLED / AccountInvalid` |
   | `user_stats.last_battle_at is None` | `DISABLED / AccountNoStats` |

2. **建库**：`SQLiteOPS.ensure_database` 在文件缺失时执行建表 SQL，失败返回 `FAILED / DbOperationFailed`；
3. **`_load_data`**：读三张表，并做完整性判定：

   | 本地状态 | 判定 |
   | --- | --- |
   | summary 为空 **且** 三模式 `mode_index` 全为 `None` | `NEW_USER`，返回 `True` |
   | 只有一项为空（summary 与索引**必须同时存在或同时为空**） | 返回 `False` → `DISABLED / DataIntegrityError` |
   | summary 只有 **1 行** | 返回 `False` → `DISABLED / DataIntegrityError` |

   随后把日期列表整理为"从今日到最早 summary 日期的连续日期"，缺失日期以 `None` 占位；**今日与昨日同时缺失**时置为 `MISSING_SUMMARY`。

4. **`_repair`**：从旧到新遍历，用上一条有效记录**补全缺失日期**（`UserSummaryRepository.insert`），并据此得出 `latest_summary`。补全时有一个特例——补今日那行且用户配置了 AC 时，把 `clan_battles` 与 `clan_index` 清零（直营服的 CLAN 不支持通过令牌查询，不能沿用旧值）。

   同时做两处状态修正：

   - **直营服 CLAN 场次回填**：`REGION in ['asia','eu','na']` 且本地 CLAN 场次 > 0 时，用本地缓存的场次替换 `user_stats.rating_battles`（直营服的 CLAN 总览数据不在账号接口里）；
   - **策略升级**：`NORMAL` 策略下若今日与昨日**均为非公开**、或最新快照的更新日期不在今日/昨日（服务离线超过 48 小时），升级为 `MISSING_SUMMARY`；若今日与昨日均为公开且 `clan_index` 均为 `NULL`，升级为 `SPECIAL_CLAN_UPDATE`。

5. **库后校验**（保留条件，不满足即停用）：

   | 判定 | 阈值 | 结果 |
   | --- | --- | --- |
   | 距上次被查询 `query_interval` | ≥ `MAX_INACTIVE_DAYS` = **60 天** | `DISABLED / UserInactiveTooLong` |
   | 连续隐藏战绩天数 | ≥ `MAX_HIDDEN_PROFILE_DAYS` = **30 天** | `DISABLED / AccountHiddenTooLong` |
   | 距上次战斗 `battle_interval` | ≥ `MAX_NO_BATTLE_DAYS` = **180 天** | `DISABLED / AccountInactiveTooLong` |

   `last_query_at` 为空视为"从未被查询"，直接判不活跃；`is_hidden` 的用户不做"无战斗"判定（隐藏状态下读不到正确的 LBT）。

### 6.2 评估阶段 `UpdateEvaluate`（`services/updater.py`）

按优先级依次判定：

1. **隐藏战绩**：`NEW_USER` 直接 `DISABLED / UserHidden`（首次更新必须是公开战绩，否则写入两条隐藏记录毫无意义）；其余情况按需把今日 summary 刷成隐藏或刷新时间戳，返回 `SKIPPED / UserHidden`；
2. **首次更新**（`NEW_USER`）：拉取全量数据，返回 `UpdatedReason.FirstUpdate`。模式范围按服务器决定：

   | 条件 | 拉取模式 |
   | --- | --- |
   | 国服（`cn`）或无 TOKEN | `BASE_UPDATE_MODES` = PVP + RANK |
   | 俄服（`ru`） | `FULL_UPDATE_MODES` = PVP + RANK + CLAN |
   | 直营服且用户配置了 AC | PVP + RANK（CLAN 不支持 AC 查询） |
   | 直营服且未配置 AC | PVP + RANK + CLAN |

3. **常规用户按模式比对场次**：

   | 模式 | 判据 |
   | --- | --- |
   | PVP / RANK | `stats.battles_for(mode) != local_data[mode].battles` |
   | CLAN（俄服） | 同上 |
   | CLAN（直营服） | 走 `_update_direct_clan`（见下） |

   有任一模式变化 → `fetch_modes` 为该变化集合并返回 `UpdatedReason.StatsChanged`；

4. **兜底刷新**：上游（Celery / Maintenance）未按 `next_refresh_at` 触发时，`current_timestamp > next_refresh_at + fallback_timeout(user_level)` 则返回 `UpdatedReason.FallbackRefresh`（Pro 用户 1 小时，普通用户 1 天）；
5. **未变化**：`latest_summary.updated_at >= stats.updated_at` → `SKIPPED / StatsUnchanged`；
6. **时间戳推进**：仍未跳过说明 MySQL 侧被别的服务更新过（如前台接口刷新），此时用 MySQL 的 `stats` 更新今日 summary（索引复用本地），随后仍返回 `SKIPPED / StatsUnchanged`——**返回 `SKIPPED` 不代表不写库，该计划同样会在 `finally` 中提交**。此分支中，直营服用户配置了 AC 时 `clan_index` 写 `NULL`，未配置 AC 时用本地缓存的 CLAN 场次替换 `rating_battles`。

**`_update_direct_clan`：直营服 CLAN 的更新闸门**

直营服的 CLAN 数据无法从账号接口读出，只能靠 Official 接口单独请求，且该接口需要服务端 TOKEN。为了避免每轮对所有直营服用户发起这笔请求，用四道闸门筛出真正需要的人：

| 条件 | 返回 | 理由 |
| --- | --- | --- |
| `period_start_ts` 为空 | `False` | 不在 CLAN 更新活跃时间段内 |
| 无 TOKEN 或用户配置了 AC | `False` | 没有数据来源 |
| 本地 CLAN 的 `update_time` 晚于本轮活跃期开始 | `False` | 本轮活跃期内已经更新过 |
| 活跃期内更新过，且 LBT 距今 ≥ **36000 秒** | `False`（但刷新 `update_time`） | 用户在这段活跃期内没有打过公会战，只推进时间戳 |
| 本轮已处理满 **60** 个直营服 CLAN | `False` | 单轮配额 |

> **CLAN 更新活跃时间段**由 `ClanBattleUtils.update_period` 从 `data/json/clan_season.json` 推导：赛季区间内、服务器当地时间的**周一 / 周四 / 周五 / 周日 01:00–05:00**。这与 `is_cb_active`（公会战窗口判定）是**两套独立规则**，不要合并。

### 6.3 拉取阶段 `UserDataProcessor`（`services/pipeline.py`）

```
build_targets → APIRequester.fetch → [用户锁] UserStatsSyncer.refresh → validate_response_pre
                                   → _parse_response → validate_response_post
```

1. **构建目标**（`EndpointRegistry.build_targets`）：恒发 1 次账号总览请求；各 `fetch_modes` 按 4.3 的路径表展开。非俄服的 CLAN 走 Official 接口（`extra=clan`），其余走 Vortex。配置了 AC 时在 Vortex URL 上附加 `?ac={token}`；
2. **并发请求**（`APIRequester.fetch`）：`asyncio.gather` 全部目标，**任一失败即整体失败**（返回 `None` → `FAILED / ObtainDataFailed`）。单请求的错误处理：

   | 响应 | 结果 |
   | --- | --- |
   | Vortex 200 + `status = ok` | `data` 字段 |
   | Vortex 404 | `{}`（账号在该端点无数据） |
   | Official 200 + `status = ok` 且 `meta.hidden` 为空 | `data` 字段 |
   | Official 200 且 `meta.hidden` 非空 | `{account_id: {'hidden_profile': True}}` |
   | 其他状态码 | `HTTP_STATUS_{code}` |
   | 异常 / JSON 解析失败 | `ERROR_{type}` / `Game_API_Error` |

3. **HTTP 指标**：每次请求按年 / 月 / 日累加到 `metrics:http:*`，错误单独累计；指标写入失败只记日志；
4. **同步 MySQL**（`UserStatsSyncer.refresh`，在 `refresh_lock:user:{id}` 锁内）：单事务写 6 张表并回读 `T_user_stats.updated_at` 作为本次的 `update_timestamp`。`ParseUtils.user_basic_data` 解析出的账号信息若缺失（`UserNotInDB` / `DataIntegrityError`）或抛异常（返回异常类名），本用户记为 `FAILED / MySQLRefreshFailed`；
5. **响应前校验**（`validate_response_pre`）：账号不存在 → `DISABLED / AccountInvalid`；`hidden_profile` 且是 `NEW_USER` → `DISABLED / UserHidden`；缺 `statistics` → `DISABLED / AccountNoStats`；各模式响应中缺账号或出现隐藏标记 → `FAILED / ObtainDataFailed`（基础接口已校验过，走到这里说明是网络异常）。为 0 的拉取模式 → `SKIPPED / NoFetchModes`；
6. **解析**（`_parse_response`）：
   - 账号不存在 / 缺 `statistics.basic` → `UserStats(is_enabled=False)` 或"新用户无战绩"；
   - `leveling_points >= 1_000_000` 时减去 1_000_000（国服特殊账号），结果作为 `total_battles`；
   - `last_battle_time == 0` 归一化为 `None`；
   - **俄服 CLAN** = `rating_solo` + `rating_div` 五个字段分别相加；**直营服 CLAN** 由各船 `clan` 数据**自行累加**（接口不提供总览），经验按 `胜 × 2500 + 负 × 250 + 平 × 250` 推算；
   - 直营服本次未拉 CLAN 且未配置 AC 时，用本地缓存的场次回填 `clan_statistics.battles_count`——因为后续写 summary 需要完整的 `UserStats`；
7. **响应后校验**（`validate_response_post`）：解析后仍无效 → `DISABLED / AccountInvalid`；`NEW_USER` 且隐藏 → `DISABLED / UserHidden`；隐藏战绩直接放行（无数据可校验）；其余逐模式校验"模式有场次必须有船只数据、有船只数据必须有场次"，不一致 → `FAILED / ObtainDataFailed`。

> **顶层场次与船只明细可能不一致**：账号总览接口给的模式总场次，与船只明细接口所有船累加的总场次由 WG 侧维护，两者可能不等。**数据库顶层记录的是总览接口的值，是否更新也只看这个值是否变动**；船只明细仅在写入快照时使用。这是 WG 接口的既有问题，不影响更新逻辑。

### 6.4 写回阶段 `UpdatePlanner`（`services/planner.py`）

按 2.3 的策略分派到三个分支：

| 分支 | 动作 |
| --- | --- |
| `_initialize`（NEW_USER） | 为每个拉取模式的每条船建快照（`ship_data` + `ship_latest`），写入一条 `ship_index_map`（索引 = **昨日**），更新 `mode_latest`；summary 写入**昨日与今日**两条 |
| `_normal`（NORMAL / MISSING_SUMMARY / SPECIAL_CLAN_UPDATE） | 逐模式增量比对，见下 |
| `_mark_hidden` | 隐藏用户的 summary 更新（**当前流程下不可达**，见第十章） |

`_normal` 的核心逻辑（对 `FULL_UPDATE_MODES` 逐模式）：

| 情况 | 处理 |
| --- | --- |
| 该模式不在 `fetch_modes` | 复用本地 `mode_index`，不写任何行 |
| 本地与接口的模式总场次**相同** | 复用本地 `mode_index`，不写任何行 |
| 本地场次 **大于** 接口场次 | 判定为**回档**，打 `warning` 日志，仍按新值继续写 |
| 接口场次为 **0**（仅回档后出现） | 把本地所有有数据的船在该模式下**置 0**（按索引是否为今日决定 `UPDATE` 或 `INSERT`），`ship_map` 写空映射 |
| 其余（正常增量） | 逐船比对：本地不存在的船 → `INSERT` 快照，索引 = **昨日**；场次相同 → 复用旧索引；场次不同 → `INSERT`/`UPDATE` 快照，索引 = **今日** |

写回 `mode_latest` 与 `ship_index_map` 时按"本地 `mode_index` 是否已是今日"决定 `UPDATE` 还是 `INSERT`——**同一天内多次刷新只产生一行**。

最后写 summary：

| 策略 | 写法 |
| --- | --- |
| `MISSING_SUMMARY` | `UPDATE` 昨日 + 今日两条（用 `user_stats`） |
| `SPECIAL_CLAN_UPDATE` | `UPDATE` 昨日一条（用本地昨日 summary 替换 CLAN 场次与索引）+ 今日一条 |
| 其余 | `UPDATE` 今日一条 |

### 6.5 近期数据差分 `_calc_recent`

这是"近期战斗数据"的来源，也是 `user_recent_stats` 唯一的写入点。触发条件与范围：

- **仅 Plus 用户**（`ctx.is_pro`，见 3.4）；
- **CLAN 模式仅俄服参与**（直营服的 CLAN 数据粒度不同，`mode != CLAN or REGION == 'ru'`）；
- **LBT 距今不超过 7200 秒**（2 小时）——没有有效的战斗时间戳或时间过旧则整体不做差分；
- 只对**本次判定为"有变化"的船**做（新增的船以全 0 作为旧值）。

对每条船的每个数据类型（solo / div2 / div3）：

1. 用旧索引（`old_entry.index`）读回旧快照；旧索引存在但读不到数据 → 记 `Missing snapshot` 错误并跳过该船；
2. 新增值 - 旧值得到差值列表（旧值缺失时以 12 个 0 代替）；
3. 差值的**场次 ≤ 0** → 该类型近期无战斗，跳过；
4. 差值中出现**任一负数** → 数据异常，跳过；
5. 通过校验则写入一行 `user_recent_stats`：场次、胜负、伤害、击毁、经验、存活、侦查伤害、潜在伤害、击落飞机，以及主炮命中率（`hits / shots`，分母为 0 时为 `0.0`）和 `battle_time`（= `user_stats.last_battle_at`）。

> 该表**只 `INSERT` 不 `UPDATE`**，是按时间累积的增量流水；前台按 `battle_time` 范围读取。

### 6.6 提交与结果汇总

`runner.py` 用两个 `try` 块把"加载阶段"与"其余阶段"分开：

- 加载阶段异常 → 落 `ProgramError` 异常日志，返回 `FAILED`；
- 其余阶段异常 → 置 `update_plan.exception_raised = True`，落异常日志，返回 `FAILED`；
- **`finally` 中提交**：`if ctx.update_plan.can_execute` 才在**一个 SQLite 事务**内依次刷新六张表（`ship_data` → `ship_map` → `ship_latest` → `mode_latest` → `user_recent` → `user_summary`）。

因此"阶段返回 `SKIPPED` 但计划已经生成"的情况（如隐藏用户刷新时间戳、时间戳推进分支）**依然会提交**——短路只是不再往下走阶段，不等于丢弃已生成的计划。

单轮结束后 `core/scheduler.py` 汇总 `RunCounter.metrics` 并打日志。

### 6.7 完整时序

```
run_worker
 └─ for account_id in shuffle(启用用户):
      ├ 状态键续期检查（每 60 个用户）
      ├ 挂载点校验（_MOUNT_POINT）
      └ [refresh_lock:recent:{id}]
           └ UserUpdateRunner.run
                ├ 阶段一 load ────► SKIPPED / FAILED / DISABLED ─┐
                ├ 阶段二 evaluate ─► SKIPPED / FAILED / DISABLED ─┤
                ├ 阶段三 fetch ────► SKIPPED / FAILED / DISABLED ─┼─► 立即返回
                ├ 阶段四 plan                                        │
                └ finally: SQLite 事务提交 ◄──────────────────────────┘
```

---

## 七、关键设计与边界处理

| 设计点 | 处理方式 | 目的 |
| --- | --- | --- |
| **索引复用** | 船与模式未变化时沿用旧 `index`，不产生新行 | 快照是整行累计值，复用能避免每天都写一份全量 |
| **同日内合并** | 按本地 `mode_index` 是否已是今日决定 `UPDATE` / `INSERT` | 一天内多次刷新只留一行 |
| **顶层场次为准** | 是否更新只看账号总览接口的模式场次 | 顶层与船只明细本就可能不一致（WG 侧问题） |
| **回档不阻断** | 本地场次 > 接口场次时打 `warning` 后继续按新值写 | 回档是既成事实，服务应记录真实值 |
| **零场次分支** | 接口场次为 0 时把本地船只数据整体置 0 | 仅账号回档后出现，否则会残留错误数据 |
| **索引语义三分** | `NULL` 未记录 / 日期 指向快照 | 前台据此决定能否展示该模式 |
| **隐藏用户也写库** | 隐藏时 summary 只写 `is_public = FALSE` 与 `update_time` | 保留"这天被隐藏"的事实，前台可区分"隐藏"与"无数据" |
| **隐藏用户不断更** | 隐藏期间按 `user_hidden_policy` 刷新时间戳（`user_level > 0` 为 1 天，否则 30 天） | 避免长时间隐藏后 summary 断档 |
| **首次隐藏直接停用** | `NEW_USER` 且隐藏 → `DISABLED` | 无战绩可写，写两条隐藏记录既无意义又增加分支 |
| **补全日期而非报错** | `_repair` 用上一条有效记录填充缺失日期 | 服务崩溃造成的缺口不应导致用户数据不可用 |
| **今日补全清 CLAN** | 补今日行且用户有 AC 时清空 `clan_battles` / `clan_index` | 直营服 CLAN 不能沿用 AC 时代的旧值 |
| **直营服 CLAN 双重回填** | `_repair` 与 `evaluate` 两处都用本地缓存替换 `rating_battles` | 直营服的 CLAN 总览不在账号接口中，`UserStats` 必须完整 |
| **直营服 CLAN 配额** | 单轮最多 60 个（`clan_update_count < 60`） | Official 接口是额外请求，需要限流 |
| **无战斗只刷时间戳** | 活跃期内更新过且 LBT 距今 ≥ 10 小时 → 只推进 `mode_latest.update_time` | 避免活跃期内对同一用户反复发 CLAN 请求 |
| **保底刷新** | `next_refresh_at + timeout` 之后强制更新 | 上游队列故障时数据仍能推进 |
| **数据完整性一票否决** | summary 与 latest 索引必须"同时存在或同时为空"，summary 不允许只有 1 行 | 这两种状态只可能是数据损坏，继续处理会写出错误索引 |
| **停用即清理** | 停用时置 `user_level = 0`、`storage_limit = 0`，移走 SQLite 文件 | 释放存储；文件移入 `data/trash/` 而非删除，保留回档可能 |
| **停用留痕** | 追加一行到 `data/local/Operation.log` | 停用是单向操作，需要可追溯 |
| **异常不提交** | `exception_raised` 使 `can_execute` 为假 | 半途异常的计划可能自相矛盾，宁可不写 |
| **每轮重建连接** | `run_once` 建连、`finally` 清连 | 规避长连接在长时间空转后失效 |
| **挂载点校验** | 每个用户检查 `SQLITE_DIR/_MOUNT_POINT` | 云硬盘掉盘时目录仍在，会把数据误写到系统盘 |
| **状态键续期** | 每 60 个用户检查"剩余 < 10 秒"则续期 | 单轮用户多时状态键不能提前过期 |
| **用户顺序打乱** | `random.shuffle` 用户列表 | 低频用户不会永远排在队尾 |
| **退出不展开栈** | `SIGTERM` / `KeyboardInterrupt` 走 `os._exit(0)` | 主线程可能阻塞在同步 IO 上 |
| **单个用户异常隔离** | `runner` 内部捕获并落盘，不向 `run_worker` 抛出 | 一个用户的数据问题不拖垮整轮 |

---

## 八、对外读取

### 8.1 数据文件

`{SQLITE_DIR}/{account_id}.db` 即前台读取的数据库文件，**服务与前台共享同一份文件**，靠 `refresh_lock:recent:{account_id}` 互斥（服务持锁期间前台按需刷新会返回获取锁失败）。

### 8.2 接口

| 接口 | 读取的数据 |
| --- | --- |
| `GET /recent/users/{user_id}/recent/` | 用户基础信息 + 按 `days` 范围计算的近期数据（`RecentAPI.recent`） |
| `GET /recent/users/{user_id}/recent/plus/` | Plus 用户的近期详细数据（`RecentAPI.recents`） |
| `GET /recent/users/{user_id}/recent/`（Summary 形态） | 存储占用、快照跨度、异常行数等统计（`RecentAPI.summary`） |

### 8.3 启用开关

用户启用 Recent 功能由前台 `/recent/users/{user_id}/recent/` 的 POST 写入 `T_user_config.user_level`（1 = Standard，2 = Plus）；本服务只读该字段决定是否纳入轮询，**停用时才会反写为 0**。

---

## 九、配置项

### 9.1 服务配置 `data/json/services_config.json`

```json
"Recent": {
    "REQUEST_TIMEOUT": 5,   // 单次 HTTP 请求超时（秒）
    "REFRESH_INTERVAL": 60, // 轮询间隔（秒），同时也是 status 键 TTL 的基数
    "MEM_MONITOR": true     // 是否每轮打印进程内存占用
}
```

### 9.2 环境与标记

| 配置 | 来源 | 说明 |
| --- | --- | --- |
| `REGION` | `data/json/init_marker.json` | 决定接口域名与各服的模式差异（CLAN 的四种走向） |
| `TIMEZONE` | `data/json/init_marker.json` | 参与重置日期计算（`重置日 = 本地时间 - 5 小时`，即当地 05:00 换日） |
| `TOKEN` | `data/json/init_marker.json` | 直营服 Official 接口凭证；为空则直营服 CLAN 不更新 |
| `SQLITE_DIR` | 环境变量 | 用户 SQLite 文件的存放目录（生产指向外挂云硬盘），未配置时回退到 `data/db` |
| `MYSQL_*` / `REDIS_*` | 环境变量（`env.dev` / `env.prod`） | 中间件连接 |
| `LOG_LEVEL` | 环境变量 | 日志级别 |
| `SSL_CA_BUNDLE` | 环境变量 | 俄服接口证书校验（设置后 `httpx.AsyncClient` 的 `verify` 指向该证书） |
| `PLATFORM` | 环境变量 | 以 `KokomiAPI` 开头判定为生产环境，从而加载 `env.prod`；开发环境会设置 `NO_PROXY` 并加载 `env.dev` |

`data/json/clan_season.json` 的 `start` / `finish` 决定 CLAN 更新活跃时间段；缺省或不在此区间时 `period_start_ts` 为 `None`，直营服 CLAN 不更新。

> `settings.py` 启动时会以项目根目录下的 `README.md` 是否存在来**校验工作目录**，不满足则直接退出——服务必须从项目根目录启动。

---

## 十、已知约束

| 约束 | 位置 | 说明 |
| --- | --- | --- |
| `_mark_hidden` 不可达 | `services/planner.py` | 隐藏用户在评估阶段已 `SKIPPED`／`DISABLED` 短路，写回层的隐藏分支不会被调用，属冗余分支 |
| 失败率计算隐式返回 `None` | `core/context.py` 的 `RunCounter.failure_rate` | `total > 20` 且非"全部失败"时函数走到底返回 `None`，`None > 10` 会抛 `TypeError`，被 `run_once` 的兜底 `except` 捕获并记为 `Fatal error`，同时删除状态键——**疑似缺陷**，见第十二章 |
| `Operation.log` 缺失时的静默继续 | `services/runner.py` 的 `_handle_stage_result` | 该文件不存在时禁用分支只记日志便 `return None`，调用方视为"不短路"继续后续阶段；此时用户已在 MySQL 被停用，但 SQLite 文件未清理 |
| 只追加、无去重约束 | `user_recent_stats` | 表无唯一键，同一条船同一时段重复触发差分会产生多行 |
| 停用不可逆（自动） | `BasicDataRepository.disable_user` | 置 `user_level = 0` 后服务不再纳入轮询，需人工或前台重新启用 |
| 单轮配额 60 | `services/updater.py` 的 `_update_direct_clan` | 直营服 CLAN 用户多时，单个周期内无法全部覆盖，靠后续轮次摊平 |
| 差分窗口 2 小时 | `services/planner.py` 的 `_calc_recent` | LBT 距今超过 7200 秒则本轮不产生近期数据 |
| Plus 判定依赖今日摘要的新鲜度 | `core/context.py` 的 `is_pro` | 今日 summary 的 `updated_at` 距今超过 3600 秒即不再计算近期数据 |
| 前台读取未迁移到新表结构 | `app/apis/recent/` | 前台 `calculate.py` / `summary.py` 仍在使用旧表名（`daily_snapshot_index`、`ship_daily_snapshot`、`ship_latest_cache`）与旧列名（`user_daily_summary.index_table`、`user_recent_stats.mode` 等），与本服务当前写入的 `init/sqlite/recent.sql` 结构不一致 |
| 部署命令为旧路径 | `docker-compose.yml` 的 `recent` 服务 | 启动命令是 `python scripts/recent/main.py`，而服务目录已迁至项目根目录的 `recent/`（其余服务均为 `python -m <pkg>.main`） |
| 重置日期与日历日期不同 | `shard.utils.time` | `TIMEZONE_OFFSET = 5` 使"日"的边界落在当地 05:00，落库的 `snapshot_date` 是重置日而非自然日 |

---

## 十一、相关文件

| 文件 | 说明 |
| --- | --- |
| `init/sqlite/recent.sql` | 用户 SQLite 库的 6 张表与 `idx_battle_time` 索引 |
| `init/mysql/01-schemas/02-user.sql` | MySQL 侧本服务涉及的表（`T_user_base` / `T_user_stats` / `T_user_action` / `T_user_random` / `T_user_ranked` / `T_user_cache` / `T_user_config`） |
| `shard/contracts.py` | `ServicesName.RECENT`、`RedisKeys.recent_lock` / `user_lock` / `user_ac_token` / `metrics`、`Endpoints` |
| `shard/db/` | `MySQLOPS` / `SQLiteOPS`（连接与事务上下文管理器）、`distributed_lock` |
| `shard/game/user.py` | `UserPolicyUtils`：活跃等级、更新间隔、保底超时、停用阈值 |
| `shard/game/clan.py` | `ClanBattleUtils.update_period`（CLAN 更新活跃时间段） |
| `shard/utils/time.py` | `TimeUtils.reset_date` / `reset_date_list`（重置日期计算） |
| `shard/utils/data.py` | `StringUtils`（索引与快照的编解码）、`ParseUtils.user_basic_data` |
| `shard/logger.py` | `create_logger` / `exception_writer` / `progress_iterable` |
| `docs/core/activity.md` | 活跃等级与刷新间隔系统（本服务复用其策略） |
| `data/json/services_config.json` | 服务级配置（`Recent` 段） |
| `data/json/clan_season.json` | CLAN 赛季起止时间，决定活跃时间段 |
| `app/apis/recent/` | 前台读取与按需刷新（共用 `refresh_lock:recent:` 键） |
| `scripts/cache/` | 消费 `T_user_cache.is_due`，重算用户船只缓存 |

---

## 十二、待确认问题

以下为撰写本文档时发现的疑似缺陷，尚未修改，列出以便后续确认：

### 12.1 `RunCounter.failure_rate` 可能返回 `None`

```python
@property
def failure_rate(self) -> int:
    if self.total == self.failed:
        return 100
    if self.total <= 20:
        return 0
    # total > 20 且非全部失败时函数走到底，隐式返回 None
```

`core/scheduler.py` 中的使用方式为 `if run_ctx.failure_rate > 10:`。当单轮用户数超过 20 且存在部分失败时，`None > 10` 抛 `TypeError`，被 `run_once` 的兜底 `except` 捕获，输出 `Fatal error: TypeError` 并**删除服务状态键**。也就是说：**只要一轮里有少量失败用户，本轮就会被记为致命错误、服务在监控上表现为掉线**，而告警本身从未生效。

### 12.2 禁用分支的文件缺失路径

`_handle_stage_result` 在 `data/local/Operation.log` 不存在时 `return`（无返回值），调用方将其视为"未短路"继续执行，结果是：用户已在 MySQL 中被停用，但没有留下操作日志、SQLite 文件也没有清理。

### 12.3 前台读取与当前表结构不一致

`app/apis/recent/calculate.py`、`summary.py` 读取的 `daily_snapshot_index` / `ship_daily_snapshot` / `ship_latest_cache` 三张表在当前 `init/sqlite/recent.sql` 中已不存在，`user_recent_stats` 的列名也与本服务写入的不一致（前台按 `mode` / `original_exp` / `planes_killed` / `created_at` 读取，实际列为 `data_mode` / `exp` / `planes` / `battle_time` 且另有 `data_type`）。需要确认前台读取是否有未提交的迁移。
