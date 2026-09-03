import os
import sys
import json
from pathlib import Path
from datetime import datetime


CLIENT_NAME = 'Recent'
REFRESH_INTERVAL = 60
DATE_FMT = '%Y-%m-%d %H:%M:%S'
USE_TQDM = sys.stdout.isatty()  # 只有在交互式终端中才使用 tqdm 显示进度条

ROOT_DIR = Path(os.getcwd())
if not (ROOT_DIR / 'README.md').exists():
    # 校验启动路径是否为根目录
    print(
        f"Invalid working directory: {ROOT_DIR}. "
        f"Please start the service from the project root directory."
    )
    exit(1)
LOG_DIR = ROOT_DIR / 'logs'
DATA_DIR = ROOT_DIR / 'data'
SQLITE_DIR = (
    Path(os.getenv("SQLITE_DIR"))
    if os.getenv("SQLITE_DIR")
    else ROOT_DIR / 'data/db'
)   # SQLITE_DIR 未配置则默认使用 ROOT_DIR / 'data/db' 下路径

# 生产环境下的环境变量由 Docker Compose 注入 env.prod，开发环境加载 env.dev
# 在程序中，通过判断环境变量中是否存在 PLATFORM 来判断是否为生产环境
if (
    not os.getenv('PLATFORM') or 
    not os.getenv('PLATFORM').startswith('KokomiAPI')
):
    # 开发环境中关闭代理，避免本地测试中请求外部 API 时被本地环境变量干扰
    os.environ['NO_PROXY'] = '127.0.0.1,localhost'
    from dotenv import load_dotenv
    if not load_dotenv('env.dev'):
        # 开发环境下如果加载 env.dev 失败，直接退出
        print(f"{datetime.now().strftime(DATE_FMT)} [ERROR] Failed to load env.dev configuration")
        exit(1)
    print(f"{datetime.now().strftime(DATE_FMT)} [INIT] Env config loaded: env.dev")
else:
    print(f"{datetime.now().strftime(DATE_FMT)} [INIT] Env config loaded: env.prod")
    
TIMEOUT = 5
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")
SSL_CA_BUNDLE = os.getenv("SSL_CA_BUNDLE")

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER", "username"),
    "password": os.getenv("MYSQL_PASSWORD", "password"),
    "database": os.getenv("MYSQL_DATABASE", "database"),
    "autocommit": False
}
REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", 6379)),
    "db": int(os.getenv("REDIS_DATABASE", 0)),
    "password": os.getenv("REDIS_PASSWORD"),
    "decode_responses": True
}

# 加载配置文件或者数据文件
# 因为是运行必要数据，故不处理可能存在的文件加载异常
# 确保在文件缺失或格式错误时能直接 raise 并停止服务
file_path = DATA_DIR / 'json/init_marker.json'
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)
    REGION: str = data['region']
    TOKEN: str = data['token']
    TIMEZONE: int = data['timezone']
file_path = DATA_DIR / 'const/endpoints.json'
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)
    VORTEX_API: list = data[REGION]['vortex_api']
    OFFICIAL_API: str = data[REGION]['official_api']
file_path = DATA_DIR / 'const/policy.json'
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)
    SERVER_RESET_OFFSET: int = data['SERVER_RESET_OFFSET']
    USER_INACTIVE_DAYS: int = data['USER_INACTIVE_DAYS']
    USER_NO_BATTLE_DAYS: int = data['USER_NO_BATTLE_DAYS']
    USER_HIDDEN_PROFILE_DAYS: int = data['USER_HIDDEN_PROFILE_DAYS']
    USER_REFRESH_TIMEOUT: dict = data['USER_REFRESH_TIMEOUT']
    USER_ACTIVITY_THRESHOLDS: list = data['USER_ACTIVITY_THRESHOLDS']
    USER_ACTIVITY_STRATEGY: dict = data['USER_ACTIVITY_STRATEGY']
    SPECIAL_ACTIVITY_STRATEGY: list = data['SPECIAL_ACTIVITY_STRATEGY']
file_path = DATA_DIR / 'const/recent.sql'
with open(file_path, "r", encoding="utf-8") as f:
    CREATE_SQL = f.read()

print(f"{datetime.now().strftime(DATE_FMT)} [INIT] Configuration data loading complete")
