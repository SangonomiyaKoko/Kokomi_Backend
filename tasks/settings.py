import os
import json
from pathlib import Path


CLIENT_NAME = 'Celery'
REQUEST_TIMEOUT = 5

_ROOT_DIR = Path(os.getcwd())
if not (_ROOT_DIR / 'README.md').exists():
    # 以 README.md 文件为标记，校验启动路径是否为根目录
    print(
        f"Invalid working directory: {_ROOT_DIR}. "
        f"Please start the service from the project root directory."
    )
    exit(1)
LOG_DIR = _ROOT_DIR / 'logs'
DATA_DIR = _ROOT_DIR / 'data'

# 生产环境下的环境变量由 Docker Compose 注入 env.prod，开发环境加载 env.dev
# 在程序中，通过判断环境变量中是否存在 PLATFORM 来判断是否为生产环境
_PLATFORM = os.getenv('PLATFORM')
if _PLATFORM is None or not _PLATFORM.startswith('KokomiAPI'):
    # 开发环境中关闭代理，避免本地测试中请求外部 API 时被本地环境变量干扰
    os.environ['NO_PROXY'] = '127.0.0.1,localhost'
    from dotenv import load_dotenv
    if not load_dotenv('env.dev'):
        # 开发环境下如果加载env.dev失败，直接退出程序
        print("[ERROR] Failed to load env.dev")
        exit(1)
    print("[INIT] Env config loaded: env.dev")
else:
    print("[INIT] Env config loaded: env.prod")

LOG_LEVEL = os.getenv("LOG_LEVEL", "debug")
SSL_CA_BUNDLE = os.getenv("SSL_CA_BUNDLE")

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER", "username"),
    "password": os.getenv("MYSQL_PASSWORD", "password"),
    "database": os.getenv("MYSQL_DATABASE", "database")
}
REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", 6379)),
    "db": int(os.getenv("REDIS_DATABASE", 0)),
    "password": os.getenv("REDIS_PASSWORD"),
    "decode_responses": True
}
RABBITMQ_CONFIG = {
    "host": os.getenv("RABBITMQ_HOST", "localhost"),
    "user": os.getenv("RABBITMQ_DEFAULT_USER", "username"),
    "password": os.getenv("RABBITMQ_DEFAULT_PASS", "password")
}

# 加载配置文件或者数据文件
file_path = DATA_DIR / 'json/init_marker.json'
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)
    REGION: str = data['region']

# 加载策略或配置文件
file_path = DATA_DIR / 'json/proxy_strategy.json'
if not file_path.exists():
    PROXY_CONFIG = ('default', [])
else:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    PROXY_CONFIG = (data['mode'], data['points'])

print("[INIT] Configuration data loading complete")