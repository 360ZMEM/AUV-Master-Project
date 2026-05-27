# Foxglove 可视化

## 概述

Foxglove 是 ROS2 数据可视化工具，支持 3D 场景渲染、曲线绘制、原始消息查看等功能。本项目已集成 Foxglove 布局自动生成，方便快速搭建 AUV 调试界面。

## 两种使用方式

### 1. 实时连接

`start_experiment.sh` 启动实验时已自动启动 `foxglove_bridge`，在 Foxglove Desktop 中通过 WebSocket 连接即可实时查看数据：

```
ws://localhost:8765
```

操作步骤：
1. 打开 Foxglove Desktop
2. 选择 "Open connection"
3. 输入 `ws://localhost:8765`
4. 连接成功后即可看到所有活跃话题

### 2. 离线回放

直接在 Foxglove 中打开 `.mcap` 文件即可回放历史数据：

1. 打开 Foxglove Desktop
2. 选择 "Open local file"
3. 选择 `$AUV_DATA_ROOT/bags/YYYYMMDD_HHMMSS/*.mcap`
4. 使用时间轴控制回放进度

## 布局生成

项目提供自动化布局生成工具：

```bash
# 方式一：通过脚本
cd scripts && bash build_foxglove_layout.sh

# 方式二：直接调用Python模块
python -m foxglove_layout_project.generator.build_layout --pretty
```

生成的布局文件输出至：

```
foxglove_layout_project/output/auv_layout.generated.<timestamp>.json
```

## 布局内容说明

### 3D 面板

- AUV 姿态可视化（实时 Mesh 渲染）
- 真值 Pose 标记（ground truth 位姿）
- 海底点云显示
- 电缆路径可视化
- 历史轨迹描绘

### Plot 面板

- **深度跟踪**：目标深度 vs 实际深度
- **速度跟踪**：目标速度 vs 实际速度
- **执行器输出**：推力/舵角指令时序

### RawMessages 面板

直接查看以下话题的原始消息：
- IMU 数据
- DVL 数据
- State（状态估计）
- Setpoint（目标设定）
- CmdVel（控制命令）
- Status（系统状态）

## 导入布局方法

1. 打开 Foxglove Desktop
2. 点击顶部菜单 **Layout**
3. 选择 **Import from file**
4. 选择生成的 JSON 文件（如 `auv_layout.generated.20260101_120000.json`）
5. 布局自动加载完成

## 常用 Topic 列表

| Topic | 类型 | 说明 |
|-------|------|------|
| /auv/state/filtered | Odometry | EKF 融合状态 |
| /auv/state/raw_dr | Odometry | 纯航位推算 |
| /auv/sensors/imu | Imu | IMU 原始数据 |
| /auv/sensors/dvl | TwistStamped | DVL 速度 |
| /auv/sensors/depth | Float32 | 深度 |
| /cmd_vel | Twist | 控制命令 |
| /auv/control/setpoint | Setpoint | 目标设定 |
| /auv/arbiter/status | ArbiterStatus | 仲裁状态 |

## 高级选项

### --topic-prefix

当多台 AUV 共存或使用命名空间时，可通过 `--topic-prefix` 指定话题前缀：

```bash
python -m foxglove_layout_project.generator.build_layout --topic-prefix /auv1
```

### --with-mock-topics

开发调试时若无真实数据源，可启用 mock 话题生成测试数据：

```bash
python -m foxglove_layout_project.generator.build_layout --with-mock-topics
```

此选项会在布局中添加模拟数据面板，方便在无仿真环境时验证布局配置。
