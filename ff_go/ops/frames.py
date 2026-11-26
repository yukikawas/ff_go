"""视频拆帧：整段抽帧、每秒抽帧、场景抽帧或只出封面。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

from ..config import FRAMES_SUFFIX, FRAMES_TIMEOUT, VIDEO_EXTS
from ..console import human_size, say
from ..ffmpeg import run_variants
from ..files import unique_path
from .common import BatchStats, Context, ItemResult, collect, run_batch

MODE_ALL = "all"
MODE_FPS = "fps"
MODE_SCENE = "scene"
MODE_COVER = "cover"

MODES = (MODE_ALL, MODE_FPS, MODE_SCENE, MODE_COVER)
MODE_LABELS = {
    MODE_ALL: "全部帧",
    MODE_FPS: "每秒 N 帧",
    MODE_SCENE: "场景变化时抽帧",
    MODE_COVER: "只出一张封面图",
}
IMAGE_CHOICES = ("png", "jpg")


@dataclass(frozen=True)
class FramesOptions:
    """拆帧选项。"""

    image_format: str = "png"
    mode: str = MODE_ALL
    fps: int = 1
    scene_threshold: float = 0.3
    timeout: int = FRAMES_TIMEOUT


def valid_image_format(value: str) -> bool:
    return value.strip().lower() in IMAGE_CHOICES


def frames_dir_for(video: Path) -> Path:
    """视频对应的帧输出目录。"""
    return video.parent / (video.stem + FRAMES_SUFFIX)


def _build_variants(video: Path, options: FramesOptions) -> List[Sequence[object]]:
    """按模式拼出候选命令；第一个跑通就用它。"""
    image_format = options.image_format
    if options.mode == MODE_COVER:
        cover = video.with_name(video.stem + "_cover." + image_format)
        base: List[object] = ["-i", str(video), "-vf", "thumbnail=100", "-frames:v", "1"]
        if image_format in ("jpg", "jpeg"):
            base.extend(["-q:v", "2"])
        return [base + [str(cover)]]

    out_dir = frames_dir_for(video)
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / ("frame_%06d." + image_format))
    base = ["-i", str(video)]

    if options.mode == MODE_FPS:
        base.extend(["-vf", "fps=%d" % max(1, options.fps)])
    elif options.mode == MODE_SCENE:
        base.extend(["-vf", "select='gt(scene,%.2f)'" % options.scene_threshold])

    if image_format in ("jpg", "jpeg"):
        base.extend(["-q:v", "2"])

    if options.mode == MODE_SCENE:
        # 场景抽帧会删掉大量帧，必须用可变帧率输出，否则时间戳会出错。
        return [
            base + ["-fps_mode", "vfr", pattern],
            base + [pattern],
        ]
    if options.mode == MODE_ALL:
        # passthrough 避免重复帧；老版本 ffmpeg 没有这个选项，回退到不带参数。
        return [
            base + ["-fps_mode", "passthrough", pattern],
            base + [pattern],
        ]
    return [base + [pattern]]


def _output_path_for(video: Path, options: FramesOptions) -> Path:
    if options.mode == MODE_COVER:
        return video.with_name(video.stem + "_cover." + options.image_format)
    return frames_dir_for(video)


def extract_one(ctx: Context, video: Path, options: FramesOptions) -> ItemResult:
    """对一个视频执行拆帧。原视频始终保留。"""
    output = _output_path_for(video, options)

    if options.mode == MODE_COVER:
        output = unique_path(output)
    if options.mode != MODE_COVER and output.exists():
        for stale in sorted(output.glob("frame_*." + options.image_format)):
            try:
                stale.unlink()
            except OSError:
                pass

    result = run_variants(
        ctx.tools,
        _build_variants(video, options),
        timeout=options.timeout,
        logger=ctx.logger,
    )
    if not result.ok:
        return ItemResult.failed(result.summary or "ffmpeg 失败")

    if options.mode == MODE_COVER:
        try:
            size = output.stat().st_size
        except OSError:
            return ItemResult.failed("没有产出封面图")
        return ItemResult.ok("封面 -> %s（%s）" % (output.name, human_size(size)))

    frames = sorted(output.glob("frame_*." + options.image_format))
    if not frames:
        return ItemResult.failed("没有产出任何帧（视频可能损坏或为空）")
    total_bytes = 0
    for frame in frames:
        try:
            total_bytes += frame.stat().st_size
        except OSError:
            pass
    return ItemResult.ok(
        "%d 帧 -> %s（共 %s）" % (len(frames), output.name, human_size(total_bytes))
    )


def run(ctx: Context, options: FramesOptions) -> BatchStats:
    """批量拆帧 Media_Folder 里的视频。"""
    videos = collect(ctx.paths, VIDEO_EXTS)
    say("一共有 %d 个待处理视频，模式：%s"
        % (len(videos), MODE_LABELS.get(options.mode, options.mode)))
    ctx.logger.info(
        "frames: %d videos, mode=%s, format=%s",
        len(videos), options.mode, options.image_format,
    )
    if not videos:
        say("Media_Folder 里没有视频文件。")
        return BatchStats()

    return run_batch(
        videos,
        lambda video: extract_one(ctx, video, options),
        logger=ctx.logger,
        verb="拆帧完成",
    )


__all__ = [
    "FramesOptions",
    "MODE_ALL",
    "MODE_COVER",
    "MODE_FPS",
    "MODE_LABELS",
    "MODE_SCENE",
    "MODES",
    "extract_one",
    "frames_dir_for",
    "run",
    "valid_image_format",
]
