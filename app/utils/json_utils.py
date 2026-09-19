import json
from pathlib import Path
from typing import Dict, Any

from shard import FileUtils

from app.core import EnvConfig, api_logger


class JsonUtils:
    """负责读取和写入 JSON 文件

    读取能力复用 shard.FileUtils，写入为 API 侧独有实现。
    """

    @staticmethod
    def _fp(filename: str) -> Path:
        """获取 JSON 文件的完整路径"""
        return EnvConfig.DATA_DIR / f"json/{filename}.json"

    @classmethod
    def read(cls, filename: str) -> Dict[str, Any]:
        """从 JSON 文件读取数据，文件不存在或解析失败时返回空字典"""
        file_path = cls._fp(filename)

        if not file_path.exists():
            return {}

        # default 传 None 以区分「文件不存在」与「解析失败」
        data = FileUtils.load_json(fp=file_path, default=None)
        if data is None:
            api_logger.error(f'Json decode error: {filename}.json')
            return {}

        return data

    @classmethod
    def write(cls, filename: str, data: dict) -> None:
        """将数据写入 JSON 文件"""
        file_path = cls._fp(filename)

        # 检查目录是否存在，不存在则抛出异常
        if not file_path.parent.exists():
            raise FileNotFoundError(f"Directory does not exist: {file_path.parent}")

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
