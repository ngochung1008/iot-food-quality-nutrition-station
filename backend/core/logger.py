"""Hệ thống ghi log chuẩn UTF-8 hỗ trợ cả Console và RotatingFileHandler."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from backend.core.config import settings


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Cấu hình logger dùng chung cho toàn dự án, an toàn với tiếng Việt trên Windows/Linux."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    root_logger = logging.getLogger("nutrition_station")
    if root_logger.handlers:
        return root_logger

    root_logger.setLevel(level)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    try:
        log_dir: Path = settings.root_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "station.log",
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception:
        # Không làm sập ứng dụng nếu không ghi được file log
        pass

    return root_logger


logger = setup_logging(logging.DEBUG if settings.debug else logging.INFO)
