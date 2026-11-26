"""兼容旧入口：视频拆帧。

带参数时等同于 python -m ff_go frames ...，不带参数时进入交互式提问。
"""

from __future__ import annotations

import sys

if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv:
        from ff_go.cli import main

        raise SystemExit(main(["frames"] + argv))

    from ff_go import config, console, menu
    from ff_go.errors import FFGoError
    from ff_go.ffmpeg import Toolchain

    paths = config.paths()
    try:
        Toolchain.discover(paths)
        menu.run_action("frames", paths)
    except FFGoError as exc:
        console.say(str(exc))
        raise SystemExit(1) from exc
    finally:
        console.pause()
