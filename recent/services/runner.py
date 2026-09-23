import traceback
from typing import Optional

from shard import (
    MySQLOPS,
    SQLiteOPS,
    RedisKeys, 
    TimeUtils, 
    StringUtils, 
    ServicesName
)

from ..core import RunContext, UpdateContext
from ..models import UpdateResult, RunnerResult
from ..repository import (
    BasicDataRepository,
    ShipMapRepository,
    ShipDataRepository,
    ModeLatestRepository,
    ShipLatestRepository,
    UserRecentRepository,
    UserSummaryRepository
)
from ..logger import logger, write_exception
from ..settings import DATA_DIR, SQLITE_DIR

from .loader import UserDataLoader
from .updater import UpdateEvaluate
from .pipeline import UserDataProcessor
from .planner import UpdatePlanner


class UserUpdateRunner:
    """单用户更新流水线"""

    @classmethod
    async def run(
        cls, run_ctx: RunContext, account_id: int
    ) -> RunnerResult:
        """执行单个用户的完整更新流程"""
        try:
            # 创建该用户的更新上下文
            ctx = cls._build_context(run_ctx, account_id)

            # 加载读取用户的本地数据库
            load_result = cls._handle_stage_result(
                run_ctx=run_ctx,
                account_id=account_id, 
                result=UserDataLoader.main(ctx)
            )
            if load_result:
                return load_result
        except Exception as e:
            error_name = type(e).__name__
            error_id = write_exception(
                error_type="ProgramError",
                error_name=error_name,
                error_info=traceback.format_exc()
            )
            logger.error(f'{account_id} | ERROR - {error_name} - {error_id}')
            return RunnerResult.FAILED
        
        try:
            # 更新评估，确定需要更新的模式合集
            evaluate_result = cls._handle_stage_result(
            run_ctx=run_ctx,
                account_id=account_id, 
                result=UpdateEvaluate.main(run_ctx, ctx)
            )
            if evaluate_result:
                return evaluate_result

            # 确定需要更新的策略和模式
            logger.debug(
                f'{account_id} | Strategy: '
                f'{ctx.update_strategy}'
            )
            logger.debug(
                f'{account_id} | Modes: '
                f'{[mode.name for mode in ctx.fetch_modes]}'
            )

            # 拉取外部接口获取最新数据，同步 MySQL 并构建数据模型
            fetch_result = cls._handle_stage_result(
                run_ctx=run_ctx,
                account_id=account_id, 
                result=await UserDataProcessor.main(run_ctx, ctx)
            )
            if fetch_result:
                return fetch_result

            # 对比本地数据库，确定写入计划
            update_result = UpdatePlanner.main(ctx)
        except Exception as e:
            ctx.update_plan.exception_raised = True
            error_name = type(e).__name__
            error_id = write_exception(
                error_type="ProgramError",
                error_name=error_name,
                error_info=traceback.format_exc()
            )
            logger.error(f'{account_id} | ERROR - {type(e).__name__} - {error_id}')
            return RunnerResult.FAILED
        finally:
            # 只有没有异常被捕获且有计划写入数据时才提交写入
            if ctx.update_plan.can_execute:
                logger.debug(
                    f'{account_id} | Planned insert/update rows: '
                    f'{ctx.update_plan.planned_count}'
                )
                cls._commit_plan(ctx)

        return update_result

    @staticmethod
    def _build_context(
        run_ctx: RunContext, account_id: int
    ) -> UpdateContext:
        """组装更新上下文，并加载用户的 MySQL 记录与统计信息"""
        ctx = UpdateContext(account_id=account_id)

        # 读取用户在 MySQL 中记录
        with MySQLOPS.read_only(run_ctx.mysql_connection) as cursor:
            record, stats = BasicDataRepository.load_user_record(cursor, account_id)
            ctx.user_record = record
            ctx.user_stats = stats

        # 加载用户访问令牌
        ac = run_ctx.redis_client.get(RedisKeys.user_ac_token(account_id))
        ctx.access_token = StringUtils.token_decode(ac)[0]
        return ctx

    @staticmethod
    def _handle_stage_result(
        run_ctx: RunContext, account_id: int, result: UpdateResult
    ) -> Optional[RunnerResult]:
        """统一处理阶段结果，记录日志与统计并短路，返回不为 None 则中断"""
        if result.is_skipped:
            logger.debug(f'{account_id} | SKIPPED - {result.reason_text}')
            return RunnerResult.SKIPPED

        if result.is_failed:
            logger.debug(f'{account_id} | FAILED - {result.reason_text}')
            return RunnerResult.FAILED
        
        if result.is_disabled:
            logger.debug(f'{account_id} | DISABLED - {result.reason_text}')
            # 关闭用户的 Recent 功能权限
            with MySQLOPS.transaction(run_ctx.mysql_connection) as cursor:
                BasicDataRepository.disable_user(cursor, account_id)
    
            # 记录时间和原因到操作日志中
            log_path = DATA_DIR / 'local' / 'Operation.log'
            if not log_path.exists():
                logger.error(f'File missing: {log_path}')
                return
            
            line = (
                f'{TimeUtils.log_time()} [{ServicesName.RECENT}] '
                f'RecentDisabled: {account_id}-{result.reason_text}\n'
            )
            with open(log_path, mode='a', encoding='utf-8') as f:
                f.write(line)
    
            # 清理 SQLite 数据库文件
            SQLiteOPS.remove_user_db(SQLITE_DIR, DATA_DIR, account_id)

            return RunnerResult.DISABLED
        
        return

    @staticmethod
    def _commit_plan(
        ctx: UpdateContext
    ) -> None:
        """提交用户更新计划"""
        plan = ctx.update_plan
        user_db_path = SQLiteOPS.user_db_path(SQLITE_DIR, ctx.account_id)
        with SQLiteOPS.transaction(user_db_path) as cursor:
            ShipDataRepository.refresh(cursor, plan.ship_data)
            ShipMapRepository.refresh(cursor, plan.ship_map)
            ShipLatestRepository.refresh(cursor, plan.ship_latest)
            ModeLatestRepository.refresh(cursor, plan.mode_latest)
            UserRecentRepository.refresh(cursor, plan.user_recent)
            UserSummaryRepository.refresh(cursor, plan.user_summary)
