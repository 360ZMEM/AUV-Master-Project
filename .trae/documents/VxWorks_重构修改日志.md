# VxWorks 重构修改日志

> 生成时间: 2026-05-26  
> 目标: 使 VxWorks 6.8 (csd_vx6.8_lastest) 对齐 Jetson/Mock AMD 协议栈

---

## 修改文件清单

| 文件 | 修改类型 | 备份文件 |
|------|----------|----------|
| main.c | 新增+修改 | main_bak.c |
| main.h | 新增声明 | main_bak.h |
| DataProcess.c | 修改 | DataProcess_bak.c |
| DataProcess.h | 未修改 | DataProcess_bak.h |
| SecurityEmergencyManage.c | 新增+修改 | SecurityEmergencyManage_bak.c |
| SecurityEmergencyManage.h | 新增声明 | - |
| CtrlAlgorithm.c | 新增函数 | - |
| CtrlAlgorithm.h | 新增声明 | - |
| **UdpLogger.h** | **新增** | - |
| **UdpLogger.c** | **新增** | - |
| **AgreedTerms.h** | **修改 (添加宏)** | AgreedTerms_bak.h |
| **usrAppInit.c** | **修改 (添加初始化)** | usrAppInit_bak2.c |
| **scripts/log_receiver.py** | **新增 (PC端)** | - |

---

## 详细变更记录

### 1. main.c

#### 1.1 主控频率提升 (10Hz)
- **位置**: Line 129
- **变更**: `Main_Ctrl_Task_Period = 6` → `Main_Ctrl_Task_Period = 1`
- **效果**: 主控周期从 0.6s (1.67Hz) 提升到 0.1s (10Hz)
- **影响**: 所有模式的控制响应频率提升, PID 带宽可用上限提高

#### 1.2 网络收发任务优先级提升
- **位置**: Task_Creation 函数
- **变更**: NetRecvTask/PackNetDataTask/UnpackNetDataTask 优先级 125 → 115
- **原因**: 确保 Jetson 下行数据包及时入队, 优先于传感器处理

#### 1.3 新增控制模式 0xEE / 0xEF
- **位置**: 全局变量区 + MainCtrlTask 函数
- **新增变量**:
  - `u8 Jetson_Shadow = 0xEE` (影子诱导模式)
  - `u8 Jetson_Hybrid = 0xEF` (全透传混合模式)
  - `static u8 prev_ctrl_mode = 0x01` (Bumpless Transfer 用)
- **0xEE 分支逻辑**:
  - 检测模式切换 → 调用 `Course_Keep_Integral_Reset()` + `Depth_Ctrl_Integral_Reset()`
  - 执行 `Jetson_Shadow_Proces()`
- **0xEF 分支逻辑**:
  - 直接复用 `Remote_Proces()` (推力+舵角全透传)

#### 1.4 Jetson_Shadow_Proces() 函数实现
- **位置**: Auto_Back_Proces() 之后
- **功能**: 推力透传 + 航向/深度 PID 闭环
- **推力**: 直接使用 `FromUI12_Motor_Speed1/2`
- **航向 PID**: `Course_Keep_Algorithm(target_heading, current_heading, gyro_z)` → 垂直舵
- **深度 PID**: `DepthCtrlAlgorithm(target_depth, current_depth, pitch, gyro_pitch, vx)` → 水平舵
- **目标航向**: `FromUI12_Set_Course / 10.0` (offset 35-36, u16, ×10 存储)
- **目标深度**: `FromUI12_Para1 / 1000.0` (offset 37-40, int32, ×1000 存储)
- **深度防超限**: 硬限幅 0~50m

#### 1.5 Jetson 失联计数器递增
- **位置**: FuncWd_InfoOutputCtrl 函数
- **新增**: `Not_Recv_From_Jetson_No++` (每 0.1s 递增一次)

---

### 2. main.h

#### 2.1 新增 extern 声明
```c
extern u8 Jetson_Shadow;   /* 0xEE */
extern u8 Jetson_Hybrid;   /* 0xEF */
```

---

### 3. DataProcess.c

#### 3.1 DVL 速度上行单位转换
- **位置**: Pack_Data_To_UI12 函数, ToUI12_DVL_Velocity
- **变更**: `(Current_State.Current_DVL_Velocity_Kn)*10` → `(short int)(DVL_Prase_Data.BI_V / 100.0f)`
- **单位**: knots×10 → m/s×10 (BI_V mm/s ÷ 100 = m/s×10)
- **对齐**: Python protocol.py 中 `parse_uplink_packet` 期望 m/s×10

#### 3.2 DVL 三轴速度扩展 (Para5-7)
- **位置**: Pack_Data_To_UI12 函数, ToUI12_Para5/6/7
- **变更**: 原来填入 `Current_State.Current_Para5/6/7`, 现覆写为:
  - `Para5 = DVL_Prase_Data.BI_X` (Body X, mm/s)
  - `Para6 = DVL_Prase_Data.BI_Y` (Body Y, mm/s)
  - `Para7 = DVL_Prase_Data.BI_Z` (Body Z, mm/s)
- **用途**: 辅助 Jetson ES-EKF 状态估计
- **极性标定**: 预留注释, 台架联调时确认 Y/Z 方向

#### 3.3 Jetson 看门狗喂狗
- **位置**: UnpackNetDataTask, 收到有效 WIFI 包后
- **新增**: `Not_Recv_From_Jetson_No = 0`

---

### 4. SecurityEmergencyManage.c

#### 4.1 Jetson 失联看门狗
- **新增变量**: `u16 Not_Recv_From_Jetson_No = 0`
- **触发条件**: `Not_Recv_From_Jetson_No >= 10` (10×0.1s = 1.0s 超时)
- **生效范围**: 仅 0xEE/0xEF 模式
- **降级动作**:
  - `FromUI12_Ctrl_Mode = 0x01` (回退遥控模式)
  - `FromUI12_Motor_Speed1 = 0` (推力归零)
  - `FromUI12_Motor_Speed2 = 0`
  - `Sys_Abnorm_Inf_Judgement |= 0x00004000` (Bit14 告警)

#### 4.2 深度超限模式回退
- **触发条件**: `Depth_Exceed_FromUI12_Depth_Para1 >= 10` 且处于 0xEE/0xEF
- **降级动作**:
  - `FromUI12_Ctrl_Mode = 0x01`
  - `FromUI12_Motor_Speed2 = 0`

---

### 5. SecurityEmergencyManage.h

#### 5.1 新增 extern 声明
```c
extern u16 Not_Recv_From_Jetson_No;
```

---

### 6. CtrlAlgorithm.c / CtrlAlgorithm.h

#### 6.1 Bumpless Transfer 预留接口
- **新增函数**:
  - `void Course_Keep_Integral_Reset(void)` — 当前为空实现 (PD 无积分)
  - `void Depth_Ctrl_Integral_Reset(void)` — 当前为空实现 (P+P+D 无积分)
- **用途**: 模式切换瞬间清除 PID 积分状态, 防止输出跳变

---

## 协议契约总结

### 下行 $CKTH (72 bytes, 大端序)

| Offset | 字段 | 类型 | 0xEE 模式语义 | 0xEF 模式语义 |
|--------|------|------|---------------|---------------|
| 7 | Ctrl_Mode | u8 | 0xEE | 0xEF |
| 23-24 | Motor_Speed1 | i16 | thrust% × 15 (RPM) | 直接透传 |
| 35-36 | Set_Course | u16 | orientation_deg × 10 | 直接透传 |
| 37-40 | Para1 | i32 | target_depth_m × 1000 | 未使用 |

### 上行 $AUV (145 bytes, 大端序)

| Offset | 字段 | 类型 | 新语义 |
|--------|------|------|--------|
| 56-57 | Para5 | i16 | DVL BI_X (mm/s) |
| 58-59 | Para6 | i16 | DVL BI_Y (mm/s) |
| 60-61 | Para7 | i16 | DVL BI_Z (mm/s) |
| 82-83 | DVL_Velocity | i16 | BI_V / 100 (m/s × 10) |

---

## 联调注意事项

1. **台架无传感器调试**: IMU/DVL 全零时, 航向 PID 输出为 `Course_Keep_Algorithm(target, 0, 0)`, 深度 PID 输出为 `DepthCtrlAlgorithm(target, 0, 0, 0, 0)`, 不会产生危险输出
2. **DVL 极性标定**: 首次 DVL 通电联调时, 对比 BI_X/Y/Z 正方向与 AUV 体坐标系, 必要时在 DataProcess.c Para5-7 赋值处取反
3. **ES-EKF 影响**: DVL 全零 → ES-EKF `auto_init` 机制不会初始化, 安全; 非零后正常融合
4. **Jetson 看门狗**: 确保 Jetson bridge 发包频率 > 1Hz, 否则会误触发降级
5. **模式切换测试**: 发送 Ctrl_Mode=0xEE → 观察舵角响应 → 发送 Ctrl_Mode=0x01 → 验证 Bumpless Transfer

---

## 附录 A: 调试输出与监控指南

### A.1 VxWorks printf 输出去向

#### 物理输出通道

VxWorks 6.8 的 `printf()` 默认输出到 **内核 Shell 控制台**（即 BSP 配置的系统主串口）。对于本项目的 PC104 硬件：

- **输出设备**: PC104 板载 COM0 串口 (非 CSD 扩展串口)
- **波特率**: 由 BSP 配置决定 (典型值 9600 或 115200)
- **查看方式**: 
  - 开发阶段: Tornado IDE → Shell 窗口 (通过 WDB agent 网络连接)
  - 独立运行: 物理串口连接 PC（minicom / PuTTY / SecureCRT）
  - 网络 Shell: 若 BSP 启用了 telnet 登录, 可通过 `telnet 192.168.0.101` 访问

#### 注意事项

- `printf()` 在 VxWorks 中是**任务级调用**, 不可在中断上下文（如 `FuncWd_InfoOutputCtrl` 看门狗回调）中使用
- 看门狗定时器回调头部有注释警告: `"tips:不在printf中打印内容！切记切记"`
- 高频 printf（如 10Hz 主控循环中）会因串口带宽瓶颈导致**任务阻塞**, 影响实时性
- 建议: 仅在 `PrintTask`（优先级145, 非关键）中集中输出调试信息

### A.2 当前活跃的 printf 输出

#### 始终输出 (DEBUG=1 时)

| 输出函数 | 位置 | 内容 | 周期 |
|----------|------|------|------|
| `MainCtrlTask` | `main.c:230` | `Main_Ctrl_Task_Count_No:%d` | 每 0.1s (10Hz) |
| `between_CPU_and_DVL()` | `main.c:1247-1276` | DVL WI_X/Y/Z/V, WI_Valid_Flag, WD_Depth | 每 0.3s (Print_Task_Period=3) |
| 各 Task start | `DataProcess.c:625,651,678...` | `"XXXTask start::::"` | 每次信号量触发 |
| `EmergencyTask` | `SecurityEmergencyManage.c:63` | `"EmergencyTask start::::"` | 每 0.5s |

#### DEBUG 开关位置

```
文件: csd_vx6.8_lastest/main.c
行号: 126
内容: unsigned short int DEBUG = 1;  // 1=输出调试信息, 0=静默
```

#### 可启用的调试函数 (取消注释即可)

所有调试函数集中在 `main.c` 的 `Debug_Print()` 函数中 (line 981-1000):

```c
void Debug_Print(void)
{
    if(DEBUG)
    {
        /*Current_State_printf();     // 全状态量 (模式/深度/舵角/电池等)
        /*recv_count_printf();*/      // 接收计数统计
        /*between_CPU_and_UI12();*/   // 上位机通信数据
        /*Beid_BDTXR();*/             // 北斗数据
        /*between_CPU_and_GPS();*/    // GPS 数据
        between_CPU_and_DVL();        // ← 当前唯一启用
        /*PathPlanning_data_printf();*/ // 路径规划
        /*debug_test();*/
        /*between_CPU_and_MCU();      // MCU 通信
        /*between_CPU_and_PSD();*/    // 频率深度计
        /*between_CPU_and_IMU();*/    // IMU 数据
        /*between_CPU_and_BMS();*/    // 电池管理
        /*between_UI_and_MCU();*/     // UI-MCU 转发
    }
}
```

---

### A.3 网络配置

#### VxWorks 端 (PC104 = AMD)

| 参数 | 值 | 位置 |
|------|-----|------|
| IP 地址 | `192.168.0.101` | `usrAppInit.c:50` |
| 网卡 | `fei1` (Intel Fast Ethernet) | `usrAppInit.c:49-50` |
| 系统时钟 | 1000 Hz (1ms/tick) | `usrAppInit.c:42` |
| 上位机 IP | `192.168.0.11` | `com.c` (define UIControllerIP) |
| 上位机端口 | `21` | `com.c` (define UIControllerPort) |
| MCU IP | `192.168.0.30` | `com.c` (define FMCUIP) |
| MCU 端口 | `8089` | `com.c` (define FMCUPort) |
| 本地端口 | `5000` | `com.c` (define LocalPort) |

#### Jetson 端 (Bridge Node)

| 参数 | 值 | 配置文件 |
|------|-----|----------|
| 本地监听 | `0.0.0.0:52365` | `config/bridge_params.yaml:69-70` |
| 远程目标 (→AMD) | `127.0.0.1:52364` | `config/bridge_params.yaml:71-72` |
| Socket 超时 | 10ms | `config/bridge_params.yaml:73` |
| 接收缓冲 | 2048 bytes | `config/bridge_params.yaml:74` |
| 镜像嗅探端口 | `127.0.0.1:52366` | `config/bridge_params.yaml:83-84` |

#### 通信拓扑图 (仿真/单机模式)

```
┌─────────────────┐    UDP :52364     ┌───────────────────┐
│  Mock AMD       │◄─────────────────│  Bridge Node      │
│  (mock_amd_     │    $CKTH (72B)   │  (bridge_node.py) │
│   server.py)    │─────────────────►│                   │
│  bind :52364    │    $AUV (145B)   │  bind :52365      │
└────────┬────────┘                   └───────────────────┘
         │ mirror
         ▼ :52366
┌─────────────────┐
│  sniffer.py     │
│  bind :52366    │
└─────────────────┘
```

#### 通信拓扑图 (实物联调模式)

```
┌─────────────────┐  UDP 192.168.0.101:5000   ┌───────────────────┐
│  VxWorks/PC104  │◄──────────────────────────│  Jetson (Bridge)  │
│  IP:192.168.0.101│  $CKTH (72B) 下行         │  IP:192.168.0.x   │
│  bind :5000     │──────────────────────────►│  bind :52365      │
│                 │  $AUV (145B) 上行          │                   │
└─────────────────┘                            └───────┬───────────┘
                                                       │ mirror
                                                       ▼ :52366
                                               ┌───────────────────┐
                                               │  sniffer.py       │
                                               │  bind :52366      │
                                               └───────────────────┘
```

> **实物联调注意**: `bridge_params.yaml` 中 `remote_host` 和 `remote_port` 需改为 VxWorks 的实际 IP:Port (`192.168.0.101:5000`)。

---

### A.4 sniffer.py 工作原理

#### 文件位置

```
scripts/sniffer.py
```

#### 工作机制

1. **绑定 UDP socket**: 监听指定端口 (默认 `0.0.0.0:52364`)，接收**所有方向**的协议包
2. **包方向自动检测**: 通过 `common/protocol_debug.py` 的 `detect_protocol_direction()` 自动判断是 `$CKTH` (下行) 还是 `$AUV` (上行)
3. **协议解包**: 调用 `common/protocol.py` 的 `parse_uplink_packet()` / `parse_downlink_packet()` 解析二进制字段
4. **格式化输出**: 三种互斥格式:
   - **紧凑格式** (默认): 单行摘要, 适合终端滚动监控
   - **ASCII 诊断块** (`--ascii-format`): 多行详细, 逐字段展示
   - **原始 CSV** (`--raw-format`): 机器友好, 适合管道处理

#### 使用方式

```bash
# 方式1: 直接监听 Mock AMD 端口 (仿真模式)
python scripts/sniffer.py --bind-port 52364

# 方式2: 监听 mirror 端口 (不干扰主通信)
python scripts/sniffer.py --bind-port 52366

# 方式3: 详细 ASCII 输出 + 十六进制
python scripts/sniffer.py --bind-port 52366 --ascii-format --show-hex

# 方式4: 抓 N 个包后停止
python scripts/sniffer.py --bind-port 52366 --count 10

# 方式5: 原始 CSV 格式 (适合重定向到文件)
python scripts/sniffer.py --bind-port 52366 --raw-format > capture.csv
```

#### 输出示例 (紧凑格式)

```
sniffer listening on udp://0.0.0.0:52366
[12:34:56.789] $CKTH↓ from 127.0.0.1:52365 mode=0xEE thrust=45 course=1800 para1=5000
[12:34:56.890] $AUV↑  from 127.0.0.1:52364 depth=5.0m heading=180.0° dvl=1.2m/s
```

#### 依赖关系

```
scripts/sniffer.py
  └── common/protocol_debug.py  (格式化函数库)
        └── common/protocol.py  (协议解包/组包核心)
              └── common/enums.py  (枚举定义)
```

---

### A.5 Mock AMD 内置监控

#### 终端日志输出

`mock_amd_server.py` 运行时自动输出收发包日志到 **stdout**:

- 控制开关: `config/bridge_params.yaml` → `log_packets: true`
- 采样率: `log_every_n: 1` (每帧都输出, 可改为 10 等降低刷屏)
- 格式选择: `log_raw_format` / `log_ascii_format` / 默认紧凑

#### Mirror 镜像机制

所有收发的 UDP 包自动复制到 `sniffer_mirror_host:sniffer_mirror_port`：
- 配置: `bridge_params.yaml:83-84`
- 默认: `127.0.0.1:52366`
- 用途: 用 `sniffer.py --bind-port 52366` 被动监控, **不影响主通信链路**

---

### A.6 ROS2 Topic 监控 (Jetson 端)

Bridge Node 将上行遥测解包后发布为标准 ROS2 Topic:

```bash
# 查看深度
ros2 topic echo /auv/sensors/depth

# 查看仲裁器模式状态
ros2 topic echo /auv/arbiter/status

# 查看完整遥测 JSON (包含所有字段)
ros2 topic echo /auv/bridge/shadow_telemetry

# 查看下发控制指令 JSON
ros2 topic echo /auv/bridge/shadow_cmd

# 查看 IMU (四元数 + 角速度)
ros2 topic echo /auv/sensors/imu

# 查看 DVL 速度
ros2 topic echo /auv/sensors/dvl
```

#### Bridge 统计日志

`bridge_node.py` 每 2 秒输出一次接收统计:
```
[bridge] rx=50 tx=50 avg_latency=2.1ms
```

---

### A.7 图形化监控

| 工具 | 启动命令 | 用途 |
|------|----------|------|
| Foxglove Studio | `bash scripts/start_foxglove_layout.sh` | 3D 可视化 + Topic 面板 |
| PySide6 Console | `python console_soft/auv_console_pyside6/main.py` | 上位机 GUI + Packet Viewer |

---

### A.8 快速验证清单

| 验证项 | 命令 | 期望结果 |
|--------|------|----------|
| AMD 双向通信正常 | `python scripts/sniffer.py --bind-port 52366` | 看到 `$CKTH↓` 和 `$AUV↑` 交替出现 |
| Jetson→AMD 下行到达 | sniffer 中看到 `$CKTH` | mode 字段 = 配置值 (0xEE/0xEF) |
| AMD→Jetson 上行正常 | `ros2 topic hz /auv/sensors/depth` | 频率 ≈ 10Hz |
| DVL 三轴数据到达 | `ros2 topic echo /auv/bridge/shadow_telemetry` | para5/6/7 非零 |
| 失联看门狗工作 | 停止 bridge → 等 1s → sniffer 观察 | mode 自动变回 0x01 |
| UDP 日志到达 | `python scripts/log_receiver.py --timestamps` | 终端实时显示 VxWorks printf 输出 |

---

## 7. UDP 日志重定向模块 (UdpLogger)

> 实施日期: 2026-05-27  
> 方案: 方案3 — UDP Logger (环形缓冲区 + 异步 Task)

### 7.1 设计目标

将 VxWorks 所有核心模块的 `printf` 输出通过以太网 UDP 重定向到上位机 (PC/Jetson)，以便在无串口连接时仍能实时查看日志。

### 7.2 架构

```
┌──────────────────────────────────────────────────────────────────────┐
│  VxWorks (192.168.0.101)                                             │
│                                                                      │
│  [MainCtrlTask]──┐                                                   │
│  [NetRecvTask]───┤  printf (宏展开)                                   │
│  [EmergencyTask]─┤───► udp_log_printf() ──intLock──► [环形缓冲区 8KB] │
│  [PrintTask]─────┘                                                   │
│                                                                      │
│  [tUdpLog Task, pri=200] ◄── taskDelay(50ms) ── rngBufGet ──► sendto │
└────────────────────────────────────────────────────────────────┬──────┘
                                                                 │ UDP :52367
                                                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  PC/Jetson (192.168.0.11)                                            │
│                                                                      │
│  scripts/log_receiver.py  ◄── bind 0.0.0.0:52367 ── recvfrom         │
│  └── 终端实时显示 + 可选文件保存                                       │
└──────────────────────────────────────────────────────────────────────┘
```

### 7.3 端口分配 (同一 IP: 192.168.0.11)

| 端口 | 用途 | 方向 |
|------|------|------|
| 52364 | 下行控制包 ($CKTH) | AMD/Jetson → VxWorks |
| 52365 | 上行状态包 ($AUV) | VxWorks → AMD/Jetson |
| 52366 | Sniffer 镜像 | 复制包 → 被动监听 |
| **52367** | **UDP 日志** | **VxWorks → PC/Jetson** |

### 7.4 新增文件

#### 7.4.1 UdpLogger.h

```
文件: csd_vx6.8_lastest/UdpLogger.h
```

**配置常量:**

| 宏 | 值 | 说明 |
|----|-----|------|
| `UDP_LOG_TARGET_IP` | `"192.168.0.11"` | 目标 IP (与协议包一致) |
| `UDP_LOG_PORT` | `52367` | 日志 UDP 端口 |
| `UDP_LOG_BUF_SIZE` | `8192` | 环形缓冲区大小 (字节) |
| `UDP_LOG_MTU` | `1400` | 单 UDP 包最大有效载荷 |
| `UDP_LOG_FLUSH_MS` | `50` | 发送任务刷新周期 (ms) |
| `UDP_LOG_TASK_PRI` | `200` | 发送任务优先级 (低) |
| `UDP_LOG_TASK_STACK` | `4096` | 发送任务堆栈大小 |

**公共接口:**

```c
void UdpLogger_Init(void);           // 初始化 (网络就绪后调用)
int  udp_log_printf(const char *fmt, ...);  // printf 替代函数
```

#### 7.4.2 UdpLogger.c

```
文件: csd_vx6.8_lastest/UdpLogger.c
```

**核心实现:**

| 组件 | 说明 |
|------|------|
| `g_logRingBuf` | VxWorks `rngLib` 环形缓冲区 (8KB) |
| `g_logSockFd` | UDP socket (SOCK_DGRAM) |
| `g_logInited` | 初始化完成标志 (安全降级判断) |
| `g_logDropCount` | 缓冲区溢出统计 |
| `udp_log_printf()` | vsnprintf → intLock → rngBufPut → intUnlock |
| `UdpLoggerTask()` | 后台循环: taskDelay → rngBufGet → sendto |

**关键设计决策:**

1. **intLock/intUnlock** 极短临界区: 仅保护 `rngBufPut` 单次调用 (~数微秒)，不影响中断延迟
2. **非阻塞写入**: 缓冲区满时新数据被丢弃，`g_logDropCount++`，调用者不被阻塞
3. **安全降级**: `g_logInited == 0` 时，`udp_log_printf` 调用 `write(1, ...)` 直接输出到串口控制台
4. **无网络操作在调用者上下文**: 所有 `sendto()` 仅在低优先级 `tUdpLog` 任务中执行
5. **UdpLogger.c 不包含 AgreedTerms.h**: 避免 `#define printf` 宏递归

### 7.5 已修改文件

#### 7.5.1 AgreedTerms.h

```
文件: csd_vx6.8_lastest/AgreedTerms.h
备份: csd_vx6.8_lastest/AgreedTerms_bak.h
```

**在 `#endif` 前追加:**

```c
#include "UdpLogger.h"
#define printf  udp_log_printf
```

**效果**: 所有包含 `AgreedTerms.h` (直接或传递) 的源文件中，`printf` token 被替换为 `udp_log_printf`。

**覆盖范围 (7个核心应用文件):**

| 文件 | 获得宏的途径 |
|------|-------------|
| main.c | 直接包含 AgreedTerms.h + main.h |
| DataProcess.c | DataProcess.h → AgreedTerms.h |
| SecurityEmergencyManage.c | SecurityEmergencyManage.h → AgreedTerms.h |
| CtrlAlgorithm.c | CtrlAlgorithm.h → AgreedTerms.h |
| com.c | com.h → AgreedTerms.h |
| SailingBox.c | SailingBox.h → AgreedTerms.h |
| XMLFile.c | 直接包含 + XMLFile.h |

**故意不覆盖:**

| 文件 | 原因 |
|------|------|
| UdpLogger.c | 避免宏递归 (使用 vsnprintf/write 直接) |
| usrAppInit.c | 早期启动阶段网络未就绪，printf 走串口 |
| dtp.c | 独立硬件测试工具，保持串口调试 |
| canTest.c | 独立 CAN 测试工具，保持串口调试 |
| linkSyms.c | 自动生成符号表，宏会破坏 `extern int printf()` 声明 |
| prjConfig.c | 自动生成配置，printf 仅出现在注释中 |

#### 7.5.2 usrAppInit.c

```
文件: csd_vx6.8_lastest/usrAppInit.c
备份: csd_vx6.8_lastest/usrAppInit_bak2.c
```

**变更:**

1. 添加 `#include "UdpLogger.h"` (line 28)
2. 在 `ipAttach/ifconfig` 之后调用 `UdpLogger_Init()` (line 54)

```c
ipAttach(1, "fei");
ifconfig("fei1 192.168.0.101 up");

/* UDP 日志模块初始化 (必须在网络初始化之后) */
UdpLogger_Init();
```

### 7.6 PC 端接收脚本

```
文件: scripts/log_receiver.py
```

**功能:**
- 监听 UDP 0.0.0.0:52367, 接收 VxWorks 日志包
- 纯文本 UTF-8 流, 无帧头 (每包最大 1400 字节)
- 可选时间戳前缀 (`--timestamps`)
- 可选文件保存 (`--save filename.txt`)
- Ctrl+C 优雅退出 + 统计输出

**使用方式:**

```bash
# 基本使用 (实时打印到终端)
python scripts/log_receiver.py

# 带时间戳 + 保存到文件
python scripts/log_receiver.py --timestamps --save vxlog.txt

# 指定端口 (若修改了 UDP_LOG_PORT)
python scripts/log_receiver.py --port 52367
```

**输出示例:**

```
╔══════════════════════════════════════════════════╗
║  VxWorks UDP Log Receiver                       ║
║  Listening on udp://0.0.0.0:52367               ║
║  Press Ctrl+C to stop                           ║
╚══════════════════════════════════════════════════╝

[14:23:01.123] Main_Ctrl_Task_Count_No:1
[14:23:01.123] EmergencyTask start::::
[14:23:01.223] Main_Ctrl_Task_Count_No:2
[14:23:01.423] DVL: WI_X=120 WI_Y=-30 WI_Z=5 WI_V=125
```

### 7.7 恢复方法

若需恢复原始 printf 串口输出:

1. **注释掉宏**: `AgreedTerms.h` 中注释 `#define printf udp_log_printf` 即可
2. **完全移除**: 用备份文件恢复:
   ```bash
   cp AgreedTerms_bak.h AgreedTerms.h
   cp usrAppInit_bak2.c usrAppInit.c
   # UdpLogger.c/.h 可保留不编译, 不影响其他模块
   ```

### 7.8 注意事项

1. **单次 printf 长度限制**: `udp_log_printf` 内部缓冲区为 256 字节, 超长格式化字符串将被截断
2. **日志延迟**: 最大约 50ms (一个 flush 周期), 非严格实时
3. **缓冲区溢出**: 10Hz 控制循环 + DVL 打印 ≈ 每秒 ~500 字节, 远小于 8KB 缓冲, 正常不会溢出
4. **sprintf 不受影响**: `#define printf` 仅替换 `printf` token, 不影响 `sprintf` / `fprintf` / `vprintf` 等
5. **网络中断容错**: `sendto` 失败不阻塞 Task, 数据静默丢弃; 网络恢复后自动续传新数据
