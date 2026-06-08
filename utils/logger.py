import os
from datetime import datetime


def log(message: str):
    """
    Writes timestamped log entries to stdout.
    GitHub Actions captures stdout automatically.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {message}"
    print(entry)

