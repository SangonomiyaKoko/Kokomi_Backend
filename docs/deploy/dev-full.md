# 开发环境（完整模式）部署步骤

> 适用于 Windows/Linux 环境

在本地搭建一个小规模用户的测试环境，用于测试相关代码和接口

## 外部依赖

需要提前部署好在本地的服务： 
- MySQL 
- Redis 
- RabbitMQ

## 项目配置

复制一份文件 `env.example` 并重命名为 `env.dev`

```bash
# Linux:

# 复制模板文件
cp env.example env.dev
# 使用 vim 编辑配置
vim env.dev

# vim 指令
# i   - 进去 INSERT 模式
# Esc - 退出 INSERT 模式
# :wq - 写入文件并退出
```

> 仅需配置带 ★ 的配置项即可

```conf
PLATFORM="KokomiAPI-01"    # 标识符
LOG_LEVEL="debug"          # ★ log 输出级别
DEV_MODE=0                 # ★

SSL_CA_BUNDLE=""
API_ROOT_TOKEN="root"      # ★ 默认 Root 用户的 Token
API_USER_TOKEN="user"      # ★ 默认 User 用户的 Token

SQLITE_DIR=""              # 不填则按默认路径

MYSQL_HOST="localhost"
MYSQL_PORT=3306
MYSQL_ROOT_PASSWORD=""     # ★ 
MYSQL_USER=""              # ★ 也可都填root及root密码
MYSQL_PASSWORD=""          # ★ 
MYSQL_DATABASE="wows"

REDIS_HOST="localhost"
REDIS_PORT=6379
REDIS_PASSWORD=""          # ★ 
REDIS_DATABASE=0

RABBITMQ_HOST="localhost"
RABBITMQ_DEFAULT_USER=""   # ★ 
RABBITMQ_DEFAULT_PASS=""   # ★ 
```

## 初始化

```bash
# 执行项目初始化脚本
# 参数1 region: 可选值 [asia, eu, na, ru, cn]
# 参数2 location: 服务器的物理地址，本地测试随便填
python init/setup.py -r <region> -l <location>

# 执行数据库初始化脚本
python init/rebuild_db.py

# 写入船只基本数据
python init/scripts/insert_ship.py
```

### 运行代码

```bash
# 加载本地测试用户集，请按照以下顺序启动服务
# 建议每步执行完成再执行下一个

# 通过读取当前赛季工会战排名，获取到数百个工会ID
python -m season.main

# 加载用户集（通过读取工会ID下的用户列表）
python -m scripts.member.main

# 将需要更新的用户 id 发送至 MQ
python -m scripts.account.main

# 启动 Celery 消费者
celery --app tasks.main:celery_app worker -Q refresh_queue -P solo --loglevel=info --concurrency=1

# 读取用户的缓存数据
python -m scripts.cache.main

# 统计船只的服务器玩家数据
python -m scripts.stats.main

# 运行 API 服务
uvicorn app.main:app --host 0.0.0.0 --port 8000
```