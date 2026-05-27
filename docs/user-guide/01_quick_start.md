# 快速开始

面向完全没有经验的新用户，目标：**5 分钟内运行第一次仿真**。

---

## 前置条件

| 依赖 | 最低版本 | 说明 |
|------|---------|------|
| Python | 3.10+ | 推荐 3.10 或 3.11 |
| ROS 2 | Humble Hawksbill | 需 source `/opt/ros/humble/setup.bash` |
| Conda 环境 | — | 环境名称：`holoocean`，用于隔离项目依赖 |
| zenoh-python | 0.10+ | Zenoh 通信中间件 Python 绑定 |
| py_trees | 2.2+ | 行为树框架 |
| HoloOcean（可选） | — | 仅使用 HoloOcean 后端时需要 |

激活环境：

```bash
conda activate holoocean
source /opt/ros/humble/setup.bash
```

---

## 最简启动命令（三步）

使用 **PVS 后端**（Pure Virtual Simulation），最轻量，无需 HoloOcean 引擎：

```bash
# 1. 进入脚本目录
cd /path/to/AUV-Master-Project/scripts

# 2. 启动 PVS 仿真，运行 120 秒
bash start_experiment.sh --sim-backend pvs --duration 120

# 3. 观察输出 —— 日志目录自动生成
#    路径格式：$AUV_DATA_ROOT/bags/YYYYMMDD_HHMMSS/
```

> **提示**：如果未设置 `$AUV_DATA_ROOT`，默认输出到项目根目录下的 `data/bags/`。

---

## 输出解读

仿真结束后，在输出目录中你会看到以下文件：

```
$AUV_DATA_ROOT/bags/20260527_143022/
├── metadata.txt        # 运行参数快照
├── rosbag2_*.mcap      # ROS2 bag 录制文件
└── ...
```

### metadata.txt

记录本次运行的完整参数快照，包括后端类型、持续时间、配置文件路径等，方便复现。

### *.mcap（ROS2 Bag 文件）

使用项目自带工具分析：

```bash
python tools/analyze_bag.py $AUV_DATA_ROOT/bags/20260527_143022/
```

### Foxglove 实时查看

仿真运行期间，Foxglove WebSocket 桥接自动启动，浏览器打开：

```
ws://localhost:8765
```

可在 [Foxglove Studio](https://foxglove.dev/studio) 中添加该 WebSocket 连接进行实时可视化。

---

## HoloOcean 后端（完整 3D 环境）

如果已安装 HoloOcean 引擎，可使用完整 3D 仿真：

```bash
bash start_experiment.sh --duration 120
```

默认 `--sim-backend` 即为 `holoocean`，将启动完整的水下 3D 渲染环境。

---

## 常见错误排查

### zenoh 未安装

```
ModuleNotFoundError: No module named 'zenoh'
```

**解决**：

```bash
pip install eclipse-zenoh
```

### py_trees 未安装

```
ModuleNotFoundError: No module named 'py_trees'
```

**解决**：

```bash
pip install py_trees
```

### Conda 环境冲突

如果出现依赖版本冲突，确保在 `holoocean` 环境中操作：

```bash
conda activate holoocean
pip list | grep -E "zenoh|py_trees|pyside6"
```

若版本不对，可重建环境：

```bash
conda deactivate
conda env remove -n holoocean
conda create -n holoocean python=3.10
conda activate holoocean
pip install -r requirements.txt
```

### ROS 2 节点找不到

```
Package 'xxx' not found
```

**解决**：确保已 source ROS 2 和工作空间：

```bash
source /opt/ros/humble/setup.bash
source ~/auv_ws/install/setup.bash
```

### HoloOcean 引擎未安装（仅 holoocean 后端）

```
HoloOcean engine not found
```

**解决**：使用 `--sim-backend pvs` 跳过 HoloOcean，或按照 HoloOcean 文档安装引擎。
