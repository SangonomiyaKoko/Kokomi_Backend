# 公会成员刷新服务设计文档

`scripts/member` 是公会成员数据的**调度与执行合体**：定时轮询 `T_clan_users`，判定哪些公会的成员数据该刷新，然后**自己**请求接口、读写数据库。

与用户刷新链路（[scripts/account](scripts_account.md) 调度 + [tasks](tasks.md) 执行）的分工不同，公会侧没有队列也没有 Celery：

| | 用户刷新（account + tasks） | 公会成员刷新（本模块） |
| --- | --- | --- |
| 取数成本 | 一个用户一次请求，百万级用户 | 一个公会一次请求，几百个成员一次取回 |
| 拆分方式 | 调度与执行拆成两个服务，中间用 RabbitMQ 缓冲 | **不拆**：一轮内直接串行刷新每个公会 |
| 在途去重 | 需要 `queue` 锁 + `user` 锁（跨进程并发） | 不需要：单进程串行，天然无并发 |
| 计划载体 | `T_user_stats.next_refresh_at` | `T_clan_users.next_refresh_at` |

判定为"量级小到不需要队列"是本模块所有设计取舍的前提：因为不拆，所以没有消息格式、没有幂等重投、也没有跨服务的锁交接。

---

## 一、设计目的

### 1.1 三个设计目标

1. **成员关系准确**：公会的成员进出、以及成员在公会之间的流动，都要在本地留下正确且可追溯的记录；
2. **成员不丢、成员数不虚**：接口返回的成员必须都能在本地找到关联（必要时自动建档），`T_clan_users.member_count` 与实际关联必须一致；
3. **刷新计划可控可观测**：全量公会的到期判定、削峰与统计每轮落库，供面板查看。

### 1.2 与用户侧共享的公用库

调度与统计的实现来自 `shard.utils.plan`（`RefreshPlanStats` / `DueEntityContainer` / `RunCounter`），削峰算法来自 `shard.utils.scheduler`。本模块**不自持**这套逻辑——历史上曾有一份 `updater.py`，现已删除。

---

## 二、核心设计思想

### 2.1 成员关系以 `T_user_clan` 为唯一事实

早期版本的成员快照存在 `T_clan_users.member_ids` 这个 JSON 列里，靠"上一次的成员列表"对比出进出。现在该列**已删除**（见 [init/mysql/01-schemas/03-clan.sql](../../init/mysql/01-schemas/03-clan.sql)），成员关系只由两张表表达：

| 表 | 语义 |
| --- | --- |
| `T_user_clan` | **当前状态**：`account_id` 一行，`clan_id` 为 NULL 表示无公会（唯一索引保证一个用户只属于一个公会） |
| `T_clan_action` | **变化历史**：只追加，`action_type` 1 = 加入、2 = 退出 |

这样做的收益是"成员在哪个公会"永远只有一个答案，且能直接按 `clan_id` 建索引查询（`WHERE clan_id = %s` 即可列出全部成员）；代价是"上一次的成员列表"不再现成，需要靠 `T_user_clan` 的**当前状态**反推变化——这正是下一节要解决的问题。

> `T_user_clan.updated_at` 参与判定，但它表达的是"该行最近一次被确认"而不是"最近一次变化"：每次刷新都会把本轮接口返回的全部成员刷成 `NOW()`。因此**判断"从未确认过"用 `updated_at IS NULL`，判断"当前属于谁"只看 `clan_id`**。

### 2.2 一次刷新要回答的三个问题

`ClanUsersSyncer._resolve_member_changes` 把"接口成员"与"本地记录"对比成两类结果：**谁需要记退出**、**谁需要记加入**。

| 本地状态 | 接口中 | 判定 | 写入 |
| --- | --- | --- | --- |
| 属于本公会 | 在 | 无变化 | 仅刷新关联时间 |
| 属于本公会 | 不在 | **退出本公会** | `clan_id = NULL` + `T_clan_action(本公会, uid, 2)` |
| 属于其他公会 | 在 | **转会** | `T_clan_action(原公会, uid, 2)` + `T_clan_action(本公会, uid, 1)` + `clan_id = 本公会` |
| `clan_id` 为 NULL | 在 | **加入** | `T_clan_action(本公会, uid, 1)` |
| 本地状态未知 | 在 | **不判断** | 只把 `clan_id` 写成本公会，不记加入行为 |

三个关键取舍：

**① 状态未知的成员不记"加入"。** 两类成员的此前状态无从判断：本轮**刚插入数据库**的新用户（本地还没有 `T_user_clan` 记录），以及 `T_user_clan.updated_at IS NULL` 的用户（记录存在但从未被确认过，例如公会第一次被本服务刷新）。对他们记一条"加入"会把"第一次见到"误报成"新加入"——尤其在一个公会首次进入刷新范围时会瞬间产出上百条假记录。因此调用方把这些 ID 通过 `invalid_users` 传入，`_resolve_member_changes` 还会额外把"接口中有、本地无记录"的成员也并入未知集合（防御性：即使调用方漏传也不会误报）。

**② 转会成员的退出行为由本服务代为记录。** 成员从公会 A 转到公会 B 时，A 与本服务的下一次刷新都可能先发生：

- 若**本服务先刷新 B**：成员当前是本次刷新的对象，可以看到"本地在 A、接口在 B"，于是记 A 的退出 + B 的加入，并把 `clan_id` 改成 B。之后 A 刷新时该成员已不在 A 的本地成员列表里，不会再记第二次退出；
- 若**A 先刷新**：A 发现成员不在接口里，记 A 的退出并把 `clan_id` 置 NULL。之后本服务刷新 B 时看到的是"本地为 NULL"，只记 B 的加入。

两种顺序都恰好产生**一条退出 + 一条加入**，不会重复也不会丢失。这也是为什么本服务要替 A 记退出：A 的刷新时机不可控，等它自己发现可能已经太晚（`clan_id` 已被改写成 B）。

**③ 退出时把 `clan_id` 置 NULL 而不是直接改指向。** 置 NULL 是"未归属"的中间态，让下一次刷新重新判定归属；这样即使两个公会的刷新顺序被打乱，判定依据始终是"当前状态"，不需要额外的中间表。

### 2.3 空公会：成功取数且成员为空才判定不可用

```python
if len(user_ids) == 0:
    cls._disable_empty_clan(...)     # is_enabled = 0, activity_level = 0,
                                     # member_count = 0, next_refresh_at = NULL
```

**触发条件严格限定为"成功拿到数据，且成员列表为空"**：`_fetch_single` 只在 `200 + status == 'ok'` 时返回 `data['items']`，其余一切情况（404 / 500 / 503 / 非 JSON / 网络异常）都返回错误标记字符串，由 `fetch` 转成 `None`，在 [refresher.py](../../scripts/member/refresher.py) 里直接跳过本轮。也就是说：

- **接口异常不会被当成"全员退出"**：跳过 → 不记任何成员行为、不禁用公会，下一轮继续尝试；
- **404 也不触发禁用**（这是有意为之）：404 走的是与其他错误相同的跳过路径，只是被 `_record_metrics` 计入 `http:daily:error` 并在日志里留一行，不写异常详情文件、不产生成员退出记录。代价是该公会会持续以较高的到期优先级被重试。

判定不可用是一次性的状态迁移：`is_enabled = 0` 之后，调度侧的 `add_batch` 会**直接跳过**该行（`if not is_enabled: continue`），公会从此不再占用刷新配额，也不再被本服务看到。反过来要恢复只能走管理接口（[app/models/clan.py](../../app/models/clan.py) 的 `set_clan_status`）——**没有自动恢复路径**，因为"没有成员"被当作"该公会不再可用"这一确定结论，而不是"暂时取不到"。

> 注意置 `next_refresh_at = NULL` 本身**不会**让公会退出调度：到期判定遇到 NULL 会按"从未刷新"处理并照常派发。真正让公会发生迁移的是 `is_enabled = 0`。

### 2.4 削峰：只提前，不推后

与用户侧同一套 `SchedulerUtils`：分布应单调不增（越早该刷新的越多），右侧高出来的桶是尖峰，把富余桶的实体**提前**到左侧低谷，迁移记录写回 `T_clan_users.next_refresh_at`（`- INTERVAL n HOUR`）。提前刷新只多花一次配额，推后刷新会让过期数据持续存在——所以迁移方向只有"提前"一个。

---

## 三、运行架构

### 3.1 进程模型

```bash
# docker-compose 的 member 服务，容器名 backend-member
python -m scripts.member.main
```

单进程常驻循环：`run_once` → `gc.collect()` → 睡 `max(0, REFRESH_INTERVAL - 本轮耗时)`（不足 1 秒睡 1 秒）。`MEM_MONITOR` 为真时每轮打印进程 RSS。

**单实例假设**：本模块没有公会对公会的互斥锁（用户侧有 `refresh_lock:queue:{uid}`）。同一公会被两个进程同时刷新会互相覆盖 `T_user_clan`，因此本服务只能部署一个实例。

### 3.2 资源

每轮建连、轮末在 `finally` 中逐个关闭：

| 资源 | 类型 | 用途 |
| --- | --- | --- |
| `mysql_conn` | `pymysql.Connection`（`autocommit=False`） | 读取 `T_clan_users`、读写成员关系与统计表 |
| `redis_client` | `Redis`（DB `REDIS_DATABASE`） | 服务状态键 + 插入新用户时的互斥锁 |
| `session` | `requests.Session` | 请求公会成员接口；设置 `SSL_CA_BUNDLE` 时用于俄服证书校验 |

### 3.3 代码分层

```
scripts/member/
├── main.py       # 进程入口：资源生命周期 + 轮询循环 + 状态键
├── worker.py     # run_worker：一轮调度的骨架（扫描 -> 削峰 -> 落统计 -> 派发）
├── refresher.py  # ClanUsersRefresher：单个公会的刷新编排
├── syncer.py     # ClanUsersSyncer：成员关系的写入逻辑
├── requester.py  # APIRequester：接口取数与指标上报
├── db_ops.py     # BasicDataRepository：表读写语句
├── settings.py   # 配置装载
└── logger.py     # 日志器与异常落盘
```

职责边界：**worker 只做调度**（不碰成员数据），**refresher 负责单个公会的编排**（取数 → 读本地 → 补建档 → 调 syncer），**syncer 只负责写入**（判定进出 + 写库），**db_ops 只有 SQL**。这样拆分后 `worker.py` 只剩约 130 行，新增一个"刷新前先做什么"的步骤只需要改 refresher。

### 3.4 状态键

```python
status_key = RedisKeys.services(ServicesName.MEMBER)     # 'status:ClanMember'
redis_client.set(name=status_key, value=1, ex=REFRESH_INTERVAL + 100)
```

每轮开头写入，致命异常时删除（让故障立即可见）。API 侧按键是否存在判定服务可用（[app/apis/manager/state.py](../../app/apis/manager/state.py)）。余量给到 100 秒而不是像 account 那样只给 10 秒，是因为本模块一轮内要**串行发最多 `MAX_DISPATCH_PER_ROUND` 次外部请求**（见 §9）。

---

## 四、单轮执行流程

```
① 扫描 T_clan_users             按 id 分批，判定到期
② 容器裁剪                      DueEntityContainer(capacity=MAX_DISPATCH_PER_ROUND)
③ 削峰 rebalance_plan()         迁移写入 all_migrations
④ write_stats()                 4 张统计表 + 迁移（一个事务）
⑤ 逐个公会 ClanUsersRefresher.refresh()
⑥ 打印汇总
```

### 4.1 扫描与到期判定

```python
with MySQLOPS.read_only(mysql_conn) as cursor:
    max_id = BasicDataRepository.load_max_id(cursor)        # SELECT MAX(id)
    if max_id == 0:
        logger.info("No local clans")
        return
    for start_id in progress_iterable(range(1, max_id + 1, BATCH_SIZE), entry='batch', logger=logger):
        rows = BasicDataRepository.load_table_batch(cursor, start_id, start_id + BATCH_SIZE - 1)
        due_clans = refresh_plan.add_batch(rows)
        candidates.offer(due_clans)
```

`load_table_batch` 一次读回 5 列（`clan_id` / `is_enabled` / `activity_level` / `UNIX_TIMESTAMP(next_refresh_at)` / `UNIX_TIMESTAMP(updated_at)`），列顺序即 `add_batch` 的解包顺序——两侧唯一的隐式契约。

到期判定（`_evaluate_row`）：`updated_at IS NULL` 或 `next_refresh_at IS NULL` 按"从未刷新"处理（`NEVER_REFRESHED_PRIORITY`，默认 600）；已到期按**超期秒数**作为优先级；`next_refresh_at` 前 `REFRESH_ADVANCE_SECONDS`（默认 60）内提前派发，优先级 0。

> 公会行由其它服务（[app/models/syncer.py](../../app/models/syncer.py)、[season/services/syncer.py](../../season/services/syncer.py)、[init/scripts/insert_clan.py](../../init/scripts/insert_clan.py)）通过 `CLAN_INIT_TABLE_LIST` 创建，新行的 `updated_at` 为 NULL —— 这正是"从未刷新"分支的用武之地：新公会会被立刻纳入刷新，无需额外初始化。

### 4.2 容器裁剪

`DueEntityContainer(capacity=MAX_DISPATCH_PER_ROUND)`（默认 1000）保留**最逾期**的一批，其余不标记、不改时间，下一轮自然排到。积压量不需要持久化，因为"到期"本身就是持久状态。

### 4.3 统计落库

```python
waiting = refresh_plan.counter.waiting
with MySQLOPS.transaction(mysql_conn) as cursor:
    BasicDataRepository.write_stats(cursor=cursor, stats_data=refresh_plan.to_db_data())
```

`distribution_len=4` 在构造时注入（`RefreshPlanStats(..., distribution_len=4)`），与 `T_clan_activity` 只有 clan_level 0–3 四行种子对应。写入的表：

| 表 | 字段 | 含义 |
| --- | --- | --- |
| `T_table_meta` | `metric_value`（`metric_key = 'planned_clans'`） | 计划更新公会总数 |
| `T_refresh_stats` | `clan_count` | 按 5 种刷新状态分布 |
| `T_clan_activity` | `clan_count` | 按活跃等级 0–3 分布 |
| `T_refresh_hourly_stats` | `planned_clans` | 按 `planned_hour` 1–24 分布（桶 0 = 已到期 → `planned_hour = 1`） |
| `T_clan_users` | `next_refresh_at` | 削峰迁移，`- INTERVAL hours HOUR` |

`T_refresh_stats` 与 `T_refresh_hourly_stats` 是用户与公会两侧共用的表：本模块只写 `clan_count` / `planned_clans`，用户侧写同行的另一列。

> 统计**每轮都写**，包括本轮无公会可派发的情况——统计描述的是"计划的形状"，面板曲线不会因为某轮无事可做而断点。

### 4.4 单个公会的刷新（[refresher.py](../../scripts/member/refresher.py)）

```
① APIRequester.fetch(clan_id)          200 + status=ok 才返回成员列表，否则返回 None -> 跳过
② users = {id: name}                   解析接口数据
③ 读本地（只读事务）
     existing_members  本地属于本公会的成员 ID（含已退出的，需要标记退出）
     existing_ids      接口成员中已存在于数据库的（其余需要建档）
     existing_users    这些成员在本地的 {clan_id: (clan_id, is_null)}
④ missing_users = users - existing_ids  需要建档的新用户
   invalid_users = missing_users + updated_at IS NULL 的成员
⑤ _insert_new_users(...)                抢 Redis 插入锁 -> 一个事务写 T_user_base + 7 张子表
⑥ ClanUsersSyncer.refresh(...)          成员关系的判定与写入
```

**⑤ 与 ⑥ 是两个独立事务**，因此存在"用户已建档但成员关系未写"的中间态：此时该用户的 `T_user_clan` 行是刚建的初始状态（`clan_id = NULL`、`updated_at = NULL`），下一轮它会被 `invalid_users` 覆盖（不记加入行为），但 `clan_id` 仍会被正常写成该公会 —— **中间态会自愈**，不需要补偿逻辑。

**插入锁的作用范围**：`_insert_new_users` 未抢到锁时返回 `None`，本轮**跳过整个公会**（而不是只跳过建档）。原因是 `_update_clan_users` 写入的 `member_count` 取自接口成员数，如果新用户没入库，`T_user_clan` 的关联行会缺一部分，而计数已经把这些人算进去了——宁可整轮不刷，也不要留下"计数虚高、关联缺失"的不一致状态。该公会保持到期，下一轮重试。

**指标**：`APIRequester` 每次取数都会向 `metrics:http:{period}:{date}` 累加（annual / monthly / daily:total），失败额外记 `daily:error`。`http` 组是[全站共享的命名空间](tasks.md)（API 服务中间件也在写），只有 `celery` 组才是 `tasks/` 独有——本模块不写 `celery` 组。

### 4.5 成员关系的写入（[syncer.py](../../scripts/member/syncer.py)）

一个事务内按固定顺序完成：

```
1. _record_member_changes
     a. 逐"退出公会的 ID"（含转会成员的原公会）：
          UPDATE T_user_clan SET clan_id = NULL, updated_at = NOW()
          INSERT T_clan_action(clan_id, uid, ACTION_LEAVE)
     b. 再统一写入加入行为：INSERT T_clan_action(本公会, uid, ACTION_JOIN)
2. _update_member_relations     UPDATE T_user_clan SET clan_id = 本公会 WHERE account_id IN (接口全部成员)
3. _update_clan_users           UPDATE T_clan_users SET is_enabled=1, activity_level, member_count,
                                    next_refresh_at = NOW() + 刷新间隔, updated_at = NOW()
```

几点说明：

- **顺序不能反**：转会成员在第 1a 步被置空、第 2 步被写成本公会，先退出后加入的顺序保证 `T_clan_action` 里两条记录的时间顺序可读；
- **退出行为按原公会分组写**：转会成员的原公会可能各不相同，`left_groups` 以公会 ID 为键收集，写入时按组批量 `executemany`；
- **`refresh` 返回本次写入的行为记录数**（转会成员计两次：一次退出、一次加入），供 worker 汇总日志使用；
- **异常只记日志不抛出**：写库失败时返回 0，异常详情写入 `logs/exception/`（见 §9 的日志风暴约束）；
- **刷新间隔由活跃等级决定**：`ClanPolicyUtils.clan_activity_level(members)` 按成员数分档（≤10 → 3、≤30 → 2、≤50 → 1、其余 0），`clan_refresh_interval(level)` 查 `ClanPolicy.NORMAL_STRATEGY`（6h / 12h / 26h，缺省 30 天）。

### 4.6 汇总日志

```
Schedule - Due: N | Consumed: M | Waiting: K
Summary  - Inserted: X | Changed: Y
```

| 字段 | 含义 |
| --- | --- |
| `Due` | 本轮扫描出的全部到期公会数 |
| `Consumed` | 本轮进入派发循环的公会数（= 容器容量上限内的一批） |
| `Waiting` | `due - pending`（本模块的 `locked` 恒为 0），即受容量限制未排上与本轮失败的公会 |
| `Inserted` | 新建档的用户数 |
| `Changed` | 写入 `T_clan_action` 的行为记录数（含转会成员的两次） |

---

## 五、数据库与数据模型

### 5.1 读取

| 表 | 用途 |
| --- | --- |
| `T_clan_users` | 全表分批扫描（`MAX(id)` 定区间），取 5 列用于到期判定与统计 |
| `T_user_clan` | `WHERE clan_id = %s` 取本公会成员；`WHERE account_id IN (...)` 取接口成员的存在性与当前公会 |
| `T_user_base` | 判断接口成员是否已建档（只取 `account_id`） |

### 5.2 写入

| 表 | 写入内容 |
| --- | --- |
| `T_clan_users` | `is_enabled` / `activity_level` / `member_count` / `next_refresh_at` / `updated_at` |
| `T_user_clan` | `clan_id`（绑定本公会、或置 NULL 表示退出）、`updated_at` |
| `T_clan_action` | 加入(1) / 退出(2)，**只追加不更新** |
| `T_user_base` + 7 张用户子表 | 新用户建档（`CommonConfig.USER_INIT_TABLE_LIST`） |
| 4 张统计表 | 见 §4.3 |

本模块**不写** `T_clan_base` / `T_clan_stats` / `T_clan_team`（公会基本信息与赛季数据归 [season](season.md) 与 API 服务），也不写用户的业务字段。

### 5.3 跨服务契约

| 数据 | 本模块 | 其它服务 |
| --- | --- | --- |
| `T_clan_users` 行 | 只更新（成员数、计划时间、启用状态） | app / season / init **创建**新公会行（`CLAN_INIT_TABLE_LIST`） |
| `T_clan_users.is_enabled` | 空公会置 0、正常置 1 | 管理接口 `set_clan_status` 可人工改（唯一的恢复路径） |
| `T_clan_users.next_refresh_at` | 刷新后按活跃等级推后、削峰时提前 | 无 |
| `T_user_clan` | 按公会批量维护 | **app 也会按用户维护**（用户数据里的 `clan_id`），两者会互相覆盖后由下一次刷新收敛 |
| `T_user_clan` 读取方 | — | app 的用户详情接口（`clan_id`） |
| `T_clan_action` | 写入 | **目前没有消费方**（面板与接口都未使用） |

### 5.4 Redis 键

| 键 | TTL | 用途 |
| --- | --- | --- |
| `status:ClanMember` | `REFRESH_INTERVAL + 100` | 服务健康度，键存在即可用 |
| `refresh_lock:insert` | 60s（`distributed_lock` 默认） | 新用户建档的互斥锁 |

---

## 六、与其它模块的协作

```
        T_clan_users（公会注册表，由 app / season / init 建行）
             │  全表扫描 + 到期判定
             ▼
   scripts/member（本模块）
             │  逐个公会：GET /api/members/{clan_id}/
             │            ├─ 新成员 -> 建档（T_user_base + 7 张子表）
             │            └─ 成员进出 -> T_user_clan + T_clan_action
             ▼
   MySQL ──┬─ T_clan_users.member_count / next_refresh_at → 回到本模块，闭环
           ├─ T_user_clan.clan_id  → API 服务的用户详情
           └─ T_clan_action        → （暂无消费方）
```

- **上游**：公会行由 app（用户数据里出现新公会时）、season（排行榜采集到新公会时）与初始化脚本创建，本模块只负责刷新已存在的行；
- **下游**：`T_user_clan` 被 API 服务读取；`T_clan_action` 目前没有消费方（见 §9）。

---

## 七、关键设计与边界处理

| 设计点 | 处理方式 | 目的 |
| --- | --- | --- |
| **成员关系用关联表** | `T_user_clan` 单行 + `T_clan_action` 历史 | "当前属于谁"只有一个答案，可直接按 `clan_id` 查询 |
| **不拆队列** | 单进程内串行刷新 | 公会量级小，不需要缓冲与跨服务去重 |
| **不拆 JSON 快照** | 删除 `T_clan_users.member_ids` | 不再维护第二份成员状态 |
| **进出的判定依据** | 本地 `T_user_clan.clan_id` vs 接口成员 | 不依赖"上一次的列表"，乱序刷新也正确 |
| **状态未知不记加入** | 新建档 + `updated_at IS NULL` → `invalid_users` | 避免公会首次刷新时产生上百条假"加入" |
| **转会双向记账** | 原公会记退出、本公会记加入 | 无论哪个公会先刷新，都恰好一条退出 + 一条加入 |
| **退出置 NULL** | `clan_id = NULL` 而非改指向 | 留下"未归属"中间态，供下次刷新重新判定 |
| **空公会才禁用** | 仅"成功取数 + 成员为空"触发 | 接口异常绝不被当成"全员退出" |
| **404 不禁用** | 走与其它错误相同的跳过路径 | 不产生错误的退出记录，也不写异常详情文件 |
| **禁用是一次性状态** | `is_enabled = 0`，planner 直接跳过 | 空公会不再占用刷新配额；恢复需人工介入 |
| **新用户不进"加入"记录** | `missing_users` 全部进 `invalid_users` | 建档不等于"刚加入公会" |
| **建档失败跳过整公会** | `_insert_new_users` 返回 None → `refresh` 返回 None | 不让 `member_count` 与实际关联不一致 |
| **建档与关系分两个事务** | 中间态靠下一轮自愈 | 避免一个大事务长时间持锁 |
| **`member_count` 取接口成员数** | `len(user_ids)` | 与接口语义一致；关联行数在正常情况下相同 |
| **削峰只提前** | `next_refresh_at - INTERVAL n HOUR` | 提前只多花配额，推后会让过期数据留存 |
| **统计每轮都写** | 不受提前 return 影响 | 面板曲线连续 |
| **未抢到插入锁不重试** | 本轮跳过该公会 | 锁的持有者会完成建档，下一轮再刷新关系 |
| **异常不抛出（syncer）** | 记日志 + 写异常详情，返回 0 | 单个公会失败不影响其余公会 |
| **单实例假设** | 无每公会锁 | 依赖"本服务只有一个进程" |

---

## 八、配置与部署

### 8.1 配置项

环境变量（`env.dev` / `env.prod`）：

| 变量 | 说明 |
| --- | --- |
| `PLATFORM` | 存在且以 `KokomiAPI` 开头即视为生产环境，加载 `env.prod`；否则加载 `env.dev` |
| `MYSQL_*` | MySQL 连接参数（`autocommit` 由代码固定为 `False`） |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` / `REDIS_DATABASE` | 状态键与插入锁 |
| `SSL_CA_BUNDLE` | 俄服证书校验；未设置时不改变 `session.verify` |
| `LOG_LEVEL` | 控制台日志等级，仅 `info` / `debug` 有效 |

`data/json/services_config.json` 的 `ClanMember` 段：

| 配置 | 默认值 | 说明 |
| --- | --- | --- |
| `REFRESH_INTERVAL` | 600 | 轮询间隔（秒），同时决定状态键 TTL |
| `REQUEST_TIMEOUT` | 5 | 单次接口请求超时（秒） |
| `BATCH_SIZE` | 10000（json 中为 1000） | 扫描分批大小 |
| `MAX_DISPATCH_PER_ROUND` | 2000（json 中为 1000） | 单轮刷新上限（容器容量） |
| `REFRESH_ADVANCE_SECONDS` | 60 | 提前刷新窗口（秒） |
| `NEVER_REFRESHED_PRIORITY` | 600 | 从未刷新公会的等效超期秒数 |
| `REBALANCE_ENABLED` | true | 是否执行削峰重均衡 |
| `MEM_MONITOR` | false（json 中为 true） | 是否每轮打印进程 RSS |

`REGION` 取自 `data/json/init_marker.json`，决定 `Endpoints.clan_api` 的域名。

### 8.2 启动与目录约定

同其它服务：以项目根目录下是否存在 `README.md` 校验工作目录，不满足则 `sys.exit(1)`，**必须从项目根目录启动**。日志目录须由 [init/setup.py](../../init/setup.py) 预先创建——`create_logger` 只校验 `logs/scripts` 是否存在，缺失直接抛 `FileNotFoundError`。

### 8.3 部署形态

```yaml
member:
  image: myapp:latest
  volumes:
    - ./logs:/app/logs
    - ./data:/app/data
  container_name: backend-member
  command: python -m scripts.member.main
  env_file:
    - env.prod
  restart: on-failure:1
```

### 8.4 日志

| 输出 | 路径 | 级别 |
| --- | --- | --- |
| 控制台 | stdout | `LOG_LEVEL` |
| 服务日志 | `logs/scripts/ClanMember.log` | WARNING 及以上（`RotatingFileHandler`：10MB 转存、保留 1 份备份，磁盘占用有上界） |
| 异常索引 / 详情 | `logs/error/{日期}.log`、`logs/exception/{id}.log` | 由 `write_exception` 写入 |

**本模块没有 `log_ops.py`**：`logs/error` 与 `logs/exception` 是所有服务共用的目录，其保留期清理由 [scripts/account/log_ops.py](../../scripts/account/log_ops.py) 统一负责，各服务不再各自扫描（见 [scripts_account.md](scripts_account.md) §8.4）。

---

## 九、已知约束

| 约束 | 位置 | 说明 |
| --- | --- | --- |
| **状态键余量取决于接口延迟** | `main.py` `run_once` | 状态键 TTL 为 `REFRESH_INTERVAL + 100`（默认 700s），而一轮最多串行请求 `MAX_DISPATCH_PER_ROUND` 个公会且对请求无节流。按每个公会 0.7s 的预算，`MAX_DISPATCH_PER_ROUND = 1000` 时尚有约 2 倍余量；若接口整体变慢或超时集中出现，状态键可能在一轮内过期，接口会把服务报成不可用 |
| **逐公会写异常详情文件** | `syncer.py` `refresh` 的 `except` | 每个写库失败的公会都会写一份 `logs/exception/{uuid}.log` 与一行索引（一轮最多 `MAX_DISPATCH_PER_ROUND` 份）。部分故障（锁等待超时、磁盘满、单表报错）下会产生大量同质记录。对比 [tasks/syncer.py](../../tasks/syncer.py) 的写法：那里刻意只返回异常类名、不落盘，理由是"批量 DB 故障时避免日志风暴" |
| **空公会的禁用没有自动恢复路径** | `syncer.py` `_disable_empty_clan` | "成功取数 + 成员为空"即 `is_enabled = 0`，之后不再刷新。恢复只能人工调管理接口。若成员重新加入一个曾经清空的公会，本服务不会察觉 |
| **404 公会持续重试** | `refresher.py` + `requester.py` | 有意不把 404 归入"成员为空"：不记退出、不禁用。代价是该公会保持到期状态，并以较高的超期优先级长期占用每轮的容量 |
| **`refresh_lock:insert` 并非跨服务锁** | `shard/contracts.py` `RedisKeys.insert_lock` | 注释写"跨服务插入新用户的互斥锁"，但仓库内只有本模块使用。单进程服务锁自己没有实际意义，"未抢到锁"分支近乎不可达 |
| **无每公会锁** | `worker.py` | 同一公会被两个实例并发刷新会互相覆盖 `T_user_clan`，因此只能单实例部署 |
| **`T_clan_action` 无消费方、无保留期** | `init/mysql/01-schemas/03-clan.sql` | 全仓没有读取这张表的代码；它随成员变动无限增长，没有清理策略 |
| **>50 人的公会同空公会共用等级 0** | `shard/game/clan.py` | `clan_activity_level` 对 >50 返回 0，而 `clan_refresh_interval` 没有 `"0-0"` 条目 → 刷新间隔落到兜底的 **30 天**，且该公会会统计进 `T_clan_activity` 的第 0 行（与空公会同一行）。游戏公会上限为 50 人，当前不可达 |
| **`waiting_clans` 指标种子行未被写入** | `init/mysql/02-data/01-base.sql` | `T_table_meta` 中有 `waiting_clans` / `waiting_users` 两行种子，但当前没有任何代码更新它们 |
| **`Changed` 计数含转会成员的两次** | `syncer.py` `refresh` 返回值 | 返回的是写入 `T_clan_action` 的**记录数**而非"变动的成员数"，转会成员在原公会与本公会下各计一次 |
| **`Consumed` 含本轮失败的公会** | `worker.py` §4.6 | 进入派发循环即计入，因此 `Waiting` 会少算这部分积压（它们下一轮会重新到期） |
| **`member_count` 与关联行数的潜在不一致** | `syncer.py` `_update_clan_users` | 计数取自接口成员数；若某用户缺 `T_user_clan` 行，`UPDATE ... WHERE account_id IN` 会静默影响 0 行。当前 app 与 init 建档都会写 `T_user_clan`，两者一致 |
| **未使用 `__init__.py`** | `scripts/` | 服务以命名空间包方式导入（`python -m scripts.member.main`），无包初始化文件 |

---

## 十、相关文件

| 文件 | 说明 |
| --- | --- |
| [scripts/member/worker.py](../../scripts/member/worker.py) | 一轮调度骨架：扫描、容器裁剪、削峰、统计落库、派发 |
| [scripts/member/refresher.py](../../scripts/member/refresher.py) | `ClanUsersRefresher`：单个公会的取数 → 读本地 → 建档 → 写关系 |
| [scripts/member/syncer.py](../../scripts/member/syncer.py) | `ClanUsersSyncer`：成员进出判定与写入 |
| [scripts/member/db_ops.py](../../scripts/member/db_ops.py) | `BasicDataRepository`：各表的 SQL |
| [scripts/member/requester.py](../../scripts/member/requester.py) | `APIRequester`：成员接口取数与 http 指标 |
| [scripts/member/main.py](../../scripts/member/main.py) | 进程入口、资源生命周期、状态键 |
| [shard/utils/plan.py](../../shard/utils/plan.py) | `RefreshPlanStats` / `DueEntityContainer` / `RunCounter` |
| [shard/utils/scheduler.py](../../shard/utils/scheduler.py) | `SchedulerUtils`：削峰区间查找与区间内均衡 |
| [shard/game/clan.py](../../shard/game/clan.py) | `ClanPolicy` 等级阈值与刷新间隔、`ClanPolicyUtils`；另含两套公会战时段规则（服务于 season 与 recent，与本模块无关） |
| [shard/contracts.py](../../shard/contracts.py) | `RedisKeys` 键名、`CommonConfig.USER_INIT_TABLE_LIST` / `CLAN_INIT_TABLE_LIST` |
| [init/mysql/01-schemas/03-clan.sql](../../init/mysql/01-schemas/03-clan.sql) | `T_clan_users` / `T_clan_action` / `T_clan_activity` 表结构 |
| [init/mysql/01-schemas/02-user.sql](../../init/mysql/01-schemas/02-user.sql) | `T_user_clan` 表结构 |
| [scripts_account.md](scripts_account.md) | 用户侧的调度服务；`logs/error` 的统一清理由它负责 |
| [tasks.md](tasks.md) | 用户侧的执行服务；异常不落盘、404 视为有效结果等对照设计 |
