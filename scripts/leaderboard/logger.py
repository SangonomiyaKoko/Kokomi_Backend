import logging
import os
from logging.handlers import RotatingFileHandler

from settings import CLIENT_NAME, LOG_PATH

logger = logging.getLogger("scheduler")
logger.setLevel(logging.WARNING)

file_handler = RotatingFileHandler(
    filename= os.path.join(LOG_PATH, f"{CLIENT_NAME}_error.log"),
    maxBytes=50 * 1024 * 1024,  # 50MB
    backupCount=5,
    encoding="utf-8"
)
file_handler.setLevel(logging.WARNING)
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s"
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
