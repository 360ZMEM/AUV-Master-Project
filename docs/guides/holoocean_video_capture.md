# 🐍 HoloOcean 视频采集指南

本文档介绍如何从 HoloOcean 仿真中直接采集视频。

---

## 快速开始

### 基础视频采集（GIF 格式）

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
python tools/capture_holoocean_video.py --format gif
```

### 高清视频采集（MP4 格式）

```bash
python tools/capture_holoocean_video.py --capture-mode viewport --show-viewport --format mp4
```

---

## 参数详解

### 基础参数

```bash
python tools/capture_holoocean_video.py \
  --format gif                    # 输出格式：gif / mp4
  --fps 30                        # 帧率（需能被 ticks_per_sec 整除）
  --output video_output           # 输出文件名（不含扩展名）
```

### 捕获模式

| 模式 | 说明 | 用途 |
|------|------|------|
| `default` | 默认相机视角 | 基础记录 |
| `viewport` | 用户视口视角 | 完全复现用户视角 |
| `all_sensors` | 所有传感器数据 | 完整数据集 |

### 视口参数

```bash
--capture-mode viewport           # 使用视口模式
--show-viewport                   # 显示捕获窗口
--viewport-width 1920             # 视口宽度
--viewport-height 1080            # 视口高度
```

---

## 输出位置

生成的视频文件位于 `log/` 目录：

```
log/
├── holoocean_capture_2026-04-25_12-34-56.gif
└── holoocean_capture_2026-04-25_12-34-56.mp4
```

---

## 常见问题

### Q: 视频录制很慢

**原因**：GPU 渲染 + 编码开销

**解决**：
```bash
# 降低分辨率
--viewport-width 1280 --viewport-height 720

# 降低帧率
--fps 15
```

### Q: 视频与仿真不同步

**原因**：帧率不是仿真速度的整数倍

**检查**：
```bash
# 确保 fps 能被 ticks_per_sec 整除
# 例如：ticks_per_sec = 30，fps 可选 1, 2, 3, 5, 6, 10, 15, 30
```

### Q: GIF 文件过大

**原因**：GIF 不支持高效压缩

**解决**：使用 MP4 格式
```bash
--format mp4
```

---

## 高级用法

### 同时记录多个视角

```bash
python tools/capture_holoocean_video.py \
  --capture-mode all_sensors \
  --format mp4
```

### 后处理视频

```bash
# 使用 ffmpeg 转换
ffmpeg -i video.mp4 -vcodec h264 -acodec aac output.mp4

# 或压缩 GIF
gifsicle --optimize=3 --delay=3 input.gif > output.gif
```

---

**更新日期**：2026-04-25
