import os

DATA_DIR = '/app/data'
LOG_DIR = '/app/logs'

ERROR_LOG_PATH = os.path.join(LOG_DIR, "error")
API_LOG_PATH = os.path.join(LOG_DIR, "metrics")
BACKUP_PATH = os.path.join(DATA_DIR, "backup")
JSON_FILE_PATH = os.path.join(DATA_DIR, "json")
DB_FILE_PATH = os.path.join(DATA_DIR, "db")