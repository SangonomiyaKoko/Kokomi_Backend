# -*- coding: utf-8 -*-

from pydantic_settings import BaseSettings

class LoadConfig(BaseSettings):
    MYSQL_HOST: str
    MYSQL_PORT: int
    MYSQL_USERNAME: str
    MYSQL_PASSWORD: str

    MAIN_DB: str
    
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_PASSWORD: str
    
    RABBITMQ_HOST: str
    RABBITMQ_USERNAME: str
    RABBITMQ_PASSWORD: str

    ROOT_API_TOKEN: str
    USER_API_TOKEN: str

    IP_BLACLIST: str
    USER_BLACLIST: str
    CLAN_BLACLIST: str

    WG_API_TOKEN: str
    LESTA_API_TOKEN: str

    class Config:
        env_file = ".env"

class EnvConfig:
    __cache = None

    @classmethod
    def load_config(cls) -> None:
        # 加载config
        config = LoadConfig()
        cls.__cache = config

    @classmethod
    def get_config(cls) -> LoadConfig:
        # 获取config
        return cls.__cache

    @classmethod
    def refresh_config(cls) -> None:
        # 刷新config
        config = LoadConfig()
        cls.__cache = config

def split_config(config_str: str) -> list:
    # Config数据分割
    if not config_str:  # None 或空字符串
        return []
    return config_str.split(":")
