# 快速参考卡

常用命令和信息的快速查询卡片。

## 一键启动

```bash
# 完整系统（推荐）
cd ~/AUV_Master_Project/scripts
bash start_foxglove_holoocean_ros.sh

# 仅仿真
bash start_lin_sim.sh sim

# 仅决策端
bash start_lin_brain.sh stack
```

## 模式切换

```bash
# zenoh_json (默认)
bash start_lin_brain.sh stack --backend zenoh_json

# protocol_udp
bash start_lin_sim.sh both --backend protocol_udp
bash start_lin_brain.sh stack --backend protocol_udp --protocol-control-mode-byte 238

# 仲裁器模式
bash start_lin_brain.sh stack --arbiter-profile
```

## 常用 ROS2 命令

```bash
# 查看话题
ros2 topic list

# 查看数据
ros2 topic echo /auv/sensors/imu
ros2 topic echo /auv/state/filtered
ros2 topic echo /cmd_vel

# 查看节点
ros2 node list
ros2 run rqt_graph rqt_graph
```

## Topic 速查

### 传感器
- `/auv/sensors/imu` - IMU 数据
- `/auv/sensors/dvl` - DVL 数据
- `/auv/sensors/depth` - 深度数据
- `/auv/sensors/magnetic` - 磁场数据

### 状态
- `/auv/state/filtered` - 融合后的状态
- `/auv/diagnostics` - 诊断信息

### 控制
- `/auv/control/setpoint` - 控制目标
- `/cmd_vel` - 控制指令
- `/auv/controller/debug` - 控制器调试

## 常见问题速解

### zenoh 模块未找到
```bash
conda deactivate
/usr/bin/python3 -m pip install --user zenoh
```

### ROS2 命令找不到
```bash
source /opt/ros/humble/setup.bash
source ~/AUV_Master_Project/brain_linux/install/setup.bash
```

### 构建失败
```bash
cd ~/AUV_Master_Project/brain_linux
rm -rf build install log
cd ~/AUV_Master_Project/scripts
bash start_lin_brain.sh bootstrap
```

### 没有传感器数据
1. 检查仿真是否运行
2. 检查桥接节点
3. 查看 `/auv/sensors/*` 话题

### 控制无效
1. 查看 `/cmd_vel` 是否有数据
2. 查看控制模式
3. 检查参数配置

## 目录结构

```
AUV_Master_Project/
├── common/              # 共享契约
├── algorithm/           # 算法
├── config/              # 配置
├── sim_holoocean/       # 仿真
├── brain_linux/         # ROS2 决策
├── scripts/             # 启动脚本
├── docs/                # 旧文档
└── docs_new/            # 新文档 ✨
```

## 文档导航

- **新手**: 查看 `docs_new/01_getting_started/`
- **架构**: 查看 `docs_new/02_architecture/`
- **开发**: 查看 `docs_new/04_development/`
- **调试**: 查看 `docs_new/05_operations/`
- **参考**: 查看 `docs_new/06_reference/`

## 配置文件

| 配置 | 路径 |
|------|------|
| 仿真配置 | `config/sim_params.yaml` |
| 桥接配置 | `config/bridge_params.yaml` |
| 决策配置 | `brain_linux/config/params.yaml` |
| UDP 桥接 | `config/bridge_params.protocol_udp.yaml` |
| 仲裁器 | `brain_linux/config/params.protocol_udp_arbiter.yaml` |

## 性能参考

| 指标 | 正常值 |
|------|--------|
| 传感器延迟 | < 1 ms |
| 状态估计延迟 | < 10 ms |
| 控制延迟 | < 20 ms |
| 总延迟 | < 50 ms |

## 关键文件

| 功能 | 文件 |
|------|------|
| 协议定义 | `common/protocol.py` |
| 枚举定义 | `common/enums.py` |
| 仲裁器 | `brain_linux/src/auv_bridge/auv_bridge/arbiter.py` |
| 控制器 | `algorithm/auv_pid_controller.py` |
| 桥接节点 | `brain_linux/src/auv_bridge/auv_bridge/bridge_node.py` |

## 环境检查

```bash
# Python 环境
which python3          # 应该是 /usr/bin/python3
/usr/bin/python3 -c "import zenoh; print(zenoh.__version__)"

# ROS2 环境
ros2 --version
source /opt/ros/humble/setup.bash

# 项目环境
ls ~/AUV_Master_Project/brain_linux/src/
```

## 调试工具

### 协议调试

```bash
# Sniffer - 单行格式（默认）
/usr/bin/python3 scripts/sniffer.py

# Sniffer - ASCII 格式（详细，适合调试）
/usr/bin/python3 scripts/sniffer.py --ascii-format

# Sniffer - 原始紧凑格式（CSV，适合脚本）⭐
/usr/bin/python3 scripts/sniffer.py --raw-format

# Sniffer - 原始格式保存到文件
/usr/bin/python3 scripts/sniffer.py --raw-format > raw_log.csv

# Sniffer - 只捕获 10 个报文
/usr/bin/python3 scripts/sniffer.py --raw-format --count 10

# 启用 Mock AMD 原始格式日志
vim config/bridge_params.protocol_udp.yaml
# 设置 log_raw_format: true
```

### 协议日志处理

```bash
# 提取深度数据
awk -F',' '$1=="$AUV" {print $6}' raw_log.csv

# 提取推力数据
awk -F',' '$1=="$CKTH" {print $10}' raw_log.csv

# 统计报文数量
echo "下行: $(grep -c '^$CKTH' raw_log.csv)"
echo "上行: $(grep -c '^$AUV' raw_log.csv)"

# 查找异常值
awk -F',' '$1=="$AUV" && $6>20' raw_log.csv  # 深度超过 20m
awk -F',' '$1=="$CKTH" && $9>80' raw_log.csv  # 推力超过 80%
```

### ROS2 调试

```bash
# Foxglove 布局生成
cd foxglove_layout_project
/usr/bin/python3 -m foxglove_layout_project.generator.build_layout --pretty

# 记录数据
ros2 bag record -a -o debug_bag

# 回放数据
ros2 bag play debug_bag

# 查看 bag 信息
mcap info debug_bag
```

### 日志分析

```bash
# 查看协议日志
cat log/experiments/*/experiment_runs/*/launcher.log

# 提取控制命令
grep "Control Surfaces:" launcher.log

# 查看校验和错误
grep "Checksum:" launcher.log | grep -v "OK"

# 统计报文数量
grep "DOWNLINK" launcher.log | wc -l
grep "UPLINK" launcher.log | wc -l
```

## 获取帮助

- [常见问题](01_getting_started/04_faq.md)
- [日志解读](05_operations/05_log_analysis.md)
- [原始格式指南](05_operations/07_raw_format_guide.md) - CSV 格式与脚本处理
- [协议日志示例](05_operations/06_protocol_logging_examples.md)
- [控制调试](05_operations/02_control_debugging.md)
- [命令参考](06_reference/03_command_reference.md)
- [历史文档](06_reference/04_legacy_docs.md)

---

**提示**: 将此文件加入书签，方便快速查询！
