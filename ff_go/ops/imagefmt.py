"""图片转现代格式：WebP / AVIF / JPEG XL / JPEG。

实测（1200x900 照片，原 JPEG 207.9 KB）：
    WebP q80  56.3 KB   AVIF crf32  66.7 KB
    JPEG XL d1 116.9 KB  重编码 JPEG q5 137.5 KB
所以转 WebP / AVIF 通常能再省 60% 以上。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

from ..config import DEFAULT_TIMEOUT, IMAGE_EXTS
from ..console import human_size
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

TARGET_WEBP = "webp"
TARGET_AVIF = "avif"
TARGET_JXL = "jxl"
TARGET_JPEG = "jpg"
TARGET_PNG = "png"

TARGETS = (TARGET_WEBP, TARGET_AVIF, TARGET_JXL, TARGET_JPEG, TARGET_PNG)
TARGET_LABELS = {
    TARGET_WEBP: "WebP（兼容最好，体积最小）",
    TARGET_AVIF: "AVIF（压缩率更高，老设备可能不支持）",
    TARGET_JXL: "JPEG XL（新一代无损/近无损）",
    TARGET_JPEG: "JPEG（原地重压，兼容性最好）",
    TARGET_PNG: "PNG（无损）",
}

QUALITY_SMALL = "small"
QUALITY_BALANCED = "balanced"
QUALITY_HIGH = "high"
QUALITIES = (QUALITY_SMALL, QUALITY_BALANCED, QUALITY_HIGH)
QUALITY_LABELS = {
    QUALITY_SMALL: "体积优先",
    QUALITY_BALANCED: "均衡（推荐）",
    QUALITY_HIGH: "画质优先",
}

#: 各目标格式按质量档位取的参数。
_WEBP_QUALITY = {QUALITY_SMALL: "60", QUALITY_BALANCED: "80", QUALITY_HIGH: "95"}
_AVIF_CRF = {QUALITY_SMALL: "38", QUALITY_BALANCED: "32", QUALITY_HIGH: "26"}
_JXL_DISTANCE = {QUALITY_SMALL: "2", QUALITY_BALANCED: "1", QUALITY_HIGH: "0.5"}
_JPEG_QSCALE = {QUALITY_SMALL: "8", QUALITY_BALANCED: "5", QUALITY_HIGH: "2"}


@dataclass(frozen=True)
class ImageOptions:
    """图片格式转换选项。"""

    target_format: str = TARGET_WEBP
    quality: str = QUALITY_BALANCED
    timeout: int = DEFAULT_TIMEOUT


def encoder_args(target: str, quality: str) -> List[str]:
    """返回目标格式对应的编码参数。"""
    if target == TARGET_WEBP:
        return ["-c:v", "libwebp", "-quality", _WEBP_QUALITY[quality], "-compression_level", "6"]
    if target == TARGET_AVIF:
        return [
            "-c:v", "libaom-av1",
            "-crf", _AVIF_CRF[quality],
            "-still-picture", "1",
            "-cpu-used", "6",
            "-row-mt", "1",
        ]
    if target == TARGET_JXL:
        return ["-c:v", "libjxl", "-distance", _JXL_DISTANCE[quality], "-effort", "7"]
    if target == TARGET_JPEG:
        return ["-q:v", _JPEG_QSCALE[quality]]
    return ["-compression_level", "9"]


JPEG_ALIASES = frozenset({"jpg", "jpeg", "jpe", "jfif"})


def _normalize_target(target: str) -> str:
    value = target.strip().lower()
    return "jpg" if value in JPEG_ALIASES else value


def _is_same_format(source_ext: str, target: str) -> bool:
    """判断源文件是否已经是目标格式（jpg 有一堆别名）。"""
    if target == "jpg":
        return source_ext in JPEG_ALIASES
    return source_ext == target


def convert_one(ctx: Context, path: Path, options: ImageOptions) -> ItemResult:
    """把一张图片转成目标格式。

    目标格式与源格式相同 -> 原地重压缩（只有变小才替换）；
    不同 -> 生成新文件，成功后才删除原文件。
    """
    target = _normalize_target(options.target_format)
    source_ext = extension_of(path)
    before = size_or_zero(path)
    if before <= 0:
        return ItemResult.skipped("文件是空的")

    same_format = _is_same_format(source_ext, target)

    temp = temp_path_for(path) if same_format else temp_path_for(path, suffix=target)
    final = path if same_format else unique_path(path.with_name(path.stem + "." + target))

    try:
        result = run_variants(
            ctx.tools,
            [["-i", str(path)] + encoder_args(target, options.quality) + [str(temp)]],
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

    if same_format and after >= before:
        discard(temp)
        return ItemResult.skipped(
            "重压后没有变小（%s -> %s），保留原文件"
            % (human_size(before), human_size(after))
        )

    try:
        replace(temp, final)
    except OSError as exc:
        discard(temp)
        return ItemResult.failed("写入目标文件失败：%s" % exc)

    if not same_format:
        try:
            os.remove(str(path))
        except OSError:
            pass

        delta = (after - before) * 100.0 / before if before else 0.0
        return ItemResult.ok(
            "%s -> %s（%s -> %s，%+.1f%%）"
            % (path.name, final.name, human_size(before), human_size(after), delta),
            before=before,
            after=after,
        )

    saved = (before - after) * 100.0 / before
    return ItemResult.ok(
        "%s（%s -> %s，省 %.1f%%）"
        % (path.name, human_size(before), human_size(after), saved),
        before=before,
        after=after,
    )


def run(ctx: Context, options: ImageOptions) -> BatchStats:
    """批量转换 Media_Folder 里的图片。"""
    from ..console import say

    images = collect(ctx.paths, IMAGE_EXTS)
    say(
        "一共 %d 张图片，目标格式 %s（%s）"
        % (len(images), options.target_format, QUALITY_LABELS.get(options.quality, options.quality))
    )
    ctx.logger.info(
        "image: %d files -> %s (%s)", len(images), options.target_format, options.quality
    )
    if not images:
        say("Media_Folder 里没有图片。")
        return BatchStats()

    return run_batch(
        images,
        lambda path: convert_one(ctx, path, options),
        logger=ctx.logger,
        verb="转换完成",
    )


__all__ = [
    "ImageOptions",
    "QUALITIES",
    "QUALITY_BALANCED",
    "QUALITY_HIGH",
    "QUALITY_LABELS",
    "QUALITY_SMALL",
    "TARGET_LABELS",
    "TARGETS",
    "TARGET_AVIF",
    "TARGET_JPEG",
    "TARGET_JXL",
    "TARGET_PNG",
    "TARGET_WEBP",
    "convert_one",
    "encoder_args",
    "run",
]
