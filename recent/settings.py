import os
from pathlib import Path

from shard import FileUtils, ServicesName


# 运行所需相关文件地址
_root_dir = Path(os.getcwd())
if not (_root_dir / 'README.md').exists():
    # 以 README.md 文件为标记，校验启动路径是否为根目录
    print(
        f"Invalid working directory: {_root_dir}. "
        f"Please start the service from the project root directory."
    )
    exit(1)
LOG_DIR = _root_dir / 'logs'
DATA_DIR = _root_dir / 'data'
INIT_DIR = _root_dir / 'init'
SQLITE_DIR = (
    Path(os.getenv("SQLITE_DIR"))
    if os.getenv("SQLITE_DIR")
    else _root_dir / 'data/db'
)   # SQLITE_DIR 未配置则默认使用 _root_dir / 'data/db' 下路径

# 加载环境配置数据
# 生产环境下的环境变量由 Docker Compose 注入 env.prod，开发环境加载 env.dev
# 在程序中，通过判断环境变量中是否存在 PLATFORM 来判断是否为生产环境
ENV_FILE = 'env.dev'
_platform = os.getenv('PLATFORM')
if (
    _platform is None or 
    not _platform.startswith('KokomiAPI')
):
    # 开发环境中关闭代理，避免本地测试中请求外部 API 时被本地环境变量干扰
    os.environ['NO_PROXY'] = '127.0.0.1,localhost'
    from dotenv import load_dotenv
    if not load_dotenv('env.dev'):
        # 开发环境下如果加载 env.dev 失败，直接退出
        print("[ERROR] Failed to load env.dev")
        exit(1)
else:
    ENV_FILE = 'env.prod'

# 中间件连接配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "debug")
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
_data = FileUtils.load_json(
    fp=DATA_DIR / 'json/init_marker.json'
)
TOKEN: str = _data['token']
REGION: str = _data['region']
TIMEZONE: int = _data['timezone']

CREATE_SQL = FileUtils.load_sql(
    fp=INIT_DIR / 'sqlite/recent.sql'
)

# 加载策略或配置文件
_data = FileUtils.load_json(
    fp=DATA_DIR / 'json/services_config.json'
).get(ServicesName.RECENT, {})
MEM_MONITOR = _data.get('MEM_MONITOR', False)
REQUEST_TIMEOUT = _data.get('REQUEST_TIMEOUT', 5)
REFRESH_INTERVAL = _data.get('REFRESH_INTERVAL', 60)
_data = FileUtils.load_json(
    fp=DATA_DIR / 'json/clan_season.json'
)
SEASON_CONFIG = (
    _data.get('start'), 
    _data.get('finish')
)
_data = FileUtils.load_json(
    fp=DATA_DIR / 'json/proxy_strategy.json'
)
PROXY_CONFIG = (
    _data.get('mode', 'default'), 
    _data.get('points', [])
)


__all__ = [
    'LOG_DIR',
    'DATA_DIR',
    'SQLITE_DIR',
    'ENV_FILE',
    'LOG_LEVEL',
    'SSL_CA_BUNDLE',
    'MYSQL_CONFIG',
    'REDIS_CONFIG',
    'TOKEN',
    'REGION',
    'TIMEZONE',
    'CREATE_SQL',
    'SEASON_CONFIG',
    'PROXY_CONFIG',
    'MEM_MONITOR',
    'REQUEST_TIMEOUT',
    'REFRESH_INTERVAL'
]
