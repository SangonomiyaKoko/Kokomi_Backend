import traceback
from typing import Union
from json import JSONDecodeError

from requests.sessions import Session
from shard import (
    Endpoints,
    RedisKeys,
    TimeUtils,
    ISOTimeString,
    ParseUtils,
    StringUtils,
    ServicesName,
    UserPolicyUtils,
    exception_writer,
    distributed_lock
)

from .context import RunContext
from .syncer import UserStatsSyncer
from .settings import (
    REGION,
    LOG_DIR,
    REQUEST_TIMEOUT,
    PROXY_CONFIG
)


class UserRefresher:
    """用户数据刷新执行器

    编排一次用户刷新的完整流程：取数 → 解析 → 抢锁写库 → 收尾
    其中收尾（释放队列锁、上报指标）无论主流程如何结束都必须执行
    """

    @staticmethod
    def _fetch_data(
        session: Session, url: str
    ) -> Union[dict, str]:
        """请求 API 获取数据

        读取成功返回 Dict 数据，失败返回错误字符串
        """
        try:
            resp = session.get(
                url=url,
                timeout=REQUEST_TIMEOUT
            )

            if resp.status_code == 200:
                try:
                    result = resp.json()
                except JSONDecodeError:
                    return "Game_API_Error"

                if result.get('status') == 'ok':
                    return result.get('data', {})

                return "Game_API_Error"
            elif resp.status_code == 404:
                # 用户不存在，认为该请求有效
                # 通过返回一个空 Dict 由后续数据解析函数中处理
                return {}

            return f'HTTP_STATUS_{resp.status_code}'
        except Exception as e:
            return f'ERROR_{type(e).__name__}'

    @classmethod
    def _refresh_data(
        cls,
        run_ctx: RunContext,
        account_id: int,
        iso_time: ISOTimeString,
        incr_keys: list[str]
    ) -> str:
        """执行刷新主流程，取数、解析并写库，返回本次的结果标识"""
        try:
            # 读取绑定的 access token
            ac = run_ctx.redis_client.get(
                name=RedisKeys.user_ac_token(account_id)
            )
            access_token = StringUtils.token_decode(ac)[0]

            # 请求接口
            base_url = Endpoints.vortex_api(REGION, PROXY_CONFIG)
            query = f'?ac={access_token}' if access_token else ''
            url = f'{base_url}/api/accounts/{account_id}/{query}'
            response = cls._fetch_data(run_ctx.session, url)

            incr_keys += [
                RedisKeys.metrics('http','annual',iso_time.date_year),
                RedisKeys.metrics('http','monthly',iso_time.date_month),
                RedisKeys.metrics('http','daily:total',iso_time.date)
            ]
            if isinstance(response, str):
                # 接口层失败，直接中断，同时计入 celery 和 http 的错误指标中
                incr_keys.append(RedisKeys.metrics('http','daily:error',iso_time.date))
                incr_keys.append(RedisKeys.metrics('celery','daily:error',iso_time.date))
                return response

            # 接口数据数据解析
            current_timestamp = TimeUtils.timestamp()
            user_data = ParseUtils.user_basic_data(
                region=REGION,
                account_id=account_id,
                response=response
            )
            activity_level = UserPolicyUtils.user_activity_level(
                timestamp=current_timestamp,
                lbt=user_data['last_battle_at']
            )

            # 为避免触发并发写入问题，写入前必须先获取分布式锁
            user_lock_key = RedisKeys.user_lock(account_id)
            with distributed_lock(user_lock_key, run_ctx.redis_client) as locked:
                if not locked:
                    # 只有极低概率获取分布式锁失败
                    incr_keys.append(RedisKeys.metrics('celery','daily:error',iso_time.date))
                    return 'AcquireLockFailed'

                # 将数据同步到 MySQL 库中
                result = UserStatsSyncer.refresh(
                    db_pool=run_ctx.db_pool,
                    timestamp=current_timestamp,
                    account_id=account_id,
                    user_data=user_data,
                    activity_level=activity_level
                )

            if isinstance(result, int):
                # 返回更新时间戳，更新成功
                return 'Success'

            incr_keys.append(RedisKeys.metrics('celery','daily:error',iso_time.date))
            return result
        except Exception as e:
            incr_keys.append(RedisKeys.metrics('celery','daily:error',iso_time.date))
            error_id = exception_writer(
                log_dir=LOG_DIR,
                client_id=ServicesName.CELERY,
                error_type='ProgramError',
                error_name=type(e).__name__,
                error_info=traceback.format_exc()
            )
            return f'ERROR {error_id}'

    @classmethod
    def refresh(
        cls, run_ctx: RunContext, account_id: int
    ) -> str:
        """刷新指定用户的基础数据

        负责指标键的初始化，以及无论主流程如何结束都必须执行的收尾：
        释放队列分布式锁、上报指标
        """
        iso_time = TimeUtils.iso_time()
        # 记录指标
        incr_keys = [
            RedisKeys.metrics('celery','annual',iso_time.date_year),
            RedisKeys.metrics('celery','monthly',iso_time.date_month),
            RedisKeys.metrics('celery','daily:total',iso_time.date)
        ]

        try:
            result = cls._refresh_data(
                run_ctx=run_ctx,
                account_id=account_id,
                iso_time=iso_time,
                incr_keys=incr_keys
            )
        finally:
            try:
                # 删除队列分布式锁
                queue_lock_key = RedisKeys.queue_lock(account_id)
                run_ctx.lock_client.delete(queue_lock_key)

                # 写入统计指标
                pipe = run_ctx.redis_client.pipeline()
                for key in incr_keys:
                    pipe.incr(key)
                pipe.execute()
            except Exception:
                # 不写异常日志，避免日志风暴
                result = 'Redis Error'

        return result
