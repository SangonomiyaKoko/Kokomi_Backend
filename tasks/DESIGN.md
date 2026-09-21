# Celery 用户数据刷新服务设计文档

`tasks` 模块是全局唯一由**消息队列驱动**（而非定时轮询）的服务：消费 RabbitMQ 中 `refresh_queue` 的任务消息，为消息指定的用户发起一次数据刷新，把结果写入 MySQL 的用户表。

---

## 一、设计目的

### 1.1 在整体架构中的位置

需要刷新的用户有几十万到上百万，每个用户的"下次该刷新时间"（`next_refresh_at`）各不相同。若由单一进程顺序刷新，既无法并行，也无法应对突发。

因此刷新被拆成**调度**与**执行**两半：

| | 调度（[scripts/account/](../scripts/account/)） | 执行（本模块 `tasks/`） |
| --- | --- | --- |
| 触发 | 定时轮询（`REFRESH_INTERVAL`） | 消息队列事件驱动 |
| 职责 | 扫描全表，判定"这轮该刷新谁" | 刷新"被指定的那一个用户" |
| 形态 | 常驻单进程 | Celery worker（可水平扩容） |
| 输出 | 向 `refresh_queue` 投递任务 | 写 MySQL + 上报指标 |

本模块**只做执行**：不关心这个用户为什么该刷新，也不关心全局有多少用户待刷新——这些全部由调度侧决定。

### 1.2 三个设计目标

1. **解耦与削峰**：调度侧只管投递，执行侧按自身消费能力处理，队列天然充当缓冲；
2. **并发安全**：同一用户绝不能被并发刷新两次（会产生数据竞争与重复的对外调用）；
3. **失败可观测且不致命**：任何一个用户的刷新失败都不影响其余任务，且失败原因要能归因到具体用户。

---

## 二、核心设计思想

### 2.1 队列即缓冲，任务即契约

调度侧与执行侧**不共享任何代码路径**，只共享两个常量与一份消息格式：

```python
# shard/contracts.py → CommonConfig
REFRESH_TASK_NAME  = 'user_refresh'     # 任务名
REFRESH_QUEUE_NAME = 'refresh_queue'    # 队列名
```

```python
# scripts/account/worker.py → send_task
celery_app.send_task(
    name=CommonConfig.REFRESH_TASK_NAME,
    args=[{'uid': account_id}],         # ← 消息载荷
    queue=CommonConfig.REFRESH_QUEUE_NAME
)
```

载荷只有 `{'uid': account_id}` 一个字段。执行侧收到后只做一件事：刷新这一个用户。

### 2.2 三层互斥

"同一用户被刷新两次"有三种成因——调度侧重复派发、队列消息重复投递、worker 并发消费。三者分别由三道防线处理：

```
第一层  next_refresh_at（MySQL TIMESTAMP）
        调度侧粗筛。刷新后由本模块推到未来，本轮扫描自然不会再选中。
        ↓ 只能挡住"已完成的"，挡不住"已入队但尚未完成"的
第二层  refresh_lock:queue:{uid}（Redis，TTL = QUEUE_LOCK_TTL，默认 14400s）
        调度侧在【入队成功后】立即 set(nx=True) 加锁；本模块在任务结束时删除。
        存活期 = 消息在队列中等待 + 正在被处理，覆盖整个"在途"窗口。
        ↓ 挡不住重复投递（如队列重发、手动补发）
第三层  refresh_lock:user:{uid}（Redis，TTL 硬编码 60s）
        本模块真正写库前，用 set(nx=True) 抢占。抢不到说明已有 worker 在处理，直接放弃。
```

三层的分工可以概括为：**第一层防"已完成"，第二层防"在途"，第三层防"同时"**。

> **锁的归属要分清**：`queue` 锁由**调度侧加、执行侧删**——这是一次跨服务的握手，锁的语义是"在途"而非"成功"，因此释放动作放在本模块的 `finally` 中，无论成败都会执行。`user` 锁则由本模块自加自删。
>
> 两条路径用的 Redis 客户端也不同：`user` 锁与指标走 `redis_client`（`REDIS_DATABASE`），`queue` 锁的**删除**走 `lock_client`（`REDIS_DATABASE + 1`）。两个键前缀相同但存在不同的库，取错客户端会删不掉锁。

### 2.3 一次刷新 = 一次请求 + 一个事务

单个用户的刷新被严格约束为：

- **一次 HTTP 请求**：`/api/accounts/{account_id}/` 一次性取回该用户全部基础数据（用户名、注册时间、各模式场次、徽章），不按需分次请求；
- **一个 MySQL 事务**：把结果写入 6 张表，全部成功或全部回滚。

这样设计的原因是：**用户数据的各字段来自同一个接口响应的同一份快照，天然一致**。拆成多次请求或多次提交只会引入中间态。

### 2.4 不向上抛异常

Celery 任务的返回值即"结果"，异常只在返回字符串里表达。整条调用链上的异常都被就地捕获并转成可读的字符串（`'UserNotInDB'` / `'OperationalError'` / `'AcquireLockFailed'` …），**不触发 Celery 的重试机制**。

这是刻意为之：账号数据是**周期性可再取**的，一次失败会在下一个刷新周期自然重试；而 Celery 重试会在短时间内反复打同一个可能正在故障的用户，放大故障面。

---

## 三、运行架构

### 3.1 进程模型

```bash
# 生产（docker-compose 的 celery 服务，容器名 backend-celery）
celery --app tasks.main:celery_app worker -Q refresh_queue --loglevel=info --concurrency=3

# 开发（Windows 下无 prefork，需 -P solo）
celery --app tasks.main:celery_app worker -Q refresh_queue -P solo --loglevel=info --concurrency=1
```

- **只消费 `refresh_queue`**：命令行 `-Q` 与代码中的 `task_routes` 双重指定，二者指向同一队列；
- `--concurrency=3` 表示单容器 3 个并发执行槽；
- **水平扩容**：再起一个容器即线性提升吞吐，无需任何协调——并发安全由 §2.2 的三层锁保证，而非由单实例假设保证。

### 3.2 Celery 应用配置

```python
# main.py
run_ctx = RunContext()                              # 模块级实例化，见 3.4

celery_app = Celery(
    "tasks",
    broker=f"pyamqp://{user}:{password}@{host}/",   # RabbitMQ
    backend="rpc://",                               # 结果回传至 RabbitMQ 临时队列
    broker_connection_retry_on_startup=True
)
celery_app.conf.update(task_routes={
    CommonConfig.REFRESH_TASK_NAME: {'queue': CommonConfig.REFRESH_QUEUE_NAME}
})
```

`backend="rpc://"` 意味着**任务结果不落盘**——结果通过 RabbitMQ 的临时队列回传给发起方，无人接收即丢弃。本模块的设计前提正是"结果不需要持久化"：任务的状态由 MySQL 中的 `next_refresh_at` 表达，而不是由 Celery 的结果后端表达。

### 3.3 代码分层

```
tasks/
├── main.py       # Celery 应用创建 + 任务定义（唯一的任务入口）
├── settings.py   # 配置装载：环境变量 / data 下 JSON
├── context.py    # RunContext：进程级单例资源（Session / 连接池 / Redis）
├── refresher.py  # UserRefresher：一次刷新的编排（取数 → 抢锁 → 收尾）
└── syncer.py     # UserStatsSyncer：用户表的写入逻辑
```

事务上下文管理器与分布式锁由 `shard.db` 提供（`MySQLOPS.transaction` / `distributed_lock`），本模块不再自持。

与 `season` / `recent` 相比，本模块**没有 `services/` 与 `repository/` 之分**：一次任务只做一件事、只写一次库，再拆一层只会增加跳转成本。`syncer.py` 中每个 `_update_user_*` 方法即一张表的写入单元。

### 3.4 RunContext：进程级单例资源

```python
run_ctx = RunContext()          # main.py 模块级实例化，随模块导入即建好资源
```

`context.py` 在 `__post_init__` 中一次性建好全部资源：

| 资源 | 类型 | 说明 |
| --- | --- | --- |
| `session` | `requests.Session` | 复用 TCP 连接；设置 `SSL_CA_BUNDLE` 时用于俄服证书校验 |
| `redis_client` | `Redis`（DB `REDIS_DATABASE`） | `user` 锁 + 指标上报 |
| `lock_client` | `Redis`（DB `REDIS_DATABASE + 1`） | 仅用于删除调度侧加的 `queue` 锁 |
| `db_pool` | `PooledDB`（`maxconnections=4`、`autocommit=False`） | **连接池** |

**与其它服务最大的差异是使用连接池而非单连接。** `season` / `cache` 等轮询型服务是"每轮建连、轮末清连"；而 Celery worker 长驻且并发执行任务，沿用该模型会让每个任务都建立/销毁 TCP 连接。连接池让并发槽共享连接，且天然处理断线重连。

> `maxconnections=4` 略大于 `--concurrency=3`，为单个任务内可能的嵌套取连接留出余量。`autocommit=False` 则是为了让 `MySQLOPS.transaction` 的显式提交成为唯一出口。

---

## 四、任务执行流程

### 4.1 入口与参数校验

```python
@celery_app.task(name=CommonConfig.REFRESH_TASK_NAME)
def task_update_user_data(payload: dict):
    account_id = payload.get('uid')
    if not isinstance(account_id, int):
        return f'InvalidParams: {payload}'        # 参数非法直接返回，不抛异常
    result = UserRefresher.refresh(run_ctx=run_ctx, account_id=account_id)
    return f'{account_id} - {result}'
```

返回值恒为 `'{account_id} - {结果}'` 形式，便于在 worker 日志中直接归因到用户。注意 `isinstance(account_id, int)` 会同时挡下 `None` 与字符串 `uid`——**布尔值 `True` 也是 `int`**，但 `True` 作为账号 ID 不会命中任何真实用户，会在第 ⓪ 步以 `UserNotInDB` 结束，不会造成危害。

### 4.2 `UserRefresher.refresh` 主流程

`refresh` 只做编排：初始化指标键、调用 `_refresh_data` 执行主流程、最后在 `finally` 中收尾（见 4.8）。真正的主流程在 `_refresh_data` 里，过程中**就地**向 `incr_keys` 追加本次应计入的指标键：

```
① 读取绑定的 access token（Redis 键 token:ac:{uid}）
② 构造接口地址
     base_url = Endpoints.vortex_api(REGION, PROXY_CONFIG)
     url      = f'{base_url}/api/accounts/{account_id}/?ac={access_token}'
③ _fetch_data 取数
     返回字符串（错误标记）→ 追加 http:daily:error 与 celery:daily:error → 直接返回
④ ParseUtils.user_basic_data(region, account_id, response)
     → UserBasicDataDict（各形态已归一化）
⑤ UserPolicyUtils.user_activity_level(timestamp, user_data['last_battle_at'])
     → 活跃等级（0–9）
⑥ 抢第三层 user 锁，抢不到 → 追加 celery:daily:error → 返回 'AcquireLockFailed'
⑦ UserStatsSyncer.refresh(...) 写库
     结果为 int（成功）→ 返回 'Success'
     否则追加 celery:daily:error 键 → 返回结果字符串
```

几个容易看错的地方：

- `http` 组的三个 total 键在 ③ **返回之后**才追加，因此无论请求成功还是失败都会计入——即 `metrics:http:*:total` 统计的是**发起的请求数**，而非成功的请求数；
- ③ 的提前返回**同时**追加 `http:daily:error` 与 `celery:daily:error`：接口层失败既算"接口侧的业务失败"，也算"本次任务失败"，两个 `daily:error` 的口径在这里重合；
- `incr_keys` 由 `refresh` 创建、`_refresh_data` 就地追加、最后回到 `refresh` 统一上报。指标键是**分阶段**决定的（`http:*` 只有真发过请求才算），外层算不出来，因此这份列表必须跨两个方法传递。

### 4.3 `_fetch_data` 的返回约定

字符串即错误标记：

| 响应 | 返回 | 语义 |
| --- | --- | --- |
| 200 + JSON + `status == 'ok'` | `data` 字段（缺省 `{}`） | 正常 |
| 200 + JSON + `status != 'ok'` | `'Game_API_Error'` | 游戏侧业务错误 |
| 200 + 非 JSON（`JSONDecodeError`） | `'Game_API_Error'` | 响应体异常 |
| **404** | `{}` | **账号不存在** |
| 其它状态码 | `'HTTP_STATUS_{code}'` | 传输层错误 |
| 请求抛异常 | `'ERROR_{ExcName}'` | 网络/超时等 |

> **404 被特殊对待**：它不是一个"错误"，而是一种**有效的业务结果**（账号已注销）。返回 `{}` 让流程继续走到解析层，由 `user_basic_data` 判定为"用户不存在"并置 `is_enabled = 0`，从而把该用户**自动摘除**出刷新队列，而不是当成故障反复重试。

调用方只用一句 `isinstance(response, str)` 区分"拿到数据"与"出错"——**把错误编码为字符串、而非异常**，是这条链路能保持扁平的关键。

### 4.4 时间戳与活跃等级

```python
current_timestamp = TimeUtils.timestamp()          # 只取一次，全流程复用
activity_level = UserPolicyUtils.user_activity_level(
    timestamp=current_timestamp,
    lbt=user_data['last_battle_at']
)
```

活跃等级由"最后战斗时间距今的差值"唯一决定，共 0–9 级（`lbt` 为空或 ≤0 时返回 0），阈值表在 `shard/game/user.py` 的 `UserPolicy.ACTIVITY_THRESHOLDS`。它是**刷新间隔策略的输入**，但不决定本次是否刷新——刷新与否在调度侧就已决定。

> `current_timestamp` 在流程开头取一次后贯穿始终（包括后续计算 `next_refresh_at` 的间隔），保证同一次刷新内的所有时间推断基于同一时刻。

### 4.5 `UserStatsSyncer.refresh`：单事务写 6 张表

`refresh` 自身不抢锁——第三层 `user` 锁由调用方 `_refresh_data` 在进入前持有（见 4.2 ⑥）。它只负责一个事务，连接取自连接池、并由 `with` 显式归还：

```
with db_pool.connection() as conn, MySQLOPS.transaction(conn) → Cursor
       │
       ├─ ⓪ _fetch_user_base_row    SELECT 读 T_user_base
       │      LEFT JOIN T_user_stats（取 pvp/ranked 场次）
       │      LEFT JOIN T_user_config（IFNULL 取 user_level）
       │   无行                → return 'UserNotInDB'
       │   pvp 或 ranked 为 NULL → return 'DataIntegrityError'
       │
       ├─ ① _update_user_base      写 T_user_base（+ 可能的 T_user_action）
       ├─ ② _update_user_stats     写 T_user_stats，返回新的 updated_at 时间戳
       ├─ ③ _update_user_battles ×2 写 T_user_random / T_user_ranked
       └─ ④ _update_user_cache     写 T_user_cache（is_due 标记）
                                     │
                                   COMMIT → 返回 ② 的 int 时间戳
```

**第 ⓪ 步的两道校验**：

- `T_user_base` 无该行 → `'UserNotInDB'`。本模块**不负责建号**，用户由其它服务的插入流程预先建档；
- `T_user_stats` 的 `pvp_battles` 或 `ranked_battles` 为 `NULL` → `'DataIntegrityError'`。这是靠 `LEFT JOIN` 的 NULL 来探测"关联行缺失"：第 ② 步最后要执行 `SELECT UNIX_TIMESTAMP(updated_at)` 并取 `fetchone()[0]`，若 `T_user_stats` 无行会直接 `TypeError`。提前拦截把不可读的异常变成可归因的业务结果。

> 选 `updated_at`（而非 `NOW()`）作为返回值，是因为它由数据库在**事务内**写入，是本次刷新的权威时间戳；下游据此判断"这份数据是什么时候的"。

**`T_user_config` 只读**：`user_level` 由其它服务维护（升级/降级），本模块仅用 `IFNULL(c.user_level, 0)` 消费它来选取刷新策略。

**异常不落盘**：整个事务体被 `except Exception` 包住，只返回 `type(e).__name__` 字符串，不写异常日志文件。批量 DB 故障时若逐个写日志会产生数千条重复记录（日志风暴），此处与 `season` 的 fail-fast 策略相反。

### 4.6 按账号状态分支写入

第 ① ② ④ 步都依据 `is_enabled` / `is_public` 两个标志走不同分支，三者必须保持一致：

| 状态 | 判定 | `T_user_base` | `T_user_stats` | `T_user_cache` |
| --- | --- | --- | --- | --- |
| **正常** | `is_enabled=1, is_public=1` | 全字段更新 | 全字段 + `activity_level` + `next_refresh_at` | 按 PvP 场次决定 `is_due` |
| **隐藏战绩** | `is_enabled=1, is_public=0` | 仅 `username` | `is_enabled=1`、`is_public=0`、`activity_level=0`、`next_refresh_at = NOW() + 隐藏策略` | `is_due = FALSE` |
| **账号无效** | `is_enabled=0` | **不更新** | `is_enabled=0`、`is_public=0`、`activity_level=0`、`next_refresh_at = NULL` | `is_due = FALSE` |

**隐藏战绩**的 `next_refresh_at` 由 `UserPolicyUtils.user_hidden_policy(user_level)` 决定（`user_level > 0` 为 1 天，否则 30 天）——战绩既已隐藏，接口取不到数据，高频刷新没有意义，但也不能永久放弃（用户可能重新公开）。

**账号无效**时 `next_refresh_at` 置 `NULL`：该用户从此**不再被调度侧选中**，相当于自动摘除。而 `T_user_base` 刻意不更新——`username` 是历史存档，不应因为账号注销而丢失。

第 ④ 步的 `is_due` 是给下游 **UserCache 服务**（`scripts/cache`）的信号：

```python
if user_data['is_enabled'] and user_data['is_public']:
    if old_pvp != user_data['pvp_battles']:
        UPDATE T_user_cache SET is_due = TRUE       -- PvP 场次变了 → 需要重建船只缓存
    else:
        UPDATE T_user_cache SET updated_at = NOW()
        WHERE account_id = %s AND is_due = FALSE    -- 没变 → 仅刷新时间戳（不覆盖已置位的 is_due）
else:
    UPDATE T_user_cache SET is_due = FALSE          -- 不可用账号 → 撤销待刷新标记
```

> 注意"没变"分支带 `AND is_due = FALSE` 条件：它**不会把已经置为 `TRUE` 的标记改回去**。`is_due` 一旦置位，只能由下游消费后清除——避免刷新流程把下游尚未处理的请求覆盖掉。
>
> 比较基准 `old_pvp` 取自第 ⓪ 步读出的 `T_user_stats.pvp_battles`，即**本次更新前**的值。

### 4.7 昵称变更留档

```python
if old_timestamp and old_username != user_data['username']:
    INSERT INTO T_user_action (account_id, username) VALUES (%s, %s);   -- 记的是【旧名】
```

`T_user_action` 只追加不更新，记录的是**曾用名**。`old_timestamp` 作为前置条件，用于排除"旧时间戳为空"的误判。该分支只在 `_update_user_base` 未被提前 `return` 时可达——即 `is_enabled=1` 的两条路径。

### 4.8 收尾：锁释放与指标（`finally`）

`refresh` 把主流程交给 `_refresh_data` 之后，自己只保留收尾；无论主流程以何种方式结束，`finally` 中都会执行两步：

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
        result = 'Redis Error'
```

**收尾失败为什么用赋值而不是 `return`**：`finally` 里的 `return` 有两个副作用——它会把 `KeyboardInterrupt` / `SystemExit` 这类 `BaseException` **一并吞掉**（`except Exception` 挡不住它们），使 worker 收到中断信号后仍要把这个任务跑完；它还会覆盖掉已经算出来的返回值。改成赋值后语义收窄为"收尾失败时以 `'Redis Error'` 覆盖结果"，中断信号能正常传出。代价是静态检查会提示 `result` 可能未绑定——那条路径上异常会继续向上抛，`return result` 不会被执行。

**为什么释放 `queue` 锁放在 `finally` 而不是成功路径**：无论成功、业务失败还是异常，任务都已经离开队列，排队锁必须释放，否则该用户会被"锁"住长达 `QUEUE_LOCK_TTL`（默认 4 小时）不被重新派发。**锁的语义是"在途"，不是"成功"。**

> 这一条**同样适用于 `AcquireLockFailed`**：抢不到 `user` 锁说明另一个 worker 正在处理该用户，本次任务什么都没做就结束了，但消息确实已被消费。`queue` 锁的语义是"该用户有一条消息在队列中/被消费中"——任务既然被消费，标记就该清除，让调度侧在下一轮重新派发。抢锁失败同时计入 `celery:daily:error`，即**算作失败**。

**指标键**分两组，period 口径一致（annual / monthly / daily:total）：

| 组 | 键前缀 | 含义 | 写入方 |
| --- | --- | --- | --- |
| `celery` | `metrics:celery:{period}:{date}` | **任务**处理量（进入任务即计数） | 仅本模块 |
| `http` | `metrics:http:{period}:{date}` | **请求**发起量（请求返回后计数） | 本模块 **+ API 服务中间件** |

> **`http` 组是跨服务共享的命名空间**：`app/middlewares/redis.py` 也会为每个 FastAPI 请求累加同一组键。因此 `metrics:http:*` 反映的是**全站对外调用的总量**，而非本模块单独的量；只有 `metrics:celery:*` 是本模块独有的。

失败数由两个 `daily:error` 键分别记录（任务级 `celery`、请求级 `http`）。这些键**均不设置 TTL**，由 `app/dashboard` 按 period 读取展示，属长期累计计数器。

---

## 五、数据库与数据模型

### 5.1 本模块触及的表

| 表 | 写入方法 | 角色 |
| --- | --- | --- |
| `T_user_base` | `_update_user_base` | 用户基础信息：`username` / `register_time` / `insignias` |
| `T_user_stats` | `_update_user_stats` | 活跃与战斗统计：各模式场次、`activity_level`、`next_refresh_at` |
| `T_user_random` | `_update_user_battles` | PvP 战斗统计：场次、总经验、胜率、场均与各类最高纪录 |
| `T_user_ranked` | `_update_user_battles` | Rank 战斗统计 |
| `T_user_cache` | `_update_user_cache` | UserCache 的重建信号：`is_due` 标记 |
| `T_user_action` | `_update_user_base` | 曾用名留档（**只追加**） |
| `T_user_config` | 仅读取 | 取 `user_level`（0无 1普通 2高级），决定刷新策略 |

即 **6 写 1 读**。

> `T_user_random` 与 `T_user_ranked` 的表结构完全同构（见 [init/mysql/01-schemas/02-user.sql](../init/mysql/01-schemas/02-user.sql)），因此共用一个 `_update_user_battles`，表名由参数传入。该方法以 `user_data is None` 作为跳过条件——`refresh` 传入的是 `user_data['random_stats']` / `['ranked_stats']`，二者在**该模式场次为 0 时解析结果即为 `None`**，因此方法直接返回、不执行 UPDATE，**避免用 0 覆盖已有战绩**。

### 5.2 `next_refresh_at`：跨服务契约

`T_user_stats.next_refresh_at` 是本模块与**调度侧**之间的核心契约：

```
本模块                                    调度侧（scripts/account）
  写：NOW() + interval_seconds   ──►   读：next_refresh_at <= NOW() 的用户即为"到期"
```

间隔由 `UserPolicyUtils.user_normal_policy(timestamp, user_level, activity_level, lbt)` 计算：

| 分支 | 条件 | 取值 |
| --- | --- | --- |
| **特殊策略** | `user_level == 2` 且 `activity_level == 1` | 按距上次战斗的差值分档：< 1h → 60s，< 3h → 180s，< 12h → 300s，< 19h → 420s（兜底 600s） |
| **常规策略** | 其余 | 查 `UserPolicy.NORMAL_STRATEGY['{user_level}-{activity_level}']`，缺省 1 天 |

即：**高级用户 + 刚打完战斗**这一最需要近实时数据的组合，会落到分钟级刷新；而普通用户随活跃度下降逐步放宽到小时、天、乃至 90 天（`"0-9"`）。

### 5.3 数据结构

本模块不定义自己的领域模型，直接使用 `shard` 中的 `UserBasicDataDict`（`TypedDict`）在层间传递：

```python
username, is_enabled, is_public,
total_battles, pve_battles, pvp_battles, ranked_battles, rating_battles,
register_time, last_battle_at, karma, insignias,
random_stats, ranked_stats        # 后两者为 BattleStatsDict，无场次时为 None
```

选 `TypedDict` 而非 `dataclass`：这份数据**由 `ParseUtils` 统一构造、被多个模块共享**，且需要能直接透传给 `UPDATE` 语句。`TypedDict` 既保留了静态类型提示，又无需在层间做"模型 ↔ 字典"的转换。

`ParseUtils.user_basic_data` 把接口响应的多种形态归一化成同一结构。它共有 **6 个出口**，**按顺序判定，先命中先返回**：

| # | 条件 | 结果 |
| --- | --- | --- |
| ① | 响应中无 `str(account_id)` 键 | `is_enabled = 0`，其余保持默认值 |
| ② | `user_info` 含 `hidden_profile` | `is_public = 0`，仅 `username` 有效 |
| ③ | `user_info` 不含 `statistics` | `is_enabled = 0`，`username` 仍为 `None`（在赋值之前就返回） |
| ④ | `int(created_at) == 0` | `is_enabled = 0`，`register_time = None` |
| ⑤ | `statistics` 不含 `basic` | 保留 `username` / `register_time`，场次全 0 |
| ⑥ | 其余 | 全字段有效，并派生 `random_stats` / `ranked_stats` |

几个细节：

- ① 与 ③ 都是 `is_enabled = 0`，且都**不带** `username`（③ 在给 `username` 赋值之前就返回了）；真正保留了 `username` 的是 ④ 与 ⑤。④ 针对的是"接口返回了 0 作为注册时间"这一异常值；
- `username = user_info['name']` 与 `int(user_info['created_at'])` **不做兜底**，缺失会抛 `KeyError`——这两个关键字段缺失应判定为接口返回值异常，交由上层捕获并计入异常日志，而不是静默降级；
- `total_battles` 取自 `statistics.basic.leveling_points`，并对中国服**主播体验账号**做 `>= 1_000_000` 时减去偏移量的处理；
- `rating_battles` **仅在 `region == 'ru'` 时计算**，为 `rating_solo` 与 `rating_div` 两个模式场次之和；
- `insignias` 由 `StringUtils.insignias_encode(user_info.get('dog_tag'))` 编码为 `texture-symbol-border-bg-color-bg` 形式的字符串，字段不全时返回 `None`；
- `random_stats` / `ranked_stats` 仅在对应场次 `> 0` 时派生，这同时也是**除零保护**——场均类字段全部由 `场次` 做除数。

### 5.4 Redis 键

| 键 | 加/删方 | TTL | 用途 |
| --- | --- | --- | --- |
| `token:ac:{uid}` | 其它服务写 / 本模块只读 | — | 该用户绑定的 access token，拼进请求 URL |
| `refresh_lock:queue:{uid}` | 调度侧加 / **本模块删** | `QUEUE_LOCK_TTL`（默认 14400s） | 在途用户不被重复派发 |
| `refresh_lock:user:{uid}` | 本模块自加自删 | 硬编码 60s | 防止同一用户被并发处理 |
| `metrics:celery:*` / `metrics:http:*` | 本模块写 | 长期（无 TTL） | 吞吐与错误率统计 |

---

## 六、与其它模块的协作

```
scripts/account（调度侧）                        tasks（本模块）
  扫描 T_user_stats
  next_refresh_at <= NOW()
  排除 queue 锁仍存在的用户
        │
        │  send_task(name='user_refresh', args=[{'uid': id}])
        │  成功后 set refresh_lock:queue:{uid} = 1  (nx=True, TTL 4h)
        ▼
   RabbitMQ  refresh_queue  ──────────────►  Celery worker
                                                   │
                                                   │ UserRefresher.refresh → 6 表事务
                                                   ▼
                                              MySQL（T_user_*）
                                                   │
                                                   ├─► next_refresh_at     → 回到调度侧，闭环
                                                   └─► T_user_cache.is_due → UserCache 服务
```

- **上游**：`scripts/account` 是唯一的生产者，本模块不感知它如何选出待刷新用户；
- **下游**：`T_user_cache.is_due` 是 **UserCache 服务**（`scripts/cache`，容器 `backend-cache`）重建用户船只缓存的触发信号——它以 `WHERE is_due = 1 LIMIT MAX_REFRESH_BATCH` 取待办用户，处理完再把 `is_due` 置 `FALSE`。`T_user_stats` 的各模式场次也被 Recent 等模块作为数据源读取；
- **旁路**：`tests/send_tasks.py` 可在本地手动投递一个任务，用于开发调试：

  ```bash
  python tests/send_tasks.py -i 7000005269
  ```

  它自建一个只发不收的 Celery 生产者，不读取 `PROXY_CONFIG` 等业务配置，因此**不受本模块 settings 的校验与副作用影响**。

---

## 七、关键设计与边界处理

| 设计点 | 处理方式 | 目的 |
| --- | --- | --- |
| **三层去重** | `next_refresh_at` → `queue` 锁 → `user` 锁 | 分别挡住"已完成 / 在途 / 同时"，覆盖全部重复成因 |
| **锁的归属跨服务** | `queue` 锁调度侧加、执行侧删 | 锁的语义是"在途"，而非"成功" |
| **抢锁失败也删 `queue` 锁** | `AcquireLockFailed` 同样走 `finally` | 消息已被消费，让调度侧下一轮重新派发 |
| **两个 Redis DB** | 业务与指标用 DB n，`queue` 锁删除用 DB n+1 | 避免不同用途的键混在同一空间 |
| **连接池** | `PooledDB(maxconnections=4)`、`autocommit=False` | worker 长驻且并发，避免每任务建连；且强制显式事务 |
| **只消费指定队列** | `-Q refresh_queue` + `task_routes` | 与其它服务的队列隔离，互不影响 |
| **不启用 Celery 重试** | 异常转字符串返回 | 周期可再取，避免重试放大故障面 |
| **不落盘任务结果** | `backend="rpc://"` | 状态由 `next_refresh_at` 表达，无需结果后端 |
| **404 视为有效结果** | 返回 `{}`，解析层置 `is_enabled=0` | 账号注销不是故障，不应反复重试 |
| **错误编码为字符串** | `_fetch_data` 返回 `'ERROR_X'` / `'HTTP_STATUS_X'` | 调用链保持扁平，`isinstance(x, str)` 即可分流 |
| **时间戳只取一次** | `current_timestamp` 在流程开头固定 | 保证同一次刷新内的所有时间推断基准一致 |
| **关联行缺失前置拦截** | `LEFT JOIN` 的 NULL → `'DataIntegrityError'` | 把后续的 `TypeError` 变成可归因的业务结果 |
| **不负责建号** | `T_user_base` 无行 → `'UserNotInDB'` | 建档职责归属其它服务，本模块只更新 |
| **无数据不覆盖** | `random_stats` / `ranked_stats` 为 `None` 时跳过 UPDATE | 防止用 0 覆盖已有战绩 |
| **`is_due` 单向置位** | 更新时带 `AND is_due = FALSE` | 不覆盖下游尚未消费的待刷新标记 |
| **无效账号自动摘除** | `next_refresh_at = NULL` | 从此不再被调度侧选中 |
| **曾用名留档** | 改名时向 `T_user_action` 追加**旧名** | 只追加不更新，保留完整改名历史 |
| **`T_user_base` 不随注销清空** | `is_enabled=0` 时不更新该表 | 保留历史存档 |
| **异常不落盘（syncer 层）** | 返回异常类名，不写异常文件 | 批量 DB 故障时避免日志风暴 |
| **关键字段缺失即抛** | `name` / `created_at` 不做兜底 | 接口返回值异常应当暴露，而非静默降级 |
| **提前失败不重试** | 参数非法 / 接口失败均直接返回字符串 | 归因清晰，交由下一个刷新周期自然重试 |
| **收尾不用 `return`** | `finally` 中只给 `result` 赋值 | 不吞 `BaseException`，也不覆盖主流程的结果 |
| **连接显式归还** | `with db_pool.connection() as conn` | 不依赖 `__del__` 回收，连接池不会被耗尽 |

---

## 八、配置与部署

### 8.1 本模块的配置项

| 配置 | 来源 | 说明 |
| --- | --- | --- |
| `RABBITMQ_HOST` / `RABBITMQ_DEFAULT_USER` / `RABBITMQ_DEFAULT_PASS` | 环境变量 | Broker 连接（`pyamqp://`） |
| `MYSQL_*` | 环境变量 | 连接池参数，`autocommit` 由代码固定为 `False` |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` / `REDIS_DATABASE` | 环境变量 | `REDIS_DATABASE + 1` 用作 `queue` 锁库 |
| `REGION` | `data/json/init_marker.json` | 决定 `Endpoints.vortex_api` 的域名与 `rating_battles` 是否计算 |
| `PROXY_CONFIG` | `data/json/proxy_strategy.json` | `(mode, points)` 二元组；文件缺失/解析失败、或键缺失时，**逐键回退为 `('default', [])`** |
| `SSL_CA_BUNDLE` | 环境变量 | 俄服证书校验；未设置时不改变 `session.verify` |
| `REQUEST_TIMEOUT` | `data/json/services_config.json` 的 `Celery` 段 | 单次请求超时（秒），缺省 `5` |
| 异常日志标识 | 代码常量 `ServicesName.CELERY` | `exception_writer` 的 `client_id`（本模块无 `CLIENT_NAME` 常量） |

**`PROXY_CONFIG` 的 `mode` 语义**（`Endpoints.vortex_api`）：

| `mode` | 实际请求地址 |
| --- | --- |
| `'direct'` | `points[0]`（本地直连入口） |
| `'proxy'` | 从 `points + [官方 vortex 域名]` 中随机选一个 |
| `'default'`，或 `points` 为空 | `REGION` 对应的官方 vortex 域名 |

本模块在 `data/json/services_config.json` 中只有 `Celery` 一个段，且只放 `REQUEST_TIMEOUT`：该文件的其它段服务于常驻轮询型服务，放的是"刷新间隔"这类需要动态调整的参数；而刷新的节奏完全由调度侧的 `next_refresh_at` 决定，worker 的并发则通过命令行参数调整。

本模块**没有 `LOG_LEVEL` 一类的日志配置**：它不自建 `logger`，日志级别由 Celery 的 `--loglevel` 决定。

### 8.2 启动与目录约定

同其它服务一致：`settings.py` 以 `PLATFORM` 环境变量是否存在且以 `KokomiAPI` 开头来判定生产/开发环境（生产用 `env.prod`，开发加载 `env.dev`），并以项目根目录下是否存在 `README.md` 校验工作目录，不满足则直接 `sys.exit(1)`——**必须从项目根目录启动**。

> `env.dev` 与 `env.prod` 中都写有 `PLATFORM`：生产环境下 Docker Compose 已通过 `env_file` 注入该变量，因此走 `env.prod` 分支；开发环境下 shell 中通常没有该变量，于是加载 `env.dev`。两者不冲突。

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

> **与其它服务的差异**：`season` / `scripts/account` 等挂载了 `./data`，而本服务**只挂载 `./logs`**。`data/json/init_marker.json` 与 `data/json/proxy_strategy.json` 通过镜像构建时的 `COPY . .` 固化在镜像内。因此**修改 `PROXY_CONFIG` 或 `REGION` 后必须重建镜像**才能生效，改宿主机上的 `data/` 目录不会影响已在运行的 Celery 容器。

---

## 九、已知约束

| 约束 | 位置 | 说明 |
| --- | --- | --- |
| 收尾失败会覆盖结果 | `refresher.UserRefresher.refresh` | 一旦 Redis 清理/上报抛异常，返回值被替换为 `'Redis Error'`，**即使刷新本身已成功**。此时真实结果已写入数据库，仅返回值失真。已不使用 `return`，因此不会吞掉 `KeyboardInterrupt` 等 `BaseException` |
| `result` 可能被静态检查判为未绑定 | `refresher.UserRefresher.refresh` | 异常路径下 `result` 未赋值，但该路径会继续抛异常，不会执行 `return result` |
| `celery:error` 的口径含接口层失败 | `refresher.UserRefresher._refresh_data` | 接口层失败同时计入 `http:daily:error` 与 `celery:daily:error`，两个 `daily:error` 在此处口径重合 |
| `http:total` 含失败的请求 | `refresher.UserRefresher._refresh_data` | 计数发生在判断返回值之前，故它是"发起量"而非"成功量" |
| `http` 指标为全站共享 | `metrics:http:*` | 与 API 中间件共用命名空间，无法单独反映本模块的对外调用量 |
| `user` 锁 TTL 硬编码 60s | `shard.db.distributed_lock` | 依据是"任务理论上不存在超过 20s 的可能"；若单任务耗时真的超过 60s，锁会提前失效并允许并发进入 |
| `queue` 锁仅在入队成功后加 | `scripts/account/worker.py` | `send_task` 失败时不会加锁，该用户本轮不会被重试，需等下一轮调度 |
| 不负责建号 | `syncer.UserStatsSyncer.refresh` | `T_user_base` 无行即返回 `'UserNotInDB'`，建档由其它服务的插入流程负责 |
| 无结果持久化 | `backend="rpc://"` | 任务返回值只在 worker 日志中可见，无法事后回查 |
| 账号 ID 校验不排除布尔值 | `main.task_update_user_data` | `isinstance(True, int)` 为真，但 `True` 不命中任何真实用户，无实际危害 |
| `PROXY_CONFIG` 改动需重建镜像 | `docker-compose.yml` | 容器未挂载 `./data`，配置文件固化在镜像内 |

---

## 十、相关文件

| 文件 | 说明 |
| --- | --- |
| [init/mysql/01-schemas/02-user.sql](../init/mysql/01-schemas/02-user.sql) | 本模块触及的 7 张用户表结构 |
| [shard/contracts.py](../shard/contracts.py) | `CommonConfig.REFRESH_TASK_NAME` / `REFRESH_QUEUE_NAME`、`RedisKeys` 键名、`Endpoints.vortex_api` |
| [shard/game/user.py](../shard/game/user.py) | `UserPolicy` 策略表、`user_activity_level` / `user_normal_policy` / `user_hidden_policy` |
| [shard/utils/data.py](../shard/utils/data.py) | `UserBasicDataDict`、`user_basic_data` 归一化、`StringUtils.token_decode` |
| [shard/db/mysql.py](../shard/db/mysql.py) | `MySQLOPS.transaction`（事务上下文管理器） |
| [shard/db/redis.py](../shard/db/redis.py) | `distributed_lock`（第三层 `user` 锁） |
| [shard/logger.py](../shard/logger.py) | `exception_writer`（异常摘要 + 详情落盘） |
| [scripts/account/worker.py](../scripts/account/worker.py) | 调度侧的筛选、投递与 `queue` 锁加锁 |
| [scripts/cache/db_ops.py](../scripts/cache/db_ops.py) | `is_due` 的下游消费方 |
| [tests/send_tasks.py](../tests/send_tasks.py) | 本地手动投递任务 |
| [docs/deploy/dev-full.md](../docs/deploy/dev-full.md) | 开发环境启动命令（含 `-P solo`） |
