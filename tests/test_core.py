"""核心工具函数的单元测试（标准库 unittest，无需第三方依赖）。"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from ff_go import config, console, files, media
from tests.helpers import temp_dir
from ff_go.ffmpeg import CommandResult


class ConsoleTests(unittest.TestCase):
    def test_display_width_counts_cjk_as_two(self) -> None:
        self.assertEqual(console.display_width("abc"), 3)
        self.assertEqual(console.display_width("中文"), 4)
        self.assertEqual(console.display_width("a中"), 3)

    def test_pad_aligns_by_display_width(self) -> None:
        self.assertEqual(console.pad("中", 4), "中  ")
        self.assertEqual(console.pad("a", 3, align="right"), "  a")

    def test_human_size(self) -> None:
        self.assertEqual(console.human_size(0), "0 B")
        self.assertEqual(console.human_size(999), "999 B")
        self.assertEqual(console.human_size(1024), "1.0 KB")
        self.assertEqual(console.human_size(1024 * 1024), "1.0 MB")

    def test_human_duration(self) -> None:
        self.assertEqual(console.human_duration(0), "-")
        self.assertEqual(console.human_duration(65), "1:05")
        self.assertEqual(console.human_duration(3725), "1:02:05")


class ConfigTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop(config.ENV_HOME, None)
        config.reset_cache()

    def test_media_extension_sets_are_disjoint_and_merged(self) -> None:
        self.assertTrue(config.IMAGE_EXTS)
        self.assertTrue(config.VIDEO_EXTS)
        self.assertTrue(config.AUDIO_EXTS)
        self.assertEqual(
            config.MEDIA_EXTS,
            config.IMAGE_EXTS | config.VIDEO_EXTS | config.AUDIO_EXTS,
        )

    def test_env_home_overrides_discovery(self) -> None:
        with temp_dir() as tmp:
            root = Path(tmp)
            (root / "libs").mkdir()
            os.environ[config.ENV_HOME] = str(root)
            config.reset_cache()
            self.assertEqual(config.paths().root, root)
            self.assertEqual(config.paths().lib_dir, root / "libs")
            self.assertEqual(config.paths().input_dir, root / "Media_Folder")

    def test_tool_lookup(self) -> None:
        with temp_dir() as tmp:
            paths = config.ProjectPaths(root=Path(tmp))
            (paths.lib_dir).mkdir()
            self.assertIsNone(paths.tool("ffmpeg"))
            (paths.lib_dir / "ffmpeg.exe").write_bytes(b"x")
            found = paths.tool("ffmpeg")
            self.assertIsNotNone(found)
            self.assertEqual(found.name, "ffmpeg.exe")


class FileTests(unittest.TestCase):
    def test_extension_of(self) -> None:
        self.assertEqual(files.extension_of(Path("a.MP4")), "mp4")
        self.assertEqual(files.extension_of(Path("a.tar.gz")), "gz")
        self.assertEqual(files.extension_of(Path("noext")), "")

    def test_is_temp_name(self) -> None:
        self.assertTrue(files.is_temp_name("__fftmp__a.mp4"))
        self.assertTrue(files.is_temp_name("OUTPUT_TEMP_COMPRESS.jpg"))
        self.assertTrue(files.is_temp_name(".hidden"))
        self.assertFalse(files.is_temp_name("正常文件.mp4"))

    def test_iter_files_skips_temp_and_frames(self) -> None:
        with temp_dir() as tmp:
            root = Path(tmp)
            (root / "sub").mkdir()
            (root / "clip_frames").mkdir()
            (root / "a.mp4").write_bytes(b"1")
            (root / "sub" / "b.jpg").write_bytes(b"2")
            (root / "__fftmp__c.mp4").write_bytes(b"3")
            (root / "clip_frames" / "frame_000001.png").write_bytes(b"4")
            (root / "d.txt").write_bytes(b"5")

            all_files = [p.name for p in files.iter_files(root)]
            self.assertEqual(all_files, ["a.mp4", "d.txt", "b.jpg"])

            only_video = [p.name for p in files.iter_files(root, config.VIDEO_EXTS)]
            self.assertEqual(only_video, ["a.mp4"])

    def test_temp_path_for_keeps_extension(self) -> None:
        self.assertEqual(
            files.temp_path_for(Path("a/b.jpg")).name, "__fftmp__b.jpg"
        )
        self.assertEqual(
            files.temp_path_for(Path("a/b.jpg"), suffix="png").name, "__fftmp__b.png"
        )

    def test_unique_path_avoids_overwrite(self) -> None:
        with temp_dir() as tmp:
            target = Path(tmp) / "x.png"
            self.assertEqual(files.unique_path(target), target)
            target.write_bytes(b"a")
            self.assertEqual(files.unique_path(target).name, "x_1.png")
            (Path(tmp) / "x_1.png").write_bytes(b"b")
            self.assertEqual(files.unique_path(target).name, "x_2.png")

    def test_check_produced(self) -> None:
        with temp_dir() as tmp:
            path = Path(tmp) / "out.bin"
            with self.assertRaises(Exception):
                files.check_produced(path)
            path.write_bytes(b"")
            with self.assertRaises(Exception):
                files.check_produced(path)
            path.write_bytes(b"data")
            self.assertEqual(files.check_produced(path), 4)


class MediaTests(unittest.TestCase):
    def test_ratio_parsing(self) -> None:
        self.assertAlmostEqual(media._ratio("30000/1001"), 29.97, places=2)
        self.assertEqual(media._ratio("25"), 25.0)
        self.assertEqual(media._ratio(""), 0.0)
        self.assertEqual(media._ratio("abc"), 0.0)
        self.assertEqual(media._ratio("1/0"), 0.0)

    def test_interval_duration(self) -> None:
        self.assertAlmostEqual(media.Interval("black", 1.0, 2.5).duration, 1.5)
        self.assertIsNone(media.Interval("black", 1.0).duration)

    def test_pair_parse_black(self) -> None:
        text = (
            "[blackdetect @ 0x1] black_start:1.5 black_end:3.25 black_duration:1.75\n"
            "[blackdetect @ 0x1] black_start:10 black_end:11 black_duration:1\n"
        )
        found = media._pair(text, "black", media._BLACK_START, media._BLACK_END)
        self.assertEqual(len(found), 2)
        self.assertAlmostEqual(found[0].start, 1.5)
        self.assertAlmostEqual(found[0].end, 3.25)

    def test_pair_parse_open_interval(self) -> None:
        text = "[silencedetect @ 0x1] silence_start: 0\n"
        found = media._pair(text, "silence", media._SILENCE_START, media._SILENCE_END)
        self.assertEqual(len(found), 1)
        self.assertIsNone(found[0].end)

    def test_media_info_helpers(self) -> None:
        info = media.MediaInfo(path=Path("a.mp4"), width=1920, height=1080, bit_rate=4000000)
        self.assertEqual(info.resolution, "1920x1080")
        self.assertAlmostEqual(info.bitrate_kbps, 4000.0)
        self.assertTrue(info.is_video)

    def test_command_summary_is_single_line(self) -> None:
        result = CommandResult(False, (), 1, "", "line one\nline two")
        self.assertNotIn("\n", result.summary)
        self.assertIn("line one", result.summary)


if __name__ == "__main__":
    unittest.main()
