"""控制台输出与交互。

只负责“怎么显示”，不掺业务逻辑；所有中文输出都走 say()，
这样在非 UTF-8 控制台上也不会抛 UnicodeEncodeError。
"""

from __future__ import annotations

import sys
import unicodedata
from typing import Callable, Iterable, Optional, Sequence

from .errors import Cancelled


def display_width(text: str) -> int:
    """按终端显示宽度计算字符串长度（中日韩字符算 2 格）。"""
    width = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return width


def pad(text: str, width: int, align: str = "left") -> str:
    """按显示宽度补齐到 width。"""
    gap = max(0, width - display_width(text))
    if align == "right":
        return " " * gap + text
    return text + " " * gap


def _raw_print(text: str) -> None:
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        safe = text.encode(encoding, "replace").decode(encoding, "replace")
        print(safe, flush=True)


def say(message: object = "") -> None:
    """打印一行。"""
    _raw_print(str(message))


def rule(title: str = "", width: int = 62) -> None:
    """打印一条分隔线，可带居中标题。"""
    if not title:
        say("=" * width)
        return
    label = " %s " % title
    left = max(0, (width - display_width(label)) // 2)
    say("=" * left + label + "=" * max(0, width - left - display_width(label)))


def table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    """打印对齐的表格；中文按双宽计算，避免串列。"""
    body = [[str(cell) for cell in row] for row in rows]
    widths = [display_width(str(header)) for header in headers]
    for row in body:
        for index, cell in enumerate(row):
            if index < len(widths):
                widths[index] = max(widths[index], display_width(cell))
    say("  ".join(pad(str(header), widths[i]) for i, header in enumerate(headers)))
    say("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in body:
        say("  ".join(pad(cell, widths[i]) for i, cell in enumerate(row)))


def human_size(num_bytes: float) -> str:
    """把字节数格式化成易读字符串。"""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0:
            return ("%d %s" % (int(size), unit)) if unit == "B" else ("%.1f %s" % (size, unit))
        size /= 1024.0
    return "%.1f TB" % size


def human_duration(seconds: Optional[float]) -> str:
    """把秒数格式化成 h:mm:ss 或 m:ss。"""
    if not seconds or seconds <= 0:
        return "-"
    total = int(round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%d:%02d" % (minutes, secs)


def _read_line(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError as exc:
        say("")
        raise Cancelled("没有读到输入（标准输入已关闭）") from exc
    except KeyboardInterrupt as exc:
        say("")
        raise Cancelled("用户取消") from exc


def prompt_text(
    prompt: str,
    default: str = "",
    validate: Optional[Callable[[str], bool]] = None,
    error_message: str = "输入不合法，请重新输入",
) -> str:
    """读一行文本；空输入取默认值，validate 不通过则重问。"""
    while True:
        suffix = "（默认 %s）" % default if default else ""
        raw = _read_line("%s%s " % (prompt, suffix))
        value = raw.strip() or default
        if not value:
            say(error_message)
            continue
        if validate is not None and not validate(value):
            say(error_message)
            continue
        return value


def prompt_int(prompt: str, default: int, minimum: int = 1, maximum: int = 1000000) -> int:
    """读一个整数。"""

    def _valid(text: str) -> bool:
        try:
            number = int(text)
        except ValueError:
            return False
        return minimum <= number <= maximum

    value = prompt_text(
        prompt,
        default=str(default),
        validate=_valid,
        error_message="请输入 %d 到 %d 之间的整数" % (minimum, maximum),
    )
    return int(value)


def prompt_yes_no(prompt: str, default: bool = True) -> bool:
    """读一个是/否。"""
    hint = "Y/n" if default else "y/N"
    while True:
        raw = _read_line("%s [%s] " % (prompt, hint)).strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes", "是", "1"):
            return True
        if raw in ("n", "no", "否", "0"):
            return False
        say("请输入 y 或 n")


def choose(title: str, options: Sequence[str], default: int = 1, allow_cancel: bool = True) -> int:
    """显示编号菜单并返回 1-based 选项号；allow_cancel 时 0 表示返回。"""
    if title:
        say("")
        say(title)
    for index, option in enumerate(options, 1):
        say("  %d) %s" % (index, option))
    if allow_cancel:
        say("  0) 返回")
    while True:
        raw = _read_line("请选择 [%d]: " % default).strip()
        if not raw:
            return default
        if raw.isdigit():
            value = int(raw)
            if value == 0 and allow_cancel:
                return 0
            if 1 <= value <= len(options):
                return value
        say("请输入 0 到 %d 之间的数字" % len(options))


def pause() -> None:
    """结束前停一下，方便双击运行；非交互环境直接跳过。"""
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return
    except (AttributeError, ValueError):
        return
    try:
        input("\n处理结束，按回车键退出...")
    except (EOFError, KeyboardInterrupt):
        say("")
