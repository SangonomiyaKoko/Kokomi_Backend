from loggers import logger
from db import fetch_user_record, sqlite_transaction
from context import RunContext, UpdateContext
from models import UpdateResult
from repository import (
    ShipMapRepository,
    ShipDataRepository,
    ModeLatestRepository,
    ShipLatestRepository,
    UserRecentRepository,
    UserSummaryRepository
)

from .loader import UserDataLoader
from .updater import UpdateEvaluate
from .pipeline import UserDataProcessor
from .planner import UpdatePlanner


class UserUpdateRunner:
    """单用户更新流水线：判定 → 拉取 → 写回，任一阶段 SKIP / DISABLED 即短路"""

    @classmethod
    async def run(cls, run_ctx: RunContext, account_id: int) -> None:
        """执行单个用户的完整更新流程"""
        # 创建用户更新上下文
        ctx = cls._build_context(run_ctx, account_id)

        # 加载本地数据库，补全 summary 数据
        load_result = UserDataLoader.main(ctx)
        if not cls._handle_stage_result(load_result, account_id, run_ctx):
            return

        error = False
        try:
            # 更新评估，确定需要更新的模式合集
            decision = UpdateEvaluate.main(run_ctx, ctx)
            if not cls._handle_stage_result(decision, account_id, run_ctx):
                return

            ctx.fetch_modes = decision.modes
            logger.debug(
                f'{account_id} | Strategy: '
                f'{ctx.update_strategy}/{decision.reason_text}'
            )
            logger.debug(
                f'{account_id} | Modes: {[mode.name for mode in ctx.fetch_modes]}'
            )

            # 拉取外部接口获取最新数据，同步 MySQL 并构建数据模型
            fetch_result = await UserDataProcessor.main(ctx, run_ctx)
            if not cls._handle_stage_result(fetch_result, account_id, run_ctx):
                return

            # 对比本地数据库，确定写入计划
            result = UpdatePlanner.main(ctx)
        except:
            error = True
            raise
        finally:
            if not error and ctx.update_plan.planned_count > 0:
                logger.debug(f'{account_id} | Plan to insert/update rows: {ctx.update_plan.planned_count}')
                cls._commit_plan(ctx)

        logger.debug(f'{account_id} | UPDATED - {result}')

    @staticmethod
    def _build_context(run_ctx: RunContext, account_id: int) -> UpdateContext:
        """组装更新上下文，并加载用户的 MySQL 记录与统计信息"""
        ctx = UpdateContext(account_id=account_id)

        # 加载用户在 MySQL 中记录
        with run_ctx.mysql_connection.cursor() as cursor:
            record, stats = fetch_user_record(cursor, account_id)
            ctx.user_record = record
            ctx.user_stats = stats

        # 加载用户访问令牌
        ac = run_ctx.redis_client.get(f"token:ac:{account_id}")
        ctx.access_token = ac.split(':')[0] if ac and ':' in ac else (ac or None)
        return ctx

    @staticmethod
    def _handle_stage_result(result: UpdateResult, account_id: int, run_ctx: RunContext) -> bool:
        """统一处理阶段结果：SKIP / DISABLED 记录日志与统计并短路"""
        if result.is_skip:
            logger.debug(f'{account_id} | SKIP - {result.reason_text}')
            return False
        if result.is_disabled:
            logger.debug(f'{account_id} | DISABLED - {result.reason_text}')
            # 统计与禁用用户直接记入 RunContext，由 run_worker 在循环结束后统一处理
            run_ctx.disabled_users[account_id] = result.reason_text
            return False
        return True

    @staticmethod
    def _commit_plan(ctx: UpdateContext) -> None:
        """在一个 SQLite 事务中提交用户更新计划"""
        plan = ctx.update_plan
        with sqlite_transaction(ctx.account_id) as cursor:
            ShipDataRepository.refresh(cursor, plan.ship_data)
            ShipMapRepository.refresh(cursor, plan.ship_map)
            ShipLatestRepository.refresh(cursor, plan.ship_latest)
            ModeLatestRepository.refresh(cursor, plan.mode_latest)
            UserRecentRepository.refresh(cursor, plan.user_recent)
            UserSummaryRepository.refresh(cursor, plan.user_summary)
