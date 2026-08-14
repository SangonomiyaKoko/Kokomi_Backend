#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

from loggers import logger
from scheduler import start_scheduler
from settings import REGION, CLIENT_NAME, REFRESH_INTERVAL


def handler(*_):
    """信号处理器，退出"""
    logger.info('The process is closing')
    os._exit(0)


def main() -> None:
    """主函数，程序入口"""

    logger.info('Start running service: %s', CLIENT_NAME)
    logger.info('Service refresh interval: %s seconds', REFRESH_INTERVAL)
    logger.info('Current node region: %s', REGION.upper())

    # 启动调度器
    start_scheduler()


if __name__ == '__main__':
    if os.name != 'nt':
        # 在非Windows系统上注册SIGTERM信号处理器，在接收到SIGTERM信号时关闭服务
        import signal
        signal.signal(signal.SIGTERM, handler)

    try:
        main()
    except KeyboardInterrupt:
        # 在Windows系统上，无法捕获SIGTERM信号，但可以通过捕获KeyboardInterrupt异常来实现类似的功能
        handler()
