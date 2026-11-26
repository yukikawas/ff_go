"""兼容旧入口：压缩 Media_Folder（等同于 python -m ff_go compress）。"""

from __future__ import annotations

import sys

from ff_go.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["compress"] + sys.argv[1:]))
