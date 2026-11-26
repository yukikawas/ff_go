"""运行期配置：路径发现、媒体扩展名、超时等常量。

本项目有意只依赖标准库，所以不做复杂的配置加载；
一个可选的 FF_GO_HOME 环境变量足以覆盖默认的项目根目录。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

APP_NAME = "ff_go"
ENV_HOME = "FF_GO_HOME"

#: 处理临时文件的前缀；放在源文件同目录，保证 os.replace 是同卷原子操作。
TEMP_PREFIX = "__fftmp__"
#: 旧版本留下的半成品前缀，遍历时一律跳过。
LEGACY_TEMP_PREFIX = "OUTPUT_TEMP_"
#: 帧序列输出目录的后缀，遍历时跳过。
FRAMES_SUFFIX = "_frames"

#: 单个文件的默认超时（秒）。
DEFAULT_TIMEOUT = 3600
#: 拆帧可能很慢，单独给一个更宽的超时。
FRAMES_TIMEOUT = 7200
#: 探测 / 版本检查这类轻量调用的超时。
PROBE_TIMEOUT = 60

IMAGE_EXTS = frozenset(
    {
        "jpg", "jpeg", "jpe", "jfif", "png", "bmp", "webp",
        "tif", "tiff", "gif", "heic", "heif", "avif", "ico",
    }
)
VIDEO_EXTS = frozenset(
    {
        "mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v",
        "mpg", "mpeg", "ts", "m2ts", "mts", "3gp", "3g2",
        "ogv", "rmvb", "rm", "vob",
    }
)
AUDIO_EXTS = frozenset(
    {"mp3", "wav", "flac", "aac", "m4a", "ogg", "opus", "wma", "aif", "aiff", "ac3", "ape"}
)
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS


def _is_project_root(path: Path) -> bool:
    """项目根目录的判定：同目录下有 libs/ 或 Media_Folder/。"""
    try:
        return (path / "libs").is_dir() or (path / "Media_Folder").is_dir()
    except OSError:
        return False


def _iter_candidates() -> List[Path]:
    candidates: List[Path] = []
    env = os.environ.get(ENV_HOME)
    if env:
        candidates.append(Path(env))
    cwd = Path.cwd()
    candidates.extend([cwd, *cwd.parents])
    pkg = Path(__file__).resolve().parent
    candidates.extend([pkg, *pkg.parents])
    return candidates


@lru_cache(maxsize=1)
def discover_root() -> Path:
    """找出项目根目录（放 libs/ 和 Media_Folder/ 的那一层）。

    查找顺序：FF_GO_HOME -> 当前工作目录及其父目录 -> 包所在目录及其父目录。
    都找不到时退回包目录，保证程序仍可启动（只是会提示找不到 ffmpeg）。
    """
    for candidate in _iter_candidates():
        if _is_project_root(candidate):
            return candidate
    return Path(__file__).resolve().parent


@dataclass(frozen=True)
class ProjectPaths:
    """一次运行用到的所有目录。"""

    root: Path

    @property
    def input_dir(self) -> Path:
        return self.root / "Media_Folder"

    @property
    def log_root(self) -> Path:
        return self.root / "ff-logs"

    @property
    def lib_dir(self) -> Path:
        return self.root / "libs"

    def tool(self, name: str) -> Optional[Path]:
        """在 libs/ 下找一个可执行文件，找到返回路径。"""
        for candidate in (name + ".exe", name):
            path = self.lib_dir / candidate
            try:
                if path.is_file():
                    return path
            except OSError:
                continue
        return None


@lru_cache(maxsize=1)
def paths() -> ProjectPaths:
    """返回当前项目的路径集合（进程内缓存）。"""
    return ProjectPaths(discover_root())


def reset_cache() -> None:
    """清空缓存，供测试在切换目录后重新发现根目录。"""
    discover_root.cache_clear()
    paths.cache_clear()
