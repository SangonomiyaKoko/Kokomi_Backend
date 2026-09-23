from redis import Redis
from requests import Session
from pymysql import Connection
from pymysql.cursors import Cursor

from shard import (
    MySQLOPS,
    RedisKeys,
    distributed_lock
)

from .logger import logger
from .syncer import ClanUsersSyncer
from .requester import APIRequester
from .db_ops import BasicDataRepository


class ClanUsersRefresher:
    """单个公会的成员刷新执行器

    编排一次公会刷新的完整流程：取数 -> 读取本地成员 -> 补齐新用户 -> 写入成员关系
    """

    @staticmethod
    def _insert_new_users(
        mysql_conn: Connection,
        redis_client: Redis,
        clan_id: int,
        missing_users: dict[int, str]
    ) -> int | None:
        """将接口返回而本地尚未储存的用户插入数据库

        返回成功插入的用户数，未获取到插入锁时返回 None
        """
        insert_lock_key = RedisKeys.insert_lock()
        with distributed_lock(insert_lock_key, redis_client) as locked:
            if not locked:
                logger.info(f'{clan_id} | FAILED - AcquireLockFailed')
                return None

            logger.debug(f'{clan_id} | Inserted users: {len(missing_users)}')

            with MySQLOPS.transaction(mysql_conn) as cursor:
                BasicDataRepository.init_new_users(
                    cursor=cursor,
                    missing_users=missing_users
                )

        return len(missing_users)

    @staticmethod
    def _load_local_data(
        cursor: Cursor,
        clan_id: int,
        user_ids: list
    ) -> tuple[list, list, dict]:
        """读取本次刷新所需的本地数据

        Returns:
            existing_members: 本地记录属于本公会的成员 ID 列表
                其中可能存在已经不位于公会的成员，需要标记退出公会
            existing_ids: 接口成员中已存在于数据库的 ID 列表
            existing_users: 接口成员在本地的公会数据 {account_id: (clan_id, is_null)}
                其中可能存在非本公会的关联记录，需要先标记退出原公会再标记加入
        """
        # 基于 T_user_clan 表读取公会下本地关联的用户
        existing_members = BasicDataRepository.get_existing_members(
            cursor=cursor,
            clan_id=clan_id
        )

        # 检查接口中所有的用户 ID 是否都存在于数据库
        # 对于在接口返回值中不在数据库的用户需要插入一条新的用户数据
        existing_ids = BasicDataRepository.get_existing_ids(
            cursor=cursor,
            user_ids=user_ids
        )

        # 此处过滤了不在数据库中的用户 ID
        existing_users = BasicDataRepository.get_existing_users(
            cursor=cursor,
            user_ids=existing_ids
        )

        return existing_members, existing_ids, existing_users

    @classmethod
    def refresh(
        cls,
        mysql_conn: Connection,
        redis_client: Redis,
        session: Session,
        clan_id: int
    ) -> tuple[int, int] | None:
        """刷新单个公会的成员数据

        Returns:
            (新增用户数, 写入的成员行为记录数)
            取数失败或者新用户未能入库时返回 None
        """
        # 获取公会内用户数据
        response = APIRequester.fetch(
            redis_client=redis_client,
            session=session,
            clan_id=clan_id
        )
        if not isinstance(response, list):
            logger.info(f'{clan_id} | Failed to obtain data')
            return None

        # 解析用户基本数据
        users = {}
        for user_info in response:
            users[user_info['id']] = user_info['name']
        user_ids = list(users.keys())

        # 读取 MySQL 数据库中储存的本地数据
        with MySQLOPS.read_only(mysql_conn) as cursor:
            existing_members, existing_ids, existing_users = (
                cls._load_local_data(
                    cursor=cursor,
                    clan_id=clan_id,
                    user_ids=user_ids
                )
            )

        # 接口中存在而数据库中不存在的用户，后续需要插入数据库
        # 数据格式: { account_id: username, ... }
        missing_users = {
            uid: users[uid] for uid in user_ids
            if uid not in existing_ids
        }

        # 对于不存在于数据库或者数据库公会信息没有更新的用户
        # 应当放入 invalid_users 中避免后续判断成员状态时认为用户为新加入
        invalid_users = list(missing_users) + [
            uid for uid, (_, is_null) in existing_users.items()
            if is_null
        ]

        # 数据库中用户的本地公会数据
        # 数据格式: { account_id: clan_id, ... }
        existing_data = {
            uid: cid
            for uid, (cid, _) in existing_users.items()
        }

        inserted_users = 0
        if missing_users:
            inserted = cls._insert_new_users(
                mysql_conn=mysql_conn,
                redis_client=redis_client,
                clan_id=clan_id,
                missing_users=missing_users
            )
            if inserted is None:
                # 新用户未能入库时公会的成员关系不完整，本轮跳过该公会
                return None
            
            inserted_users = inserted

        changed_actions = ClanUsersSyncer.refresh(
            conn=mysql_conn,
            clan_id=clan_id,
            user_ids=user_ids,
            invalid_users=invalid_users,
            existing_data=existing_data,
            existing_members=existing_members
        )

        return inserted_users, changed_actions
