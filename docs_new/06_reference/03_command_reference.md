# 命令参考

本文档提供所有命令的完整参考。

## 目录

- [仿真命令](#仿真命令)
- [决策端命令](#决策端命令)
- [系统命令](#系统命令)
- [ROS2 命令](#ros2-命令)
- [调试命令](#调试命令)

## 仿真命令

### start_lin_sim.sh

启动 HoloOcean 仿真和 Zenoh 桥接。

```bash
bash start_lin_sim.sh <mode> [options]
```

**模式**:
- `sim` - 仅启动 HoloOcean 仿真
- `bridge` - 启动仿真 + Zenoh 桥接
- `both` - 同 bridge

**选项**:
- `--backend <backend>` - 桥接后端类型
  - `zenoh_json` (默认) - Zenoh JSON 通信
  - `protocol_udp` - 二进制 UDP 协议
- `--bridge-cfg <path>` - 桥接配置文件路径
- `--sim-cfg <path>` - 仿真配置文件路径

**示例**:
```bash
# 启动仿真
bash start_lin_sim.sh sim

# 启动仿真+桥接 (默认 zenoh_json)
bash start_lin_sim.sh both

# 启动仿真+桥接 (protocol_udp)
bash start_lin_sim.sh both --backend protocol_udp

# 使用自定义配置
bash start_lin_sim.sh both --bridge-cfg /path/to/config.yaml
```

### start_win_sim.bat

Windows 启动脚本。

```cmd
start_win_sim.bat <mode>
```

**模式**: `sim` 或 `bridge`

## 决策端命令

### start_lin_brain.sh

启动 ROS2 决策系统。

```bash
bash start_lin_brain.sh <command> [options]
```

**命令**:
- `bootstrap` - 首次构建 ROS2 工作区
- `stack` - 启动完整决策栈
- `bridge` - 仅启动桥接节点
- `localization` - 仅启动定位节点
- `controller` - 仅启动控制器节点
- `decision` - 仅启动决策节点
- `foxglove` - 仅启动 Foxglove

**选项**:
- `--backend <backend>` - 桥接后端 (zenoh_json, protocol_udp)
- `--protocol-control-mode-byte <value>` - 控制模式字节 (如 238)
- `--arbiter-profile` - 使用仲裁器配置

**示例**:
```bash
# 首次构建
bash start_lin_brain.sh bootstrap

# 启动完整栈 (zenoh_json)
bash start_lin_brain.sh stack

# 启动完整栈 (protocol_udp)
bash start_lin_brain.sh stack --backend protocol_udp --protocol-control-mode-byte 238

# 使用仲裁器配置
bash start_lin_brain.sh stack --arbiter-profile

# 启动单个节点
bash start_lin_brain.sh controller
```

## 系统命令

### start_foxglove_holoocean_ros.sh

一键启动完整系统（Foxglove + 仿真 + ROS2）。

```bash
bash start_foxglove_holoocean_ros.sh [options]
```

**选项**:
- `--bridge-backend <backend>` - 桥接后端类型
- `--bridge-cfg <path>` - 桥接配置文件
- `--sim-cfg <path>` - 仿真配置文件
- `--protocol-control-mode-byte <value>` - 控制模式字节
- `--skip-layout` - 跳过 Foxglove 布局生成

**示例**:
```bash
# 完整系统启动
bash start_foxglove_holoocean_ros.sh

# protocol_udp 模式
bash start_foxglove_holoocean_ros.sh --bridge-backend protocol_udp --protocol-control-mode-byte 238

# 跳过布局生成
bash start_foxglove_holoocean_ros.sh --skip-layout
```

### start_experiment.sh

运行长时间实验。

```bash
bash start_experiment.sh [options]
```

**选项**:
- `--duration <seconds>` - 实验持续时间（秒）
- `--bag-storage <type>` - bag 存储类型 (mcap, sqlite)

**示例**:
```bash
# 120 秒实验
bash start_experiment.sh --duration 120 --bag-storage mcap
```

## ROS2 命令

### Topic 操作

```bash
# 列出所有话题
ros2 topic list

# 查看话题信息
ros2 topic info /topic_name

# 查看话题类型
ros2 topic info /auv/sensors/imu

# 实时查看话题数据
ros2 topic echo /topic_name

# 查看单条消息
ros2 topic echo /topic_name --once

# 查看话题发布频率
ros2 topic hz /topic_name

# 查看话题带宽
ros2 topic bw /topic_name
```

### 节点操作

```bash
# 列出所有节点
ros2 node list

# 查看节点信息
ros2 node info /node_name

# 查看节点参数
ros2 param list /node_name

# 获取参数值
ros2 param get /node_name parameter_name

# 设置参数值
ros2 param set /node_name parameter_name value
```

### 服务操作

```bash
# 列出所有服务
ros2 service list

# 查看服务类型
ros2 service type /service_name

# 调用服务
ros2 service call /service_name service_type "{arg: value}"
```

### Bag 操作

```bash
# 记录所有话题
ros2 bag record -a -o bag_name

# 记录特定话题
ros2 bag record /topic1 /topic2 -o bag_name

# 回放 bag
ros2 bag play bag_name

# 查看 bag 信息
ros2 bag info bag_name
```

## 调试命令

### sniffer.py

UDP 协议嗅探工具。

```bash
/usr/bin/python3 scripts/sniffer.py [options]
```

**选项**:
- `--bind-port <port>` - 绑定端口（默认 52364）
- `--show-hex` - 显示十六进制

**示例**:
```bash
# 监听默认端口
/usr/bin/python3 scripts/sniffer.py

# 监听指定端口，显示十六进制
/usr/bin/python3 scripts/sniffer.py --bind-port 52364 --show-hex
```

### 独立节点运行

```bash
# 桥接节点
ros2 run auv_bridge zenoh_json_bridge_node \
  --ros-args \
  -p params_file:=/path/to/params.yaml

# 控制器节点
ros2 run auv_controller controller_node \
  --ros-args \
  -p params_file:=/path/to/params.yaml

# 定位节点
ros2 run auv_localization localization_node \
  --ros-args \
  -p params_file:=/path/to/params.yaml

# 决策节点
ros2 run auv_decision decision_node \
  --ros-args \
  -p params_file:=/path/to/params.yaml
```

## 工具命令

### Foxglove 布局生成

```bash
cd foxglove_layout_project
/usr/bin/python3 -m foxglove_layout_project.generator.build_layout [options]
```

**选项**:
- `--pretty` - 美化输出 JSON
- `--with-mock-topics` - 生成 mock topic 快照

**示例**:
```bash
# 生成布局
/usr/bin/python3 -m foxglove_layout_project.generator.build_layout --pretty

# 生成布局 + mock topics
/usr/bin/python3 -m foxglove_layout_project.generator.build_layout --with-mock-topics --pretty
```

### 仿真等价性检查

```bash
bash scripts/run_sim_equivalence_check.sh [options]
```

**选项**:
- `--dry-run` - 只检查不运行

## 快速参考卡

### 最常用命令

```bash
# 完整系统启动
bash start_foxglove_holoocean_ros.sh

# 仅仿真
bash start_lin_sim.sh sim

# 仅决策端
bash start_lin_brain.sh stack

# 查看话题
ros2 topic list
ros2 topic echo /auv/sensors/imu

# 查看节点
ros2 node list
ros2 run rqt_graph rqt_graph
```

### 模式切换

```bash
# zenoh_json 模式
bash start_lin_brain.sh stack --backend zenoh_json

# protocol_udp 模式
bash start_lin_brain.sh stack --backend protocol_udp --protocol-control-mode-byte 238

# 仲裁器模式
bash start_lin_brain.sh stack --arbiter-profile
```

### 调试

```bash
# 查看控制器调试信息
ros2 topic echo /auv/controller/debug

# 查看诊断信息
ros2 topic echo /auv/diagnostics

# 记录数据
ros2 bag record -a -o debug_bag

# 协议嗅探
/usr/bin/python3 scripts/sniffer.py
```

## 环境变量

```bash
# 项目根目录
export AUV_PROJECT_ROOT=~/AUV_Master_Project

# ROS2 环境
source /opt/ros/humble/setup.bash

# 工作区环境
source $AUV_PROJECT_ROOT/brain_linux/install/setup.bash
```

## 相关文档

- [快速开始](../01_getting_started/03_first_run.md) - 第一次运行
- [运行模式切换](../05_operations/01_mode_switching.md) - 模式切换详解
- [控制调试](../05_operations/02_control_debugging.md) - 调试指南
