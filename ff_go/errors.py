"""项目异常层次。

所有对外抛出的异常都继承自 FFGoError，方便上层统一捕获，
也方便测试断言没有意料之外的异常类型。
"""

from __future__ import annotations


class FFGoError(Exception):
    """所有 ff_go 异常的基类。"""


class ToolNotFoundError(FFGoError):
    """找不到或无法启动所需的 ffmpeg / ffprobe 可执行文件。"""


class ProbeError(FFGoError):
    """ffprobe 返回了无法解析的结果。"""


class OperationFailed(FFGoError):
    """单个文件的处理失败（不影响批处理里的其它文件）。"""


class TempOutputError(FFGoError):
    """ffmpeg 没有产出预期的临时文件。"""


class Cancelled(FFGoError):
    """用户取消或标准输入被关闭。"""
