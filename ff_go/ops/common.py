"""批处理公共部分：结果、统计、统一的进度输出。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence

from .. import console
from ..config import ProjectPaths
from ..ffmpeg import Toolchain

STATUS_OK = "ok"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"


@dataclass(frozen=True)
class ItemResult:
    """单个文件的处理结果。"""

    status: str
    detail: str = ""
    before: int = 0
    after: int = 0

    @classmethod
    def ok(cls, detail: str = "", before: int = 0, after: int = 0) -> "ItemResult":
        return cls(STATUS_OK, detail, before, after)

    @classmethod
    def skipped(cls, detail: str = "") -> "ItemResult":
        return cls(STATUS_SKIPPED, detail)

    @classmethod
    def failed(cls, detail: str = "") -> "ItemResult":
        return cls(STATUS_FAILED, detail)


@dataclass
class BatchStats:
    """一批文件处理完后的统计。"""

    ok: int = 0
    skipped: int = 0
    failed: int = 0
    bytes_before: int = 0
    bytes_after: int = 0

    def add(self, result: ItemResult) -> None:
        if result.status == STATUS_OK:
            self.ok += 1
        elif result.status == STATUS_SKIPPED:
            self.skipped += 1
        else:
            self.failed += 1
        if result.before:
            self.bytes_before += result.before
            self.bytes_after += result.after or result.before

    @property
    def total(self) -> int:
        return self.ok + self.skipped + self.failed

    @property
    def saved_bytes(self) -> int:
        return max(0, self.bytes_before - self.bytes_after)

    @property
    def saved_ratio(self) -> float:
        if not self.bytes_before:
            return 0.0
        return self.saved_bytes * 100.0 / self.bytes_before

    @property
    def exit_code(self) -> int:
        return 0 if self.failed == 0 else 1

    def render(self, title: str) -> None:
        console.rule(title)
        console.say(
            "成功 %d / 跳过 %d / 失败 %d"
            % (self.ok, self.skipped, self.failed)
        )
        if self.bytes_before:
            console.say(
                "体积 %s -> %s（省 %s，%.1f%%）"
                % (
                    console.human_size(self.bytes_before),
                    console.human_size(self.bytes_after),
                    console.human_size(self.saved_bytes),
                    self.saved_ratio,
                )
            )


@dataclass(frozen=True)
class Context:
    """一次运行共享的上下文。"""

    paths: ProjectPaths
    tools: Toolchain
    logger: logging.Logger


Worker = Callable[[Path], ItemResult]


def run_batch(
    items: Sequence[Path],
    worker: Worker,
    *,
    logger: logging.Logger,
    verb: str,
) -> BatchStats:
    """逐个处理并打印进度；单个文件失败不打断整批。"""
    stats = BatchStats()
    total = len(items)
    for index, path in enumerate(items, 1):
        label = "%s (%d/%d)" % (path.name, index, total)
        try:
            result = worker(path)
        except Exception as exc:  # noqa: BLE001 - 批处理必须继续
            logger.exception("处理 %s 时出现未预期的异常", path)
            result = ItemResult.failed("意外错误：%s" % exc)

        stats.add(result)
        if result.status == STATUS_OK:
            message = "%s：%s | %s" % (verb, label, result.detail)
            logger.info(message)
            console.say(message)
        elif result.status == STATUS_SKIPPED:
            message = "跳过：%s | %s" % (label, result.detail)
            logger.info(message)
            console.say(message)
        else:
            logger.error("失败：%s | %s", label, result.detail)
            console.say("失败：%s | %s（原文件已保留）" % (label, result.detail))
    return stats


def collect(paths: ProjectPaths, exts: Optional[Iterable[str]]) -> List[Path]:
    """按扩展名收集待处理文件。"""
    from ..files import iter_files

    return iter_files(paths.input_dir, exts)
