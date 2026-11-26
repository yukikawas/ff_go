"""ffmpeg / ffprobe 的定位与调用。

两条原则：

* 参数一律用列表传递，不经过 shell，文件名里的引号、&、| 都不会出问题；
* 调用失败时把 stderr 完整写进日志，控制台只显示压缩过的一行摘要。
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

from .config import DEFAULT_TIMEOUT, PROBE_TIMEOUT, ProjectPaths
from .errors import ToolNotFoundError

FFMPEG_HELP = (
    "{name}: 未找到可用的 ffmpeg。\n"
    "请从 https://github.com/BtbN/FFmpeg-Builds 下载 Windows 版 ffmpeg，\n"
    "把 ffmpeg.exe（以及同包的 ffprobe.exe）放到下面这个目录里：\n"
    "    {path}\n"
)


@dataclass(frozen=True)
class Toolchain:
    """一次运作用到的可执行文件集合。"""

    ffmpeg: Path
    ffprobe: Optional[Path] = None

    @classmethod
    def discover(cls, paths: ProjectPaths) -> "Toolchain":
        """在 libs/ 下找 ffmpeg 与 ffprobe。"""
        ffmpeg = paths.tool("ffmpeg")
        if ffmpeg is None:
            raise ToolNotFoundError(FFMPEG_HELP.format(name="ff_go", path=paths.lib_dir))
        return cls(ffmpeg=ffmpeg, ffprobe=paths.tool("ffprobe"))

    def require_ffprobe(self) -> Path:
        """需要 ffprobe 的操作调用它；缺失时抛出可读的错误。"""
        if self.ffprobe is None:
            raise ToolNotFoundError(
                "这个功能需要 ffprobe.exe，但 libs 目录里没有找到。\n"
                "请从同一个 FFmpeg 压缩包里把 ffprobe.exe 一起放进：\n"
                "    %s" % self.ffmpeg.parent
            )
        return self.ffprobe


@dataclass(frozen=True)
class CommandResult:
    """一次子进程调用的结果。"""

    ok: bool
    args: Sequence[str] = field(default_factory=tuple)
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""

    @property
    def summary(self) -> str:
        """把多行 stderr 压成一行，供控制台显示。"""
        flat = " ".join(self.stderr.split())
        if not flat:
            return ""
        return flat[:157] + "..." if len(flat) > 160 else flat


def _decode(raw: Optional[bytes]) -> str:
    if not raw:
        return ""
    return raw.decode("utf-8", "replace").strip()


def run(
    executable: Path,
    args: Sequence[object],
    *,
    prefix: Sequence[str] = ("-hide_banner", "-nostdin"),
    loglevel: str = "error",
    timeout: int = DEFAULT_TIMEOUT,
    logger: Optional[logging.Logger] = None,
) -> CommandResult:
    """执行一次可执行文件，返回结构化结果；不抛异常，由调用方判断 ok。"""
    cmd: List[str] = [str(executable)]
    cmd.extend(prefix)
    if loglevel:
        cmd.extend(["-loglevel", loglevel])
    cmd.extend(str(arg) for arg in args)

    if logger is not None:
        logger.debug("CMD: %s", subprocess.list2cmdline(cmd))

    try:
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        message = "命令超过 %s 秒未结束，已放弃" % timeout
        if logger is not None:
            logger.error("%s | %s", message, subprocess.list2cmdline(cmd))
        return CommandResult(False, tuple(cmd), -1, "", message)
    except OSError as exc:
        message = "无法启动 %s：%s" % (executable.name, exc)
        if logger is not None:
            logger.error("%s | %s", message, subprocess.list2cmdline(cmd))
        return CommandResult(False, tuple(cmd), -1, "", message)

    stdout = _decode(proc.stdout)
    stderr = _decode(proc.stderr)
    ok = proc.returncode == 0
    if logger is not None:
        if ok:
            if stderr:
                logger.debug("stderr: %s", stderr)
        else:
            logger.error(
                "退出码 %s | %s\n%s", proc.returncode, subprocess.list2cmdline(cmd), stderr
            )
    return CommandResult(ok, tuple(cmd), proc.returncode, stdout, stderr)


def run_ffmpeg(
    tools: Toolchain,
    args: Sequence[object],
    *,
    loglevel: str = "error",
    timeout: int = DEFAULT_TIMEOUT,
    logger: Optional[logging.Logger] = None,
) -> CommandResult:
    """用 ffmpeg 执行一条命令（自动补上 -y，方便覆盖临时文件）。"""
    full: List[object] = ["-y"]
    full.extend(args)
    return run(
        tools.ffmpeg, full, loglevel=loglevel, timeout=timeout, logger=logger
    )


def run_variants(
    tools: Toolchain,
    variants: Sequence[Sequence[object]],
    *,
    timeout: int = DEFAULT_TIMEOUT,
    logger: Optional[logging.Logger] = None,
) -> CommandResult:
    """依次尝试多套参数，返回第一套成功的；全失败则返回最后一次结果。"""
    last = CommandResult(False, (), -1, "", "没有可用的参数组合")
    for index, args in enumerate(variants):
        result = run_ffmpeg(tools, args, timeout=timeout, logger=logger)
        if result.ok:
            if index and logger is not None:
                logger.info("第 %d 套参数可用", index + 1)
            return result
        last = result
        if logger is not None:
            logger.debug("第 %d 套参数失败：%s", index + 1, result.summary)
    return last


def version(tools: Toolchain) -> str:
    """返回 ffmpeg 版本行（第一行）。"""
    result = run(tools.ffmpeg, ["-version"], prefix=(), timeout=PROBE_TIMEOUT)
    if not result.ok or not result.stdout:
        return "unknown"
    return result.stdout.splitlines()[0]
