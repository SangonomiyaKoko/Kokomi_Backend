import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from datetime import datetime, timezone

from shard import FileUtils


@dataclass(frozen=True)
class MySQLConfig:
    """MySQL 数据库配置"""
    host: str
    port: int
    user: str
    password: str
    db: str

@dataclass(frozen=True)
class RedisConfig:
    """Redis 配置"""
    host: str
    port: int
    password: str
    db: str

@dataclass(frozen=True)
class RabbitMQConfig:
    """RabbitMQ 配置"""
    host: str
    username: str
    password: str

@dataclass(frozen=True)
class SecurityConfig:
    """API 权限令牌配置"""
    root: str
    user: str
    manager: str

@dataclass(frozen=True)
class RuntimeConfig:
    SECURITY: SecurityConfig
    MYSQL: MySQLConfig
    REDIS: RedisConfig
    RABBITMQ: RabbitMQConfig

class EnvConfig:
    PLATFORM: Optional[str] = None
    DEV_MODE: Optional[bool] = False
    REGION: Optional[str] = None
    TIMEZONE: Optional[int] = 0
    LOCATION: Optional[str] = None
    INIT_TIME : Optional[int] = None
    SSL_CA_BUNDLE: Optional[str] = None

    ROOT_DIR: Path = Path('/app')
    LOG_DIR: Path = Path('/app/logs')
    DATA_DIR: Path = Path('/app/data')
    INIT_DIR: Path = Path('/app/init')
    SQLITE_DIR: Path = Path('/app/data/local')

    # Vortex 接口代理策略，格式为 (mode, points)，交由 shard.Endpoints 解析
    PROXY_CONFIG: tuple = ('default', [])

    _config: Optional[RuntimeConfig] = None

    @classmethod
    def _require_env(
        cls, key: str, default: Optional[str] = None
    ) -> str:
        """获取环境变量（不存在会报错）"""
        value = os.getenv(key, default)
        if value is None:
            raise ValueError(f"Missing required environment variable: {key}")
        return value

    @classmethod
    def _require_env_optional(
        cls, key: str, default: Optional[str] = None
    ) -> str:
        """获取环境变量（可选）"""
        return os.getenv(key, default)

    @classmethod
    def _require_json_file(
        cls, file_path: Path
    ) -> dict:
        """加载运行必要的 JSON 文件数据，文件缺失或解析失败时抛错"""
        data = FileUtils.load_json(fp=file_path, default=None)
        if data is None:
            raise FileNotFoundError(
                f"Configuration file not found or invalid: {file_path}"
            )
        return data

    @classmethod
    def _load_env_file(cls) -> str:
        """加载环境变量文件，返回环境文件名"""
        # 判断是否在 Docker 环境：PLATFORM 环境变量由 Docker 容器注入
        if os.getenv('PLATFORM') is None:
            # Windows 本地开发，需要手动从文件加载环境变量
            from dotenv import load_dotenv
            if not load_dotenv('env.dev'):
                raise RuntimeError("Failed to load env.dev file")
            return 'env.dev'
        # Docker 容器环境，环境变量已通过容器编排工具注入
        # 直接使用 os.getenv() 即可读取，无需加载文件
        return 'env.prod'

    @classmethod
    def _init_runtime_config(cls):
        """初始化运行时配置"""
        cls.PLATFORM=cls._require_env('PLATFORM')
        cls.DEV_MODE=True if cls._require_env('DEV_MODE') == '1' else False
        cls.SSL_CA_BUNDLE=cls._require_env_optional('SSL_CA_BUNDLE')

        cls._config = RuntimeConfig(
            SECURITY=SecurityConfig(
                root=cls._require_env("API_ROOT_TOKEN"),
                user=cls._require_env("API_USER_TOKEN"),
                manager=cls._require_env("API_MANAGER_TOKEN")
            ),
            MYSQL=MySQLConfig(
                host=cls._require_env("MYSQL_HOST"),
                port=int(cls._require_env("MYSQL_PORT", "3306")),
                user=cls._require_env("MYSQL_USER"),
                password=cls._require_env("MYSQL_PASSWORD"),
                db=cls._require_env("MYSQL_DATABASE")
            ),
            REDIS=RedisConfig(
                host=cls._require_env("REDIS_HOST"),
                port=int(cls._require_env("REDIS_PORT", "6379")),
                password=cls._require_env("REDIS_PASSWORD"),
                db=int(cls._require_env("REDIS_DATABASE", "0"))
            ),
            RABBITMQ=RabbitMQConfig(
                host=cls._require_env("RABBITMQ_HOST"),
                username=cls._require_env("RABBITMQ_DEFAULT_USER"),
                password=cls._require_env("RABBITMQ_DEFAULT_PASS")
            )
        )

        custom_sqlite_dir = cls._require_env_optional("SQLITE_DIR")
        cls.SQLITE_DIR = Path(custom_sqlite_dir) if custom_sqlite_dir else cls.DATA_DIR / 'local'

    @classmethod
    def _init_region(cls):
        file_path = cls.DATA_DIR / 'json/init_marker.json'
        data = cls._require_json_file(file_path)

        if 'region' not in data:
            raise ValueError(f"Missing 'region' key in {file_path}")

        cls.REGION = data.get('region')
        cls.TIMEZONE = data.get("timezone", 0)
        cls.LOCATION = data.get('location', 'N/A')
        init_timestamp = data.get('init_time')
        cls.INIT_TIME = datetime.fromtimestamp(
            init_timestamp, 
            tz=timezone.utc
        ).strftime("%Y-%m-%d") if init_timestamp else "N/A"

        if cls.REGION not in ['asia', 'eu', 'na', 'ru', 'cn']:
            raise ValueError(f"Invalid region value: {cls.REGION}")

    @classmethod
    def _init_proxy(cls):
        """读取 Vortex 接口代理策略配置"""
        file_path = cls.DATA_DIR / 'json/proxy_strategy.json'
        data = FileUtils.load_json(
            fp=file_path, 
            default={}
        )

        cls.PROXY_CONFIG = (
            data.get('mode', 'default'),
            data.get('points', [])
        )

    @classmethod
    def init(cls, root_path: str) -> str:
        """
        初始化所有配置，返回当前使用的环境文件名 (`env.dev` 或 `env.prod`)
        """
        # 加载文件路径
        cls.ROOT_DIR = Path(root_path)
        cls.LOG_DIR = cls.ROOT_DIR / 'logs'
        cls.DATA_DIR = cls.ROOT_DIR / 'data'
        cls.INIT_DIR = cls.ROOT_DIR / 'init'
        # 加载环境变量文件
        env_file = cls._load_env_file()
        # 初始化运行配置
        cls._init_runtime_config()
        # 读取子节点的区域配置
        cls._init_region()
        # 读取接口代理策略配置
        cls._init_proxy()

        return env_file

    @classmethod
    def get_config(cls) -> RuntimeConfig:
        """获取运行时配置，如果未初始化则抛出异常"""
        if cls._config is None:
            raise RuntimeError("Configuration not initialized")
        return cls._config
