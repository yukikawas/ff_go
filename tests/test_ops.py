"""各类操作的纯函数测试。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ff_go import reports
from ff_go.media import Interval, MediaInfo
from ff_go.ops import compress, convert, frames, imagefmt, scan
from tests.helpers import temp_dir


class CompressTests(unittest.TestCase):
    def test_video_extension_uses_libx264(self) -> None:
        args = compress.quality_args("mp4")
        self.assertIn("libx264", args)
        self.assertIn("-crf", args)

    def test_image_extension_uses_quality_flag(self) -> None:
        self.assertEqual(compress.quality_args("jpg"), ["-q:v", "5"])
        self.assertEqual(compress.quality_args("png"), ["-compression_level", "9"])

    def test_unknown_extension_has_no_forced_args(self) -> None:
        self.assertEqual(compress.quality_args("xyz"), [])


class ConvertTests(unittest.TestCase):
    def test_valid_format(self) -> None:
        self.assertTrue(convert.valid_format("mp4"))
        self.assertTrue(convert.valid_format("WEBP"))
        self.assertFalse(convert.valid_format(""))
        self.assertFalse(convert.valid_format("a/b"))
        self.assertFalse(convert.valid_format("toolongformat"))


class FrameTests(unittest.TestCase):
    def test_frames_dir_name(self) -> None:
        self.assertEqual(
            frames.frames_dir_for(Path("clip.mp4")).name, "clip_frames"
        )

    def test_modes_are_distinct(self) -> None:
        self.assertEqual(len(set(frames.MODES)), len(frames.MODES))
        self.assertEqual(set(frames.MODES), set(frames.MODE_LABELS))

    def test_image_format_validation(self) -> None:
        self.assertTrue(frames.valid_image_format("PNG"))
        self.assertTrue(frames.valid_image_format("jpg"))
        self.assertFalse(frames.valid_image_format("bmp"))


class ImageFormatTests(unittest.TestCase):
    def test_encoder_args_per_target(self) -> None:
        self.assertIn("libwebp", imagefmt.encoder_args("webp", imagefmt.QUALITY_BALANCED))
        self.assertIn("libaom-av1", imagefmt.encoder_args("avif", imagefmt.QUALITY_BALANCED))
        self.assertIn("libjxl", imagefmt.encoder_args("jxl", imagefmt.QUALITY_BALANCED))
        self.assertIn("-q:v", imagefmt.encoder_args("jpg", imagefmt.QUALITY_BALANCED))
        self.assertIn(
            "-compression_level", imagefmt.encoder_args("png", imagefmt.QUALITY_BALANCED)
        )

    def test_quality_presets_differ(self) -> None:
        # PNG 是无损格式，质量档对它没有意义，只固定用最高压缩级别。
        quality_sensitive = [t for t in imagefmt.TARGETS if t != imagefmt.TARGET_PNG]
        for target in quality_sensitive:
            small = imagefmt.encoder_args(target, imagefmt.QUALITY_SMALL)
            high = imagefmt.encoder_args(target, imagefmt.QUALITY_HIGH)
            self.assertNotEqual(small, high, "目标 %s 的质量档没有区别" % target)

    def test_same_format_detection(self) -> None:
        self.assertTrue(imagefmt._is_same_format("jpeg", "jpg"))
        self.assertTrue(imagefmt._is_same_format("jpg", "jpg"))
        self.assertFalse(imagefmt._is_same_format("png", "jpg"))
        self.assertTrue(imagefmt._is_same_format("webp", "webp"))

    def test_normalize_target(self) -> None:
        self.assertEqual(imagefmt._normalize_target("JPEG"), "jpg")
        self.assertEqual(imagefmt._normalize_target("webp"), "webp")


class ScanTests(unittest.TestCase):
    def test_advise_image(self) -> None:
        info = MediaInfo(path=Path("a.jpg"), width=800, height=600)
        advice = scan.advise(info, 1000)
        self.assertIsNotNone(advice)
        self.assertEqual(advice.action, "转 WebP")
        self.assertGreater(advice.estimated_saving, 0)

    def test_advise_4k_video_prefers_downscale(self) -> None:
        info = MediaInfo(
            path=Path("a.mp4"), video_codec="h264", width=3840, height=2160, bit_rate=20000000
        )
        advice = scan.advise(info, 10000)
        self.assertIsNotNone(advice)
        self.assertEqual(advice.action, "限制到 1080p")

    def test_advise_lossless_audio(self) -> None:
        info = MediaInfo(path=Path("a.flac"), audio_codec="flac")
        advice = scan.advise(info, 5000)
        self.assertIsNotNone(advice)
        self.assertEqual(advice.action, "转 MP3/AAC")

    def test_advise_none_for_already_small(self) -> None:
        info = MediaInfo(path=Path("a.webp"))
        self.assertIsNone(scan.advise(info, 1000))


class ReportTests(unittest.TestCase):
    def _entry(self) -> reports.ScanEntry:
        info = MediaInfo(
            path=Path("clip.mp4"),
            size=2048,
            duration=12.5,
            video_codec="h264",
            width=1920,
            height=1080,
            bit_rate=3000000,
        )
        return reports.ScanEntry(
            path=Path("clip.mp4"),
            size=2048,
            info=info,
            detections=[Interval("black", 1.0, 2.0)],
            advice=reports.Advice("转 H.265", "测试", 800),
        )

    def test_to_dict_shape(self) -> None:
        report = reports.ScanReport(root=Path("."), entries=[self._entry()])
        payload = report.to_dict()
        self.assertEqual(payload["summary"]["files"], 1)
        self.assertEqual(payload["summary"]["estimated_saving"], 800)
        self.assertEqual(payload["files"][0]["video_codec"], "h264")
        self.assertEqual(payload["files"][0]["detections"][0]["kind"], "black")

    def test_write_json_roundtrip(self) -> None:
        report = reports.ScanReport(root=Path("."), entries=[self._entry()])
        with temp_dir() as tmp:
            target = Path(tmp) / "nested" / "scan.json"
            written = report.write_json(target)
            self.assertTrue(written.exists())
            payload = json.loads(written.read_text(encoding="utf-8"))
            self.assertEqual(payload["files"][0]["name"], "clip.mp4")




class CategoryTests(unittest.TestCase):
    """图片不能因为 ffprobe 报了一个视频流就被当成视频。"""

    def test_image_extensions_are_images(self) -> None:
        for name in ("a.jpg", "a.png", "a.webp", "a.avif"):
            info = MediaInfo(path=Path(name), video_codec="png", width=800, height=600)
            self.assertEqual(info.category, "image", name)
            self.assertTrue(info.is_image)
            self.assertFalse(info.is_video)

    def test_video_with_audio(self) -> None:
        info = MediaInfo(path=Path("a.mp4"), video_codec="h264", audio_codec="aac")
        self.assertEqual(info.category, "video")
        self.assertTrue(info.is_video)

    def test_audio_file(self) -> None:
        info = MediaInfo(path=Path("a.flac"), audio_codec="flac")
        self.assertEqual(info.category, "audio")
        self.assertTrue(info.is_audio_only)

    def test_unknown_extension_falls_back_to_streams(self) -> None:
        image_like = MediaInfo(path=Path("a.bin"), video_codec="mjpeg")
        self.assertEqual(image_like.category, "image")
        audio_like = MediaInfo(path=Path("b.bin"), audio_codec="mp3")
        self.assertEqual(audio_like.category, "audio")

    def test_scan_entry_kind_labels(self) -> None:
        image = reports.ScanEntry(
            path=Path("a.png"), info=MediaInfo(path=Path("a.png"), video_codec="png")
        )
        self.assertEqual(image.kind, "图片")
        video = reports.ScanEntry(
            path=Path("b.mp4"), info=MediaInfo(path=Path("b.mp4"), video_codec="h264")
        )
        self.assertEqual(video.kind, "视频")
        broken = reports.ScanEntry(path=Path("c.mp4"), error="boom")
        self.assertEqual(broken.kind, "mp4")


if __name__ == "__main__":
    unittest.main()