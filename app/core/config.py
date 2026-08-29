import os
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from datetime import datetime, timezone


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
    """RabbitMQ 配置"""
    root: str
    user: str
    manager: str

@dataclass(frozen=True)
class RuntimeConfig:
    SECURITY: SecurityConfig
    MYSQL: MySQLConfig
    REDIS: RedisConfig
    RABBITMQ: RabbitMQConfig

@dataclass(frozen=True)
class EndpointsConfig:
    VORTEX_API: list[str]
    CLAN_API: str
    OFFICIAL_API: Optional[str]

@dataclass(frozen=True)
class ConstantsConfig:
    SERVICE_LIST: list[str]
    USER_INIT_TABLE_LIST: list[str]
    CLAN_INIT_TABLE_LIST: list[str]
    SHIP_INIT_TABLE_LIST: list[str]
    METRIC_RATING_THRESHOLDS: dict[list]

@dataclass(frozen=True)
class PolicyConfig:
    USER_ACTIVITY_THRESHOLDS: list[list]
    USER_ACTIVITY_STRATEGY: dict[str, int]
    SPECIAL_ACTIVITY_STRATEGY: list[list]

class EnvConfig:
    PLATFORM: Optional[str] = None
    DEV_MODE: Optional[bool] = False
    REGION: Optional[str] = None
    TIMEZONE: Optional[int] = 0
    LOCALTION: Optional[str] = None
    INIT_TIME : Optional[int] = None
    UID_RULE: Optional[list] = None
    SSL_CA_BUNDLE: Optional[str] = None

    ROOT_DIR: Path = Path('/app')
    LOG_DIR: Path = Path('/app/logs')
    DATA_DIR: Path = Path('/app/data')
    INIT_DIR: Path = Path('/app/init')
    SQLITE_DIR: Path = Path('/app/data/db')
    SQLITE_SQL: str = None

    _config: Optional[RuntimeConfig] = None
    _policy: Optional[PolicyConfig] = None
    _endpoints: Optional[EndpointsConfig] = None
    _constants: Optional[ConstantsConfig] = None

    @classmethod
    def _require_env(cls, key: str, default: Optional[str] = None) -> str:
        """获取环境变量（不存在会报错）"""
        value = os.getenv(key, default)
        if value is None:
            raise ValueError(f"Missing required environment variable: {key}")
        return value

    @classmethod
    def _require_env_optional(cls, key: str, default: Optional[str] = None) -> str:
        """获取环境变量（可选）"""
        return os.getenv(key, default)

    @classmethod
    def _load_json_file(cls, file_path: Path) -> dict:
        """加载运行必要的 JSON 文件数据"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {file_path}: {e}")

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
        cls.SQLITE_DIR = Path(custom_sqlite_dir) if custom_sqlite_dir else cls.DATA_DIR / 'db'

        sql_file_path = cls.DATA_DIR / 'const/recent.sql'
        with open(sql_file_path, "r", encoding="utf-8") as f:
            cls.SQLITE_SQL = f.read()
        
    @classmethod
    def _init_region(cls):
        file_path = cls.DATA_DIR / 'json/init_marker.json'
        data = cls._load_json_file(file_path)
        
        if 'region' not in data:
            raise ValueError(f"Missing 'region' key in {file_path}")
        
        cls.REGION = data.get('region')
        cls.TIMEZONE = data.get("timezone", 0)
        cls.LOCATION = data.get('location', 'N/A')
        init_timestamp = data.get('init_time')
        cls.INIT_TIME = datetime.fromtimestamp(init_timestamp, tz=timezone.utc).strftime("%Y-%m-%d") if init_timestamp else "N/A"

        if cls.REGION not in ['asia', 'eu', 'na', 'ru', 'cn']:
            raise ValueError(f"Invalid region value: {cls.REGION}")

    @classmethod
    def _init_endpoints(cls):
        file_path = cls.DATA_DIR / 'const/endpoints.json'
        data = cls._load_json_file(file_path)
        
        if cls.REGION not in data:
            raise ValueError(f"Region '{cls.REGION}' not found in endpoints config")
        
        region_data = data[cls.REGION]
        
        required_fields = ['vortex_api', 'clan_api', 'uid_rule']
        for field in required_fields:
            if field not in region_data:
                raise ValueError(
                    f"Missing required field '{field}' in endpoints config"
                )
        
        cls._endpoints = EndpointsConfig(
            VORTEX_API=region_data['vortex_api'],
            CLAN_API=region_data['clan_api'],
            OFFICIAL_API=region_data.get('official_api')
        )
        
        cls.UID_RULE = region_data['uid_rule']

    @classmethod
    def _init_constants(cls):
        file_path = cls.DATA_DIR / 'const/constants.json'
        data = cls._load_json_file(file_path)
        
        cls._constants = ConstantsConfig(
            SERVICE_LIST=data['SERVICE_LIST'],
            USER_INIT_TABLE_LIST=data['USER_INIT_TABLE_LIST'],
            CLAN_INIT_TABLE_LIST=data['CLAN_INIT_TABLE_LIST'],
            SHIP_INIT_TABLE_LIST=data['SHIP_INIT_TABLE_LIST'],
            METRIC_RATING_THRESHOLDS=data['METRIC_RATING_THRESHOLDS']
        )

    @classmethod
    def _init_policy(cls):
        file_path = cls.DATA_DIR / 'const/policy.json'
        data = cls._load_json_file(file_path)
        
        cls._policy = PolicyConfig(
            USER_ACTIVITY_THRESHOLDS=data['USER_ACTIVITY_THRESHOLDS'],
            USER_ACTIVITY_STRATEGY=data['USER_ACTIVITY_STRATEGY'],
            SPECIAL_ACTIVITY_STRATEGY=data['SPECIAL_ACTIVITY_STRATEGY']
        )

    @classmethod
    def init(cls, root_path: str) -> str:
        """
        初始化所有配置
        返回当前使用的环境文件名 (`env.dev` 或 `env.prod`)
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
        # 加载运行必要的数据文件
        cls._init_policy()
        cls._init_endpoints()
        cls._init_constants()

        return env_file

    @classmethod
    def get_config(cls) -> RuntimeConfig:
        """获取运行时配置，如果未初始化则抛出异常"""
        if cls._config is None:
            raise RuntimeError("Configuration not initialized")
        return cls._config

    @classmethod
    def get_policy(cls) -> PolicyConfig:
        if cls._policy is None:
            raise RuntimeError("Endpoints not initialized. Call EnvConfig.init() first")
        return cls._policy

    @classmethod
    def get_endpoints(cls) -> EndpointsConfig:
        """获取端点配置"""
        if cls._endpoints is None:
            raise RuntimeError("Endpoints not initialized. Call EnvConfig.init() first")
        return cls._endpoints

    @classmethod
    def get_constants(cls) -> ConstantsConfig:
        """获取常量配置"""
        if cls._constants is None:
            raise RuntimeError("Constants not initialized. Call EnvConfig.init() first")
        return cls._constants