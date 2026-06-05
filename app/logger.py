"""
logger.py — Structured, rotating-file logger for the ingestion platform.

Creates a named logger that writes to:
  • stdout  (for container / terminal visibility)
  • logs/scraper_YYYYMMDD.log  (daily rotating file)
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

from app.config import settings


def setup_logger(name: str = "platform") -> logging.Logger:
    """Return a configured logger with console + rotating-file handlers."""

    logger = logging.getLogger(name)
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)

    if logger.handlers:
        return logger  # avoid duplicate handlers on reimport

    fmt = logging.Formatter(
        "[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── Console ─────────────────────────────────────
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # ── Rotating file ───────────────────────────────
    os.makedirs(settings.LOG_DIR, exist_ok=True)
    log_file = os.path.join(
        settings.LOG_DIR,
        f"scraper_{datetime.now().strftime('%Y%m%d')}.log",
    )
    file_h = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB per file
        backupCount=30,              # keep 30 rotated copies
    )
    file_h.setFormatter(fmt)
    logger.addHandler(file_h)

    return logger


logger = setup_logger()
