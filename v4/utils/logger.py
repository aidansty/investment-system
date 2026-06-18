import logging
from datetime import datetime
import pytz

def get_logger(name: str = "investment_system_v4") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        eastern = pytz.timezone("America/New_York")
        
        class ETFormatter(logging.Formatter):
            def formatTime(self, record, datefmt=None):
                ct = datetime.fromtimestamp(record.created, eastern)
                return ct.strftime("%Y-%m-%d %H:%M:%S ET")
        
        handler.setFormatter(ETFormatter("[%(asctime)s] %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

log = get_logger()


# Callable wrapper so log("message") works alongside log.info("message")
class _CallableLogger:
    def __init__(self, logger):
        self._logger = logger

    def __call__(self, msg):
        self._logger.info(msg)

    def info(self, msg):
        self._logger.info(msg)

    def warning(self, msg):
        self._logger.warning(msg)

    def error(self, msg):
        self._logger.error(msg)

    def debug(self, msg):
        self._logger.debug(msg)

log = _CallableLogger(get_logger())
