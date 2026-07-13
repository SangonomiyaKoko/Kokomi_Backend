import asyncio
import aiomysql
from typing import Optional
from aiomysql.pool import Pool
from aiomysql.cursors import Cursor
from aiomysql.connection import Connection
from contextlib import asynccontextmanager
from dataclasses import asdict

from app.core import EnvConfig, api_logger


class MySQLManager:
    """MySQL连接与事务管理器"""
    _pool: Optional[Pool] = None

    @classmethod
    async def init_pool(cls) -> None:
        """初始化MySQL连接池"""
        if cls._pool is not None:
            return
        
        if EnvConfig.DEV_MODE:
            api_logger.info("DEV_MODE on, skip MySQL connection")
            return
        
        config = EnvConfig.get_config()
        cls._pool = await aiomysql.create_pool(
            # 必须关闭自动提交，使用 transaction 确保数据完整
            autocommit=False,
            pool_recycle=3600,
            minsize=1,
            maxsize=10,
            **asdict(config.MYSQL)
        )
        api_logger.info("MySQL pool initialized successfully")

    @classmethod
    async def close_pool(cls, timeout: float = 5.0) -> None:
        """关闭连接池，带超时保护防止异常死锁。"""
        if not cls._pool:
            api_logger.info("MySQL connection is already closed or not initialized")
            return
        
        try:
            # 等待一小段时间，让正在进行的操作尽量完成
            await asyncio.sleep(1)
            cls._pool.close()
            await asyncio.wait_for(cls._pool.wait_closed(), timeout=timeout)
            api_logger.info("MySQL connection pool closed")
        except (asyncio.TimeoutError, Exception) as e:
            api_logger.warning(f"MySQL connection pool close failed, forcing...")
            cls._force_close_all()
        finally:
            cls._pool = None

    @classmethod
    async def test_connection(cls) -> bool:
        if EnvConfig.DEV_MODE:
            return

        if cls._pool is None:
            await cls.init_pool()

        try:
            async with MySQLManager.read_only_cursor() as cur:
                await cur.execute("SELECT VERSION();")
                ver = await cur.fetchone()
                api_logger.info(f"MySQL version: {ver[0]}")
                await cur.execute("SELECT @@GLOBAL.transaction_isolation;")
                iso = await cur.fetchone()
                api_logger.info(f"Transaction isolation: {iso[0]}")
                await cur.execute("SELECT @@GLOBAL.time_zone;")
                global_tz = await cur.fetchone()
                api_logger.info(f"Global timezone: {global_tz[0]}")
                await cur.execute("SELECT @@GLOBAL.system_time_zone;")
                system_tz = await cur.fetchone()
                api_logger.info(f"System timezone: {system_tz[0]}")
                await cur.execute("SELECT NOW();")
                current_time = await cur.fetchone()
                api_logger.info(f"Now ISO time: {current_time[0]}")
            return True
        except Exception as e:
            api_logger.error(f"Connection test failed: {e}")
            return False
        
    @classmethod
    def _force_close_all(cls) -> None:
        """直接 abort 所有连接的底层 transport，确保关闭不阻塞"""
        pool = cls._pool
        if not pool:
            return
        
        # 获取池中所有连接（包括空闲和正在使用的）
        all_conns: list[Connection] = list(getattr(pool, '_free_conns', [])) + list(getattr(pool, '_used_conns', []))
        for conn in all_conns:
            try:
                # 直接从底层 abort 传输层
                if hasattr(conn, '_writer') and conn._writer:
                    transport = conn._writer.transport
                    if transport and not transport.is_closing():
                        transport.abort()
                conn.close()
            except Exception:
                pass
        api_logger.info("All connections force-aborted")

    @classmethod
    async def _acquire_healthy_conn(cls) -> Connection:
        """获取健康连接，失败直接抛出异常"""
        if cls._pool is None:
            raise RuntimeError("Pool not initialized")

        conn = await cls._pool.acquire()
        try:
            await asyncio.wait_for(conn.ping(), timeout=2.0)
            return conn
        except Exception:
            await cls._release_conn_only(conn)
            raise RuntimeError("Acquire healthy connection Failed")

    @classmethod
    async def _discard_conn(cls, conn: Connection) -> None:
        """强制丢弃异常连接"""
        try:
            if hasattr(conn, '_writer') and conn._writer:
                transport = conn._writer.transport
                if transport and not transport.is_closing():
                    transport.abort()
            conn.close()
        except Exception:
            pass

    @classmethod
    async def _release_conn_only(cls, conn: Connection) -> None:
        """释放连接，失败则丢弃"""
        try:
            if cls._pool:
                await cls._pool.release(conn)
        except Exception:
            api_logger.warning(f"MySQL connection release failed, discarding")
            await cls._discard_conn(conn)

    @classmethod
    @asynccontextmanager
    async def auto_transaction_cursor(cls):
        """### 自动管理事务（返回游标）

        正常退出时自动提交事务+释放连接回连接池, 异常退出时自动回滚事务+丢弃连接

        Usage:
        ```
        async with MySQLManager.auto_transaction_cursor() as cur:
            sql = "..."
            await cur.execute(sql)
        ```
        """
        conn = await cls._acquire_healthy_conn()
        try:
            async with conn.cursor() as cur:
                cur: Cursor
                yield cur
        except Exception:
            try:
                await conn.rollback()
            except Exception:
                pass
            await cls._release_conn_only(conn)
            api_logger.warning("Auto transaction rolled back due to exception")
            raise
        else:
            await conn.commit()
            await cls._release_conn_only(conn)

    @classmethod
    @asynccontextmanager
    async def read_only_cursor(cls):
        """### 只读查询（返回游标）

        不使用事务，仅允许查询操作，退出直接释放连接

        Usage:
        ```
        async with MySQLManager.read_only_cursor() as cur:
            sql = "..."
            await cur.execute(sql)
        ```
        """
        conn = await cls._acquire_healthy_conn()
        try:
            async with conn.cursor() as cur:
                cur: Cursor
                yield cur
        finally:
            await cls._release_conn_only(conn)

    @classmethod
    @asynccontextmanager
    async def manual_transaction_conn(cls):
        """### 手动管理事务（返回连接）
        
        正常退出时自动检测事务状态，若未提交/回滚则自动回滚并警告，异常退出时自动回滚并丢弃连接

        注意：事务结束必须 commit/rollback，若忘记则退出时自动回滚

        ```
        async with MySQLManager.manual_transaction_conn() as conn:
            async with conn.cursor() as cur:
                cur: Cursor
                sql = "..."
                await cur.execute(sql)
                await conn.commit()  # 手动提交
        ```
        """
        conn = await cls._acquire_healthy_conn()
        try:
            yield conn
        except Exception:
            # 异常 → 回滚并丢弃连接
            try:
                await conn.rollback()
            except Exception:
                pass
            await cls._discard_conn(conn)
            api_logger.warning("Manual transaction rolled back due to exception")
            raise
        else:
            # 正常退出 → 检测事务状态
            try:
                async with conn.cursor() as cur:
                    cur: Cursor
                    await cur.execute("SELECT @@in_transaction")
                    row = await cur.fetchone()
                    if row and row[0] == 1:
                        api_logger.warning("Manual transaction was not committed/rolled back, auto-rolling back!")
                        await conn.rollback()
            except Exception as e:
                api_logger.error(f"Failed to check/rollback transaction on exit: {e}")
            finally:
                # 正常释放连接
                await cls._release_conn_only(conn)