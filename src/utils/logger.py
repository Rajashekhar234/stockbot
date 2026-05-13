"""Colorised logger with file rotation."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import colorlog

from config import LOG_DIR

_FMT = "%(asctime)s | %(levelname)-8s | %(name)-22s | %(message)s"
_COLOR_FMT = "%(log_color)s" + _FMT


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)

    ch = colorlog.StreamHandler()
    ch.setFormatter(colorlog.ColoredFormatter(_COLOR_FMT))
    logger.addHandler(ch)

    fh = RotatingFileHandler(
        Path(LOG_DIR) / "bot.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(logging.Formatter(_FMT))
    logger.addHandler(fh)

    logger.propagate = False
    return logger
