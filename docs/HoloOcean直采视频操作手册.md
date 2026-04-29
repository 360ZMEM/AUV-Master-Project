# HoloOcean 直采视频操作手册

本文档说明如何使用 [tools/capture_holoocean_video.py](../tools/capture_holoocean_video.py) 直接启动一个新的 HoloOcean 环境、采集画面并导出 GIF/MP4。它面向“先复现画面，再核对控制”的快速操作场景。

## 1. 适用场景

- 想快速生成一段可分享的视频产物。
- 想验证当前 HoloOcean 画面、控制和轨迹是否一致。
- 想同时支持“仿真相机视角”和“窗口等价回放”两种采集方式。

## 2. 基本用法

默认会使用 [config/sim_params.yaml](../config/sim_params.yaml) 里的轨迹与控制参数，输出 GIF：

```bash
/usr/bin/python3 tools/capture_holoocean_video.py --format gif
```

生成 MP4：

```bash
/usr/bin/python3 tools/capture_holoocean_video.py --format mp4
```

如果不指定 `--output`，脚本会默认写到 `log/holoocean_capture_<timestamp>.<format>`。

## 3. 两种采集模式

### 3.1 agent 模式

```bash
/usr/bin/python3 tools/capture_holoocean_video.py --capture-mode agent --max-steps 5 --fps 15 --format gif
```

特点：

- 使用挂在 agent 上的 `RGBCamera`。
- 适合看本体视角、前视角或者相机挂载是否正常。
- 该模式默认不强制开启 HoloOcean viewport。

### 3.2 viewport 模式

```bash
/usr/bin/python3 tools/capture_holoocean_video.py --capture-mode viewport --show-viewport --max-steps 3 --fps 15 --format gif
```

特点：

- 使用 `ViewportCapture`。
- 会自动把窗口打开为 viewport 对齐模式。
- 适合做“看到什么，录到什么”的等价回放。

viewport 模式的关键约束：

- 需要 `--show-viewport`。
- 采集分辨率默认是 `1280x720`。
- `--fps` 必须能整除 `simulation.ticks_per_sec`。

## 4. 读产物的顺序

生成视频后，建议按下面顺序看：

1. 先看命令行开头打印的 `capture_mode`、`show_viewport` 和 `capture_resolution`。
2. 再看中间的 `step=xxxx` 日志，确认位置、姿态和速度变化是否合理。
3. 最后打开 GIF/MP4，看路径是否和控制方向一致。

如果是 viewport 模式，优先确认窗口里看到的画面和导出视频一致。

## 5. 常见问题

### 5.1 报 `HoloOcean camera rate must divide ticks_per_sec exactly`

说明 `--fps` 与 `simulation.ticks_per_sec` 不整除。把 `--fps` 改成 15、10、5 这类整除值。

### 5.2 生成了视频但画面不对

优先检查两点：

- 是否误用了 `agent` 和 `viewport` 模式。
- 是否在 viewport 模式下漏掉了 `--show-viewport`。

### 5.3 没有输出任何帧

先确认当前环境可以启动 HoloOcean，再检查 `tools/capture_holoocean_video.py` 的运行日志是否已经进入主循环。

## 6. 已验证命令

下面两条命令已经在当前环境验证过并成功产出 GIF：

```bash
/usr/bin/python3 tools/capture_holoocean_video.py --capture-mode agent --max-steps 5 --fps 15 --format gif --output log/test_holoocean_capture.gif
/usr/bin/python3 tools/capture_holoocean_video.py --capture-mode viewport --show-viewport --max-steps 3 --fps 15 --format gif --output log/test_holoocean_viewport_capture.gif
```

## 7. 和主线文档的关系

这份手册只负责“怎么直接录视频”。更完整的实验分析、rosbag 回放和指标解释，请继续看 [PVS 全流程 Runbook](PVS全流程runbook.md)。