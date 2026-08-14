#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import signal
import asyncio

from loggers import logger
from scheduler import start_scheduler
from settings import REGION, CLIENT_NAME, REFRESH_INTERVAL


def handler(*_):
    """信号处理器，退出"""
    logger.info('The process is closing')
    os._exit(0)


async def main() -> None:
    """主函数，程序入口"""
    
    logger.info('Start running service: %s', CLIENT_NAME)
    logger.info('Service refresh interval: %s seconds', REFRESH_INTERVAL)
    logger.info('Current node region: %s', REGION.upper())

    # 启动调度器
    await start_scheduler()


if __name__ == '__main__':
    if os.name != 'nt':
        signal.signal(signal.SIGTERM, handler)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        handler()