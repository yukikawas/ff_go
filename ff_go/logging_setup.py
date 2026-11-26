"""日志配置：每个工具一份按日期归档的文件日志。"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from .config import ProjectPaths

_FORMAT = "%(asctime)s:%(levelname)s:%(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def daily_log_dir(paths: ProjectPaths, when: Optional[time.struct_time] = None) -> Path:
    """返回 ff-logs/YYYYMMDD 目录（不创建）。"""
    stamp = time.strftime("%Y%m%d", when or time.localtime())
    return paths.log_root / stamp


def configure(paths: ProjectPaths, name: str, level: int = logging.DEBUG) -> logging.Logger:
    """配置并返回名为 ff_go.<name> 的 logger，日志写入 ff-logs/YYYYMMDD/name.log。"""
    log_dir = daily_log_dir(paths)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / (name + ".log")

    logger = logging.getLogger("ff_go." + name)
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.FileHandler(str(log_path), encoding="utf-8")
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter(_FORMAT, _DATEFMT))
        logger.addHandler(handler)
        logger.propagate = False
    return logger


def get(name: str) -> logging.Logger:
    """取一个可能尚未配置过的 logger。"""
    return logging.getLogger("ff_go." + name)
