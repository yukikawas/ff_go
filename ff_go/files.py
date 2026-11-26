"""文件系统辅助：遍历、临时文件、原子替换。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Optional, Union

from .config import FRAMES_SUFFIX, LEGACY_TEMP_PREFIX, TEMP_PREFIX
from .errors import FFGoError, TempOutputError

PathLike = Union[str, "os.PathLike[str]"]


def extension_of(path: PathLike) -> str:
    """返回小写扩展名（不含点）；没有扩展名时返回空串。"""
    return Path(path).suffix.lower().lstrip(".")


def is_temp_name(name: str) -> bool:
    """判断是否为本工具产生的临时 / 半成品文件。"""
    return (
        name.startswith(TEMP_PREFIX)
        or name.startswith(LEGACY_TEMP_PREFIX)
        or name.startswith(".")
        or name.endswith(".ff_tmp")
    )


def iter_files(root: PathLike, exts: Optional[Iterable[str]] = None) -> List[Path]:
    """递归列出 root 下待处理的文件，结果按路径排序。

    exts 为允许的扩展名集合；为 None 表示所有文件。
    """
    base = Path(root)
    base.mkdir(parents=True, exist_ok=True)
    allowed = frozenset(exts) if exts is not None else None
    found: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(str(base)):
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not name.endswith(FRAMES_SUFFIX) and not name.startswith(".")
        )
        for name in sorted(filenames):
            if is_temp_name(name):
                continue
            path = Path(dirpath) / name
            if allowed is not None and extension_of(path) not in allowed:
                continue
            found.append(path)
    return found


def temp_path_for(source: PathLike, suffix: Optional[str] = None) -> Path:
    """返回源文件同目录下的临时文件路径（保持扩展名，便于 ffmpeg 推断格式）。"""
    src = Path(source)
    if suffix is None:
        return src.with_name(TEMP_PREFIX + src.name)
    return src.with_name(TEMP_PREFIX + src.stem + "." + suffix)


def discard(path: PathLike) -> None:
    """安静地删掉临时文件；不存在或删不掉都不报错。"""
    try:
        Path(path).unlink()
    except OSError:
        pass


def check_produced(path: PathLike) -> int:
    """确认 ffmpeg 真的产出了非空文件，返回大小；否则抛 TempOutputError。"""
    produced = Path(path)
    if not produced.is_file():
        raise TempOutputError("ffmpeg 未生成输出文件")
    size = produced.stat().st_size
    if size <= 0:
        raise TempOutputError("ffmpeg 生成的输出文件是空的")
    return size


def unique_path(target: PathLike) -> Path:
    """目标文件已存在时追加序号，避免覆盖别的文件。"""
    path = Path(target)
    if not path.exists():
        return path
    suffix = path.suffix
    stem = path.name[: -len(suffix)] if suffix else path.name
    for index in range(1, 1000):
        candidate = path.with_name("%s_%d%s" % (stem, index, suffix))
        if not candidate.exists():
            return candidate
    raise FFGoError("无法为 %s 生成不冲突的文件名" % path)


def replace(temp: PathLike, target: PathLike) -> None:
    """用临时文件原子替换目标文件。"""
    os.replace(str(temp), str(target))


def size_or_zero(path: PathLike) -> int:
    """取文件大小；取不到返回 0。"""
    try:
        return Path(path).stat().st_size
    except OSError:
        return 0
