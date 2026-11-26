"""双击运行入口：进入交互菜单（等同于 python -m ff_go）。"""

from __future__ import annotations

import sys

from ff_go.cli import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["menu"]))
