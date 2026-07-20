"""Application logging setup."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from backend.config import Config


def configure_logging() -> logging.Logger:
    Config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("smart_crowd")
    if logger.handlers:
        return logger
    Config.create_directories()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    handler = RotatingFileHandler(Config.LOG_DIR / "application.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)
    return logger


logger = configure_logging()
