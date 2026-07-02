from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from app.core import EnvConfig
from app.loggers import ExceptionLogger
from app.models import ClanModel, RankingModel
from app.response import JSONResponse, ResponseDict
from app.middlewares import RedisClient


@dataclass
class ClanLeaderboardResponse:
    """排行榜响应数据结构"""
    meta: Dict[str, Any] = field(default_factory=dict)
    rows: List[Dict[str, Any]] = field(default_factory=list)
    credits: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'meta': self.meta,
            'rows': self.rows,
            'credits': self.credits
        }

class ClanRankingAPI:
    @staticmethod
    def _build_leaderboard(start_rank: int, clan_ids: list, clans_data: dict) -> list[dict]:
        """构建工会排行榜数据列表

        Args:
            start_rank: 起始排名（1-based）
            clan_ids: 工会ID列表（按排名顺序）
            clans_data: 工会详情数据字典，键为字符串 clan_id

        Returns:
            排行榜数据列表，每个元素包含排名、工会信息、战绩数据等
        """
        leaderboard = []
        for offset, clan_id in enumerate(clan_ids):
            clan_detail = clans_data.get(str(clan_id), {})

            leaderboard.append({
                'rank': start_rank + offset,
                'clan_id': int(clan_id),
                'tag': clan_detail.get('tag', ''),
                'leading_team': clan_detail.get('leading_team', ''),
                'battles': clan_detail.get('battles', 0),
                'win_rate': clan_detail.get('win_rate', 0.0),
                'win_rate_level': clan_detail.get('win_rate_level', 1),
                'league': clan_detail.get('league', 0),
                'division': clan_detail.get('division', 0),
                'rating': clan_detail.get('rating', 0),
                'max_streak': clan_detail.get('max_streak', 0),
                'stage_type': clan_detail.get('stage_type', ''),
                'stage_progress': clan_detail.get('stage_progress', 0),
                'last_battle_at': clan_detail.get('last_battle_at', 0)
            })

        return leaderboard

    @staticmethod
    async def _get_season() -> tuple[Optional[Any], Optional[int]]:
        """获取当前赛季编号

        Returns:
            (error, season): error为None时season有效，否则season为错误响应
        """
        error, season = JSONResponse.extract_data(
            response=await ClanModel.get_latest_season()
        )
        return error, season

    @classmethod
    @ExceptionLogger.handle_program_exception_async
    async def get_clan_ranking(cls, page_index: int = 1, page_size: int = 50) -> ResponseDict:
        """获取工会排行榜分页数据

        Args:
            page_index: 页码，从1开始
            page_size: 每页数量

        Returns:
            ResponseDict
        """
        # 获取赛季编号
        error, season = await cls._get_season()
        if error:
            return season

        # 计算分页起止索引
        clan_ranking_key = "leaderboard:clan"
        start = (page_index - 1) * page_size
        stop = start + page_size - 1

        # 获取排行榜总工会数
        error, total_users = JSONResponse.extract_data(
            response=await RedisClient.zget_total(clan_ranking_key)
        )
        if error:
            return total_users

        # 起始索引超过总工会数时返回空数据
        if start >= total_users:
            return JSONResponse.API_1000_Success

        # 获取当前页的工会ID列表
        error, page_clan_ids = JSONResponse.extract_data(
            response=await RedisClient.zget_range(clan_ranking_key, start, stop)
        )
        if error:
            return page_clan_ids

        if not page_clan_ids:
            return JSONResponse.API_1000_Success

        # 批量获取工会详情数据
        error, clans_data = JSONResponse.extract_data(
            response=await RankingModel.get_clan_leaderboard(page_clan_ids)
        )
        if error:
            return clans_data

        # 构建返回数据
        data = ClanLeaderboardResponse(
            meta={
                'region': EnvConfig.REGION,
                'season': season,
                'clans': total_users,
            },
            rows=cls._build_leaderboard(start + 1,page_clan_ids,clans_data),
            credits=2
        )

        return JSONResponse.success(data.to_dict())

    @classmethod
    @ExceptionLogger.handle_program_exception_async
    async def get_clan_user_ranking(cls, clan_id: int, page_size: int = 50) -> ResponseDict:
        """获取指定工会在排行榜中的排名及所在页数据

        Args:
            clan_id: 工会ID
            page_size: 每页数量

        Returns:
            ResponseDict
        """
        # 获取指定工会的排名
        clan_ranking_key = "leaderboard:clan"
        error, user_rank = JSONResponse.extract_data(
            response=await RedisClient.zget_rank(clan_ranking_key, str(clan_id))
        )
        if error:
            return user_rank

        # 工会不存在于排行榜中
        if user_rank is None:
            return JSONResponse.API_1000_Success

        # 获取排行榜总工会数
        error, total_users = JSONResponse.extract_data(
            response=await RedisClient.zget_total(clan_ranking_key)
        )
        if error:
            return total_users

        # 计算工会所在页码及该页的起止索引
        rank = int(user_rank) + 1  # Redis rank 为 0-based，转为 1-based
        page_index = (user_rank // page_size) + 1
        start = (page_index - 1) * page_size
        stop = start + page_size - 1

        # 4. 获取所在页的工会ID列表
        error, page_clan_ids = JSONResponse.extract_data(
            response=await RedisClient.zget_range(clan_ranking_key, start, stop)
        )
        if error:
            return page_clan_ids

        if not page_clan_ids:
            return JSONResponse.API_1000_Success

        # 获取赛季编号
        error, season = await cls._get_season()
        if error:
            return season

        # 批量获取工会详情数据
        error, clans_data = JSONResponse.extract_data(
            response=await RankingModel.get_clan_leaderboard(page_clan_ids)
        )
        if error:
            return clans_data

        # 8. 构建返回数据
        total_pages = (total_users + page_size - 1) // page_size
        data = {
            'page': {
                'index': page_index,
                'size': page_size,
                'total': total_pages
            },
            'info': {
                'region': EnvConfig.REGION,
                'season': season,
                'clans': total_users,
                'rank': rank
            },
            'datas': cls._build_leaderboard(
                start + 1,
                page_clan_ids,
                clans_data
            )
        }

        return JSONResponse.success(data)