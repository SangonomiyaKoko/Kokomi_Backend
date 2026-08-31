import uuid
from pathlib import Path
from typing import Optional

from utils import get_current_iso_time
from settings import (
    LOG_DIR,
    CLIENT_NAME
)

def write_exception(
    error_type: str,
    error_name: str,
    error_info: Optional[str] = None,
    error_id: Optional[str] = None
):
    now_iso = get_current_iso_time()

    if error_id is None:
        error_id = str(uuid.uuid4())

    log_path = Path(LOG_DIR) / 'error' / f'{now_iso[:10]}.log'

    log_line = f"{now_iso[11:19]},{CLIENT_NAME},{error_name},{error_id}\n"

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(log_line)

    error_path = Path(LOG_DIR) / 'exception' / f'{error_id}.log'

    with open(error_path, "a", encoding="utf-8") as f:
        f.write(f"[FROM]:    {CLIENT_NAME}\n")
        f.write(f"[TIME]:    {now_iso}\n")
        f.write(f"[TYPE]:    {error_type}\n")
        f.write(f"[NAME]:    {error_name}\n")
        f.write("\n")
        f.write(error_info)