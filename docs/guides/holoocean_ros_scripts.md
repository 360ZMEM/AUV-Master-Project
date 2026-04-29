# 🚀 HoloOcean 与 ROS 脚本集成说明

本文档介绍如何将 HoloOcean 仿真、Foxglove 可视化和 ROS2 决策栈通过脚本集成使用。

---

## 一键启动脚本

### 完整联动启动（推荐）

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/scripts
bash start_foxglove_holoocean_ros.sh
```

**功能**：
- ✅ 自动启动 HoloOcean 仿真
- ✅ 自动启动 Zenoh 桥接
- ✅ 自动启动 ROS2 决策栈
- ✅ 自动启动 Foxglove Web 界面
- ✅ 自动打开浏览器到 `http://localhost:3000`

### 高级选项

```bash
# 使用协议 UDP（二进制通信）
bash start_foxglove_holoocean_ros.sh --backend protocol_udp

# 指定控制模式字节（与实物相同）
bash start_foxglove_holoocean_ros.sh --backend protocol_udp --protocol-control-mode-byte 238

# 指定实验时长（秒）
bash start_foxglove_holoocean_ros.sh --duration 120
```

---

## 独立启动脚本

### 1. 仅启动 Foxglove 布局生成

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/scripts
bash start_foxglove_layout.sh
```

**输出**：
- `foxglove_layout_project/output/auv_layout.generated.<unix>.json`
- `foxglove_layout_project/output/auv_layout.generated.<unix>.meta.json`

### 2. 仅启动 HoloOcean / Zenoh

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/scripts
bash start_holoocean_sim.sh

# 指定参数
bash start_holoocean_sim.sh --sim-backend pvs --backend protocol_udp
```

### 3. 仅启动 ROS2 脑端

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/scripts
bash start_ros_brain.sh

# 启动特定节点
bash start_ros_brain.sh stack
bash start_ros_brain.sh decision
bash start_ros_brain.sh controller
```

---

## 脚本工作原理

### start_foxglove_holoocean_ros.sh 的执行流程

```bash
# 步骤 1：验证环境
- 检查 Python 3.10+
- 检查 ROS2 Humble 是否安装
- 检查 HoloOcean 是否可用

# 步骤 2：启动仿真后台
python sim_holoocean/apps/main.py --config config/sim_params.yaml &

# 步骤 3：等待仿真初始化
sleep 5

# 步骤 4：启动 ROS2 决策栈
source /opt/ros/humble/setup.bash
ros2 launch brain_linux/launch/decision_stack.launch.py &

# 步骤 5：启动 Foxglove 桥接
ros2 launch foxglove_bridge foxglove_bridge_launch.xml &

# 步骤 6：打开浏览器
xdg-open http://localhost:3000
```

---

## 常见使用场景

### 场景 1：快速验证闭环

```bash
# 一键启动，默认 150 秒实验
bash start_foxglove_holoocean_ros.sh

# 在 Foxglove 中观察：
# - 车体轨迹（3D Scene）
# - 控制指令（Plot）
# - 状态变化（State Indicator）
```

### 场景 2：对比 HoloOcean 与 PVS

```bash
# 运行 HoloOcean 版本
bash start_foxglove_holoocean_ros.sh --sim-backend holoocean --run-id holoocean

# 运行 PVS 版本
bash start_foxglove_holoocean_ros.sh --sim-backend pvs --run-id pvs

# 对比结果
python tools/compare_runs.py log/holoocean/ log/pvs/
```

### 场景 3：实物协议验证

```bash
# 使用与实物完全相同的配置
bash start_foxglove_holoocean_ros.sh \
  --backend protocol_udp \
  --protocol-control-mode-byte 238
```

---

## 脚本参数详解

### 通用参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--sim-backend` | `holoocean` | 仿真后端：`holoocean` 或 `pvs` |
| `--backend` | `zenoh_json` | 通信后端：`zenoh_json` 或 `protocol_udp` |
| `--duration` | `150` | 实验时长（秒） |
| `--run-id` | 自动生成 | 实验标识（用于日志命名） |

### 仿真参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--config` | `config/sim_params.yaml` | 仿真配置文件路径 |
| `--no-zenoh` | false | 禁用 Zenoh 桥接（仅仿真） |

### 决策参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--protocol-control-mode-byte` | - | 控制模式字节（协议 UDP 用） |
| `--arbiter-profile` | false | 启用仲裁器 |

---

## 故障排除

### Q: 脚本启动后什么都没发生

**检查**：
```bash
# 查看进程
ps aux | grep -E "(python|ros2)"

# 查看日志
tail -f log/sim_*.log
tail -f log/decision_*.log
```

### Q: Foxglove 浏览器没有打开

**手动打开**：
```bash
xdg-open http://localhost:3000
# 或
firefox http://localhost:3000
```

### Q: ROS2 节点启动失败

**解决**：
```bash
# 重新编译
cd brain_linux
colcon build --symlink-install
source install/setup.bash

# 检查环境
echo $ROS_DOMAIN_ID
export ROS_DOMAIN_ID=0  # 若需要
```

### Q: 不同步（仿真 vs 决策）

**检查**：
```bash
# 查看 Zenoh topic 是否发布
ros2 topic list | grep auv

# 查看消息频率
ros2 topic hz /auv/sensors/imu
```

---

## 扩展与自定义

### 修改实验时长

编辑 `start_foxglove_holoocean_ros.sh`：

```bash
# 找到这一行
DURATION=150

# 改为你想要的值
DURATION=300  # 5 分钟
```

### 添加自定义启动选项

在脚本顶部添加新参数：

```bash
# 解析参数
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --my-custom-option) MY_CUSTOM_OPTION="$2"; shift ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done
```

### 集成到其他工作流

```bash
# 在 CI/CD 脚本中
#!/bin/bash
set -e  # 遇到错误立即停止

# 启动实验
bash scripts/start_foxglove_holoocean_ros.sh --duration 60

# 等待完成
sleep 60

# 运行验证
python tools/validate_experiment.py log/latest/
```

---

## 相关资源

- [端到端设置](end_to_end_setup.md) — 完整闭环的详细说明
- [仿真启动指南](simulation_startup.md) — HoloOcean 启动
- [决策启动指南](brain_startup.md) — ROS2 决策启动
- [Foxglove 配置](foxglove_setup.md) — 可视化界面配置

---

**更新日期**：2026-04-25
