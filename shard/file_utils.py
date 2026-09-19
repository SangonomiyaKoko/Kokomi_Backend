import json
from pathlib import Path
from typing import Any, Optional
from json import JSONDecodeError


class FileUtils:

    @staticmethod
    def load_json(
        fp: Path, default: Optional[dict] = {}
    ) -> dict:
        """加载 JSON 文件"""
        if not fp.exists():
            return default

        with open(fp, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except JSONDecodeError:
                return default

    @staticmethod
    def load_sql(
        fp: Path, default: Optional[Any] = None
    ) -> Optional[str]:
        """加载数据库初始化 SQL 文件"""
        if not fp.exists():
            return default

        with open(fp, "r", encoding="utf-8") as f:
            return f.read()