"""命令行入口：既能进交互菜单，也能被脚本 / 批处理直接调用。

    python -m ff_go                       进入交互菜单
    python -m ff_go compress              压缩 Media_Folder
    python -m ff_go convert --format mp4  转换格式
    python -m ff_go frames --mode fps --fps 1
    python -m ff_go image --format webp --quality balanced
    python -m ff_go scan --deep --json out.json
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from . import __version__, config, console, logging_setup, menu
from .errors import Cancelled, FFGoError
from .ffmpeg import Toolchain
from .ops import compress, convert, frames, imagefmt, scan
from .ops.common import BatchStats, Context

EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_ERROR = 2


def _context(name: str) -> "tuple[Context, config.ProjectPaths]":
    paths = config.paths()
    tools = Toolchain.discover(paths)
    return Context(paths=paths, tools=tools, logger=logging_setup.configure(paths, name)), paths


def _finish(stats: BatchStats, title: str) -> int:
    stats.render(title)
    return stats.exit_code


def cmd_compress(args: argparse.Namespace) -> int:
    ctx, _ = _context("compress")
    stats = compress.run(ctx, compress.CompressOptions(only_images=args.images_only))
    return _finish(stats, "压缩结果")


def cmd_convert(args: argparse.Namespace) -> int:
    ctx, _ = _context("convert")
    stats = convert.run(ctx, convert.ConvertOptions(target_format=args.format.lower()))
    return _finish(stats, "转换结果")


def cmd_frames(args: argparse.Namespace) -> int:
    ctx, _ = _context("frames")
    options = frames.FramesOptions(
        image_format=args.format.lower(), mode=args.mode, fps=args.fps
    )
    return _finish(frames.run(ctx, options), "拆帧结果")


def cmd_image(args: argparse.Namespace) -> int:
    ctx, _ = _context("image")
    options = imagefmt.ImageOptions(target_format=args.format, quality=args.quality)
    return _finish(imagefmt.run(ctx, options), "图片转换结果")


def cmd_scan(args: argparse.Namespace) -> int:
    ctx, _ = _context("scan")
    json_path = Path(args.json) if args.json else None
    report = scan.run(ctx, scan.ScanOptions(deep=args.deep, json_path=json_path))
    return EXIT_OK if report.entries else EXIT_PARTIAL


def cmd_info(args: argparse.Namespace) -> int:
    paths = config.paths()
    tools = Toolchain.discover(paths)
    menu.show_environment(paths, tools)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ff-go",
        description="调用 FFmpeg 的批量媒体处理工具",
        epilog="不带子命令时进入交互菜单。",
    )
    parser.add_argument("--version", action="version", version="ff_go %s" % __version__)
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("menu", help="进入交互菜单").set_defaults(func=lambda a: menu.main())

    p_compress = sub.add_parser("compress", help="压缩 Media_Folder 里的媒体文件")
    p_compress.add_argument("--images-only", action="store_true", help="只压缩图片")
    p_compress.set_defaults(func=cmd_compress)

    p_convert = sub.add_parser("convert", help="转换媒体格式")
    p_convert.add_argument("-f", "--format", required=True, help="目标格式，例如 mp4 / png")
    p_convert.set_defaults(func=cmd_convert)

    p_frames = sub.add_parser("frames", help="视频拆帧")
    p_frames.add_argument("-f", "--format", default="png", choices=list(frames.IMAGE_CHOICES))
    p_frames.add_argument("-m", "--mode", default=frames.MODE_ALL, choices=list(frames.MODES))
    p_frames.add_argument("--fps", type=int, default=1, help="每秒抽帧数（--mode fps 时生效）")
    p_frames.set_defaults(func=cmd_frames)

    p_image = sub.add_parser("image", help="图片转现代格式")
    p_image.add_argument("-f", "--format", default=imagefmt.TARGET_WEBP, choices=list(imagefmt.TARGETS))
    p_image.add_argument("-q", "--quality", default=imagefmt.QUALITY_BALANCED, choices=list(imagefmt.QUALITIES))
    p_image.set_defaults(func=cmd_image)

    p_scan = sub.add_parser("scan", help="扫描并生成体检报告")
    p_scan.add_argument("--deep", action="store_true", help="额外检测黑屏/静音/冻结")
    p_scan.add_argument("--json", default="", help="把报告写到指定 JSON 文件")
    p_scan.set_defaults(func=cmd_scan)

    sub.add_parser("info", help="显示环境信息").set_defaults(func=cmd_info)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """命令行主函数，返回进程退出码。"""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not getattr(args, "command", None):
        args = parser.parse_args(["menu"])

    try:
        result = args.func(args)
    except Cancelled:
        console.say("已取消。")
        return EXIT_ERROR
    except FFGoError as exc:
        console.say(str(exc))
        return EXIT_ERROR
    except KeyboardInterrupt:
        console.say("")
        return EXIT_ERROR
    return int(result or 0)


def run() -> None:
    """console_scripts 入口。"""
    raise SystemExit(main())


if __name__ == "__main__":
    run()
