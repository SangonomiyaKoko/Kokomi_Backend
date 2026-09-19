# Celery 刷新任务设计文档

`tasks` 模块是全局唯一由**消息队列驱动**（而非定时轮询）的服务：消费 RabbitMQ 中的 `refresh_queue`，为任务消息指定的用户发起一次数据刷新，把结果落库到 MySQL 的 7 张用户表。

---

## 一、设计目的

### 1.1 在整体架构中的位置

用户数据的刷新需求来自全站几十万到上百万账号，每个账号的"下次该刷新时间"（`next_refresh_at`）各不相同。若由单一进程顺序刷新，既无法并行、也无法应对突发。

因此系统被拆成**调度**与**执行**两半：

| | 调度（`scripts/account`） | 执行（本模块 `tasks`） |
| --- | --- | --- |
| 触发 | 定时轮询 | 消息队列事件驱动 |
| 职责 | 扫描全表，判定"这轮该刷新谁" | 刷新"被指定的那一个用户" |
| 形态 | 常驻单进程 | Celery worker（可水平扩容） |
| 输出 | 向 `refresh_queue` 投递任务 | 写 MySQL + 上报指标 |

本模块**只做执行**：它不关心为什么这个用户该刷新、也不关心全局有多少用户待刷新——这些全部由调度侧决定。

### 1.2 三个设计目标

1. **解耦与削峰**：调度侧只管投递，执行侧按自身消费能力处理，队列天然充当缓冲；
2. **并发安全**：同一用户绝不能被并发刷新两次（会产生数据竞争与重复 API 调用）；
3. **失败可观测且不致命**：任何一个用户的刷新失败都不能影响其余任务，且失败原因要能归因。

---

## 二、核心设计思想

### 2.1 队列即缓冲，任务即契约

调度侧与执行侧**不共享任何代码路径**，只共享两个常量与一份消息格式：

```python
# shard/constants.py
REFRESH_TASK_NAME  = 'user_refresh'     # 任务名
REFRESH_QUEUE_NAME = 'refresh_queue'    # 队列名
```

```python
celery_app.send_task(
    name='user_refresh',
    args=[{'uid': account_id}],        # ← 消息载荷
    queue='refresh_queue'
)
```

载荷只有 `{'uid': account_id}` 一个字段。执行侧收到后只做一件事：刷新这一个用户。

### 2.2 三层互斥：从粗到细挡住重复刷新

"同一用户被刷新两次"有三种成因——调度侧重复派发、队列消息重复投递、worker 并发消费。三者分别由三道防线处理：

```
第一层  next_refresh_at（MySQL 时间戳）
        调度侧粗筛。刷新后把它推到未来，本轮扫描自然不会再选中。
        ↓ 只能挡住"已完成的"，挡不住"已入队但尚未完成"的
第二层  refresh_lock:queue:{uid}（Redis，TTL 4h）
        调度侧在【入队成功后】立即加锁；执行侧在任务【结束时】删除。
        存活期 = 消息在队列中等待 + 正在被处理，覆盖整个"在途"窗口。
        ↓ 挡不住重复投递（如队列重发、手动补发）
第三层  refresh_lock:user:{uid}（Redis，TTL 60s）
        执行侧真正开始写库前，用 nx=True 抢占。抢不到说明已有 worker 在处理，直接放弃。
```

三层的分工可以概括为：**第一层防"已完成"，第二层防"在途"，第三层防"同时"**。

> **锁的归属要分清**：`queue` 锁由**调度侧加、执行侧删**（跨服务的握手）；`user` 锁由**执行侧自己加、自己删**。两条路径的 Redis 客户端也不同——`user` 锁与指标走 `redis_client`（DB 0），`queue` 锁的删除走 `lock_client`（DB 1），避免键混淆。

### 2.3 一次刷新 = 一次请求 + 一个事务

单个用户的刷新被严格约束为：

- **一次 HTTP 请求**：`/api/accounts/{account_id}/` 一次性取回该用户全部基础数据（用户名、注册时间、各模式场次、徽章），不按需分次请求；
- **一个 MySQL 事务**：把结果写入 7 张表，全部成功或全部回滚。

这样设计的原因是：**用户数据的各字段来自同一个接口响应，天然一致**。拆成多次请求或多次提交只会引入中间态。

### 2.4 不向上抛异常

Celery 任务的返回值即"结果"，异常只在返回字符串里表达。整条调用链上所有异常都被就地捕获并转成可读的字符串（`'UserNotInDB'` / `'OperationalError'` …），**不触发 Celery 的重试机制**。

这是刻意为之：账号数据是**周期性可再取**的，一次失败会在下一个刷新周期自然重试；而 Celery 重试会在短时间内反复打同一个可能正在故障的用户，放大故障面。

---

## 三、运行架构

### 3.1 进程模型

```bash
# 生产（docker-compose 的 celery 服务，容器名 backend-celery）
celery --app tasks.main:celery_app worker -Q refresh_queue --loglevel=info --concurrency=3

# 开发（PowerShell / Windows 下需 -P solo）
celery --app tasks.main:celery_app worker -Q refresh_queue -P solo --loglevel=info --concurrency=1
```

- **只消费 `refresh_queue`**（`-Q`），不订阅其它队列；
- `--concurrency=3` 表示单容器 3 个并发执行槽；
- **水平扩容**：再起一个容器即线性提升吞吐，无需任何协调——并发安全由 §2.2 的三层锁保证，而非由单实例假设保证。

### 3.2 Celery 应用配置

```python
celery_app = Celery(
    "tasks",
    broker=f"pyamqp://{user}:{password}@{host}/",   # RabbitMQ
    backend="rpc://",                               # 结果存于 RabbitMQ 临时队列
    broker_connection_retry_on_startup=True
)
celery_app.conf.update(task_routes={...})           # 按任务名路由到指定队列
```

`backend="rpc://"` 意味着**任务结果不落盘**——结果通过 RabbitMQ 的临时队列回传给发起方，无人接收即丢弃。本模块的设计前提正是"结果不需要持久化"：任务的状态由 MySQL 中的 `next_refresh_at` 表达，而不是由 Celery 的结果后端表达。

### 3.3 代码分层

```
tasks/
├── main.py       # Celery 应用创建 + 任务定义（唯一的任务入口）
├── settings.py   # 配置装载：环境变量 / data 下 JSON
├── context.py    # RunContext：进程级单例资源（Session / 连接池 / Redis）
├── scripts.py    # refresh_user：单用户刷新主流程 + 分布式锁 + HTTP 取数
├── syncer.py     # UserStatsSyncer：7 张表的写入逻辑（纯 SQL，无 IO 之外的分支）
└── db_ops.py     # mysql_transaction：连接池上的事务上下文管理器
```

与 `season` / `recent` 模块相比，本模块**没有 `services/` 与 `repository/` 之分**：因为一次任务只做一件事、只写一次库，再拆一层只会增加跳转成本。`syncer.py` 中的每个 `_update_user_*` 方法即一张表的写入单元。

### 3.4 RunContext：进程级单例资源

```python
run_ctx = RunContext()          # main.py 模块级实例化，全进程共享
```

`context.py` 在 `__post_init__` 中一次性建好全部资源：

| 资源 | 类型 | 说明 |
| --- | --- | --- |
| `session` | `requests.Session` | 复用 TCP 连接；设置 `SSL_CA_BUNDLE` 时用于俄服证书校验 |
| `db_pool` | `PooledDB`（maxconnections=4） | **连接池**，`autocommit=False` |
| `redis_client` | `Redis`（DB `REDIS_DATABASE`） | 分布式锁 + 指标上报 |
| `lock_client` | `Redis`（DB `REDIS_DATABASE + 1`） | 仅用于删除调度侧加的 `queue` 锁 |

**与其它服务最大的差异是使用连接池而非单连接。** 原因：Celery worker 是长驻进程且并发执行任务，若沿用"每轮建连"的模型，每个任务都要建立/销毁 TCP 连接；而连接池让 4 个并发槽共享连接，且天然处理断线重连。

> `maxconnections=4` 略大于 `--concurrency=3`，为单个任务内可能的嵌套取连接留出余量。

---

## 四、任务执行流程

### 4.1 入口与参数校验

```python
@celery_app.task(name=CommonConfig.REFRESH_TASK_NAME)
def task_update_user_data(payload: dict):
    account_id = payload.get('uid')
    if not isinstance(account_id, int):
        return f'InvalidParams: {payload}'        # 参数非法直接返回，不抛异常

    result = refresh_user(run_ctx=run_ctx, account_id=account_id)
    return f'{account_id} - {result}'
```

返回值恒为 `'{account_id} - {结果}'` 形式的字符串，便于在 worker 日志中直接归因到用户。

### 4.2 `refresh_user` 主流程

```
① 组装 celery 指标键（annual / monthly / daily:total）
② 构造接口地址
     base_url = Endpoints.vortex_api(REGION, PROXY_CONFIG)
     url      = f'{base_url}/api/accounts/{account_id}/'
③ fetch_data 取数
     返回字符串（错误标记）→ 记 http:error → 直接返回
④ ParseUtils.user_basic_data(region, account_id, response)
     → UserBasicDataDict（可空字段已归一化）
⑤ PolicyUtils.user_activity_level(timestamp, user_data['last_battle_at'])
     → activity_level（0–9）
⑥ with refresh_lock(user_lock):        ← 第三层互斥
     抢不到 → 记 celery:error → 返回 'AcquireLockFailed'
     抢到   → UserStatsSyncer.refresh(...) 写库
⑦ 结果为 int（成功）→ 'Success'；否则记 celery:error → 返回结果字符串
```

**`fetch_data` 的返回约定**（字符串即错误标记）：

| 响应 | 返回 | 语义 |
| --- | --- | --- |
| 200 + JSON + `status == 'ok'` | `data` 字段（缺省 `{}`） | 正常 |
| 200 + JSON + `status != 'ok'` | `'Game_API_Error'` | 游戏侧业务错误 |
| 200 + 非 JSON | `'Game_API_Error'` | 响应体异常 |
| **404** | `{}` | **账号不存在**——交由解析层置 `is_enabled = 0` |
| 其它状态码 | `'HTTP_STATUS_{code}'` | 传输层错误 |
| 请求抛异常 | `'ERROR_{ExcName}'` | 网络/超时等 |

> **404 被特殊对待**：它不是一个"错误"，而是一种**有效的业务结果**（账号已注销）。返回 `{}` 让流程继续走到解析层，最终把该用户标记为失效（`is_enabled = 0`），而不是当成故障反复重试。

调用方只用一句 `isinstance(response, str)` 区分"拿到数据"与"出错"——**把错误编码为字符串、而非异常**，是这条链路能保持扁平的关键。

### 4.3 时间戳与活跃等级

```python
current_timestamp = TimeUtils.timestamp()          # 只取一次，全流程复用
activity_level = PolicyUtils.user_activity_level(
    timestamp=current_timestamp,
    lbt=user_data['last_battle_at']
)
```

活跃等级由"最后战斗时间距今的差值"唯一决定，共 0–9 级，取值规则见 [docs/activity.md](../docs/activity.md)。它是**刷新间隔策略的输入**，但不决定本次是否刷新——刷新与否在调度侧就已决定。

> `current_timestamp` 在流程开头取一次后贯穿始终（包括后续计算 `next_refresh_at` 的间隔），保证同一次刷新内的所有时间推断基于同一时刻。

### 4.4 `UserStatsSyncer.refresh`：单事务写 7 张表

```
mysql_transaction(db_pool)
  │
  ├─ ⓪ _fetch_user_base_row          SELECT 读 T_user_base + LEFT JOIN T_user_stats / T_user_config
  │     无行            → return 'UserNotInDB'
  │     pvp/ranked 为 NULL → return 'DataIntegrityError'   （关联行缺失，见下）
  │
  ├─ ① _update_user_base             写 T_user_base（+ 可能的 T_user_action）
  ├─ ② _update_user_stats            写 T_user_stats，返回新的 updated_at 时间戳
  ├─ ③ _update_user_battles ×2       写 T_user_random / T_user_ranked
  └─ ④ _update_user_cache            写 T_user_cache（is_due 标记）
                                     │
                                   COMMIT → 返回 ② 的 int 时间戳
```

**第 ⓪ 步的两道校验**：

- `T_user_base` 无该行 → `'UserNotInDB'`。本模块**不负责建号**，用户由其它服务（如 ClanMember / Recent 的插入流程）预先建档；
- `T_user_stats` 的 `pvp_battles` 或 `ranked_battles` 为 `NULL` → `'DataIntegrityError'`。这是靠 `LEFT JOIN` 的 NULL 来探测"关联行缺失"：由于第 ② 步最后要执行 `SELECT UNIX_TIMESTAMP(updated_at)` 并取下标 `[0]`，若 `T_user_stats` 无行会直接 `TypeError`；提前拦截把不可读的异常变成可归因的业务结果。

> 选 `updated_at`（而非 `NOW()`）作为返回值，是因为它由数据库在**事务内**写入，是本次刷新的权威时间戳；下一个环节（如 Recent 的兜底判断）据此判断"这份数据是什么时候的"。

### 4.5 按账号状态分支写入

第 ① ② ④ 步都依据 `is_enabled` / `is_public` 两个标志走不同分支，三者必须保持一致：

| 状态 | 判定 | `T_user_base` | `T_user_stats` | `T_user_cache` |
| --- | --- | --- | --- | --- |
| **正常** | `is_enabled=1, is_public=1` | 全字段更新 | 全字段 + `activity_level` + `next_refresh_at` | 按 PvP 场次决定 `is_due` |
| **隐藏战绩** | `is_enabled=1, is_public=0` | 仅 `username` | `next_refresh_at = NOW() + 隐藏策略`，其余清零 | `is_due = FALSE` |
| **账号无效** | `is_enabled=0` | **不更新** | `is_enabled=0`、`next_refresh_at = NULL` | `is_due = FALSE` |

**隐藏战绩**的 `next_refresh_at` 由 `PolicyUtils.user_hidden_policy(user_level)` 决定（高级用户 1 天、普通用户 30 天）——战绩既已隐藏，接口取不到数据，高频刷新没有意义，但也不能永久放弃（用户可能重新公开）。

**账号无效**时 `next_refresh_at` 置 `NULL`：该用户从此**不再被调度侧选中**，相当于自动摘除。而 `T_user_base` 刻意不更新——`username` 是历史存档，不应因为账号注销而丢失。

第 ④ 步的 `is_due` 是给下游 Recent 服务的信号：

```python
if user_data['is_enabled'] and user_data['is_public']:
    if old_pvp != user_data['pvp_battles']:
        UPDATE T_user_cache SET is_due = TRUE       -- PvP 场次变了 → 需要重建 Recent 缓存
    else:
        UPDATE T_user_cache SET updated_at = NOW()
        WHERE account_id = %s AND is_due = FALSE    -- 没变 → 仅刷新时间戳（不覆盖已置位的 is_due）
else:
    UPDATE T_user_cache SET is_due = FALSE          -- 不可用账号 → 撤销待刷新标记
```

> 注意"没变"分支带 `AND is_due = FALSE` 条件：它**不会把已经置为 `TRUE` 的标记改回去**。`is_due` 一旦置位，只能由下游消费后清除——避免刷新流程把下游尚未处理的请求覆盖掉。

### 4.6 昵称变更留档

```python
if old_timestamp and old_username != user_data['username']:
    INSERT INTO T_user_action (account_id, username) VALUES (%s, %s);   -- 记的是【旧名】
```

`T_user_action` 只追加不更新，记录的是**曾用名**。`old_timestamp` 作为前置条件，用于排除"首次建档时旧名为空"的误判。

### 4.7 收尾：锁释放与指标（`finally`）

无论前序流程以何种方式结束，`finally` 中都会执行两步：

```python
finally:
    try:
        # ① 释放调度侧加的排队锁 —— 宣告"这个用户已经不在队列里了"
        run_ctx.lock_client.delete(RedisKeys.queue_lock(account_id))

        # ② 汇总上报本任务的指标
        pipe = run_ctx.redis_client.pipeline()
        for key in incr_keys:
            pipe.incr(key)
        pipe.execute()
    except Exception:
        return 'Redis Error'
```

**指标键**分两组，累计口径一致（annual / monthly / daily:total）：

| 组 | 键前缀 | 含义 | 写入方 |
| --- | --- | --- | --- |
| `celery` | `metrics:celery:{period}:{date}` | **任务**处理量（进入任务即计数） | 仅本模块 |
| `http` | `metrics:http:{period}:{date}` | **HTTP 请求**量（请求发出后才计数） | 本模块 **+ API 服务中间件** |

> **`http` 组是跨服务共享的命名空间**：`app/middlewares/redis.py` 也会为每个 FastAPI 请求累加同一组键。因此 `metrics:http:*` 反映的是**全站对外调用的总量**，而非本模块单独的量；只有 `metrics:celery:*` 是本模块独有的。

两组的差额主要反映"在发出请求前就中断的任务"（如代理配置解析失败）。失败数则由两个 `daily:error` 键分别记录（任务级 `celery`、请求级 `http`）。

这些键**均不设置 TTL**，由 `app/dashboard` 按 period 读取展示（见 `app/dashboard/metrics.py`、`app/dashboard/services.py`），属长期累计计数器。

> **为什么释放 `queue` 锁放在 `finally` 而不是成功路径**：无论成功、业务失败还是异常，任务都已经离开队列，排队锁必须释放，否则该用户会被"锁"住长达 `QUEUE_LOCK_TTL`（4 小时）不被重新派发。锁的语义是"在途"，不是"成功"。

---

## 五、数据库与数据模型

### 5.1 本模块写入的表

| 表 | 写入方法 | 角色 |
| --- | --- | --- |
| `T_user_base` | `_update_user_base` | 用户基础信息：`username` / `register_time` / `insignias` |
| `T_user_stats` | `_update_user_stats` | 活跃与战斗统计：各模式场次、`activity_level`、`next_refresh_at` |
| `T_user_random` | `_update_user_battles` | PvP 战斗统计：场次、胜率、场均、各类最高纪录 |
| `T_user_ranked` | `_update_user_battles` | Rank 战斗统计（字段与上表同构） |
| `T_user_cache` | `_update_user_cache` | Recent 缓存状态：`is_due` 标记 |
| `T_user_action` | `_update_user_base` | 曾用名留档（**只追加**） |
| `T_user_config` | 仅读取 | 取 `user_level`（0无 1普通 2高级），决定刷新策略 |

**只有 `T_user_config` 是只读的**——`user_level` 由其它服务维护（升级/降级），本模块仅消费它来选取策略。

> `T_user_random` 与 `T_user_ranked` 的表结构完全同构，因此共用一个 `_update_user_battles`，表名由参数传入。若 `user_data['random_stats']` 为 `None`（该模式无场次），方法直接返回、不执行 UPDATE——**避免用 0 覆盖已有数据**。

### 5.2 `next_refresh_at`：跨服务契约

`T_user_stats.next_refresh_at` 是本模块与**调度侧**之间的核心契约：

```
本模块                               调度侧（scripts/account）
  写：NOW() + interval_seconds   ──►   读：next_refresh_at <= NOW() 的用户即为"到期"
```

间隔由 `PolicyUtils.user_normal_policy(timestamp, user_level, activity_level, lbt)` 计算：

| 分支 | 条件 | 取值 |
| --- | --- | --- |
| **特殊策略** | `user_level == 2` 且 `activity_level == 1` | 按距上次战斗的时间分档：< 1h → 1min，< 3h → 2min，< 12h → 5min，< 19h → 7min（基准 10min） |
| **常规策略** | 其余 | 查 `NORMAL_STRATEGY['{user_level}-{activity_level}']`，缺省 1 天 |

即：**高级用户 + 刚打完战斗**这一最需要近实时数据的组合，会落到分钟级刷新；而普通用户随活跃度下降逐步放宽到小时、天、乃至 90 天。

### 5.3 数据结构

本模块不定义自己的领域模型，直接使用 `shard` 中的 `UserBasicDataDict`（`TypedDict`）在层间传递：

```python
username, is_enabled, is_public,
total_battles, pve_battles, pvp_battles, ranked_battles, rating_battles,
register_time, last_battle_at, karma, insignias,
random_stats, ranked_stats        # 后两者为嵌套的战斗统计 dict，无场次时为 None
```

选 `TypedDict` 而非 `dataclass` 的原因：这份数据**由 `ParseUtils` 统一构造、被多个模块共享**，且需要能直接透传给 `UPDATE` 语句。用 `TypedDict` 既保留了静态类型提示，又无需在层间做"模型 ↔ 字典"的转换。

`ParseUtils.user_basic_data` 负责把接口响应的**四种形态**归一化成同一结构：

| 响应形态 | 归一化结果 |
| --- | --- |
| 用户不存在 | `is_enabled = 0`，其余为默认值 |
| 隐藏战绩（`hidden_profile`） | `is_public = 0`，仅 `username` 有效 |
| 无战斗数据（缺 `basic`） | 保留 `username` / `register_time`，场次全 0 |
| 正常 | 全字段有效，并派生 `random_stats` / `ranked_stats` |

### 5.4 Redis 键

| 键 | 加/删方 | TTL | 用途 |
| --- | --- | --- | --- |
| `refresh_lock:queue:{uid}` | 调度侧加 / **本模块删** | 14400s | 在途用户不被重复派发 |
| `refresh_lock:user:{uid}` | 本模块自加自删 | 60s | 防止同一用户被并发处理 |
| `metrics:celery:*` / `metrics:http:*` | 本模块写 | 长期 | 吞吐与错误率统计 |

---

## 六、与其它模块的协作

```
scripts/account（调度侧）                     tasks（本模块）
  扫描 T_user_stats
  next_refresh_at <= NOW()
        │
        │  send_task(name='user_refresh', args=[{'uid': id}])
        │  成功后 set refresh_lock:queue:{uid} = 1  (TTL 4h)
        ▼
   RabbitMQ  refresh_queue  ──────────────►  Celery worker
                                                   │
                                                   │ refresh_user → 7 表事务
                                                   ▼
                                              MySQL（T_user_*）
                                                   │
                                                   ├─► next_refresh_at   → 回到调度侧，闭环
                                                   └─► T_user_cache.is_due → Recent 服务
```

- **上游**：`scripts/account` 是唯一的生产者，本模块不感知它如何选出待刷新用户；
- **下游**：`T_user_cache.is_due` 是 Recent 服务重建用户缓存的触发信号；`T_user_stats` 的各模式场次也是 Recent 判断"哪些模式变了"的依据；
- **旁路**：`tests/send_tasks.py` 可在本地手动投递一个任务，用于开发调试：

  ```bash
  python tests/send_tasks.py -i 7000005269
  ```

---

## 七、关键设计与边界处理

| 设计点 | 处理方式 | 目的 |
| --- | --- | --- |
| **三层去重** | `next_refresh_at` → `queue` 锁 → `user` 锁 | 分别挡住"已完成 / 在途 / 同时"，覆盖全部重复成因 |
| **锁的归属跨服务** | `queue` 锁调度侧加、执行侧删 | 锁的语义是"在途"，而非"成功" |
| **两个 Redis DB** | 业务/指标用 DB n，`queue` 锁用 DB n+1 | 避免不同用途的键混在同一空间 |
| **连接池** | `PooledDB(maxconnections=4)`、`autocommit=False` | worker 长驻且并发，避免每任务建连；且强制显式事务 |
| **只消费指定队列** | `-Q refresh_queue` | 与其它服务的队列隔离，互不影响 |
| **不启用 Celery 重试** | 异常转字符串返回 | 周期可再取，避免重试放大故障面 |
| **不落盘任务结果** | `backend="rpc://"` | 状态由 `next_refresh_at` 表达，无需结果后端 |
| **404 视为有效结果** | 返回 `{}`，解析层置 `is_enabled=0` | 账号注销不是故障，不应反复重试 |
| **错误编码为字符串** | `fetch_data` 返回 `'ERROR_X'` / `'HTTP_STATUS_X'` | 调用链保持扁平，`isinstance(x, str)` 即可分流 |
| **时间戳只取一次** | `current_timestamp` 在流程开头固定 | 保证同一次刷新内时间推断基准一致 |
| **关联行缺失前置拦截** | `LEFT JOIN` 的 NULL → `'DataIntegrityError'` | 把后续的 `TypeError` 变成可归因的业务结果 |
| **不负责建号** | `T_user_base` 无行 → `'UserNotInDB'` | 建档职责归属其它服务，本模块只更新 |
| **无数据不覆盖** | `random_stats` / `ranked_stats` 为 `None` 时跳过 UPDATE | 防止用 0 覆盖已有战绩 |
| **`is_due` 单向置位** | 更新时带 `AND is_due = FALSE` | 不覆盖下游尚未消费的待刷新标记 |
| **无效账号自动摘除** | `next_refresh_at = NULL` | 从此不再被调度侧选中 |
| **曾用名留档** | 改名时向 `T_user_action` 追加**旧名** | 只追加不更新，保留完整改名历史 |
| **`T_user_base` 不随注销清空** | `is_enabled=0` 时不更新该表 | 保留历史存档 |
| **异常不落盘（syncer 层）** | 返回异常类名，不写日志文件 | 批量 DB 故障时避免日志风暴 |

---

## 八、配置与部署

### 8.1 本模块的配置项

| 配置 | 来源 | 说明 |
| --- | --- | --- |
| `RABBITMQ_HOST` / `RABBITMQ_DEFAULT_USER` / `RABBITMQ_DEFAULT_PASS` | 环境变量 | Broker 连接（`pyamqp://`） |
| `MYSQL_*` / `REDIS_*` | 环境变量 | 中间件连接，`REDIS_DATABASE + 1` 用作锁库 |
| `REGION` | `data/json/init_marker.json` | 决定 `Endpoints.vortex_api` 的域名 |
| `PROXY_CONFIG` | `data/json/proxy_strategy.json` | `(mode, points)`，用于选择 Vortex 接口的调用方式；**文件缺失时回退为 `('default', [])`** |
| `CLIENT_NAME` | 代码常量 `'Celery'` | 异常日志的写入目录标识 |
| `REQUEST_TIMEOUT` | 代码常量 `5` | 单次请求超时 |
| `LOG_LEVEL` / `SSL_CA_BUNDLE` | 环境变量 | 日志级别 / 俄服证书校验 |

本模块的配置项**不放在 `data/json/services_config.json`**（该文件服务于常驻轮询型服务）：Celery worker 通过命令行参数与并发配置调整，没有"刷新间隔"这类需要动态调整的参数——刷新的节奏完全由调度侧的 `next_refresh_at` 决定。

### 8.2 启动与目录约定

同其它服务一致：`settings.py` 以项目根目录下是否存在 `README.md` 校验工作目录，不满足则直接退出——**必须从项目根目录启动**。

### 8.3 部署形态

```yaml
celery:
  image: myapp:latest
  volumes:
    - ./logs:/app/logs          # 注意：未挂载 ./data
  container_name: backend-celery
  command: celery --app tasks.main:celery_app worker -Q refresh_queue --loglevel=info --concurrency=3
  env_file:
    - env.prod
  restart: on-failure:1
```

> **与 `season` 服务的差异**：`season` 挂载了 `./data`，而本服务**只挂载 `./logs`**。`data/json/init_marker.json` 与 `data/json/proxy_strategy.json` 通过镜像构建时的 `COPY . .` 固化在镜像内。因此**修改 `PROXY_CONFIG` 或 `REGION` 后必须重建镜像**才能生效，改宿主机上的 `data/` 目录不会影响已在运行的 Celery 容器。
