# 上位机使用指南

说明上位机 `console_soft/auv_console_pyside6/` 的使用方法。

---

## 概述

PySide6 GUI 上位机程序，提供以下核心功能：

- **遥控 AUV**：手动发送舵角/推力指令
- **授权自主控制**：向 Jetson 下发任务目标，授权自主决策
- **紧急停止（ESTOP）**：一键切断所有自主动作
- **任务规划**：航点设定、路径预览

---

## 启动方式

```bash
cd console_soft/auv_console_pyside6
python main.py
```

---

## 依赖安装

```bash
cd console_soft/auv_console_pyside6
pip install -r requirements.txt
```

主要依赖：

| 包 | 用途 |
|----|------|
| PySide6 | Qt GUI 框架 |
| eclipse-zenoh | Zenoh 通信 |
| numpy | 数据处理 |
| pyserial（可选） | 串口通信（真机调试） |

---

## 三种工作模式

| 模式 | 通信方式 | 用途 |
|------|---------|------|
| 手动遥控 (MANUAL) | UDP `$CKTH` 包 | 直接操控舵角/推力，低延迟控制 |
| 自主授权 (AUTONOMY) | Zenoh JSON | 下发任务目标给 Jetson，由 Brain 自主执行 |
| 紧急切断 (ESTOP) | UDP + Zenoh 双通道 | 紧急停止一切自主动作，双通道确保可靠性 |

### 手动遥控 (MANUAL)

- 通过 UDP 发送 `$CKTH` 格式数据包
- 直接控制舵角（水平舵、垂直舵）和推进器推力
- 适用于人工干预或手动导航

### 自主授权 (AUTONOMY)

- 通过 Zenoh JSON 消息下发任务目标（航点坐标、深度、速度等）
- Jetson 端 Brain 节点接收后自主规划执行
- 上位机监控执行状态，可随时回收控制权

### 紧急切断 (ESTOP)

- 同时通过 UDP 和 Zenoh 双通道发送停止指令
- 双通道设计确保至少一个通道可达
- 触发后 AUV 立即停止所有自主动作，进入安全状态

---

## 配置文件

配置文件位于 `console_config.yaml`，主要配置项：

```yaml
zenoh:
  peer: "tcp/192.168.1.100:7447"    # Zenoh 对端地址
  prefix: "auv/"                     # Topic 前缀

udp:
  target_ip: "192.168.1.100"         # AUV 目标 IP
  target_port: 5000                  # 目标端口
  listen_port: 5001                  # 本地监听端口

heartbeat:
  frequency_hz: 2                    # 心跳发送频率（Hz）
  timeout_ms: 3000                   # 心跳超时时间（ms）

estop:
  confirm_dialog: true               # ESTOP 前是否弹出确认对话框
```

---

## 界面功能说明

### 遥测显示

- 姿态角（Roll/Pitch/Yaw）
- 深度、高度
- 速度（前进/侧移/垂直）
- 电池电压、电流
- 通信状态指示灯

### 地图

- 显示 AUV 当前位置（GPS/惯导）
- 历史轨迹绘制
- 航点标注

### 航点规划

- 在地图上点击添加航点
- 设置每个航点的目标深度和速度
- 一键下发航点序列

### ESTOP 按钮

- 界面右上角醒目红色按钮
- 点击后立即发送双通道停止指令
- 可配置是否弹出确认对话框（`estop.confirm_dialog`）

---

## 与仿真联调

### 连接 Mock AMD（PVS 模式）

当仿真使用 PVS 后端时，上位机直接连接 Mock AMD 节点：

```yaml
# console_config.yaml
udp:
  target_ip: "127.0.0.1"
  target_port: 5000
  listen_port: 5001

zenoh:
  peer: "tcp/127.0.0.1:7447"
```

### 连接 Zenoh Bridge（HoloOcean 模式）

HoloOcean 后端通过 Zenoh Bridge 转发 ROS2 话题：

```yaml
# console_config.yaml
zenoh:
  peer: "tcp/127.0.0.1:7447"
  prefix: "auv/"
```

### 联调步骤

1. 先启动仿真：`bash start_experiment.sh --sim-backend pvs --duration 300`
2. 再启动上位机：`python main.py`
3. 上位机自动连接本地 Zenoh/UDP 端口
4. 在界面中切换到 MANUAL 模式进行手动控制测试

---

## 注意事项

> **⚠️ `console_soft/csharp/` 是旧版 C# WinForms 程序，已废弃。**
>
> 该目录仅供协议格式参照（`$CKTH` 包结构、校验算法等），不再维护和使用。
> 所有新开发工作请基于 `auv_console_pyside6/` 进行。
