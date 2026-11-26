"""各类批量操作。

每个模块都暴露两种入口：

* xxx_one(ctx, path, options) -> ItemResult   处理单个文件，可单独测试
* run(ctx, options) -> BatchStats / ScanReport 遍历 Media_Folder 批量执行
"""

from __future__ import annotations

from . import compress, convert, frames, imagefmt, scan

__all__ = ["compress", "convert", "frames", "imagefmt", "scan"]
