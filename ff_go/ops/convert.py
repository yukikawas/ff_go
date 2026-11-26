"""转换：把媒体文件转成指定格式。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from ..config import DEFAULT_TIMEOUT, IMAGE_EXTS, MEDIA_EXTS, VIDEO_EXTS
from ..console import human_size, say
from ..errors import FFGoError
from ..ffmpeg import run_variants
from ..files import (
    check_produced,
    discard,
    extension_of,
    replace,
    size_or_zero,
    temp_path_for,
    unique_path,
)
from .common import BatchStats, Context, ItemResult, collect, run_batch

#: 目标格式只允许字母数字，杜绝拼出路径或空格式。
FORMAT_PATTERN = re.compile(r"^[A-Za-z0-9]{1,8}$")


def valid_format(value: str) -> bool:
    """校验用户输入的目标格式。"""
    return bool(FORMAT_PATTERN.match(value.strip()))


@dataclass(frozen=True)
class ConvertOptions:
    """转换选项。"""

    target_format: str
    timeout: int = DEFAULT_TIMEOUT


def convert_one(ctx: Context, path: Path, options: ConvertOptions) -> ItemResult:
    """转换单个文件：成功后才删除原文件。"""
    target_format = options.target_format.lower()
    source_ext = extension_of(path)
    if source_ext == target_format:
        return ItemResult.skipped("已经是 %s 格式" % target_format)
    if source_ext in VIDEO_EXTS and target_format in IMAGE_EXTS:
        # ffmpeg 只会写第一帧，随后又删掉源视频，等于丢内容。
        return ItemResult.skipped("视频转图片序列请用「视频拆帧」功能")

    target = unique_path(path.with_name(path.stem + "." + target_format))
    temp = temp_path_for(path, suffix=target_format)
    before = size_or_zero(path)

    try:
        result = run_variants(
            ctx.tools,
            [["-i", str(path), str(temp)]],
            timeout=options.timeout,
            logger=ctx.logger,
        )
        if not result.ok:
            discard(temp)
            return ItemResult.failed(result.summary or "ffmpeg 失败")
        after = check_produced(temp)
    except FFGoError as exc:
        discard(temp)
        return ItemResult.failed(str(exc))

    try:
        replace(temp, target)
    except OSError as exc:
        discard(temp)
        return ItemResult.failed("写入目标文件失败：%s" % exc)

    note = ""
    try:
        os.remove(str(path))
    except OSError as exc:
        note = "（原文件删除失败，已保留：%s）" % exc

    return ItemResult.ok(
        "%s -> %s（%s -> %s）%s"
        % (path.name, target.name, human_size(before), human_size(after), note),
        before=before,
        after=after,
    )


def run(ctx: Context, options: ConvertOptions) -> BatchStats:
    """批量转换 Media_Folder。"""
    files = collect(ctx.paths, MEDIA_EXTS)
    total = len(files)
    say("一共有 %d 个待处理文件，目标格式 %s" % (total, options.target_format))
    ctx.logger.info("convert: %d files -> %s", total, options.target_format)
    if not files:
        say("Media_Folder 里没有可处理的文件，先放点素材再运行。")
        return BatchStats()

    return run_batch(
        files,
        lambda path: convert_one(ctx, path, options),
        logger=ctx.logger,
        verb="转换完成",
    )


__all__ = ["ConvertOptions", "convert_one", "run", "valid_format"]
