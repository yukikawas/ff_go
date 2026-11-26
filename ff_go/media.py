"""ffprobe 封装与媒体信息模型。

有 ffprobe 时给出结构化信息；没有时上层可以选择降级（压缩/转换不需要它）。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from . import ffmpeg as ffmpeg_mod
from .config import AUDIO_EXTS, IMAGE_EXTS, PROBE_TIMEOUT, VIDEO_EXTS
from .errors import ProbeError
from .files import extension_of, size_or_zero


@dataclass(frozen=True)
class MediaInfo:
    """一个媒体文件的探测结果。"""

    path: Path
    size: int = 0
    duration: float = 0.0
    container: str = ""
    video_codec: str = ""
    audio_codec: str = ""
    width: int = 0
    height: int = 0
    fps: float = 0.0
    pix_fmt: str = ""
    bit_rate: int = 0
    stream_count: int = 0

    @property
    def suffix(self) -> str:
        return extension_of(self.path)

    @property
    def category(self) -> str:
        """按扩展名判定类别：image / video / audio / other。

        不能只看有没有视频流：ffprobe 会把 jpg/png 报成只有一个视频流的容器，
        按流判断会把图片误判成视频。
        """
        suffix = self.suffix
        if suffix in IMAGE_EXTS:
            return "image"
        if suffix in VIDEO_EXTS:
            return "video"
        if suffix in AUDIO_EXTS:
            return "audio"
        if self.video_codec and not self.audio_codec:
            return "image"
        if self.audio_codec and not self.video_codec:
            return "audio"
        return "video" if self.video_codec else "other"

    @property
    def is_video(self) -> bool:
        return self.category == "video"

    @property
    def is_image(self) -> bool:
        return self.category == "image"

    @property
    def is_audio_only(self) -> bool:
        return self.category == "audio"

    @property
    def resolution(self) -> str:
        if self.width and self.height:
            return "%dx%d" % (self.width, self.height)
        return "-"

    @property
    def bitrate_kbps(self) -> float:
        return self.bit_rate / 1000.0 if self.bit_rate else 0.0


@dataclass(frozen=True)
class Interval:
    """检测到的一段时间区间（黑屏 / 静音 / 冻结）。"""

    kind: str
    start: float
    end: Optional[float] = None

    @property
    def duration(self) -> Optional[float]:
        if self.end is None:
            return None
        return max(0.0, self.end - self.start)


def _ratio(value: str) -> float:
    """把 ffprobe 的 "30000/1001" 这种分数转成浮点数。"""
    if not value:
        return 0.0
    try:
        if "/" in value:
            numerator, denominator = value.split("/", 1)
            denominator_f = float(denominator)
            return float(numerator) / denominator_f if denominator_f else 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: object) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _as_float(value: object) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def probe(
    tools: ffmpeg_mod.Toolchain,
    path: Path,
    *,
    logger: Optional[logging.Logger] = None,
) -> MediaInfo:
    """用 ffprobe 读取一个文件的信息；解析失败抛 ProbeError。"""
    ffprobe = tools.require_ffprobe()
    result = ffmpeg_mod.run(
        ffprobe,
        ["-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        prefix=(),
        loglevel="",
        timeout=PROBE_TIMEOUT,
        logger=logger,
    )
    if not result.ok:
        raise ProbeError(result.summary or "ffprobe 读取失败")
    try:
        payload = json.loads(result.stdout or "{}")
    except ValueError as exc:
        raise ProbeError("ffprobe 输出不是合法 JSON：%s" % exc) from exc

    streams = payload.get("streams") or []
    fmt = payload.get("format") or {}
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})

    return MediaInfo(
        path=path,
        size=_as_int(fmt.get("size")) or size_or_zero(path),
        duration=_as_float(fmt.get("duration")),
        container=str(fmt.get("format_name") or ""),
        video_codec=str(video.get("codec_name") or ""),
        audio_codec=str(audio.get("codec_name") or ""),
        width=_as_int(video.get("width")),
        height=_as_int(video.get("height")),
        fps=_ratio(str(video.get("r_frame_rate") or "")),
        pix_fmt=str(video.get("pix_fmt") or ""),
        bit_rate=_as_int(fmt.get("bit_rate")) or _as_int(video.get("bit_rate")),
        stream_count=len(streams),
    )


# ---------------------------------------------------------------------------
# 检测器：解析 ffmpeg 滤镜写进 stderr 的事件行
# ---------------------------------------------------------------------------

_BLACK_START = re.compile(r"black_start:\s*(-?[0-9.]+)")
_BLACK_END = re.compile(r"black_end:\s*(-?[0-9.]+)")
_SILENCE_START = re.compile(r"silence_start:\s*(-?[0-9.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*(-?[0-9.]+)")
_FREEZE_START = re.compile(r"freeze_start:\s*(-?[0-9.]+)")
_FREEZE_END = re.compile(r"freeze_end:\s*(-?[0-9.]+)")


def _pair(
    text: str,
    kind: str,
    start_re: "re.Pattern[str]",
    end_re: "re.Pattern[str]",
) -> List[Interval]:
    """把 "start ... end ..." 这样的成对事件解析成区间列表。"""
    intervals: List[Interval] = []
    pending: Optional[float] = None
    for line in text.splitlines():
        match_start = start_re.search(line)
        match_end = end_re.search(line)
        if match_start and match_end:
            # blackdetect 会在同一行同时给出 black_start 和 black_end。
            intervals.append(
                Interval(kind, float(match_start.group(1)), float(match_end.group(1)))
            )
            pending = None
            continue
        if match_start:
            if pending is not None:
                intervals.append(Interval(kind, pending, None))
            pending = float(match_start.group(1))
            continue
        if match_end:
            end = float(match_end.group(1))
            start = pending if pending is not None else end
            intervals.append(Interval(kind, start, end))
            pending = None
    if pending is not None:
        intervals.append(Interval(kind, pending, None))
    return intervals


def detect(
    tools: ffmpeg_mod.Toolchain,
    path: Path,
    kinds: Sequence[str] = ("black", "silence", "freeze"),
    *,
    logger: Optional[logging.Logger] = None,
) -> List[Interval]:
    """跑检测滤镜并解析结果。只读，不产生输出文件。"""
    filters: List[str] = []
    args: List[object] = ["-i", str(path)]
    if "black" in kinds:
        filters.append("blackdetect=d=0.5:pix_th=0.10")
    if "freeze" in kinds:
        filters.append("freezedetect=n=-60dB:d=2")
    if filters:
        args.extend(["-vf", ",".join(filters)])
    if "silence" in kinds:
        args.extend(["-af", "silencedetect=noise=-40dB:d=0.5"])
    args.extend(["-f", "null", "-"])

    result = ffmpeg_mod.run_ffmpeg(
        tools,
        args,
        loglevel="info",
        timeout=PROBE_TIMEOUT * 20,
        logger=logger,
    )
    text = result.stderr
    found: List[Interval] = []
    if "black" in kinds:
        found.extend(_pair(text, "black", _BLACK_START, _BLACK_END))
    if "silence" in kinds:
        found.extend(_pair(text, "silence", _SILENCE_START, _SILENCE_END))
    if "freeze" in kinds:
        found.extend(_pair(text, "freeze", _FREEZE_START, _FREEZE_END))
    return sorted(found, key=lambda item: item.start)
