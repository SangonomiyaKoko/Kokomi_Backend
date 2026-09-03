import random
from dataclasses import dataclass
from typing import Optional

from context import UpdateContext
from models import BattleMode, DataType
from settings import (
    REGION, 
    TOKEN, 
    VORTEX_API, 
    OFFICIAL_API
)


@dataclass(frozen=True)
class RequestTarget:
    """单个请求目标"""
    url: str
    mode: Optional[BattleMode] = None  # None 表示 account 基础信息端点
    data_type: Optional[DataType] = None


class EndpointRegistry:
    """模式 → 接口路径的注册表"""

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
        base_url = random.choice(VORTEX_API)
        query = f'?ac={ctx.access_token}' if ctx.access_token else ''

        targets = [
            RequestTarget(url=f'{base_url}/api/accounts/{ctx.account_id}/{query}')
        ]
        for mode in ctx.fetch_modes:
            if mode == BattleMode.CLAN and REGION != 'ru':
                # 只有直营服的 CLAN 模式数据需要通过 OFFICAL_API 接口获取
                targets.append(RequestTarget(
                    url=(
                        f'{OFFICIAL_API}/ships/stats/?application_id={TOKEN}'
                        f'&account_id={ctx.account_id}&extra=clan'
                    ),
                    mode=BattleMode.CLAN,
                    data_type=DataType.DIV2
                ))
            else:
                # 其他模式均通过 VORTEX_API 接口读取数据
                for data_type, path in cls.MODE_PATHS[mode]:
                    targets.append(RequestTarget(
                        url=(
                            f'{base_url}/api/accounts/{ctx.account_id}/ships/'
                            f'{path}/{query}'
                        ),
                        mode=mode,
                        data_type=data_type,
                    ))
        return targets
