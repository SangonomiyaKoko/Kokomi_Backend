# 用户数据刷新调度服务设计文档

`scripts/account` 是用户刷新的**调度侧**：定时轮询 MySQL，判定"这一轮该刷新哪些用户"，把任务投递到 RabbitMQ 的 `refresh_queue`。本模块**不刷新任何数据**——不请求游戏接口，也不写用户的业务字段，只更新调度统计与刷新计划。

---

## 一、设计目的

### 1.1 在整体架构中的位置

需要刷新的用户有几十万到上百万，每个用户的"下次该刷新时间"（`next_refresh_at`）各不相同。因此刷新被拆成**调度**与**执行**两半，本模块是前者：

| | 调度（本模块 `scripts/account/`） | 执行（[tasks/](../../tasks/)） |
| --- | --- | --- |
| 触发 | 定时轮询（`REFRESH_INTERVAL`） | 消息队列事件驱动 |
| 职责 | 扫描全表，判定"这轮该刷新谁" | 刷新"被指定的那一个用户" |
| 形态 | 常驻单进程 | Celery worker（可水平扩容） |
| 输出 | 向 `refresh_queue` 投递任务 | 写 MySQL + 上报指标 |

本模块是 `refresh_queue` 的**唯一生产者**。两侧不共享任何代码路径，只共享两个常量与一份消息格式（见 §2.3），执行侧的细节见 [tasks.md](tasks.md)。

### 1.2 三个设计目标

1. **不重复派发**：同一个用户不能在途两次——重复刷新既浪费对外调用，也会产生写竞争；
2. **吞吐可调且不失控**：单轮派发量必须有硬上限，否则一轮就能把队列与执行侧同时压垮；
3. **调度计划可观测、运行痕迹不自增**：全量的刷新计划（总数、状态分布、未来 24 小时的分布）每轮落库供面板查看；错误日志按保留期清理，磁盘占用有上界。

---

## 二、核心设计思想

### 2.1 全表轮询，而非"待办队列"

判定"谁该刷新"最自然的做法是把用户放进一个按 `next_refresh_at` 排序的 Redis 有序集合，取到期的一批即可。本模块**没有采用**，而是每轮把 `T_user_stats` **全表扫一遍**：

```python
max_id = BasicDataRepository.load_max_id(cursor)          # SELECT MAX(id)
for start_id in range(1, max_id + 1, BATCH_SIZE):          # 按自增 ID 区间分批
    rows = BasicDataRepository.load_table_batch(start_id, start_id + BATCH_SIZE - 1)
    due_users = refresh_plan.add_batch(rows)               # {account_id: priority}
```

这么做的理由是**使"到期"成为唯一事实（single source of truth）**：`next_refresh_at` 在 MySQL 里，执行侧写完即生效，调度侧下一轮自然看到，不需要维护第二份状态，也不存在"Redis 计划表与 MySQL 不一致"的修复逻辑。代价是每轮 O(全表) 的读取，用 `BATCH_SIZE`（默认 10000）分批 + 游标顺序读把代价压到可接受范围。

> **为什么不用 `WHERE next_refresh_at <= NOW()` 直接筛到期用户**：统计口径要求**全量**——活跃度分布、5 种刷新状态分布、未来 24 小时分布，都必须基于所有用户行计算，因此这一轮注定要读全表。既然全表都要读，到期判定放在 Python 侧（`add_batch`）不额外增加任何成本，反而省掉了"过滤条件与统计口径不一致"的风险。反过来，如果只为派发而读，也确实该用有序集合——但那会把计划拆成两份状态。

**不可用用户不参与计划**：`add_batch` 遇到 `is_enabled = 0` 直接跳过（不计入 `planned_counts`，也不参与到期判定）。执行侧把注销/隐藏的账号置 `is_enabled = 0` 或 `next_refresh_at = NULL`（见 [tasks.md §4.6](tasks.md)），本模块据此**自动摘除**，无需额外的清理流程。

### 2.2 到期判定只有一条规则

`shard/utils/plan.py` 的 `_evaluate_row` 把一行的状态收敛为 `(remaining_seconds, update_priority)` 二元组，`update_priority is None` 即未到期：

| 行状态 | 判定 | `priority` |
| --- | --- | --- |
| `updated_at IS NULL` | 从未刷新过，按逾期处理 | `NEVER_REFRESHED_PRIORITY`（600） |
| `next_refresh_at IS NULL` | 无刷新计划，同样按逾期处理 | `NEVER_REFRESHED_PRIORITY`（600） |
| `NOW() > next_refresh_at` | 已到期 | `NOW() - next_refresh_at`（**超期秒数**） |
| `next_refresh_at - advance <= NOW() <= next_refresh_at` | 提前窗口内，准备刷新 | `0` |
| 其余 | 未到期 | `None`（不派发） |

`priority` 就是"这一轮先派发给谁"的排序依据，取值设计是：**越逾期越优先**（超期秒数天然递增），从未刷新过的排在 600 秒超期之后，提前窗口内的最后。

> **`NEVER_REFRESHED_PRIORITY` 是"等效超期秒数"**：它不是开关，而是把"从未刷新"折算成一个可比的大小。设成 600 意味着"一个用户如果已经逾期超过 10 分钟，就应该先于从未刷新过的用户被派发"。
>
> **`REFRESH_ADVANCE_SECONDS`（默认 60）制造了一个提前窗口**：`next_refresh_at` 还差 60 秒之内的用户也一并派发。这是为了抵消"调度轮询间隔（60s）+ 任务在队列中等待"的延迟——若不提前，实际刷新时间会稳定晚于计划时间。

### 2.3 三层互斥的前两层

[tasks.md §2.2](tasks.md) 描述了三层去重，其中**前两层由本模块负责**：

```
第一层  next_refresh_at（MySQL TIMESTAMP）
        调度侧粗筛。它只能挡住"已完成的刷新"，挡不住"已入队但尚未完成"的。
        ↓
第二层  refresh_lock:queue:{uid}（Redis DB n+1，TTL = QUEUE_LOCK_TTL，默认 14400s）
        本模块在【入队成功后】加锁，执行侧在任务结束时删除。
        存活期 = 消息在队列中等待 + 正在被处理，覆盖整个"在途"窗口。
        ↓
第三层  refresh_lock:user:{uid}（Redis，TTL 60s）——由执行侧自加自删
```

第二层的过滤发生在扫描过程中，用**一次 pipeline 批量 `EXISTS`**：

```python
pipe = lock_client.pipeline()
for account_id in due_account_ids:
    pipe.exists(RedisKeys.queue_lock(account_id))
existing_results = pipe.execute()                     # [0/1, ...]，顺序与入参一致
pending_users = {uid: prio for uid, locked in zip(due_account_ids, existing_results) if not locked}
```

**为什么先入队、后加锁？** 反过来（先 `SETNX` 再加锁）会在"加锁成功但 `send_task` 抛异常"时留下一个**没有任务的锁**：该用户会被锁住 `QUEUE_LOCK_TTL`（默认 4 小时）不被派发，且没有任何机制能发现这个孤锁。当前顺序的代价是"`send_task` 成功但加锁前进程崩溃"会漏加一次锁，此时该用户下一轮会被重复派发一次——由第三层 `user` 锁兜底，不会真的并发写库。

> **`EXISTS` 而非 `SETNX` 也是同一个取舍**：本服务是队列锁的**唯一写入者**且单线程，读取时不必抢占式加锁；若在扫描阶段就用 `SETNX` 占坑，任何异常（进程被杀、DB 报错）都会留下一批需要批量回收的锁。锁的存在性判断与实际加锁分离在扫描与派发两个阶段，中间**没有**需要回滚的状态。

> 加锁用 `nx=True`：若执行侧刚把锁删掉（任务已完成）而本模块正要补发，`nx` 保证不会覆盖执行侧尚未产生的下一次状态；`ex=QUEUE_LOCK_TTL` 保证即使进程崩溃，锁也会在 4 小时后自然释放。

### 2.4 削峰重均衡：只提前，不推后

用户是**批量建号**的（导入、赛季初始化），建号时 `next_refresh_at` 往往取同一个时间，于是刷新计划会出现"某一小时堆了几十万个用户、其余小时空着"的尖峰——`calc_imbalance_score` 定义为：

```
score = Σ max(0, counts[i+1] - counts[i]) / Σ counts[i] × 100
```

即"违反单调不增的相邻逆增量占总量的百分比"。理想的计划分布应当**单调不增**（越早的时段该刷新的越多，因为都是同一时刻到期的），因此右侧比左侧高的桶就是峰的右肩。

`find_rebalance_intervals` 从后向前找出这样的区间，并受两个**绝对量**阈值过滤，避免对少量用户做无意义的搬迁：峰值桶的实体数须达到 `min_peak_abs = max(100, 桶内实体总数 / 10000 × 100)`，区间实体总数须达到 `min_interval_total = 2 × min_peak_abs`。`rebalance_interval` 在选中的区间内**从左往右填谷**：把右侧富余桶里的实体挪到左侧低于平均值的桶里，产生 `(advance_hours, entity_id)` 迁移记录。

**迁移只会让实体提前**（`advance_hours = j - i > 0`），落库语句是 `next_refresh_at - INTERVAL %s HOUR`。这样做的理由是：提前刷新**只是多花一点配额，不会错过任何数据**；而推后刷新会让"该更新时没更新"的状态持续存在，是不可接受的。极端情况下提前量不会超过 23 小时（桶只有 0–23）。

重均衡在 `REBALANCE_ENABLED` 为真时执行，**结果通过 `write_stats` 写回数据库**（`all_migrations`），下一轮扫描看到的就是调整后的计划，因此重均衡是"一次生效、层层收敛"的，不需要在内存里维持跨轮状态。

> 阈值 `MIN_IMBALANCE_SCORE = 20` 与 `min_peak_abs = max(100, 实体总数 / 10000 × 100)` 定义在 [shard/utils/plan.py](../../shard/utils/plan.py) 中，属公用库常量，**不随服务配置变化**——用户侧与公会侧共用同一套削峰规则。

### 2.5 调度与统计解耦

每轮都会把统计写入 4 张表（见 §4.5、§5.2），**包括本轮没有派发任何任务的情况**：统计写的是"计划的形状"（总数、状态分布、活跃度分布、24 小时分布），而不是"本轮干了什么"。这样面板上的曲线是连续的，不会因为某轮无事可做而断点。

---

## 三、运行架构

### 3.1 进程模型

```bash
# docker-compose 的 account 服务，容器名 backend-account
python -m scripts.account.main
```

`main.py` 是一个**单进程常驻循环**：`start_scheduler` → `run_once` → `gc.collect()` → 睡 `max(0, REFRESH_INTERVAL - 本轮耗时)`（不足 1 秒则睡 1 秒）→ 再进入下一轮。`MEM_MONITOR` 为真时每轮打印一次进程 RSS（依赖 `psutil`）。

> 每轮结束时 `gc.collect()` 是必要的：一轮扫描会产生大量临时列表（每批 `BATCH_SIZE` 行、每行的判定结果），百万级用户下只靠分代回收会让 RSS 缓慢爬升。

### 3.2 资源：每轮建连、轮末断开

`run_once` 在一轮内建好全部资源，并在 `finally` 中逐个关闭：

| 资源 | 类型 | 用途 |
| --- | --- | --- |
| `mysql_conn` | `pymysql.Connection`（`autocommit=False`） | 读取 `T_user_stats`、写入 4 张统计表 |
| `redis_client` | `Redis`（DB `REDIS_DATABASE`） | 仅写服务状态键 |
| `lock_client` | `Redis`（DB `REDIS_DATABASE + 1`） | 读写 `refresh_lock:queue:*` |
| `celery_app` | `Celery` producer | 向 `refresh_queue` 投递任务 |

**与执行侧（`tasks/`）最大的差异是不用连接池、也不长驻 `requests.Session`**：本模块每轮只做"读一批 → 写一次 → 发一批"，每轮建连的开销远小于一轮扫描本身的耗时；而 Celery worker 是并发长驻的，才需要连接池。

> **两个 Redis 客户端分属不同的库**：状态键在 `REDIS_DATABASE`，队列锁在 `REDIS_DATABASE + 1`。两个键前缀不同（`status:` / `refresh_lock:`），取错客户端不会报错，只会静默地读写到另一个库——执行侧删除队列锁用的是同一个 `+1` 库（见 [tasks/context.py](../../tasks/context.py)），两处必须一致。

`Celery` 只作为 producer 使用，不注册任务、不消费队列：

```python
_broker = f"pyamqp://{user}:{password}@{host}/"
celery_app = Celery('producer', broker=_broker, broker_connection_retry_on_startup=True)
```

### 3.3 代码分层

```
scripts/account/
├── main.py      # 进程入口：资源生命周期 + 轮询循环 + 状态键
├── worker.py    # run_worker：一轮调度的全部编排
├── db_ops.py    # BasicDataRepository：T_user_stats 读取 + 统计表写入
├── log_ops.py   # 错误日志的保留期清理
├── settings.py  # 配置装载：环境变量 / data 下 JSON
└── logger.py    # 日志器与异常落盘
```

事务与只读上下文管理器由 `shard.db.MySQLOPS` 提供，调度计划与统计由 `shard.utils.plan` 提供，本模块不再自持。**历史包袱已清理**：原先的 `updater.py`（自带一套 `RefreshPlanStats` / `DueClanContainer`）已删除，两类服务共用公用库实现。

### 3.4 状态键与存活判定

```python
status_key = RedisKeys.services(ServicesName.ACCOUNT)   # 'status:Account'
redis_client.set(name=status_key, value=1, ex=REFRESH_INTERVAL + 10)
```

每轮**开始时**写入，TTL 为 `REFRESH_INTERVAL + 10`；致命异常时在 `except` 中删除该键，让故障**立即**可见而不是等 TTL 过期。

[app/apis/manager/state.py](../../app/apis/manager/state.py) 与 [app/dashboard/metrics.py](../../app/dashboard/metrics.py) 通过 `EXISTS` 读取：**键存在即视为服务可用**，不存在即返回 0。因此单轮耗时必须控制在 `REFRESH_INTERVAL + 10`（默认 70 秒）以内，否则服务健康但接口会报不可用。

> 这里的 TTL 只有 10 秒余量，是因为本模块一轮内**不发起任何外部请求**——扫描、写统计、投递都是本地或局域网操作。执行侧（`tasks/`）不写状态键：它的健康度由队列积压量表达。

---

## 四、单轮执行流程

`run_worker(mysql_conn, lock_client, celery_app)` 是本模块唯一的业务入口，一轮的编排如下：

```
① maintain_log_files()                 清理保留期之外的错误日志
② 扫描 T_user_stats → add_batch        判定到期，累加统计
     每批到期用户再经 queue 锁过滤 → candidates.offer()
③ rebalance_plan()                     削峰，结果进入 migrations
④ write_stats()                        统计与迁移落库（一个事务）
⑤ candidates.get_entity_ids() → 逐个 send_task() + 加 queue 锁
⑥ 打印本轮汇总（Due / Locked / Pending / Waiting）
```

### 4.1 清洗日志

```python
# 清理过期日志文件
maintain_log_files()
```

放在**函数最前面**而不是结尾，是为了避开后面的两个提前返回（`max_id == 0` 与"本轮无待派发用户"）：日志保留期是**时间**维度的事，与"这一轮有没有活干"无关。清理只碰文件系统，不依赖 MySQL 与 Redis（见 §8.4）。

### 4.2 扫描与到期判定

```python
with MySQLOPS.read_only(mysql_conn) as cursor:
    max_id = BasicDataRepository.load_max_id(cursor)      # SELECT MAX(id)
    if max_id == 0:
        logger.info("No local users")
        return
    logger.enable_tqdm()                                  # 进入进度条模式
    try:
        for start_id in progress_iterable(range(1, max_id + 1, BATCH_SIZE), entry='batch', logger=logger):
            rows = BasicDataRepository.load_table_batch(cursor, start_id, start_id + BATCH_SIZE - 1)
            ...
    finally:
        logger.disable_tqdm()
```

`load_table_batch` 一次读回 5 列：`account_id` / `is_enabled` / `activity_level` / `UNIX_TIMESTAMP(next_refresh_at)` / `UNIX_TIMESTAMP(updated_at)`——**列顺序即 `add_batch` 的解包顺序**，这是两侧唯一的隐式契约。

**`max_id == 0` 是"空库"的判定**：新部署尚未导入用户时直接返回，避免进入一个必然无事的循环。注意它取的是 `MAX(id)` 而**不是** `COUNT(*)`：`id` 有空洞（删除、批量导入回滚）时区间会偏大，多读出的空区间由 `if not rows: continue` 消化。

### 4.3 队列锁过滤与容器裁剪

每批到期用户先过 `queue` 锁（§2.3），再整体交给 `DueEntityContainer`：

```python
candidates = DueEntityContainer(capacity=MAX_DISPATCH_PER_ROUND)   # 默认 1000
...
candidates.offer(pending_users)        # {account_id: priority}
```

容器是**固定容量的最小堆**，堆内元素为 `(priority, -account_id)`，`offer` 时若已满则与堆顶（当前优先级最低者）比较后替换。因此：

- 单轮派发量**硬上限**为 `MAX_DISPATCH_PER_ROUND`，与全表的到期用户数无关；
- 保留下来的是**最逾期的一批**（超期秒数最大的），同一优先级下 `id` 较小者优先——保证调度是确定的、可复现的；
- 落选的用户不做任何标记（不加锁、不改 `next_refresh_at`），下一轮仍在到期集合里，自然排队。**积压不需要持久化，因为"到期"本身就是持久状态。**

### 4.4 统计落库

```python
logger.debug(f"PreStats - {refresh_plan.bucket_counts}")
if REBALANCE_ENABLED:
    refresh_plan.rebalance_plan()
    logger.debug(f"PostStats - {refresh_plan.bucket_counts}")
    logger.debug(f"Rebalanced: {refresh_plan.migrations}")

with MySQLOPS.transaction(mysql_conn) as cursor:
    BasicDataRepository.write_stats(cursor=cursor, stats_data=refresh_plan.to_db_data())
```

`to_db_data()` 与 `write_stats` 的 SQL **参数顺序是配套设计的**——`to_db_data()` 返回的每个列表已是"按 SQL 中 `%s` 出现顺序摆好的元组序列"，写入侧直接 `executemany` 即可：

| `to_db_data()` 键 | 形如 | 目标 | 单个元组 → SQL 参数 |
| --- | --- | --- | --- |
| `planned_count` | `int` | `T_table_meta.metric_value`（`metric_key = 'planned_users'`） | `[planned_count, 'planned_users']` |
| `refresh_stats` | `[(count, status), ...]` | `T_refresh_stats.user_count` `WHERE status` | `(count, status)` |
| `distribution` | `[(count, level), ...]` | `T_user_activity.user_count` `WHERE user_level` | `(count, level)` |
| `hourly_counts` | `[(count, hour + 1), ...]` | `T_refresh_hourly_stats.planned_users` `WHERE planned_hour` | `(count, hour + 1)` |
| `all_migrations` | `[(hours, entity_id), ...]` | `T_user_stats.next_refresh_at - INTERVAL hours HOUR` | `(hours, entity_id)` |

几个容易看错的地方：

- **`hourly_counts` 的桶 0 映射到 `planned_hour = 1`**：桶 0 装的是**已到期**用户（与"现在就刷"同义），桶 1–23 装的是"还有 1–23 小时到期"的用户，因此 `planned_hour = 桶号 + 1`，取值范围 1–24 与表结构注释一致；
- **`distribution` 的槽位数由构造参数 `distribution_len` 注入**：用户侧传 `10`（活跃等级 0–9，与 `T_user_activity` 的种子行一一对应），公会侧传 `4`（`T_clan_activity` 只有 clan_level 0–3 四行）。这个长度必须与目标表的种子行数一致——**多出来的槽位会 `UPDATE` 到不存在的行**（0 行受影响，不报错，但白跑一趟），少则高等级统计不到；
- **`all_migrations` 为空时不执行**：`REBALANCE_ENABLED` 为假、或本轮分布已经单调不增（`rebalance_plan` 提前返回）时都是空列表，此时统计照写、迁移不写；
- **`counter` 不落库**：`RunCounter` 的 `due` / `locked` / `pending` 只在日志里出现，面板要的是分布而不是单轮计数。

> 统计写入**与派发无关**：即使本轮 `update_ids` 为空（提前 return），统计也已经落库——这是 §2.5 的"每轮都写计划形状"的落实。

### 4.5 派发与加锁

```python
update_ids = candidates.get_entity_ids()          # 按优先级从高到低
refresh_plan.counter.add_pending(len(update_ids))  # pending 供 waiting 与日志使用
if len(update_ids) == 0:
    logger.info("No pending users")
    return

for account_id in progress_iterable(items=update_ids, entry='user', logger=logger, sample_print='Pending tasks'):
    if not send_task(celery_app=celery_app, task_name=CommonConfig.REFRESH_TASK_NAME,
                     entity_id=account_id, queue_name=CommonConfig.REFRESH_QUEUE_NAME):
        logger.warning(f'{account_id} | Task send failed')
        continue                                   # 入队失败：不加锁，下一轮自然重试
    lock_client.set(name=RedisKeys.queue_lock(account_id), value=1, nx=True, ex=QUEUE_LOCK_TTL)
```

消息载荷只有 `{'uid': account_id}` 一个字段（与执行侧 `payload.get('uid')` 对应）：

```python
# shard/contracts.py → CommonConfig
REFRESH_TASK_NAME  = 'user_refresh'      # 任务名
REFRESH_QUEUE_NAME = 'refresh_queue'     # 队列名
```

- **`send_task` 把所有异常转成 `False` 并 `logger.error`**，不让单个投递失败中断整轮——Broker 抖动时其余用户仍能正常派发；
- **入队失败的用户不加锁**，因此它仍是"到期且未在途"，下一轮会被再次派发。这是"宁可多试一次，也不留孤锁"的体现（对比 §2.3 的顺序取舍）；
- **加锁不做 `nx` 结果判断**：若 `nx` 未生效（锁已存在），说明该用户在别的路径上已处于在途状态，锁的 TTL 会由执行侧删除或自然过期，不值得为它做补偿。

### 4.6 汇总日志

```python
logger.info(
    'Schedule - Due: %s | Locked: %s | Pending: %s | Waiting: %s',
    refresh_plan.counter.due, refresh_plan.counter.locked,
    refresh_plan.counter.pending, refresh_plan.counter.waiting
)
```

| 字段 | 含义 | 来源 |
| --- | --- | --- |
| `due` | 本轮扫描出的**全部**到期用户数 | `add_batch` 逐批累加 |
| `locked` | 其中仍持有 `queue` 锁（在途）的用户数 | 逐批累加 `到期数 - 未加锁数` |
| `pending` | 本轮实际进入派发循环的用户数 | `len(update_ids)` |
| `waiting` | `max(due - locked - pending, 0)` | `RunCounter` 属性 |

`waiting` 即**积压量**：既包含"队列还在消化"的在途用户，也包含"受容器容量限制本轮没排上"的用户。这两个口径在日志里不做区分——但它们都会在后续轮次被自然消化，不需要人工干预。

---

## 五、数据库与数据模型

### 5.1 读取

| 表 | 方法 | 说明 |
| --- | --- | --- |
| `T_user_stats` | `load_max_id` / `load_table_batch` | 唯一的读取来源，取 `account_id` / `is_enabled` / `activity_level` / `next_refresh_at` / `updated_at` 五列（`id` 仅用于区间过滤） |

### 5.2 写入

| 表 | 方法 | 写入内容 |
| --- | --- | --- |
| `T_table_meta` | `write_stats` | `metric_value`（`metric_key = 'planned_users'`）：计划更新用户总数 |
| `T_refresh_stats` | `write_stats` | `user_count`：按 5 种刷新状态（`overdue` / `within_24h` / `within_week` / `within_month` / `within_quarter`）分布 |
| `T_user_activity` | `write_stats` | `user_count`：按活跃等级 0–9 分布 |
| `T_refresh_hourly_stats` | `write_stats` | `planned_users`：按 `planned_hour` 1–24 分布 |
| `T_user_stats` | `write_stats` | **仅** `next_refresh_at`：削峰迁移，`- INTERVAL hours HOUR` |

本模块**不写 `T_user_stats` 的任何业务字段**（场次、活跃度、`is_enabled` 等全部由执行侧写入），也无权修改 `T_user_base` / `T_user_clan`。

> `T_refresh_stats` 与 `T_refresh_hourly_stats` 是**用户与公会两侧共用的表**：表结构同时提供两侧的列（`user_count` / `clan_count`、`planned_users` / `planned_clans`），两列互不覆盖。本模块只写用户侧的列。

### 5.3 `next_refresh_at`：跨服务契约

```
执行侧（tasks/）                          调度侧（本模块）
  新用户建档：不写该列（NULL）
  写：NOW() + interval_seconds   ──►   读：update_priority 判定是否到期
  账号无效：写 NULL              ──►   读：按 NEVER_REFRESHED_PRIORITY 处理
  削峰迁移：由本模块直接减小时数 ◄──── 写：next_refresh_at - INTERVAL n HOUR
```

`NULL` 的语义是**"从未刷新过"/"不再刷新"**，本模块对它的处理是"按逾期处理并给一个固定优先级"，因此既不会漏掉新用户，也不会因为脏数据（`updated_at` 有值而 `next_refresh_at` 为空）让某一行永远不被刷新。

### 5.4 Redis 键

| 键 | 读写 | TTL | 用途 |
| --- | --- | --- | --- |
| `status:Account` | 本模块写 / API 读 | `REFRESH_INTERVAL + 10` | 服务健康度，键存在即可用 |
| `refresh_lock:queue:{uid}` | **本模块加，执行侧删** | `QUEUE_LOCK_TTL`（默认 14400s） | 在途用户不被重复派发 |

---

## 六、与其它模块的协作

```
      MySQL（T_user_stats）
            │  全表扫描 + 到期判定
            ▼
   scripts/account（本模块）
            │  ① 过滤 queue 锁仍存在的用户
            │  ② 削峰重均衡 → 写回 next_refresh_at
            │  ③ send_task(name='user_refresh', args=[{'uid': id}])
            │     成功后 set refresh_lock:queue:{uid} = 1（nx, TTL 4h）
            ▼
   RabbitMQ  refresh_queue ──────────────► tasks/（Celery worker，可水平扩容）
                                                   │ 刷新该用户 → 写 6 张表
                                                   ├─ next_refresh_at     → 回到本模块，闭环
                                                   └─ T_user_cache.is_due → UserCache 服务
```

- **下游执行侧**：本模块不关心任务何时被执行、成功与否——`next_refresh_at` 与 `queue` 锁的组合已经把"在途"这件事表达清楚；
- **状态键的消费者**：API 服务（`app/apis/manager/state.py`）与面板（`app/dashboard/metrics.py`）；
- **统计表的消费者**：`app/dashboard` 读取 4 张统计表绘制刷新计划面板。

---

## 七、关键设计与边界处理

| 设计点 | 处理方式 | 目的 |
| --- | --- | --- |
| **全表轮询** | 按 `id` 区间分批扫 `T_user_stats` | "到期"只有 MySQL 一个事实来源，无需维护第二份计划状态 |
| **分批大小** | `BATCH_SIZE`（默认 10000） | 控制单次查询的内存与网络开销 |
| **不可用用户跳过** | `is_enabled = 0` 直接不参与计划 | 注销/隐藏账号自动摘除 |
| **空库提前返回** | `MAX(id) == 0` → return | 新部署不空转 |
| **单轮派发上限** | `DueEntityContainer(capacity=MAX_DISPATCH_PER_ROUND)` | 防止一轮压垮队列与执行侧 |
| **优先派发最逾期的** | 堆内按 `(priority, -id)` 保留容量内最大者 | 调度确定、可复现，先到期的先刷新 |
| **在途过滤** | pipeline 批量 `EXISTS refresh_lock:queue:*` | 已入队未完成的用户不重复派发 |
| **先入队后加锁** | `send_task` 成功才 `set(nx=True)` | 不留"有锁无任务"的孤锁 |
| **入队失败不加锁** | `continue`，下一轮自然重试 | 宁可多试一次，也不制造孤儿状态 |
| **锁 TTL** | `QUEUE_LOCK_TTL`（默认 4 小时） | 进程崩溃后锁能自然释放 |
| **削峰只提前** | `next_refresh_at - INTERVAL n HOUR` | 提前刷新只多花配额，推后刷新会留下过期数据 |
| **重均衡结果落库** | 迁移写入 `all_migrations` | 跨轮收敛，内存不持有跨轮状态 |
| **统计每轮都写** | `write_stats` 不受提前 return 影响 | 面板曲线连续，不因无事可做而断点 |
| **统计写入单事务** | 4 张表 + 迁移在同一个 `MySQLOPS.transaction` 内 | 统计与计划不出现半更新状态 |
| **状态键即健康度** | 每轮开头 `SET ex=REFRESH_INTERVAL+10` | 单轮耗时超过该 TTL 才会被判为不可用 |
| **致命异常删状态键** | `except` 中 `delete(status_key)` | 故障立即可见，不必等 TTL 过期 |
| **日志清理前置** | `maintain_log_files()` 放在 `run_worker` 开头 | 保留期与"本轮有没有活干"无关 |
| **两个 Redis 库** | 状态键用 DB n，队列锁用 DB n+1 | 不同用途的键隔离 |
| **每轮建连/断连** | `run_once` 的 `finally` 逐个 `close()` | 轮询型服务的资源模型，避免长连接的假死 |
| **`gc.collect()`** | 每轮结束显式回收 | 百万级扫描产生的临时对象不靠分代回收 |
| **producer 不复用 Session** | `Celery` 仅作 producer | 不注册任务、不消费队列，职责单一 |

---

## 八、配置与部署

### 8.1 本模块的配置项

环境变量（`env.dev` / `env.prod`）：

| 变量 | 说明 |
| --- | --- |
| `PLATFORM` | 存在且以 `KokomiAPI` 开头即视为生产环境，加载 `env.prod`；否则加载 `env.dev` |
| `MYSQL_*` | MySQL 连接参数（`autocommit` 由代码固定为 `False`） |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` / `REDIS_DATABASE` | `REDIS_DATABASE + 1` 用作队列锁库 |
| `RABBITMQ_HOST` / `RABBITMQ_DEFAULT_USER` / `RABBITMQ_DEFAULT_PASS` | Broker 连接（`pyamqp://`） |
| `LOG_LEVEL` | 控制台日志等级，仅 `info` / `debug` 有效（其它值一律按 `info` 处理） |

`data/json/services_config.json` 的 `Account` 段：

| 配置 | 默认值 | 说明 |
| --- | --- | --- |
| `REFRESH_INTERVAL` | 60 | 轮询间隔（秒），同时决定状态键 TTL |
| `BATCH_SIZE` | 10000 | 扫描分批大小 |
| `MAX_DISPATCH_PER_ROUND` | 1000 | 单轮派发上限（容器容量） |
| `QUEUE_LOCK_TTL` | 14400 | 队列锁 TTL（秒） |
| `REFRESH_ADVANCE_SECONDS` | 60 | 提前刷新窗口（秒） |
| `NEVER_REFRESHED_PRIORITY` | 600 | 从未刷新实体的等效超期秒数 |
| `REBALANCE_ENABLED` | true | 是否执行削峰重均衡 |
| `ERROR_LOG_RETAIN_DAYS` | 7 | 错误日志保留天数 |
| `MEM_MONITOR` | true | 是否每轮打印进程 RSS |

其它文件来源：`REGION` 取自 `data/json/init_marker.json`，本模块仅在启动日志中打印。`data/json/services_config.json` 文件缺失或该段缺失时，上表全部走默认值。

### 8.2 启动与目录约定

与其它服务一致：`settings.py` 以项目根目录下是否存在 `README.md` 校验工作目录，不满足则 `sys.exit(1)`——**必须从项目根目录启动**（`python -m scripts.account.main`）。

**日志目录必须预先存在**：`create_logger` 只校验目录、不创建目录——`logs/scripts` 缺失时直接抛 `FileNotFoundError`，服务启动即失败；`logs/error` 与 `logs/exception` 缺失时 `exception_writer` 不落盘、直接返回 `'Log-Dir-Missing'`。这些目录由 [init/setup.py](../../init/setup.py) 连同 `logs/metrics` 一起创建，因此**首次部署必须先执行该脚本**：

```bash
python init/setup.py -r <region> -l <location>
```

### 8.3 部署形态

```yaml
account:
  image: myapp:latest
  volumes:
    - ./data:/app/data            # 读取 data/json 下的配置
    - ./logs:/app/logs
  container_name: backend-account
  command: python -m scripts.account.main
  env_file:
    - env.prod
  restart: on-failure:1
```

`restart: on-failure:1` 的含义是"异常退出后重启一次"，与其它常驻服务一致；进程被 `SIGTERM` 时打印一行日志后 `os._exit(0)`（Windows 下不注册信号处理器）。

### 8.4 日志

| 输出 | 路径 | 级别 |
| --- | --- | --- |
| 控制台 | stdout | `LOG_LEVEL`（info / debug） |
| 服务日志 | `logs/scripts/Account.log` | **WARNING 及以上**（与 `LOG_LEVEL` 无关） |
| 异常索引 | `logs/error/{YYYY-MM-DD}.log` | 每行 `时间,服务名,异常名,error_id` |
| 异常详情 | `logs/exception/{error_id}.log` | 完整 traceback |

- 服务日志由 `RotatingFileHandler` 自行转存：超过 10 MB 改名为 `.log.1`，只保留 1 份备份，因此**磁盘占用有上界**，本模块不再做备份清理；
- **`logs/error` 与 `logs/exception` 的清理由本模块统一负责**（`maintain_log_files` → `cleanup_error_logs`）：这两个目录是**所有服务共用**的（异常索引由各服务的 `exception_writer` 追加），因此清理动作只放在本服务一处，避免多个服务重复扫描；
- 清理规则：保留 `ERROR_LOG_RETAIN_DAYS` 天内的 `logs/error/{日期}.log`，删除更早的索引，并**连同索引中引用到的** `logs/exception/{id}.log` 一起删除。索引行数不设上限，也不做孤儿文件清理（详见 §9）。

---

## 九、已知约束

| 约束 | 位置 | 说明 |
| --- | --- | --- |
| 状态键余量仅 10 秒 | `main.py` `run_once` | 单轮耗时超过 `REFRESH_INTERVAL + 10`（默认 70s）时，接口会把服务判为不可用。这是有意的紧约束：本模块一轮内不发起外部请求，超过 70 秒即说明扫描或投递已异常 |
| 异常路径不清理日志 | `worker.py` `run_worker` | `maintain_log_files()` 在 `run_worker` 内部，异常逃出（如 `pymysql.connect` 失败）时不会执行；此时错误日志会持续累积 |
| 入队失败的用户不计入"未派发" | `worker.py` §4.6 | `counter.pending` 统计的是"进入派发循环"的数量，`send_task` 失败的用户也在其中，故 `waiting` 会少算这部分积压 |
| 全表扫描随用户数线性增长 | `worker.py` §4.2 | 每轮固定扫描一遍 `T_user_stats`；百万级用户下这是本模块的主要开销，只能靠 `BATCH_SIZE` 与 `REFRESH_INTERVAL` 平衡 |
| 削峰阈值不可配置 | `shard/utils/plan.py` | `MIN_IMBALANCE_SCORE = 20` 等阈值是公用库常量，用户侧与公会侧共用，无法按服务调整 |
| 削峰会让部分用户提前刷新 | `shard/utils/scheduler.py` | 迁移只提前、不推后，被迁移的用户会比原计划更早刷新（最多提前 23 小时） |
| 统计的"今天"用本地时区 | `shard/utils/plan.py` | `today_remained_counts` 仅用于日志输出，按服务器本地时区计算；写库的时间一律为 UTC |
| 迁移记录不区分"提前到已到期" | `shard/utils/scheduler.py` | 迁移目标是桶 0（已到期）时不改变实际行为——该用户本来就是到期的 |
| 不清理孤儿异常文件 | `log_ops.cleanup_error_logs` | 只删除被过期索引引用的详情文件；索引缺失或写入中断留下的 `logs/exception/*.log` 不会被回收 |
| 异常索引行数不设上限 | `log_ops.cleanup_error_logs` | 单日索引文件按行追加，仅在超过保留期后整体删除，不限制单日条数 |
| `ERROR_INDEX_MAX_LINES` 已移除 | `scripts/account/settings.py` | 该配置项曾用于限制单日索引行数，随 `limit_error_index` 一并删除 |
| 队列锁的写入者唯一性假设 | `worker.py` §2.3 | 依赖"本服务单线程写入队列锁"；若将来把本服务水平扩容，`EXISTS` 过滤与后续 `SET` 之间的窗口会产生竞态 |

---

## 十、相关文件

| 文件 | 说明 |
| --- | --- |
| [scripts/account/worker.py](../../scripts/account/worker.py) | 一轮调度的全部编排：扫描、过滤、削峰、落库、派发 |
| [scripts/account/db_ops.py](../../scripts/account/db_ops.py) | `BasicDataRepository`：`T_user_stats` 读取 + 4 张统计表写入 |
| [scripts/account/log_ops.py](../../scripts/account/log_ops.py) | 错误日志的保留期清理（`logs/error` + `logs/exception`） |
| [scripts/account/main.py](../../scripts/account/main.py) | 进程入口、资源生命周期、轮询循环、状态键 |
| [scripts/account/settings.py](../../scripts/account/settings.py) | 配置装载与环境判定 |
| [shard/utils/plan.py](../../shard/utils/plan.py) | `RefreshPlanStats` / `DueEntityContainer` / `RunCounter`：到期判定、统计、削峰 |
| [shard/utils/scheduler.py](../../shard/utils/scheduler.py) | `SchedulerUtils`：分布不均衡评分、削峰区间查找与区间内均衡 |
| [shard/contracts.py](../../shard/contracts.py) | `CommonConfig.REFRESH_TASK_NAME` / `REFRESH_QUEUE_NAME`、`RedisKeys` 键名 |
| [shard/db/mysql.py](../../shard/db/mysql.py) | `MySQLOPS.read_only` / `MySQLOPS.transaction` |
| [shard/logger.py](../../shard/logger.py) | `create_logger`（目录校验 + 转存）、`exception_writer` |
| [init/mysql/01-schemas/01-base.sql](../../init/mysql/01-schemas/01-base.sql) | `T_table_meta` / `T_refresh_stats` / `T_refresh_hourly_stats` 表结构 |
| [init/mysql/01-schemas/02-user.sql](../../init/mysql/01-schemas/02-user.sql) | `T_user_stats` / `T_user_activity` 表结构 |
| [init/mysql/02-data/01-base.sql](../../init/mysql/02-data/01-base.sql) | 统计表的种子行（5 种状态、1–24 小时、活跃等级 0–9） |
| [tasks.md](tasks.md) | 执行侧：任务的消费、三层互斥的第三层、`next_refresh_at` 的写回 |
