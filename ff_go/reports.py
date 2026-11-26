"""扫描结果的数据模型与渲染（控制台表格 + JSON）。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import console
from .files import extension_of
from .media import Interval, MediaInfo


@dataclass(frozen=True)
class Advice:
    """对单个文件的处理建议。"""

    action: str
    reason: str = ""
    estimated_saving: int = 0


@dataclass(frozen=True)
class ScanEntry:
    """一个文件的扫描结果。"""

    path: Path
    size: int = 0
    info: Optional[MediaInfo] = None
    error: str = ""
    detections: List[Interval] = field(default_factory=list)
    advice: Optional[Advice] = None

    @property
    def kind(self) -> str:
        labels = {"image": "图片", "video": "视频", "audio": "音频"}
        if self.info is None:
            return extension_of(self.path) or "?"
        return labels.get(self.info.category, "其它")

    @property
    def has_issue(self) -> bool:
        return bool(self.error) or bool(self.detections)


@dataclass(frozen=True)
class ScanReport:
    """整批扫描的结果。"""

    root: Path
    entries: List[ScanEntry]
    deep: bool = False
    generated_at: str = ""

    @property
    def total_size(self) -> int:
        return sum(entry.size for entry in self.entries)

    @property
    def total_saving(self) -> int:
        return sum(
            entry.advice.estimated_saving for entry in self.entries if entry.advice is not None
        )

    @property
    def problem_count(self) -> int:
        return sum(1 for entry in self.entries if entry.has_issue)

    def render(self) -> None:
        """在控制台打印表格 + 汇总。"""
        console.rule("扫描结果")
        if not self.entries:
            console.say("Media_Folder 里没有可扫描的文件。")
            return

        rows = []
        for entry in self.entries:
            info = entry.info
            advice = entry.advice.action if entry.advice else "-"
            issues = ""
            if entry.error:
                issues = "读取失败"
            elif entry.detections:
                issues = ",".join(sorted({item.kind for item in entry.detections}))
            rows.append(
                [
                    entry.path.name,
                    entry.kind,
                    info.resolution if info else "-",
                    console.human_duration(info.duration if info else None),
                    ("%.0f kbps" % info.bitrate_kbps) if info and info.bitrate_kbps else "-",
                    console.human_size(entry.size),
                    advice,
                    issues or "-",
                ]
            )
        console.table(
            ["文件", "类型", "分辨率", "时长", "码率", "大小", "建议", "问题"], rows
        )

        console.say("")
        console.say("共 %d 个文件，合计 %s" % (len(self.entries), console.human_size(self.total_size)))
        if self.deep:
            console.say("发现问题 %d 个" % self.problem_count)
        if self.total_saving:
            ratio = self.total_saving * 100.0 / self.total_size if self.total_size else 0.0
            console.say(
                "预计可再省 %s（约 %.0f%%）"
                % (console.human_size(self.total_saving), ratio)
            )

    def to_dict(self) -> Dict[str, Any]:
        """转成可 JSON 序列化的结构。"""
        files = []
        for entry in self.entries:
            info = entry.info
            files.append(
                {
                    "path": str(entry.path),
                    "name": entry.path.name,
                    "kind": entry.kind,
                    "size": entry.size,
                    "duration": info.duration if info else None,
                    "container": info.container if info else "",
                    "video_codec": info.video_codec if info else "",
                    "audio_codec": info.audio_codec if info else "",
                    "width": info.width if info else 0,
                    "height": info.height if info else 0,
                    "fps": round(info.fps, 3) if info else 0,
                    "pix_fmt": info.pix_fmt if info else "",
                    "bit_rate": info.bit_rate if info else 0,
                    "error": entry.error,
                    "detections": [
                        {"kind": item.kind, "start": item.start, "end": item.end}
                        for item in entry.detections
                    ],
                    "advice": (
                        {
                            "action": entry.advice.action,
                            "reason": entry.advice.reason,
                            "estimated_saving": entry.advice.estimated_saving,
                        }
                        if entry.advice
                        else None
                    ),
                }
            )
        return {
            "generated_at": self.generated_at or time.strftime("%Y-%m-%d %H:%M:%S"),
            "root": str(self.root),
            "deep": self.deep,
            "summary": {
                "files": len(self.entries),
                "total_size": self.total_size,
                "estimated_saving": self.total_saving,
                "problems": self.problem_count,
            },
            "files": files,
        }

    def write_json(self, target: Path) -> Path:
        """把报告写成 JSON 文件，返回实际写入路径。"""
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(str(target), "w", encoding="utf-8", newline="\n") as handle:
            json.dump(self.to_dict(), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        return target
