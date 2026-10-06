import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from config import settings

def setup_logger(name: str = "library") -> logging.Logger:
    logger = logging.getLogger()
    logger.setLevel(settings.log_level.upper())

    if logger.handlers:
        return logger

    # Log formatters
    console_formatter = logging.Formatter("[%(levelname)s %(message)s]")
    file_formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(filename)s:%(lineno)d | %(message)s")

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler
    log_directory = Path("logs")
    log_directory.mkdir(exist_ok = True)
    file_handler = RotatingFileHandler(
        log_directory / "library.log",
        maxBytes = 10 * (1024 ** 2), # 10 MBs
        backupCount = 10,
        encoding = "utf-8"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger

logger = setup_logger()