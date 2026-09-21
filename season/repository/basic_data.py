from pymysql.cursors import Cursor

from ..settings import FALLBACK_REFRESH_SECONDS


class BasicDataRepository:
    """T_tracking_meta 表的数据访问对象"""

    @staticmethod
    def is_need_update(
        cursor: Cursor, tracking_key: str, tracking_type: str
    ) -> bool:
        """检查数据追踪状态

        追踪值缺失（tracking_value 为 NULL），或距上次更新已超过
        FALLBACK_REFRESH_SECONDS 秒时返回 True

        追踪记录整行缺失时返回 False，该情况由初始化种子数据兜底
        """
        sql = """
            SELECT
                CASE
                    WHEN tracking_value IS NULL THEN TRUE
                    WHEN UNIX_TIMESTAMP(NOW()) - UNIX_TIMESTAMP(tracking_value) > %s THEN TRUE
                    ELSE FALSE
                END AS need_update
            FROM T_tracking_meta
            WHERE tracking_key = %s
              AND tracking_type = %s;
        """
        # 实际提前 600s 更新，宁可早更
        cursor.execute(
            sql,
            [FALLBACK_REFRESH_SECONDS - 600, tracking_key, tracking_type]
        )
        result = cursor.fetchone()
        if not result or not result[0]:
            return False

        return True

    @staticmethod
    def update_tracking_key(
        cursor: Cursor, tracking_key: str, tracking_type: str
    ) -> None:
        """将追踪时间戳更新为当前时间

        用于在一轮更新成功后标记本轮任务已完成
        """
        sql = """
            UPDATE T_tracking_meta
            SET
                tracking_value = NOW()
            WHERE tracking_key = %s
              AND tracking_type = %s;
        """
        cursor.execute(sql, [tracking_key, tracking_type])
