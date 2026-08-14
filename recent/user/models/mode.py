from __future__ import annotations

from enum import Enum


class BattleMode(Enum):
    """战斗模式（对应 ship_index_map / ship_index_data 的 ship_mode 列）

    注：clan 模式因 wg/lesta 接口差异，由后续单独实现，此处暂不处理。
    """
    PVP = 1
    RANK = 2
    CLAN = 3

    def __str__(self) -> str:
        return self.name


class DataType(Enum):
    """数据类型（对应 ship_index_data 的 data_type_1/2/3 列）"""
    SOLO = 1
    DIV2 = 2
    DIV3 = 3

    def __str__(self) -> str:
        return self.name

class UpdateStrategy(Enum):
    """根据本地数据库确定更新时的操作"""
    NORMAL = 1            # 正常更新流程
    NEW_USER = 2          # 本地没有 summary / latest_index 数据，需要全量初始化
    MISSING_SUMMARY = 3   # 今日和昨日的 summary 均缺失（服务崩溃）或均为隐藏战绩，需同时更新昨日+今日 summary

    def __str__(self) -> str:
        return self.name

BASE_UPDATE_MODES = {BattleMode.PVP, BattleMode.RANK}
FULL_UPDATE_MODES = {BattleMode.PVP, BattleMode.RANK, BattleMode.CLAN}