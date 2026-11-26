"""测试辅助：把临时目录放在仓库内，避免依赖系统 TEMP 的权限。

注意：这里不用 tempfile.mkdtemp —— 它在 Windows 上会把目录设成仅属主可访问，
在某些受限令牌下反而写不进去。普通 mkdir 继承父目录权限，最稳。
"""

from __future__ import annotations

import contextlib
import itertools
import os
import shutil
from pathlib import Path
from typing import Iterator

_TMP_ROOT = Path(__file__).resolve().parent / "_tmp"
_counter = itertools.count(1)


@contextlib.contextmanager
def temp_dir() -> Iterator[Path]:
    """创建并自动清理一个临时目录。"""
    _TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = _TMP_ROOT / ("t-%d-%d" % (os.getpid(), next(_counter)))
    path.mkdir(exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(str(path), ignore_errors=True)
