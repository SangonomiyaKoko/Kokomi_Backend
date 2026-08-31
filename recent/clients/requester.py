from __future__ import annotations

import asyncio
import traceback
from dataclasses import dataclass
from typing import Any, Optional

from redis import Redis
from httpx import AsyncClient

from loggers import logger, write_exception
from models import BattleMode, DataType
from context import UpdateContext, RunContext
from utils import TimeUtils

from .endpoints import RequestTarget


@dataclass
class FetchResult:
    """请求结果：account 响应 + 按模式/数据类型组织的船数据"""
    account: dict
    ships: dict[BattleMode, dict[DataType, dict]]

    @classmethod
    def from_targets(
        cls, targets: list[RequestTarget], responses: list
    ) -> FetchResult:
        """根据请求目标和响应结果构建统一结果"""
        account = None
        ships = {}
        for target, response in zip(targets, responses):
            if target.mode is None:
                account = response
            else:
                ships.setdefault(target.mode, {})[target.data_type] = response
        return cls(account=account, ships=ships)


class ApiRequester:
    """从 API 获取用户原始数据"""

    @classmethod
    async def fetch(
        cls, ctx: UpdateContext, run_ctx: RunContext, targets: list[RequestTarget]
    ) -> Optional[FetchResult]:
        """并发请求所有目标，任一请求失败则返回 None"""
        try:
            # 创建并发任务
            tasks = [
                cls._fetch_single(
                    async_client=run_ctx.async_client,
                    account_id=ctx.account_id,
                    url=target.url
                ) for target in targets
            ]
            responses = await asyncio.gather(*tasks)

            # 记录指标，任一响应为错误标记则整体失败
            error = cls._record_metrics(
                redis_client=run_ctx.redis_client,
                responses=responses,
                urls=[target.url for target in targets]
            )
            if error:
                return None

            return FetchResult.from_targets(targets, responses)
        except Exception as e:
            error_name = type(e).__name__
            logger.error(f"Fetch user data failed: {error_name}")
            write_exception(
                error_type="NetworkError",
                error_name=error_name,
                error_info=traceback.format_exc(),
            )
            return None

    @staticmethod
    def _record_metrics(
        redis_client: Redis, responses: list, urls: list
    ) -> Optional[str]:
        """记录 HTTP 指标，返回错误标记，无错误时返回 None"""
        error_count = 0
        error = None
        today = TimeUtils.get_current_iso_time()[:10]

        for i, response in enumerate(responses):
            if isinstance(response, str):
                logger.info(f'{response} {urls[i]}')
                error_count += 1
                error = response

        try:
            redis_client.incrby(f'metrics:http:annual:{today[:4]}', len(urls))
            redis_client.incrby(f'metrics:http:monthly:{today[:7]}', len(urls))
            redis_client.incrby(f'metrics:http:daily:total:{today}', len(urls))

            if error_count > 0:
                redis_client.incrby(f'metrics:http:daily:error:{today}', error_count)
        except Exception:
            logger.warning('Failed to record HTTP metrics')

        return error

    @staticmethod
    async def _fetch_single(
        async_client: AsyncClient, account_id: int, url: str
    ) -> dict[str, Any] | str:
        """发送单个请求，返回数据 dict 或错误标记字符串"""
        try:
            resp = await async_client.get(url)
            logger.debug(f'GET {url}')
            if 'application_id' in url:
                # OFFICIAL API 处理逻辑
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('status') == 'ok':
                        if data.get('meta', {}).get('hidden') is None:
                            return data.get('data', {})
                        else:
                            return {str(account_id): {'hidden_profile': True}}
                    return "Game_API_Error"
            else:
                # VORTEX API 处理逻辑
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('status') == 'ok':
                        return data.get('data', {})
                    return "Game_API_Error"
                elif resp.status_code == 404:
                    return {}

            return f'HTTP_STATUS_{resp.status_code}'
        except Exception as e:
            return f'ERROR_{type(e).__name__}'
