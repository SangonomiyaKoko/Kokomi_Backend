#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import signal
import asyncio

from shard import ServicesName

from .core import start_scheduler
from .logger import logger
from .settings import (
    REGION,
    ENV_FILE,
    REFRESH_INTERVAL
)


async def main() -> None:
    """主函数，程序入口"""

    pid = os.getpid()
    logger.info('Service startup parameters:')
    logger.info('├─ Service:      %s', ServicesName.SEASON)
    logger.info('├─ Node region:  %s', REGION.upper())
    logger.info('├─ Env file:     %s', ENV_FILE)
    logger.info('├─ Refresh:      %s s', REFRESH_INTERVAL)
    logger.info('├─ Platform:     %s', os.name)
    logger.info('└─ Process ID:   %s', pid)

    # 启动调度器
    await start_scheduler(pid)

def _handler(*_):
    """信号处理器，退出"""
    logger.info('The process is closing')
    os._exit(0)

if __name__ == '__main__':
    if os.name != 'nt':
        signal.signal(signal.SIGTERM, _handler)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _handler()
