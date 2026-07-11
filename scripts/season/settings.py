import os
import sys
import json
from pathlib import Path
from datetime import datetime


CLIENT_NAME = 'ClanSeason'
REFRESH_INTERVAL = 60
DATE_FMT = '%Y-%m-%d %H:%M:%S'
USE_TQDM = sys.stdout.isatty()  # 只有在交互式终端中才使用 tqdm 显示进度条

ROOT_DIR = Path(os.getcwd())
LOG_DIR = ROOT_DIR / 'logs'
DATA_DIR = ROOT_DIR / 'data'

# 生产环境下的环境变量由 Docker Compose 注入 env.prod，开发环境下则通过加载 env.dev 文件来设置
if not os.getenv('PLATFORM') or not os.getenv('PLATFORM').startswith('KokomiAPI'):
    # 关闭代理，避免请求外部API时被本地环境变量干扰
    os.environ['NO_PROXY'] = '127.0.0.1,localhost'
    from dotenv import load_dotenv
    if not load_dotenv('env.dev'):
        # 开发环境下如果加载env.dev失败，直接退出程序
        print(f"{datetime.now().strftime(DATE_FMT)} [ERROR] Failed to load env.dev configuration")
        exit(1)
    print(f"{datetime.now().strftime(DATE_FMT)} [INIT] Env config loaded: env.dev")
else:
    print(f"{datetime.now().strftime(DATE_FMT)} [INIT] Env config loaded: env.prod")

SSL_CA_BUNDLE = os.getenv("SSL_CA_BUNDLE")
LOG_LEVEL = os.getenv("LOG_LEVEL")
MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": os.getenv("MYSQL_DATABASE"),
    "autocommit": False  # 关闭自动提交，改为手动控制事务，以便在发生异常时能正确回滚，保证数据一致性
}
REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST"),
    "port": int(os.getenv("REDIS_PORT", 6379)),
    "db": int(os.getenv("REDIS_DATABASE", 0)),
    "password": os.getenv("REDIS_PASSWORD"),
    "decode_responses": True
}

# 因为是运行必要数据，故不处理可能存在的文件加载异常
# 确保在文件缺失或格式错误时能直接raise并停止服务，避免进入不稳定状态
file_path = DATA_DIR / 'json/init_marker.json'
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)
    REGION: str = data['region']
file_path = DATA_DIR / 'const/endpoints.json'
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)
    CLAN_API: str = data[REGION]['clan_api']
file_path = DATA_DIR / 'const/constants.json'
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)
    CLAN_REALM_MAP: list = data['CLAN_REALM_MAP']
    CLAN_LEAGUE_LIST: list = data['CLAN_LEAGUE_LIST']
    CLAN_BATTLE_WINDOWS: list = data['CLAN_BATTLE_WINDOWS']
    CLAN_INIT_TABLE_LIST: list = data['CLAN_INIT_TABLE_LIST']
    METRIC_RATING_THRESHOLDS: list = data['METRIC_RATING_THRESHOLDS']
print(f"{datetime.now().strftime(DATE_FMT)} [INIT] Configuration data loading complete")