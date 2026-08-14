from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from models import BattleMode, DataType, UpdateContext
from settings import VORTEX_API


@dataclass(frozen=True)
class RequestTarget:
    """单个请求目标"""
    url: str
    mode: Optional[BattleMode] = None       # None 表示 account 基础信息端点
    data_type: Optional[DataType] = None


class EndpointRegistry:
    """模式 → 接口路径的注册表（根据变更的模式按需构建请求）"""

    # 模式 → [(DataType, 路径段)]
    MODE_PATHS: dict[BattleMode, list] = {
        BattleMode.PVP: [
            (DataType.SOLO, 'pvp_solo'),
            (DataType.DIV2, 'pvp_div2'),
            (DataType.DIV3, 'pvp_div3')
        ],
        BattleMode.RANK: [
            (DataType.SOLO, 'rank_solo')
        ],
        BattleMode.CLAN: [
            (DataType.SOLO, 'rating_solo'),
            (DataType.DIV2, 'rating_div')
        ]
    }

    @classmethod
    def mode_key(cls, mode: BattleMode, data_type: DataType) -> str:
        """获取 (mode, data_type) 对应的接口路径段，用于解析响应"""
        for dtype, path in cls.MODE_PATHS[mode]:
            if dtype == data_type:
                return path
        raise ValueError(f'Unknown path for {mode} {data_type}')

    @classmethod
    def build_targets(cls, ctx: UpdateContext) -> list[RequestTarget]:
        """构建请求目标：恒有 account 端点 + 各变更模式的 data_type 端点"""
        ac = ctx.redis_client.get(f"token:ac:{ctx.account_id}")
        base_url = random.choice(VORTEX_API)
        query = f'?ac={ac}' if ac else ''

        targets = [
            RequestTarget(url=f'{base_url}/api/accounts/{ctx.account_id}/{query}')
        ]
        for mode in ctx.fetch_modes:
            for data_type, path in cls.MODE_PATHS[mode]:
                targets.append(RequestTarget(
                    url=f'{base_url}/api/accounts/{ctx.account_id}/ships/{path}/{query}',
                    mode=mode,
                    data_type=data_type,
                ))
        return targets
