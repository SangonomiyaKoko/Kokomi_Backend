import os
import csv
import queue

from app.core import API_LOG_PATH


log_queue = queue.Queue(maxsize=1000)

HEADER = [
    "timestamp",   # 时间戳
    "client_ip",   # 请求客户端 IP
    "method",      # HTTP 方法 GET/POST...
    "url",         # 请求路径
    "status_code", # 响应状态码
    "elapsed_ms",  # 接口耗时（毫秒）
]

class CSVWriter:
    """负责将日志记录写入 CSV 文件，按日期自动切分文件"""

    def __init__(self):
        self.current_date = None  # 当前文件对应日期
        self.file = None          # 当前打开的文件对象
        self.writer = None        # csv.writer 对象

    def _open_file(self, date_str: str):
        # 如果之前有打开的文件，先关闭
        if self.file:
            self.file.close()
        file_path = os.path.join(API_LOG_PATH, f"{date_str}.csv")
        file_exists = os.path.exists(file_path)
        self.file = open(file_path, "a", newline="", encoding="utf-8")
        self.writer = csv.writer(self.file)
        if not file_exists:  # 新文件，写入表头
            self.writer.writerow(HEADER)
        self.current_date = date_str  # 更新当前日期

    def write(self, record: list):
        # 取 timestamp 的日期部分作为文件名
        date_str = record[0][:10]  # YYYY-MM-DD
        if date_str != self.current_date:
            self._open_file(date_str)

        # 写入 CSV
        self.writer.writerow(record)
        self.file.flush()

    # 关闭当前文件
    def close(self):
        if self.file:
            self.file.close()



