# 快速安装

本文档指导你在 5 分钟内完成开发环境配置。

## 系统要求

### 硬件要求

- CPU: 4 核心及以上
- 内存: 4GB 及以上（推荐 8GB）
- 硬盘: 20GB 可用空间

### 软件版本

- **操作系统**: Ubuntu 22.04 LTS
- **Python**: 3.10（系统 Python `/usr/bin/python3`）
- **ROS2**: Humble Hawksbill

### 多个后端

- 本仿真仓库目前包含了holoocean和Python Vehicle Simulator（下称PVS）两个后端仿真，它们支持AUV的动力学仿真。
- 其中holoocean建议使用6GB+ VRAM的显卡进行驱动（如果运行声呐，建议至少100GB+的磁盘空间，8GB+ VRAM和较强的CPU）。由于Python Vehicle Simulator配置和安装难度显著较低，我们建议新手从这里开始。holoocean更适合炫酷的画面效果，真实的动力学，但是算法迭代上更推荐PVS。
- 本代码仓库已经在2.2.2的holoocean版本，以及截至2025年5月的Python Vehicle Simulator（使用\`git checkout c717e07\`）下测试通过。
- 遵循两个后端各自的安装规程完成基础配置：
  - holoocean：<https://byu-holoocean.github.io/holoocean-docs/develop/usage/installation.html>
  - PVS：<https://github.com/cybergalactic/PythonVehicleSimulator>

## 安装步骤

### 1. 安装 ROS2 Humble

如果尚未安装 ROS2 Humble：

```bash
# 懒人安装脚本
wget http://fishros.com/install -O fishros && . fishros
```

### 2. 安装 ROS2 系统包

```bash
sudo apt-get update
sudo apt-get install -y \
    ros-humble-foxglove-bridge \
    ros-humble-rosbag2-storage-mcap \
    libwebsocketpp-dev \
    nlohmann-json3-dev \
    fonts-wqy-zenhei
```

| 包名                                | 说明                            |
| --------------------------------- | ----------------------------- |
| `ros-humble-foxglove-bridge`      | Foxglove WebSocket 桥接，用于实时可视化 |
| `ros-humble-rosbag2-storage-mcap` | MCAP 存储 backend，用于高效 bag 录制   |
| `libwebsocketpp-dev`              | foxglove\_bridge 的编译依赖        |
| `nlohmann-json3-dev`              | JSON 处理库依赖                    |
| `fonts-wqy-zenhei`                  | 中文字体，用于 matplotlib 图表显示 |

### 3. 安装 Python 依赖

**重要提示**: 使用系统 Python，避免使用 conda 环境！

```bash
# 确认使用系统 Python
which python3  # 应该输出 /usr/bin/python3

# 安装核心 Python 包 (全局安装，不要 --user)
/usr/bin/python3 -m pip install \
    eclipse-zenoh \
    pyyaml \
    py_trees \
    numpy \
    matplotlib \
    foxglove-sdk \
    mcap \
    mcap-ros2-support \
    pandas \
    seaborn \
    PySide6
```

| 包名                           | 说明                                                            |
| ---------------------------- | ------------------------------------------------------------- |
| `eclipse-zenoh`              | Zenoh 通信中间件（注意：安装包名是 `eclipse-zenoh`，但代码中 `import zenoh`）     |
| `py_trees`                   | 行为树引擎，决策系统核心依赖                                                |
| `foxglove-sdk`               | Foxglove Python SDK，用于数据记录和可视化                                |
| `mcap` / `mcap-ros2-support` | MCAP 格式读写，离线分析工具依赖                                            |
| `pandas` / `seaborn`         | 数据分析和可视化                                                      |
| `PySide6`                    | Qt for Python 框架，用于底层协议调试小工具 (Manual Protocol Injector) 等独立工具 |

### 4. 设置 Foxglove SDK ROS 工作区

启动脚本 `start_foxglove_holoocean_ros.sh` 需要一个 Foxglove SDK ROS 工作区路径。
由于 `ros-humble-foxglove-bridge` 已通过 apt 安装，只需创建一个 stub：

```bash
mkdir -p /home/$USER/auv_ws/foxglove-sdk/ros/install
cat > /home/$USER/auv_ws/foxglove-sdk/ros/install/local_setup.bash << 'EOF'
# Foxglove SDK ROS stub - uses system-installed ros-humble-foxglove-bridge
# The actual foxglove_bridge is provided by: ros-humble-foxglove-bridge (apt)
source /opt/ros/humble/setup.bash
EOF
```

### 5. 首次构建 ROS2 工作区

```bash
cd scripts
bash start_lin_brain.sh bootstrap
```

这个脚本会：

- 检查系统 Python 环境
- 自动禁用 conda 环境
- 构建 brain\_linux ROS2 工作区
- 安装必要的依赖

### 6. 验证安装

```bash
# 检查 ROS2 环境
source /opt/ros/humble/setup.bash
ros2 --version  # 应该显示 ROS 2 版本

# 检查 Python 包
/usr/bin/python3 -c "import zenoh; print('zenoh OK')"
/usr/bin/python3 -c "import py_trees; print('py_trees OK')"
/usr/bin/python3 -c "import foxglove; print('foxglove-sdk OK')"
/usr/bin/python3 -c "import mcap; print('mcap OK')"
/usr/bin/python3 -c "import PySide6; print('PySide6 OK')"

# 检查项目结构
ls brain_linux/src/

# 检查 Foxglove bridge
ros2 pkg list | grep foxglove  # 应该显示 foxglove_bridge

# 检查 MCAP 存储
ros2 bag record -h 2>&1 | grep mcap  # 应该显示 mcap 选项
```

## 常见安装问题

### 问题 1: ModuleNotFoundError: No module named 'zenoh'

**原因**: 可能使用了 conda 环境或 pip 安装到了错误的 Python 环境。正确的包名是 `eclipse-zenoh`。

**解决方法**:

```bash
# 确认退出 conda 环境
conda deactivate
conda deactivate

# 使用系统 Python 重新安装（全局安装，不要 --user）
/usr/bin/python3 -m pip install eclipse-zenoh
```

**导入说明**: 安装包名是 `eclipse-zenoh`，但代码中 `import zenoh`，这是正常的。

### 问题 2: ROS2 命令找不到

**原因**: ROS2 环境未正确 source。

**解决方法**:

```bash
source /opt/ros/humble/setup.bash
source ~/AUV_Master_Project/brain_linux/install/setup.bash
```

### 问题 3: 构建失败

**原因**: 可能是 Python 版本或路径问题。

**解决方法**:

```bash
# 清理构建缓存
cd brain_linux
rm -rf build install log

# 重新构建
cd ~/AUV_Master_Project/scripts
bash start_lin_brain.sh bootstrap
```

### 问题 4: foxglove\_bridge 启动失败

**原因**: Foxglove SDK ROS 工作区路径不存在。

**解决方法**: 确保已创建 stub 文件（见步骤 4）：

```bash
ls /home/$USER/auv_ws/foxglove-sdk/ros/install/local_setup.bash
# 如果不存在，按照步骤 4 创建
```

### 问题 5: MCAP bag 录制失败

**原因**: 未安装 `ros-humble-rosbag2-storage-mcap`。

**解决方法**:

```bash
sudo apt-get install -y ros-humble-rosbag2-storage-mcap
```

如果 MCAP 不可用，可使用 sqlite3 替代：

```bash
bash start_experiment.sh --bag-storage sqlite3 --duration 120
```

## 环境变量配置（可选）

为了方便使用，可以添加以下内容到 `~/.bashrc`：

```bash
# ROS2 环境
source /opt/ros/humble/setup.bash

# AUV 项目环境
export AUV_PROJECT_ROOT=~/AUV_Master_Project
source $AUV_PROJECT_ROOT/brain_linux/install/setup.bash

# 确保使用系统 Python
alias python=/usr/bin/python3
alias pip='/usr/bin/python3 -m pip'
```

## 附录：在 Linux (arm64) 上安装 `ffmpeg`

本项目在将 GIF/帧转换为 MP4 或做视频转码时会用到 `ffmpeg`。可以遵循下面的命令安装:

### 1) Ubuntu / Debian（arm64）

```bash
sudo apt update
sudo apt install -y ffmpeg
```

或者:

```bash
#mamba install -y -c conda-forge ffmpeg
# 或
conda install -y -c conda-forge ffmpeg
```

### 验证安装

```bash
ffmpeg -version
which ffmpeg
```

## 附录：MCAP 一键导出三路 MP4（曲线 + Holoocean 双视角）

安装好 `ffmpeg` 后，可以用如下命令从一个 MCAP 一次性导出三路 MP4：

```bash
/usr/bin/python3 tools/capture_holoocean_video.py \
  --mcap-input log/experiments/20260503_204842/rosbag/rosbag_0.mcap \
  --mcap-render-all \
  --mcap-render-all-prefix replay_batch \
  --mcap-render-all-dir log/replays \
  --mcap-render-all-json log/replays/replay_batch_manifest.json \
  --format mp4 \
  --fps 12
```

输出文件说明：
- `*_curves.mp4`：matplotlib 轨迹/深度曲线回放
- `*_holoocean_agent.mp4`：Holoocean agent 视角（MCAP 位姿驱动）
- `*_holoocean_viewport.mp4`：Holoocean viewport 视角（MCAP 位姿驱动）

新增参数说明：
- `--mcap-render-all-dir`：指定三路视频输出目录（默认 `log/`）
- `--mcap-render-all-json`：输出 JSON 清单（包含三路结果路径）
- `--mcap-render-all-prefix`：批次文件名前缀

## 下一步

安装完成后，继续阅读：

- [第一次运行](03_first_run.md) - 启动第一个仿真

