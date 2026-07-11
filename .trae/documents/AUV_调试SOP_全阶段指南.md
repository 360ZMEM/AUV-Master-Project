# AUV 系统调试 SOP — 从仿真到实机部署

> 生成时间: 2026-05-26  
> 基于仓库实际代码结构分析

---

## 一、系统架构总览与模式流转

### 1.1 三层架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│  上位机 Console (PySide6)                                                │
│  IP: 192.168.0.11                                                        │
│  发送: 72字节 $CKTH → UDP → AMD                                          │
│  功能: 模式切换(字节7) + 设备指令(字节22) + 推力/舵角(字节23-34)           │
│        + Zenoh 语义心跳 → rt/pc/cmd_raw                                  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ UDP / Zenoh
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Jetson (brain_linux ROS2 栈)                                            │
│  IP: 192.168.0.102 (Jetson) 或 localhost (仿真)                           │
│                                                                           │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  Bridge Node (zenoh_json_bridge / protocol_udp_bridge)           │    │
│  │    ├─ AutonomyGuard: 准入检查 (电压/漏水/遥测新鲜度)             │    │
│  │    ├─ CommandArbiter: 仲裁 REMOTE ↔ AUTONOMOUS                  │    │
│  │    └─ Transport: Zenoh JSON 或 Protocol UDP                      │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│  ┌────────────────┐ ┌────────────────────┐ ┌────────────────────────┐   │
│  │ Localization   │ │ Controller (MPC)   │ │ Decision (行为树)       │   │
│  │ (ES-EKF)       │ │ (PID级联/MPC)      │ │ (任务规划)             │   │
│  └────────────────┘ └────────────────────┘ └────────────────────────┘   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ UDP 52364↔52365 / Zenoh
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  AMD (VxWorks PC104 / Mock AMD)                                          │
│  IP: 192.168.0.101 (实机) / 127.0.0.1 (仿真)                            │
│  Port: 52364                                                             │
│  功能: 解析控制模式字节 → 执行舵面/推力 → 读取传感器 → 上报 $AUV 包       │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 模式流转确认：是否遵循 [透传] → [许可后自主]？

**是的，当前代码 100% 遵循此流程。**

完整流转链路：

```
                 默认状态
                    │
                    ▼
    ┌──────────────────────────────┐
    │  REMOTE (0x01) 透传模式       │ ← 上电默认 / ESTOP后 / 看门狗超时
    │  - PC 推力/舵角 → 直透 AMD   │
    │  - Jetson 仅观测, 不输出     │
    │  - Controller 做 Setpoint    │
    │    Shadowing (跟随实际状态)   │
    └──────────────┬───────────────┘
                   │ 操作员点击 "请求自主" (console 发送 字节7=0xEE)
                   ▼
    ┌──────────────────────────────┐
    │  AutonomyGuard 准入检查       │
    │  - 电压 > 47V?              │
    │  - 无漏水?                   │
    │  - 遥测新鲜度 < 200ms?      │
    │  - 定位置信度 > 0.5?        │
    └──────────────┬───────────────┘
                   │ 全部通过
                   ▼
    ┌──────────────────────────────┐
    │  AUTONOMOUS (0xEE) 自主模式   │
    │  - MPC/PID → 计算推力/舵角   │
    │  - Arbiter 选择 JETSON_MPC    │
    │  - 发往 AMD: 0xEE 模式包     │
    │  - AMD 执行 PID 闭环 (航向/  │
    │    深度) + 推力透传           │
    └──────────────────────────────┘
                   │
    退出条件:      │
    - 操作员 "手动接管" → 0x01
    - ESTOP → work_instruction=0x02
    - 看门狗超时 (PC 1.5s / AMD 1.0s)
    - 守卫条件不满足 (电压/漏水)
```

---

## 二、分阶段调试 SOP

### 阶段 0：纯仿真 (PVS + zenoh_json 后端)

**目标**: 验证决策逻辑、控制器、行为树

**启动命令**:
```bash
cd scripts
bash start_experiment.sh --sim-backend pvs --duration 120
```

**数据通路**:
```
Console →(Zenoh: rt/pc/cmd_raw)→ Bridge(zenoh_json) →(Zenoh JSON)→ PVS Wrapper
PVS Wrapper →(Zenoh: rt/auv/sensors/*)→ Bridge → ROS2 Topics → Localization/Controller
```

**此阶段特点**:
- 无二进制协议：纯 Zenoh JSON 格式
- 无 Mock AMD 进程：PVS 物理引擎直接由 zenoh bridge 驱动
- 控制模式字节由 bridge 内部 `_resolve_control_mode_byte()` 决定
- Controller Bumpless Transfer 正常工作

**调试检查项**:
| # | 检查内容 | 预期 | 验证方法 |
|---|----------|------|----------|
| 1 | ROS2 节点全部就绪 | 5个节点 running | `ros2 node list` |
| 2 | 传感器数据流入 | IMU/DVL/depth 有数据 | `ros2 topic hz /auv/sensors/imu` |
| 3 | 定位输出 | pose 发布中 | `ros2 topic echo /auv/localization/pose --once` |
| 4 | 控制器输出 | setpoint → cmd_vel | `ros2 topic echo /auv/control/cmd_vel --once` |
| 5 | Arbiter 状态 | AUTONOMOUS (默认0xEE) | `ros2 topic echo /auv/bridge/arbiter_status --once` |

---

### 阶段 1：仿真 + Mock AMD (protocol_udp 后端)

**目标**: 验证完整二进制协议栈, 模拟真实 AMD 行为

**启动方式** (两种等价方式):

方式 A — 修改仿真配置使用 protocol_udp:
```bash
cd scripts
bash start_experiment.sh --sim-backend pvs --brain-mode stack \
    --launch-arg bridge_backend:=protocol_udp
```

方式 B — 使用专用配置:
```bash
# 终端1: 启动 Mock AMD 服务器
cd sim_holoocean
python3 main.py --config ../config/sim_params.pvs.yaml

# 终端2: 启动 zenoh bridge (仿真侧)
python3 run_zenoh_bridge.py --config ../config/bridge_params.protocol_udp.pvs.yaml

# 终端3: 启动 ROS2 决策栈
cd brain_linux
source install/setup.bash
ros2 launch launch/auv_stack.launch.py bridge_backend:=protocol_udp
```

**数据通路**:
```
Console →(UDP 52364)→ Mock AMD ←→ PVS
                        ↕ (UDP 52364↔52365, 二进制 $CKTH/$AUV)
                    Bridge(protocol_udp) → ROS2
```

**此阶段新增特点**:
- **二进制协议完整走通**: $CKTH 72字节下行 + $AUV 145字节上行
- **Mock AMD 模拟 VxWorks 行为**: 控制模式分发、传感器上报
- **命令心跳必须**: `requires_command_heartbeat=True`, 停止发包 → AMD 看门狗触发

**调试检查项**:
| # | 检查内容 | 预期 | 验证方法 |
|---|----------|------|----------|
| 1 | Mock AMD 收到下行包 | 控制台无错误 | Mock AMD 日志 `[RX] mode=0xEE` |
| 2 | Bridge 收到上行遥测 | 遥测回传正常 | `ros2 topic hz /auv/bridge/telemetry` |
| 3 | 协议抓包验证 | 帧头/长度正确 | `python3 scripts/sniffer.py --port 52364` |
| 4 | 模式切换响应 | Console切手动→AMD收0x01 | 切换后观察 Mock AMD 日志 |
| 5 | 看门狗触发测试 | 停止Console→1.5s后降级 | 关闭 Console, 观察 Bridge 日志 |
| 6 | DVL 三轴上行 | Para5/6/7 有值 | sniffer.py 解析上行包 offset 56-61 |

**sniffer.py 验证命令** (协议抓包):
```bash
python3 scripts/sniffer.py --port 52364 --direction both
# 观察:
#   TX: $CKTH len=72 mode=0xEE course=1800 para1=5000 motor=750
#   RX: $AUV  len=145 mode=0xEE dvl_vel=15 para5=120 para6=-30 para7=5
```

---

### 阶段 2：接入真实 AMD (无传感器 / 台架)

**目标**: 验证 Jetson ↔ AMD 通信链路, 检查舵面/推力响应

**前提条件**:
- AMD PC104 已上电, IP=192.168.0.101
- Jetson (或调试 PC) 在 192.168.0.x 网段
- 物理急停按钮就绪

**配置修改** (`brain_linux/config/params.protocol_udp_arbiter.yaml`):
```yaml
bridge:
  backend: protocol_udp
protocol_udp:
  local_host: 0.0.0.0
  local_port: 52365
  remote_host: 192.168.0.101   # ← 真实 AMD IP
  remote_port: 52364
```

**启动命令**:
```bash
# Jetson 端
cd brain_linux
source install/setup.bash
ros2 launch launch/auv_stack.launch.py \
    bridge_backend:=protocol_udp \
    bridge_config:=config/params.protocol_udp_arbiter.yaml
```

**安全注意事项**:
- 此阶段 **禁止接通主推电源** (0x11 设备指令暂不发送)
- 仅验证通信+舵面响应
- 准备物理急停按钮

**调试检查项**:
| # | 检查内容 | 预期 | 验证方法 |
|---|----------|------|----------|
| 1 | 网络连通 | ping 通 | `ping 192.168.0.101` |
| 2 | AMD 收到包 | Not_Recv_From_Jetson_No 保持 0 | AMD 串口调试输出 |
| 3 | 上行帧 | Bridge 收到 $AUV 帧 | Bridge 日志 `[UPLINK] frame_no=...` |
| 4 | 遥控透传 | Console 推舵→舵面转动 | 观察编码器反馈 |
| 5 | 0xEE 模式 | AMD 进入 Jetson_Shadow_Proces | AMD 调试打印 `mode=0xEE` |
| 6 | 0xEF 模式 | AMD 进入 Remote_Assignment | AMD 调试打印 `mode=0xEF` |
| 7 | 看门狗测试 | 断开Jetson→1.0s后AMD降级 | 拔网线, 观察 AMD 输出 |
| 8 | 深度超限 | Para1设过限值→AMD回退0x01 | 发送 Para1=55000(55m) |

**台架静态测试包** (用于验证 VxWorks 解析):
```bash
# 发送 0xEE 模式测试包
python3 tools/manual_protocol_injector.py \
    --ip 192.168.0.101 --port 52364 \
    --mode 0xEE \
    --motor1 150 --motor2 0 \
    --course 900 \
    --para1 3000

# 预期: AMD 解析为 target_heading=90°, target_depth=3.0m, motor=150 RPM
# 航向PID输出: Course_Keep_Algorithm(90, 0, 0) = 2.0*90 = ±20° (饱和)
# 深度PID输出: DepthCtrlAlgorithm(3.0, 0, 0, 0, 0) = 4.0*3.0 = 12° (P项)
```

---

### 阶段 3：接入真实 AMD + 传感器就绪

**目标**: 全系统闭环运行, ES-EKF 定位融合

**前提条件**:
- IMU 上电正常 (航向/角速率)
- DVL 上电正常 (三轴速度)  
- 深度计上电正常
- 所有传感器数据链路确认

**传感器确认清单**:
| 传感器 | 验证内容 | AMD端确认 | Jetson端确认 |
|--------|----------|-----------|-------------|
| IMU | Heading/Pitch/Roll 有效 | 上行包 offset 72-77 非零 | `/auv/sensors/imu` topic |
| DVL | BI_X/Y/Z 有效 | 上行包 Para5/6/7 非零 | `/auv/sensors/dvl` topic |
| 深度计 | Depth > 0 (入水后) | 上行包 offset 38-39 非零 | `/auv/sensors/depth` topic |

**ES-EKF 初始化条件**:
```python
# algorithm/es_ekf.py auto_init 逻辑:
# DVL 数据非全零时自动初始化
if np.any(dvl_measurement != 0):
    self._initialize_state(imu_data, dvl_data, depth)
```

所以：**DVL 全零 = EKF 不初始化 = 安全**。一旦 DVL 有真实数据，EKF 自动开始融合。

**调试检查项**:
| # | 检查内容 | 预期 | 验证方法 |
|---|----------|------|----------|
| 1 | IMU 数据流 | heading 变化正常 | `ros2 topic echo /auv/sensors/imu --once` |
| 2 | DVL 数据流 | BI_X/Y/Z 合理范围 | `ros2 topic echo /auv/sensors/dvl --once` |
| 3 | DVL 极性 | 前进时 BI_X > 0 | 手动推动 AUV 前进, 观察符号 |
| 4 | EKF 初始化 | auto_init 触发 | Localization 日志 `EKF initialized` |
| 5 | Pose 输出 | 位置/航向连续 | `ros2 topic echo /auv/localization/pose` |
| 6 | AutonomyGuard | 全部条件满足 | Bridge 日志 `guard=ACTIVE` |
| 7 | 0xEE 闭环 | 舵面响应正确方向 | 设定 heading=当前+30°, 观察垂直舵偏转 |
| 8 | 0xEE 深度闭环 | 水平舵响应 | 设定 depth=当前+1m, 观察水平舵 |

**DVL 极性标定步骤**:
1. 进入遥控模式 (0x01)
2. 手动给小推力前进
3. 读取上行包 Para5 (BI_X): 应为正值
4. 读取 Para6 (BI_Y): 左移应为负值 (待确认)
5. 若极性反转: 修改 DataProcess.c 中 `temp->ToUI12_Para5 = -(short int)DVL_Prase_Data.BI_X`

---

## 三、模式切换完整时序图

```
Time    Console         Jetson Bridge      AMD (VxWorks)
─────────────────────────────────────────────────────────────────
t=0     [上电]          [启动ROS2栈]       [上电, mode=0x01]
        mode=0x01       Arbiter=REMOTE     MainCtrlTask running
        │               │                  ├── 看门狗启动
        │               │                  └── Not_Recv_From_Jetson_No++
        ▼               ▼                  ▼
t=0.3   TX $CKTH(0x01)  ─── UDP ──→       收到包: mode=0x01
        舵角/推力 ─────  透传 ────→       Remote_Proces() 执行
                                           Not_Recv_From_Jetson_No=0 ✓
        
        ... (操作员验证通信正常，设备上电) ...
        
t=30    操作员点击                         
        "请求自主"                         
        mode=0xEE      
        ▼               ▼                  ▼
t=30.6  TX $CKTH(0xEE) ─── UDP ──→       收到包: mode=0xEE
                        handle_pc_raw():   Jetson_Shadow_Proces():
                        Guard.request()    ├── thrust=Motor_Speed1
                        ├─ 电压OK          ├── heading PID
                        ├─ 无漏水          └── depth PID
                        ├─ 遥测新鲜
                        └─ 置信度OK
                        Arbiter=AUTONOMOUS
                        Controller:
                        ├─ MPC/PID计算
                        └─ 输出 cmd_vel
                        
        ... (自主运行中) ...
        
t=60    操作员点击
        "手动接管"
        mode=0x01
        work=0x02
        ▼               ▼                  ▼
t=60.6  TX $CKTH(0x01) ─── UDP ──→       收到包: mode=0x01
        + TASK_CANCEL   Guard.lock()       Remote_Proces()
                        Arbiter=REMOTE     prev_ctrl_mode=0xEE→0x01
                        Controller.reset() (Bumpless Transfer
                                            下次进0xEE时触发)
```

---

## 四、关键配置差异对照表

| 场景 | 后端 | AMD 地址 | 心跳要求 | 仲裁器 | 守卫器 |
|------|------|----------|----------|--------|--------|
| PVS 纯仿真 | zenoh_json | N/A (Zenoh) | 否 | 有效 | 宽松 |
| PVS + Mock AMD | protocol_udp | 127.0.0.1:52364 | 是 (600ms) | 有效 | 宽松 |
| 真实 AMD 台架 | protocol_udp | 192.168.0.101:52364 | 是 (100ms) | 有效 | 严格 |
| 真实 AMD 下水 | protocol_udp | 192.168.0.101:52364 | 是 (100ms) | 有效 | 严格 |

---

## 五、安全降级优先级

```
优先级从高到低:

1. [物理急停] → 硬件断电 (不可软件覆盖)
2. [ESTOP 按钮] → Console 发 work=0x02 → Guard.lock + Arbiter.force_remote
3. [AMD 看门狗] → Not_Recv_From_Jetson_No>=10 → mode→0x01, motor→0
4. [Jetson 看门狗] → PC link LOST (1.5s) → Guard.lock + Arbiter.force_remote  
5. [深度超限] → Depth_Para1 连续10次 → motor→0 (+0xEE/0xEF模式回退)
6. [守卫器撤销] → 电压/漏水/置信度异常 → Guard.DENIED → Arbiter降级
```

---

## 六、FAQ

### Q1: Mock AMD 和真实 AMD 的代码差异?
**协议完全一致**。Mock AMD (`mock_amd_server.py`) 模拟了 VxWorks 的 $CKTH 解析 + $AUV 上报行为。切换到真实 AMD 只需改 IP 地址，无需修改 Bridge/Controller/Decision 代码。

### Q2: 不连 Console 能否测试?
可以。使用 `tools/manual_protocol_injector.py` 直接发送测试包:
```bash
python3 tools/manual_protocol_injector.py --ip 192.168.0.101 --port 52364 --mode 0xEE --motor1 0 --course 1800 --para1 2000
```

### Q3: 如何验证 VxWorks 代码修改生效?
1. 发送 0xEE 包，观察 AMD 打印 `Jetson_Shadow_Proces` 相关日志
2. 检查上行包 Para5/6/7 是否有 DVL 数据
3. 停止发包 1.0s，确认 AMD 自动降级到 0x01

### Q4: 提频到 10Hz 后旧代码路径是否受影响?
受影响。原来依赖 `Main_Ctrl_Task_Interval_Num >= 212` (约 21.2s) 发送 BEIDOU 的逻辑不变（仍以 0.1s tick 计数），但因 MainCtrlTask 现在每 0.1s 执行一次，BEIDOU 发送的内层计数器需要确认是否与 MainCtrlTask 频率耦合。经检查：BEIDOU 计数在 MainCtrlTask 内部递增，从 6 ticks→1 tick 提频意味着 BEIDOU 发送频率从 ~21.2s/(6 ticks) ≈ 127s → 21.2s。这是可接受的（BEIDOU 通信本来就慢）。

### Q5: ES-EKF 在台架调试时会崩溃吗?
不会。`auto_init` 机制确保 DVL 全零时 EKF 不初始化，只有真实 DVL 数据到来后才开始融合。台架无传感器时 EKF 处于休眠态。

---

## 七、补充：阶段 2 详细操作手册 — 接入真实 AMD 台架调试

### 7.1 上位机配置步骤

#### Step 1: 修改配置文件

编辑 `console_soft/auv_console_pyside6/console_config.yaml`:

```yaml
# 确认以下配置正确：
udp:
  amd_ip: "192.168.0.101"     # AMD PC104 的真实 IP
  amd_port: 52364              # AMD 监听端口 (固定)
  local_port: 52365            # 上位机本地端口

zenoh:
  router_ip: "192.168.0.102"   # Jetson IP (如果 Jetson 参与)
  # 或 "127.0.0.1" 如果上位机和 Jetson 在同一台机器
```

> **注意**: 如果是直连 AMD 不经过 Jetson (纯手动遥控验证)，只需 UDP 配置正确即可，Zenoh 可以不连。

#### Step 2: 启动上位机

```bash
cd console_soft/auv_console_pyside6
python3 main.py
```

#### Step 3: 确认界面状态

启动后 GUI 应显示:
```
┌─────────────────────────────────────────────────────────────┐
│ 顶部遥测栏:                                                  │
│   报文编号: 0    本机地址: --    工作模式: 遥控(0x01)          │
│   经度: 0.000000  纬度: 0.000000  深度: 0.0m  航向: 0.0°     │
│   控制归属: REMOTE  自主状态: LOCKED  拒绝原因: --  时延: --   │
├─────────────────────────────────────────────────────────────┤
│ 底部控制栏:                                                  │
│   [手动遥控 MANUAL]  [紧急切断 ESTOP]  [Zenoh: 状态:未连接]  │
│   推力滑块: 0    舵角: 0/0/0/0                               │
└─────────────────────────────────────────────────────────────┘
```

---

### 7.2 上位机按钮操作序列 (阶段2台架)

#### 测试 1: 基本通信验证

| 步骤 | 操作 | 预期反馈 |
|------|------|----------|
| 1 | 确保 AMD 已上电，网线连接 | `ping 192.168.0.101` 通 |
| 2 | 启动 Console (`python3 main.py`) | GUI 界面正常显示 |
| 3 | **等待 3-5 秒** | 顶部 "报文编号" 开始递增 (每600ms+1) |
| 4 | 观察 Console 顶部 "工作模式" | 应显示 `遥控(0x01)` |
| 5 | 观察 "深度" 字段 | 显示 `0.0m` (无深度计时) 或实际值 |
| 6 | 观察 "航向" 字段 | 显示 `0.0°` (无IMU时) 或实际值 |

**判定标准**:
- ✅ 报文编号持续递增 → UDP 双向通信正常
- ❌ 报文编号不变 → AMD 未回包，检查网络/端口/AMD是否运行

#### 测试 2: 手动舵面验证

| 步骤 | 操作 | 预期反馈 |
|------|------|----------|
| 1 | 确认模式为 "手动遥控 MANUAL" | 底部按钮显示 MANUAL |
| 2 | 拖动 **垂直舵滑块** 到 +10° | Console 显示舵角 10° |
| 3 | 观察 AMD 串口 (若开启 `between_CPU_and_UI12`) | 打印 `FromUI12_RCD_UV_Set_Rud_Angle:100` (×10存储) |
| 4 | 观察 AMD MCU 反馈 (若开启 `between_CPU_and_MCU`) | 打印 `McuFU_UV_Back_Rud_Location:xxxx` 编码器值变化 |
| 5 | 物理观察 | 垂直舵片偏转约10° |

**判定标准**:
- ✅ 编码器反馈值与指令方向一致 → 舵面链路正常
- ❌ 无反馈变化 → MCU 通信异常或舵机未上电

#### 测试 3: 切换到 0xEE 自主模式

| 步骤 | 操作 | 预期反馈 |
|------|------|----------|
| 1 | 点击底部 **"手动遥控 MANUAL"** 按钮（切换为自主） | 按钮变为 "自主授权 AUTONOMY" |
| 2 | 或点击 **"请求自主"** 按钮 | 仲裁状态显示 "请求自主..." |
| 3 | 观察 Console 顶部 "工作模式" | 变为 `Jetson自主(0xEE)` |
| 4 | 观察 AMD 串口 | `FromUI12_Ctrl_Mode:ee` |
| 5 | 观察 AMD 舵面 | 即使推力=0，航向/深度PID仍计算舵角 |

**判定标准**:
- ✅ AMD 串口打印 `Ctrl_Mode:ee` → 模式字节正确传递
- ✅ 垂直舵偏转 (航向PID响应) → `Jetson_Shadow_Proces()` 执行正常
- ❌ 模式仍为 `01` → 检查 AutonomyGuard 是否拒绝 (看 Console "拒绝原因")

#### 测试 4: Jetson 失联看门狗验证

| 步骤 | 操作 | 预期反馈 |
|------|------|----------|
| 1 | 处于 0xEE 模式正常运行 | AMD 串口: `Ctrl_Mode:ee` |
| 2 | **关闭 Console** (Ctrl+C 或关窗口) | 停止发包 |
| 3 | 等待 **1.0 秒** | AMD 看门狗触发 |
| 4 | 观察 AMD 串口 | `FromUI12_Ctrl_Mode:01` (自动降级) |
| 5 | 观察推力 | `FromUI12_Motor_Speed1:0` (归零) |

**判定标准**:
- ✅ 1.0s 内自动降级 → `Not_Recv_From_Jetson_No >= 10` 正确
- ❌ 超过 1.0s 仍为 0xEE → 看门狗计数器未递增，检查 FuncWd_InfoOutputCtrl

#### 测试 5: ESTOP 急停验证

| 步骤 | 操作 | 预期反馈 |
|------|------|----------|
| 1 | 处于任何模式 | Console 正常 |
| 2 | 点击 **"紧急切断 ESTOP"** (红色按钮) | 按钮锁定为激活状态 |
| 3 | 观察 Console | 推力显示归零，模式切回 0x01 |
| 4 | 观察 AMD 串口 | `FromUI12_Motor_Speed1:0`, `FromUI12_Ctrl_Mode:01` |
| 5 | 点击 **"解除急停"** | 需要推力已归零才能解除 |

---

### 7.3 AMD VxWorks 串口监控指南

#### 串口连接方式
- **硬件**: PC104 调试串口 → USB-TTL → 开发 PC
- **波特率**: 115200 (VxWorks shell 默认)
- **终端工具**: `minicom`, `picocom`, 或 Workbench 内置终端

#### 当前默认 printf 输出 (DEBUG=1)

AMD 上电后，串口上每 **0.1s** 会看到:
```
program starting:::::
Main_Ctrl_Task_Count_No:1
UnpackNetDataTask start::::
EmergencyTask start::::
Main_Ctrl_Task_Count_No:2
...
```

每 **0.3s** 会看到 DVL 数据 (即使无 DVL 全为 0):
```
WI_X:0
WI_Y:0
WI_Z:0
WI_V:0.000000
WI_Valid_Flag:0
WD_Depth:0.000000
WD_Check:0
```

#### 建议: 开启更多调试输出

为台架调试，建议**临时修改** `Debug_Print()` 中的注释，启用关键打印:

```c
void Debug_Print(void)
{
    if(DEBUG)
    {
        between_CPU_and_UI12();   /* ← 取消注释: 看下行包解析结果 */
        between_CPU_and_MCU();    /* ← 取消注释: 看舵面反馈 */
        between_CPU_and_DVL();    /* 已启用 */
        /* between_CPU_and_IMU(); */  /* 有IMU时启用 */
    }
}
```

#### 开启 `between_CPU_and_UI12()` 后的输出示例

正常收到 0xEE 模式包时:
```
msg between CPU and UIWifi::::
Not_Recv_From_WIFI_No:0
from_UIWifi_buf:
24 43 4b 54 48 48 01 ee 00 14 00 28 ...
FromUI12_Head_BUF:24,43,4b,54
FromUI12_Msg_Length:72
FromUI12_Msg_Num:42
FromUI12_ID:01
FromUI12_Ctrl_Mode:ee          ← ★ 关键: 确认收到 0xEE
FromUI12_Depth_Para1:20        ← 深度保护参数 (20m)
FromUI12_Depth_Para2:40        ← 深度保护参数 (40m)
FromUI12_Work_Cmd:00
FromUI12_Motor_Speed1:150      ← ★ Jetson 下发的推力 RPM
FromUI12_Motor_Speed2:0
FromUI12_RCD_LH_Set_Rud_Angle:0
FromUI12_RCD_RH_Set_Rud_Angle:0
FromUI12_RCD_UV_Set_Rud_Angle:0
FromUI12_RCD_LV_Set_Rud_Angle:0
FromUI12_Set_Course:1800       ← ★ 目标航向 180° (×10)
FromUI12_Check_Sum:xx
FromUI12_End_Buf:0d,0a
```

#### 开启 `between_CPU_and_MCU()` 后的输出示例

舵面反馈 (编码器位置):
```
McuFU_LH_Back_Rud_Location:2048    ← 水平舵-左 (中位约2048)
McuFU_RH_Back_Rud_Location:2048    ← 水平舵-右
McuFU_UV_Back_Rud_Location:2162    ← ★ 垂直舵-上 (偏离中位=有PID输出)
McuFU_LV_Back_Rud_Location:1934    ← ★ 垂直舵-下 (反方向偏转)
```

---

### 7.4 关键判定标准一览表 (阶段2)

| 编号 | 验证项 | 正常值/现象 | 异常值/现象 | 根因排查 |
|------|--------|-------------|-------------|----------|
| **A1** | AMD 收到包 | `Not_Recv_From_WIFI_No:0` 保持 | 持续递增 (每0.5s+1) | 网络不通/端口错/防火墙 |
| **A2** | 控制模式 | `FromUI12_Ctrl_Mode:01` 或 `ee` | 乱码/固定值不变 | 校验和错误/帧头不对齐 |
| **A3** | 帧编号递增 | `FromUI12_Msg_Num` 持续+1 | 卡在某值不变 | Unpack 函数未被调用 |
| **A4** | 推力值 | `Motor_Speed1` 与 Console 滑块一致 | 0 或固定值 | 字节序错/偏移错位 |
| **A5** | 舵角值 | 滑块 10° → `Rud_Angle:100` | 0 或极大值 | ×10 缩放未对齐 |
| **A6** | Set_Course | Console 设 180° → `Set_Course:1800` | 0 或 65535 | u16 大端序解析异常 |
| **A7** | Para1 (深度) | Console 设 3m → `Para1:3000` | 0 | int32 大端序解析异常 |
| **B1** | 0xEE 模式舵面 | 垂直舵偏转 (航向PID) | 舵面不动 | `Jetson_Shadow_Proces` 未进入 |
| **B2** | 深度PID舵面 | 水平舵偏转方向正确 | 反方向偏转 | `LH_Ref_Location` 符号错 |
| **B3** | 推力透传 | Motor_Speed1 = Console下发值 | 一直为 0 | 未进入 `if(UI_Channel_Selection_Down==0x02)` |
| **C1** | 看门狗降级 | 1.0s 无包后 mode→0x01 | 不降级 | `Not_Recv_From_Jetson_No++` 未执行 |
| **C2** | 看门狗恢复 | 恢复发包后不再降级 | 仍然降级 | 喂狗清零语句未生效 |
| **C3** | 深度保护 | depth > Para1 连续10次 → 停推 | 无反应 | EmergencyTask 未运行 |

---

### 7.5 VxWorks Shell 运行时命令 (DTP 诊断)

如果串口连接了 VxWorks Shell，可以直接输入以下调试命令:

```
→ DEBUG = 1                    # 开启调试打印
→ DEBUG = 0                    # 关闭调试打印 (减少串口噪音)
→ d &UI_WIFI_Instruction, 72  # 查看当前下行包缓冲区 (16进制)
→ d &Current_State, 200       # 查看当前状态结构体
→ d &Instruction_To_FMCU, 50  # 查看发给 MCU 的指令
→ Not_Recv_From_Jetson_No     # 查看 Jetson 失联计数器
→ Main_Ctrl_Task_Count_No     # 查看主控循环计数 (确认 10Hz)
```

验证 10Hz 提频是否生效:
```
→ Main_Ctrl_Task_Count_No
value = 100 (0x64)
# 等待 10 秒后再查:
→ Main_Ctrl_Task_Count_No
value = 200 (0xc8)
# 差值 100 / 10s = 10Hz ✓
```

---

### 7.6 上位机 Console 端观察要点

#### 顶部遥测栏 — 正常值:

| 字段 | 台架无传感器正常值 | 有传感器正常值 |
|------|-------------------|---------------|
| 报文编号 | 持续递增 (每600ms+1) | 持续递增 |
| 工作模式 | `遥控(0x01)` 或 `Jetson自主(0xEE)` | 同左 |
| 深度 | `0.0m` | 0.0~50.0m 实际值 |
| 航向 | `0.0°` | 0~359.9° 实际值 |
| 经度/纬度 | `0.000000` | 实际 GPS 坐标 |

#### 底部状态栏 — Zenoh 侧通道:

| 状态 | 含义 | 动作 |
|------|------|------|
| `状态: 未连接` (红) | Zenoh 侧通道未建立 | 点击 "连接" 按钮，输入 Jetson IP |
| `状态: 已连接 (IP)` (绿) | 侧通道正常 | 可以进行自主模式切换 |
| `控制归属: REMOTE` | 当前为手动模式 | 正常初始状态 |
| `控制归属: AUTONOMOUS` | 自主模式已激活 | 0xEE 包正在发送 |
| `拒绝原因: AMD_UPLINK_STALE` | 遥测太旧 (>200ms) | 检查 AMD→Jetson 上行链路 |
| `拒绝原因: LOW_VOLTAGE` | 电压 < 47V | 检查电池/电源 |

#### 消息日志区域 (如果有):

正常日志:
```
[链路] Zenoh side channel connected to 192.168.0.102
[TX] 发送CKTH包 #42, mode=0xEE, motor=150, course=1800
[RX] 接收AUV包 #42, depth=0.0, heading=0.0
```

异常日志:
```
[链路] UDP send timeout - AMD unreachable
[仲裁] 自主请求被拒绝: AMD_UPLINK_STALE
[安全] Jetson 看门狗触发, 回退 REMOTE
```

---

### 7.7 典型故障排查流程图

```
Console 报文编号不递增?
    │
    ├─ ping 192.168.0.101 不通 → 检查网线/IP/交换机
    │
    ├─ ping 通但无回包 → AMD 未启动 / 端口 52364 未监听
    │                     → 确认 VxWorks 程序已加载 (shell 输出 "program starting")
    │
    └─ AMD 串口有 "UnpackNetDataTask start" 但 Console 无回包
       → AMD 发包端口配错 / 回包方向网络不通
       → 检查 usrAppInit.c 中 PC104 网卡配置

AMD 串口 Not_Recv_From_WIFI_No 持续递增?
    │
    ├─ Console 已启动且模式正确 → 包未到达 AMD
    │   → 在 AMD 端抓 UDP: 确认 52364 端口有入包
    │   → 检查防火墙 / 路由
    │
    └─ Console 未启动 / 配置错误 → 启动 Console 并确认配置

切到 0xEE 后舵面无响应?
    │
    ├─ AMD 串口 Ctrl_Mode 仍为 01 → Console 未发 0xEE
    │   → 检查 Console 是否连接了 Zenoh (AutonomyGuard 需通过)
    │   → 或直接用 manual_protocol_injector.py 绕过 Guard
    │
    ├─ AMD 串口 Ctrl_Mode 为 ee 但舵面不动 → Jetson_Shadow_Proces 未执行
    │   → 检查 Current_State.Current_Mode 是否正确更新
    │   → 确认 MainCtrlTask 中 0xEE 分支代码存在
    │
    └─ AMD 串口 Ctrl_Mode 为 ee, PID 有输出但舵面不动
       → MCU 通信异常 → 检查 between_CPU_and_MCU 输出
       → 或舵机未上电 → 发送 work_cmd=0x15 (HR_Power_ON)
```

---

### 7.8 静态测试包快速验证 (无需 Console)

使用 `tools/manual_protocol_injector.py` 直接构造测试包:

```bash
# 测试 1: 纯透传模式 - 验证通信
python3 tools/manual_protocol_injector.py \
    --ip 192.168.0.101 --port 52364 \
    --mode 0x01 --motor1 0 --count 10
# AMD 预期: FromUI12_Ctrl_Mode:01, Motor_Speed1:0
# 用途: 确认通信链路

# 测试 2: 0xEE 模式 - 验证航向PID
python3 tools/manual_protocol_injector.py \
    --ip 192.168.0.101 --port 52364 \
    --mode 0xEE --motor1 0 --course 900 --para1 0 --count 50
# AMD 预期:
#   FromUI12_Ctrl_Mode:ee
#   Set_Course:900 (目标 90°)
#   target_heading_deg = 90.0
#   Course_Keep_Algorithm(90, 0, 0) = 2.0×90 = 180 → 饱和 → 20°
#   UV_Rud_Location = UV_Ref - 20×4096/360 = UV_Ref - 227
#   LV_Rud_Location = LV_Ref + 227
# 物理观察: 垂直舵偏转至最大 (±20°)

# 测试 3: 0xEE 模式 - 验证深度PID
python3 tools/manual_protocol_injector.py \
    --ip 192.168.0.101 --port 52364 \
    --mode 0xEE --motor1 0 --course 0 --para1 3000 --count 50
# AMD 预期:
#   Para1:3000 → target_depth_m = 3.0m
#   DepthCtrlAlgorithm(3.0, 0, 0, 0, 0) = 4.0×3.0 = 12°
#   LH_Rud_Location = LH_Ref - 12×4096/360 = LH_Ref - 136
#   RH_Rud_Location = RH_Ref + 136
# 物理观察: 水平舵偏转约 12°

# 测试 4: 0xEE 模式 - 验证深度超限保护
python3 tools/manual_protocol_injector.py \
    --ip 192.168.0.101 --port 52364 \
    --mode 0xEE --motor1 150 --course 0 --para1 55000 --count 50
# AMD 预期:
#   Para1:55000 → target_depth_m = 55.0 → 被限幅为 50.0m
#   (不会超过 50m 硬限幅)

# 测试 5: 0xEF 模式 - 验证全透传
python3 tools/manual_protocol_injector.py \
    --ip 192.168.0.101 --port 52364 \
    --mode 0xEF --motor1 100 \
    --lh-angle 50 --rh-angle 50 --uv-angle 80 --lv-angle 80 --count 50
# AMD 预期: 复用 Remote_Proces → Remote_Assignment
#   Motor_Speed1:100
#   UV 偏转 = 80/10 = 8° (角度除以10是协议约定)
```

---

### 7.9 阶段2完整操作 Checklist

```
□ 1. 硬件准备
    □ AMD PC104 上电
    □ 串口调试线连接 (115200 baud)
    □ 网线连接 (192.168.0.x 网段)
    □ 物理急停按钮就绪
    □ 舵机 / MCU 电源 OFF (安全起步)

□ 2. 通信验证 (5分钟)
    □ ping 192.168.0.101 成功
    □ AMD 串口输出 "program starting"
    □ 启动 Console → 报文编号递增
    □ AMD 串口 Not_Recv_From_WIFI_No = 0

□ 3. 手动模式验证 (10分钟)
    □ Console mode = 0x01
    □ AMD 串口 FromUI12_Ctrl_Mode:01
    □ 推力滑块 → Motor_Speed1 对应
    □ 舵角滑块 → Rud_Angle 对应
    □ (选做) 舵机上电(0x15) → 编码器反馈变化

□ 4. 0xEE 模式验证 (15分钟)
    □ Console 切换到 "自主授权"
    □ AMD 串口 FromUI12_Ctrl_Mode:ee
    □ Set_Course / Para1 值正确传递
    □ 垂直舵有 PID 输出 (航向偏差时)
    □ 水平舵有 PID 输出 (Para1 > 0 时)
    □ 深度限幅 50m 生效 (Para1=55000 时限为 50m)

□ 5. 安全机制验证 (10分钟)
    □ 关闭 Console → 1.0s 内 AMD 降级到 0x01
    □ 重启 Console → 恢复正常
    □ ESTOP 按钮 → 推力归零 + 模式 0x01
    □ 解除 ESTOP → 正常恢复

□ 6. 0xEF 模式验证 (5分钟)
    □ 发送 mode=0xEF 包
    □ AMD 走 Remote_Proces 路径
    □ 舵角直透传 (无 PID 干预)

□ 全部通过 → 可以进入阶段3 (接入传感器)
```
