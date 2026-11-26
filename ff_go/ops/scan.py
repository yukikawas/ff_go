"""体检扫描：只读地分析 Media_Folder，给出体积与问题报告。

不会修改任何文件；深度扫描时额外跑 blackdetect / silencedetect / freezedetect。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ..config import MEDIA_EXTS
from ..console import say
from ..files import extension_of, size_or_zero
from ..media import MediaInfo, detect, probe
from ..reports import Advice, ScanEntry, ScanReport
from .common import Context, collect

#: 各类素材的经验压缩率，用于估算"还能省多少"。
IMAGE_SAVING = 0.55
VIDEO_SAVING = 0.40
AUDIO_SAVING = 0.70
DOWNSCALE_SAVING = 0.30

LOSSLESS_IMAGE = frozenset({"png", "bmp", "tif", "tiff"})
LOSSLESS_AUDIO = frozenset({"flac", "wav", "aiff", "ape"})


@dataclass(frozen=True)
class ScanOptions:
    """扫描选项。"""

    deep: bool = False
    json_path: Optional[Path] = None


def advise(info: MediaInfo, size: int) -> Optional[Advice]:
    """按经验规则给出一条最有价值的建议（避免重复计算收益）。"""
    suffix = extension_of(info.path)
    category = info.category

    if category == "video":
        if info.height and info.height > 1080:
            return Advice(
                "限制到 1080p",
                "分辨率 %s 高于 1080p" % info.resolution,
                int(size * DOWNSCALE_SAVING),
            )
        if info.video_codec in ("h264", "mpeg4", "wmv3", "msmpeg4v3", "vp8"):
            return Advice(
                "转 H.265",
                "当前编码 %s，同画质可再省约 40%%" % (info.video_codec or "未知"),
                int(size * VIDEO_SAVING),
            )
        return None

    if category == "audio":
        if suffix in LOSSLESS_AUDIO:
            return Advice(
                "转 MP3/AAC",
                "无损音频，转有损可省很多",
                int(size * AUDIO_SAVING),
            )
        return None

    if suffix in LOSSLESS_IMAGE or suffix in ("jpg", "jpeg"):
        return Advice(
            "转 WebP",
            "实测同画质可省 50% 以上",
            int(size * IMAGE_SAVING),
        )
    return None


def scan_one(ctx: Context, path: Path, options: ScanOptions) -> ScanEntry:
    """扫描单个文件；任何失败都记录在条目里，不抛异常。"""
    size = size_or_zero(path)
    try:
        info = probe(ctx.tools, path, logger=ctx.logger)
    except Exception as exc:  # noqa: BLE001 - 单个文件失败不影响整批
        ctx.logger.warning("探测失败 %s: %s", path, exc)
        return ScanEntry(path=path, size=size, error=str(exc))

    detections = []
    if options.deep and (info.is_video or info.audio_codec):
        kinds = ("black", "freeze", "silence") if info.is_video else ("silence",)
        try:
            detections = detect(ctx.tools, path, kinds, logger=ctx.logger)
        except Exception as exc:  # noqa: BLE001
            ctx.logger.warning("检测失败 %s: %s", path, exc)

    return ScanEntry(
        path=path,
        size=size,
        info=info,
        detections=detections,
        advice=advise(info, size),
    )


def run(ctx: Context, options: ScanOptions | None = None) -> ScanReport:
    """扫描整个 Media_Folder，返回报告（可选写 JSON）。"""
    opts = options or ScanOptions()
    files = collect(ctx.paths, MEDIA_EXTS)
    say("扫描 %s，共 %d 个文件%s"
        % (ctx.paths.input_dir, len(files), "（深度扫描）" if opts.deep else ""))
    ctx.logger.info("scan: %d files, deep=%s", len(files), opts.deep)

    entries: List[ScanEntry] = []
    for index, path in enumerate(files, 1):
        say("  [%d/%d] %s" % (index, len(files), path.name))
        entries.append(scan_one(ctx, path, opts))

    report = ScanReport(
        root=ctx.paths.input_dir,
        entries=entries,
        deep=opts.deep,
        generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )
    report.render()

    target = opts.json_path
    if target is not None:
        written = report.write_json(target)
        say("报告已写入 %s" % written)
        ctx.logger.info("report written to %s", written)

    return report


__all__ = ["ScanOptions", "advise", "run", "scan_one"]
