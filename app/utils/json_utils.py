import os
import time
import json
import shutil
from typing import Any

from app.core import JSON_FILE_PATH, BACKUP_PATH



class JsonUtils:
    """
    负责读取和写入json文件
    """
    @staticmethod
    def read(filename: str) -> dict:
        """读取json文件数据"""
        file_path = os.path.join(JSON_FILE_PATH, f'{filename}.json')

        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def write(filename: str, data: Any) -> None:
        """刷新json文件数据，写入前备份一份旧数据到备份文件夹内"""
        file_path = os.path.join(JSON_FILE_PATH, f'{filename}.json')
        if os.path.exists(file_path):
            backup_name = f"{filename}_{int(time.time())}.json"
            backup_path = os.path.join(BACKUP_PATH, backup_name)
            shutil.copy2(file_path, backup_path)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
