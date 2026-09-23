import traceback

from pymysql import Connection
from pymysql.cursors import Cursor

from shard import MySQLOPS, ClanPolicyUtils

from .logger import logger, write_exception


# T_clan_action 表中的成员行为类型
ACTION_JOIN = 1     # 成员加入公会
ACTION_LEAVE = 2    # 成员退出公会


class ClanUsersSyncer:
    """公会成员关系同步器"""
    @staticmethod
    def _record_actions(cursor: Cursor, actions: list) -> None:
        """批量写入成员进出公会的行为记录"""
        if not actions:
            return

        sql = """
            INSERT INTO T_clan_action (
                clan_id,
                account_id,
                action_type
            ) VALUES (
                %s, %s, %s
            );
        """
        cursor.executemany(sql, actions)

    @staticmethod
    def _resolve_member_changes(
        clan_id: int,
        user_ids: list,
        invalid_users: list,
        existing_data: dict,
        existing_members: list
    ) -> tuple[dict, list]:
        """解析本次刷新中成员进出公会的情况"""
        api_ids = set(user_ids)
        # 本轮新插入的成员在本地尚无公会记录，与调用方标记的成员同样视为状态未知
        unknown_users = set(invalid_users) | (api_ids - set(existing_data))

        # 本地记录属于本公会而接口中已不存在 -> 成员退出本公会
        left_groups = {}
        for uid in existing_members:
            if uid not in api_ids:
                left_groups.setdefault(clan_id, []).append(uid)

        joined_members = []
        for uid in user_ids:
            # 本地公会状态未知的成员无法判断此前的状态
            # 此部分成员不记录加入行为，避免被误认为新加入
            if uid in unknown_users:
                continue

            previous_clan = existing_data.get(uid)
            if previous_clan == clan_id:
                # 本地记录已属于本公会，成员状态未发生变化
                continue
            elif previous_clan is not None:
                # 成员由其他公会转入，需要先在其原公会下记录退出行为
                left_groups.setdefault(previous_clan, []).append(uid)

            joined_members.append(uid)

        return left_groups, joined_members

    @classmethod
    def _record_member_changes(
        cls,
        cursor: Cursor,
        clan_id: int,
        left_groups: dict,
        joined_members: list
    ) -> int:
        """记录成员进出公会的行为并清理其原有的公会关联

        退出与加入的行为按先后顺序写入，保证转会成员的行为可读。
        返回本次写入的行为记录数，转会成员在原公会与本公会下各计一次
        """
        left_actions = []
        for left_clan_id, user_ids in left_groups.items():
            # 退出公会的成员统一将公会关联置空，由后续刷新重新判定归属
            sql = """
                UPDATE T_user_clan
                SET
                    clan_id = NULL,
                    updated_at = NOW()
                WHERE account_id = %s;
            """
            cursor.executemany(sql, [[uid] for uid in user_ids])
            left_actions.extend(
                [left_clan_id, uid, ACTION_LEAVE] 
                for uid in user_ids
            )

        join_actions = [
            [clan_id, uid, ACTION_JOIN] 
            for uid in joined_members
        ]

        cls._record_actions(
            cursor=cursor,
            actions=left_actions
        )
        cls._record_actions(
            cursor=cursor,
            actions=join_actions
        )

        return len(left_actions) + len(join_actions)

    @classmethod
    def _disable_empty_clan(
        cls,
        cursor: Cursor,
        clan_id: int,
        existing_members: list
    ) -> int:
        """将无成员的公会标记为不可用并清理尚处于该公会下的成员关系

        返回清理过程中写入的成员行为记录数
        """
        sql = """
            UPDATE T_clan_users
            SET
                is_enabled = 0,
                activity_level = 0,
                member_count = 0,
                next_refresh_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE clan_id = %s;
        """
        cursor.execute(sql, [clan_id])

        # 接口中已无成员，本地记录属于该公会的成员均已退出
        return cls._record_member_changes(
            cursor=cursor,
            clan_id=clan_id,
            left_groups={clan_id: existing_members},
            joined_members=[]
        )

    @staticmethod
    def _update_member_relations(
        cursor: Cursor, clan_id: int, user_ids: list
    ) -> None:
        """批量更新公会成员关系"""
        placeholders = ",".join(["%s"] * len(user_ids))
        sql = f"""
            UPDATE T_user_clan
            SET
                clan_id = %s,
                updated_at = NOW()
            WHERE account_id IN ({placeholders});
        """
        cursor.execute(sql, [clan_id] + user_ids)

    @staticmethod
    def _update_clan_users(
        cursor: Cursor, clan_id: int, user_ids: list
    ) -> None:
        """更新公会成员统计信息"""
        sql = """
            UPDATE T_clan_users
            SET
                is_enabled = 1,
                activity_level = %s,
                member_count = %s,
                next_refresh_at = DATE_ADD(NOW(), INTERVAL %s SECOND),
                updated_at = NOW()
            WHERE clan_id = %s;
        """
        activity_level = ClanPolicyUtils.clan_activity_level(len(user_ids))
        interval_seconds = ClanPolicyUtils.clan_refresh_interval(activity_level)
        cursor.execute(sql, [
            activity_level,
            len(user_ids),
            interval_seconds,
            clan_id
        ])

    @classmethod
    def refresh(
        cls,
        conn: Connection,
        clan_id: int,
        user_ids: list,
        invalid_users: list,
        existing_data: dict,
        existing_members: list
    ) -> int:
        """基于公会成员接口数据刷新数据库中的公会成员信息"""
        try:
            left_groups, joined_members = cls._resolve_member_changes(
                clan_id=clan_id,
                user_ids=user_ids,
                invalid_users=invalid_users,
                existing_data=existing_data,
                existing_members=existing_members
            )

            with MySQLOPS.transaction(conn) as cursor:
                if len(user_ids) == 0:
                    # 用户下用户数为 0 认为该工会不可用
                    action_count = cls._disable_empty_clan(
                        cursor=cursor,
                        clan_id=clan_id,
                        existing_members=existing_members
                    )
                else:
                    action_count = cls._record_member_changes(
                        cursor=cursor,
                        clan_id=clan_id,
                        left_groups=left_groups,
                        joined_members=joined_members
                    )
                    cls._update_member_relations(cursor, clan_id, user_ids)

                    cls._update_clan_users(
                        cursor=cursor,
                        clan_id=clan_id,
                        user_ids=user_ids
                    )

            return action_count
        except Exception as e:
            error_name = type(e).__name__
            logger.error(f'{clan_id} | {error_name}')
            return 0
