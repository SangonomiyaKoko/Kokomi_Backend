import traceback
from typing import Union
from json import JSONDecodeError

from requests.sessions import Session
from shard import (
    Endpoints,
    RedisKeys, 
    TimeUtils, 
    ParseUtils, 
    PolicyUtils,
    exception_writer
)

from .context import RunContext
from .syncer import UserStatsSyncer
from .settings import (
    REGION,
    LOG_DIR, 
    CLIENT_NAME, 
    REQUEST_TIMEOUT, 
    PROXY_CONFIG
)


def fetch_data(
    session: Session, url: str, params: dict = None
) -> Union[dict, str]:
    """请求 API 获取数据"""
    try:
        resp = session.get(
            url=url,
            params=params,
            timeout=REQUEST_TIMEOUT
        )

        if resp.status_code == 200:
            try:
                result = resp.json()
            except JSONDecodeError:
                return "Game_API_Error"
            if result.get('status') == 'ok':
                return result.get('data', {})
            else:
                return "Game_API_Error"
        elif resp.status_code == 404:
            return {}

        return f'HTTP_STATUS_{resp.status_code}'
    except Exception as e:
        return f'ERROR_{type(e).__name__}'

def refresh_user(
    run_ctx: RunContext, account_id: int
) -> str:
    """刷新指定用户的基础数据"""
    # 记录指标
    iso_time = TimeUtils.iso_time()
    incr_keys = [
        RedisKeys.metrics('celery','annual',iso_time.date_year),
        RedisKeys.metrics('celery','monthly',iso_time.date_month),
        RedisKeys.metrics('celery','daily:total',iso_time.date)
    ]

    try:
        # 读取绑定的 access token
        # ac = run_ctx.redis_client.get(
        #     name=RedisKeys.user_ac_token(account_id)
        # )
        # access_token = StringUtils.token_decode(ac)[0]
        access_token = None

        # 请求接口
        base_url = Endpoints.vortex_api(REGION, PROXY_CONFIG)
        query = f'?ac={access_token}' if access_token else ''
        url = f'{base_url}/api/accounts/{account_id}/{query}'
        response = fetch_data(run_ctx.session, url)

        incr_keys += [
            RedisKeys.metrics('http','annual',iso_time.date_year),
            RedisKeys.metrics('http','monthly',iso_time.date_month),
            RedisKeys.metrics('http','daily:total',iso_time.date)
        ]
        if isinstance(response, str):
            # 接口层失败，直接中断
            incr_keys.append(RedisKeys.metrics('http','daily:error',iso_time.date))
            return response

        # 接口数据数据解析
        current_timestamp = TimeUtils.timestamp()
        user_data = ParseUtils.user_basic_data(
            region=REGION,
            account_id=account_id, 
            response=response
        )
        user_level = PolicyUtils.user_activity_level(
            timestamp=current_timestamp,
            lbt=user_data['last_battle_at']
        )

        # 将数据同步到 MySQL 库中
        result = UserStatsSyncer.refresh(
            db_pool=run_ctx.db_pool, 
            redis_client=run_ctx.redis_client,
            timestamp=current_timestamp,
            account_id=account_id, 
            user_data=user_data,
            activity_level=user_level
        )

        if isinstance(result, int):
            return 'Success'

        incr_keys.append(RedisKeys.metrics('celery','daily:error',iso_time.date))
        return result
    except Exception as e:
        incr_keys.append(RedisKeys.metrics('celery','daily:error',iso_time.date))
        error_id = exception_writer(
            log_dir=LOG_DIR,
            client_id=CLIENT_NAME,
            error_type='ProgramError',
            error_name=type(e).__name__,
            error_info=traceback.format_exc()
        )
        return f'Exception {error_id}'
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
            return 'Redis Error'
