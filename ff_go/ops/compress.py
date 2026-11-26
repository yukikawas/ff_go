"""压缩：重新编码媒体文件，只有变小才替换原文件。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

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
)
from .common import BatchStats, Context, ItemResult, collect, run_batch

#: 视频压缩：H.264 CRF 28 + AAC 128k，兼顾体积与观感。
VIDEO_ARGS: Sequence[str] = (
    "-c:v", "libx264",
    "-crf", "28",
    "-preset", "veryfast",
    "-c:a", "aac",
    "-b:a", "128k",
)

#: 各格式的压缩参数；空表示交给 ffmpeg 默认值。
QUALITY_ARGS = {
    "jpg": ["-q:v", "5"],
    "jpeg": ["-q:v", "5"],
    "png": ["-compression_level", "9"],
    "webp": ["-quality", "75"],
    "mp3": ["-c:a", "libmp3lame", "-b:a", "128k"],
    "aac": ["-c:a", "aac", "-b:a", "128k"],
    "m4a": ["-c:a", "aac", "-b:a", "128k"],
    "ogg": ["-c:a", "libopus", "-b:a", "96k"],
    "opus": ["-c:a", "libopus", "-b:a", "96k"],
    "flac": ["-compression_level", "8"],
}


@dataclass(frozen=True)
class CompressOptions:
    """压缩选项。"""

    timeout: int = DEFAULT_TIMEOUT
    only_images: bool = False


def quality_args(ext: str) -> List[str]:
    """按扩展名返回编码参数。"""
    if ext in VIDEO_EXTS:
        return list(VIDEO_ARGS)
    return list(QUALITY_ARGS.get(ext, []))


def compress_one(ctx: Context, path: Path, options: CompressOptions) -> ItemResult:
    """压缩单个文件：先写临时文件，确认变小才原子替换。"""
    temp = temp_path_for(path)
    ext = extension_of(path)
    before = size_or_zero(path)
    if before <= 0:
        return ItemResult.skipped("文件是空的")

    # 编码参数必须放在 -i 之后、输出之前，否则会被当成输入解码器选项。
    variants: List[Sequence[object]] = [
        ["-i", str(path)] + quality_args(ext) + [str(temp)],
        ["-i", str(path), str(temp)],
    ]

    try:
        result = run_variants(ctx.tools, variants, timeout=options.timeout, logger=ctx.logger)
        if not result.ok:
            discard(temp)
            return ItemResult.failed(result.summary or "ffmpeg 失败")

        after = check_produced(temp)
    except FFGoError as exc:
        discard(temp)
        return ItemResult.failed(str(exc))

    if after >= before:
        discard(temp)
        return ItemResult.skipped(
            "压缩后没有变小（%s -> %s），保留原文件"
            % (human_size(before), human_size(after))
        )

    try:
        replace(temp, path)
    except OSError as exc:
        discard(temp)
        return ItemResult.failed("替换原文件失败：%s" % exc)

    saved = (before - after) * 100.0 / before
    return ItemResult.ok(
        "%s -> %s（省 %.1f%%）" % (human_size(before), human_size(after), saved),
        before=before,
        after=after,
    )


def run(ctx: Context, options: Optional[CompressOptions] = None) -> BatchStats:
    """批量压缩 Media_Folder。"""
    opts = options or CompressOptions()
    exts = IMAGE_EXTS if opts.only_images else MEDIA_EXTS
    files = collect(ctx.paths, exts)

    say("在 %s 检测到 %d 个媒体文件" % (ctx.paths.input_dir, len(files)))
    ctx.logger.info("compress: %d files", len(files))
    if not files:
        say("没有需要压缩的文件，把素材放进 Media_Folder 再运行。")
        return BatchStats()

    return run_batch(
        files,
        lambda path: compress_one(ctx, path, opts),
        logger=ctx.logger,
        verb="压缩完成",
    )


__all__ = [
    "CompressOptions",
    "QUALITY_ARGS",
    "VIDEO_ARGS",
    "compress_one",
    "quality_args",
    "run",
]
