"""交互式批量菜单：选功能 -> 选参数 -> 批量处理 Media_Folder。"""

from __future__ import annotations

import logging
import sys
from typing import Callable, Optional

from . import __version__, config, console, logging_setup
from .config import MEDIA_EXTS, ProjectPaths
from .errors import Cancelled, FFGoError, ToolNotFoundError
from .ffmpeg import Toolchain, version as ffmpeg_version
from .files import iter_files
from .ops import compress, convert, frames, imagefmt, scan
from .ops.common import Context

MENU_TITLE = "ff_go 主菜单"


def _wait() -> None:
    """让用户看一眼结果再回主菜单；非交互环境直接返回。"""
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return
        input("\n按回车返回主菜单...")
    except (EOFError, KeyboardInterrupt):
        console.say("")


def _policy_context(paths: ProjectPaths, tools: Toolchain, name: str) -> Context:
    return Context(paths=paths, tools=tools, logger=logging_setup.configure(paths, name))


def _count_media(paths: ProjectPaths) -> int:
    try:
        return len(iter_files(paths.input_dir, MEDIA_EXTS))
    except OSError:
        return 0


def show_environment(paths: ProjectPaths, tools: Toolchain) -> None:
    """打印一次环境信息，方便排查问题。"""
    console.rule("环境信息")
    console.say("ff_go 版本      : %s" % __version__)
    console.say("Python 版本     : %s" % sys.version.split()[0])
    console.say("项目根目录      : %s" % paths.root)
    console.say("素材目录        : %s" % paths.input_dir)
    console.say("日志目录        : %s" % paths.log_root)
    console.say("ffmpeg          : %s" % tools.ffmpeg)
    console.say("ffprobe         : %s" % (tools.ffprobe or "（缺失，扫描功能不可用）"))
    console.say("ffmpeg 版本     : %s" % ffmpeg_version(tools))
    console.say("可处理文件      : %d 个" % _count_media(paths))


def action_compress(paths: ProjectPaths, tools: Toolchain) -> None:
    options = compress.CompressOptions()
    choice = console.choose(
        "压缩范围：",
        ["图片 + 视频 + 音频（全部）", "只压缩图片"],
        default=1,
    )
    if choice == 0:
        return
    if choice == 2:
        options = compress.CompressOptions(only_images=True)
    stats = compress.run(_policy_context(paths, tools, "compress"), options)
    stats.render("压缩结果")


def action_convert(paths: ProjectPaths, tools: Toolchain) -> None:
    target = console.prompt_text(
        "转换成什么格式？只要扩展名，例如 mp4 / png / mp3",
        validate=convert.valid_format,
        error_message="格式只能是 1-8 位字母或数字",
    ).lower()
    if console.choose("确认转换？目标格式 %s" % target, ["开始转换", "取消"], default=1) != 1:
        return
    stats = convert.run(
        _policy_context(paths, tools, "convert"), convert.ConvertOptions(target_format=target)
    )
    stats.render("转换结果")


def action_frames(paths: ProjectPaths, tools: Toolchain) -> None:
    mode_names = [frames.MODE_LABELS[mode] for mode in frames.MODES]
    mode_index = console.choose("拆帧模式：", mode_names, default=1)
    if mode_index == 0:
        return
    mode = frames.MODES[mode_index - 1]

    image_format = "png"
    if mode != frames.MODE_COVER:
        format_index = console.choose("输出图片格式：", ["PNG", "JPG"], default=1)
        if format_index == 0:
            return
        image_format = frames.IMAGE_CHOICES[format_index - 1]

    fps_value = 1
    if mode == frames.MODE_FPS:
        fps_value = console.prompt_int("每秒抽几帧？", default=1, minimum=1, maximum=60)

    options = frames.FramesOptions(
        image_format=image_format, mode=mode, fps=fps_value
    )
    stats = frames.run(_policy_context(paths, tools, "frames"), options)
    stats.render("拆帧结果")


def action_image(paths: ProjectPaths, tools: Toolchain) -> None:
    target_names = [imagefmt.TARGET_LABELS[t] for t in imagefmt.TARGETS]
    target_index = console.choose("目标格式：", target_names, default=1)
    if target_index == 0:
        return
    quality_names = [imagefmt.QUALITY_LABELS[q] for q in imagefmt.QUALITIES]
    quality_index = console.choose("质量档位：", quality_names, default=2)
    if quality_index == 0:
        return

    options = imagefmt.ImageOptions(
        target_format=imagefmt.TARGETS[target_index - 1],
        quality=imagefmt.QUALITIES[quality_index - 1],
    )
    stats = imagefmt.run(_policy_context(paths, tools, "image"), options)
    stats.render("图片转换结果")


def action_scan(paths: ProjectPaths, tools: Toolchain) -> None:
    if tools.ffprobe is None:
        console.say("扫描需要 ffprobe.exe，请把它放进 %s" % paths.lib_dir)
        return

    deep = console.prompt_yes_no("是否深度扫描（额外检测黑屏/静音/冻结，比较慢）？", default=False)
    default_json = logging_setup.daily_log_dir(paths) / "scan_report.json"
    save = console.prompt_yes_no("是否保存 JSON 报告？", default=True)
    options = scan.ScanOptions(deep=deep, json_path=default_json if save else None)

    report = scan.run(_policy_context(paths, tools, "scan"), options)
    if report.problem_count:
        console.say("")
        console.say("有问题的文件：")
        for entry in report.entries:
            if entry.error:
                console.say("  %s：%s" % (entry.path.name, entry.error))
            elif entry.detections:
                kinds = ", ".join(sorted({item.kind for item in entry.detections}))
                console.say("  %s：%s" % (entry.path.name, kinds))


ACTIONS: "list[tuple[str, str, Callable[[ProjectPaths, Toolchain], None]]]" = [
    ("compress", "压缩媒体文件（体积变小才替换）", action_compress),
    ("convert", "转换媒体格式", action_convert),
    ("frames", "视频拆帧（全部/每秒/场景/封面）", action_frames),
    ("image", "图片转现代格式（WebP/AVIF/JXL/JPEG）", action_image),
    ("scan", "扫描并生成体检报告（只读）", action_scan),
]


def main(paths: Optional[ProjectPaths] = None) -> int:
    """交互式主循环。"""
    target_paths = paths or config.paths()
    try:
        tools = Toolchain.discover(target_paths)
    except ToolNotFoundError as exc:
        console.say(str(exc))
        return 1

    console.rule("ff_go %s" % __version__)
    console.say("素材目录：%s" % target_paths.input_dir)
    console.say("ffmpeg  ：%s" % tools.ffmpeg)

    while True:
        labels = ["%s（%s）" % (title, key) for key, title, _ in ACTIONS]
        labels.append("查看环境信息")
        try:
            choice = console.choose(MENU_TITLE, labels, default=1)
        except Cancelled:
            console.say("")
            return 0
        if choice == 0:
            console.say("再见。")
            return 0

        try:
            if choice == len(ACTIONS) + 1:
                show_environment(target_paths, tools)
            else:
                _, _, action = ACTIONS[choice - 1]
                action(target_paths, tools)
        except Cancelled:
            console.say("已取消，没有改动任何文件。")
        except FFGoError as exc:
            console.say("出错了：%s" % exc)
        except KeyboardInterrupt:
            console.say("")
            return 0
        _wait()


def run_action(
    key: str, paths: Optional[ProjectPaths] = None, logger: Optional[logging.Logger] = None
) -> int:
    """按 key 直接执行某个动作（供命令行入口复用）。"""
    target_paths = paths or config.paths()
    tools = Toolchain.discover(target_paths)
    for action_key, _title, callable_action in ACTIONS:
        if action_key == key:
            callable_action(target_paths, tools)
            return 0
    raise FFGoError("未知的操作：%s" % key)


__all__ = ["ACTIONS", "main", "run_action", "show_environment"]
