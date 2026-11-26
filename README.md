# ff_go

调用 FFmpeg 的照片 / 视频 / 音频**批量处理工具**：零第三方依赖，交互菜单和命令行都能用。

支持 Python **3.9 ~ 3.15.2**，在 Windows 上开箱即用。

## 功能

| 功能 | 说明 |
| --- | --- |
| 压缩媒体文件 | 重新编码，**只有变小才替换原文件**；视频 H.264 CRF 28，图片按格式取质量参数 |
| 转换媒体格式 | 转成任意指定格式；成功后删除原文件，重名自动加序号 |
| 视频拆帧 | 全部帧 / 每秒 N 帧 / 场景变化时抽帧 / 只出一张封面 |
| 图片转现代格式 | WebP / AVIF / JPEG XL / JPEG，三档质量 |
| 体检扫描 | **只读**分析整个目录：编码、分辨率、码率、黑屏、静音、冻结，并估算还能省多少 |

所有操作都是"先写临时文件 → 确认 ffmpeg 成功且产物非空 → 才动原文件"，失败时原文件一定还在。

## 快速开始

1. 安装 Python 3.9 或更高版本。
2. 从 <https://github.com/BtbN/FFmpeg-Builds> 下载 Windows 版 FFmpeg，把 `ffmpeg.exe` 和 `ffprobe.exe` 放进 `libs/`。
3. 把素材放进 `Media_Folder/`（支持子目录，会递归处理）。

```
ff_go/
├── libs/ffmpeg.exe, ffprobe.exe
├── Media_Folder/          ← 素材放这里
├── ff_go/                 ← 主程序包
├── tests/                 ← 单元测试
├── ff_go.bat              ← 双击进入菜单
└── pyproject.toml
```

## 用法：交互菜单

双击 `ff_go.bat`（或在命令行执行 `python -m ff_go`）：

```
============ ff_go 1.0.0 ============
素材目录：E:\...\Media_Folder
ffmpeg  ：E:\...\libs\ffmpeg.exe

ff_go 主菜单
  1) 压缩媒体文件（体积变小才替换）（compress）
  2) 转换媒体格式（convert）
  3) 视频拆帧（全部/每秒/场景/封面）（frames）
  4) 图片转现代格式（WebP/AVIF/JXL/JPEG）（image）
  5) 扫描并生成体检报告（只读）（scan）
  6) 查看环境信息
  0) 返回
```

## 用法：命令行（适合写进 bat / 计划任务）

```
python -m ff_go compress                    压缩全部媒体
python -m ff_go compress --images-only      只压缩图片
python -m ff_go convert --format mp4        全部转成 mp4
python -m ff_go frames --mode fps --fps 1   每秒抽 1 帧
python -m ff_go frames --mode cover         只出封面图
python -m ff_go image --format webp --quality balanced
python -m ff_go scan --deep --json report.json
python -m ff_go info                        环境信息
```

退出码：`0` 全部成功，`1` 有文件失败，`2` 配置 / 参数问题。

旧入口 `ff_compress.py` / `ff_transfer.py` / `ff_v2p.py` / `ff_menu.py` 仍然可用，内部转调新命令。

## 实现要点

- **安全替换**：临时文件用 `__fftmp__` 前缀放在源文件同目录，成功后 `os.replace` 原子替换；遍历时自动跳过。
- **不经过 shell**：ffmpeg 参数用列表传递，文件名里的引号、`&`、`|` 都不会出问题。
- **编码参数位置**：`-crf`、`-q:v` 等必须放在 `-i` 之后，否则会被当成输入解码器选项。
- **fps_mode**：新版 FFmpeg 已移除 `-vsync`，拆帧统一用 `-fps_mode`，并对老版本 ffmpeg 做回退。
- **EXIF 方向**：新版 FFmpeg 会自动应用 JPEG 的 EXIF 方向，竖拍照片不会躺平。

## 开发

```
python -m unittest discover -s tests -t . -v    跑单元测试（标准库 unittest，无需依赖）
python -m ff_go --help                          查看所有子命令
```

代码结构：

```
ff_go/
├── cli.py           命令行入口（argparse）
├── menu.py          交互菜单
├── config.py        路径发现、扩展名、超时
├── ffmpeg.py        ffmpeg/ffprobe 调用封装
├── media.py         ffprobe 解析、检测器
├── reports.py       扫描报告模型与 JSON 输出
├── files.py         遍历、临时文件、原子替换
├── console.py       输出、表格、交互问答
├── logging_setup.py 按日期归档的日志
└── ops/             compress / convert / frames / imagefmt / scan
```

## 日志

每次运行写入 `ff-logs/YYYYMMDD/<功能名>.log`（UTF-8，追加），含完整 ffmpeg 命令行和失败时的 stderr。

## 已知限制

- 只在 Windows 上验证过（优先找 `libs/ffmpeg.exe`，其次 `libs/ffmpeg`）。
- 体检扫描需要 `ffprobe.exe`，缺失时其余功能照常可用。
- 拆帧会把每帧都导出，长视频注意磁盘空间。
