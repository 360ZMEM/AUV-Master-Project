# 01 - 物理坐标系与极性真值表 (Coordinate & Polarity Truth Table)

> 本文件定义了 AUV 系统中所有坐标系、执行器极性、传感器符号的物理含义与协议编码映射。  
> 仿真侧（HoloOcean / UE4）与实机侧（AMD 固件 / Jetson / PC104）必须在以下定义上达成一致，否则将出现"仿真完美、实机失控"的典型暗病。

---

## 1. 载具坐标系 (Body Frame) 定义

本系统采用 **NED (North-East-Down)** 惯性系 + **右手体轴系 (Body-Fixed Frame)** 的混合约定，这也是海洋工程与 ROS REP-103 的标准做法。

### 1.1 NED 惯性系 (World Frame)

| 轴 | 正方向 | 物理含义 | 协议编码位置 |
|:---:|:---:|:---:|:---|
| **X** | 正北 (True North) | 沿经线向北 | `position_ned[0]` / `vel_ned[0]` |
| **Y** | 正东 (True East) | 沿纬线向东 | `position_ned[1]` / `vel_ned[1]` |
| **Z** | **垂直向下** (Down) | 深度方向，值越大越深 | `position_ned[2]` / `KEY_DEPTH_M` |

> **关键差异对照**：UE4 仿真使用左手系 (Z-Up)，必须通过 `pose_matrix_ue_to_ned()` 转换。  
> 如果在 `mock_amd_server.py` 的坐标转换链中漏掉这一步，航向角将偏移 180°，深度值将符号反转。

### 1.2 体轴系 (Body Frame) —— 载具固连坐标系

| 轴 | 正方向 | 物理含义 | 欧拉角顺序 |
|:---:|:---:|:---:|:---|
| **X** | **指向载具前方** (Surge) | 前进方向 | Roll (φ) 绕此轴旋转 |
| **Y** | **指向载具右舷** (Sway) | 向右横移 | Pitch (θ) 绕此轴旋转 |
| **Z** | **指向载具底部** (Heave) | 向下运动 | Yaw (ψ) 绕此轴旋转 |

### 1.3 欧拉角 (ZYX 顺规，NED)

| 角度 | 物理动作 | 正值效果 | 负值效果 | 协议字段 |
|:---:|:---:|:---:|:---:|:---|
| **Roll (φ)** | 绕 X 轴旋转 | **右倾** (右舷下沉) | 左倾 (左舷下沉) | `roll_deg` at offset 76 |
| **Pitch (θ)** | 绕 Y 轴旋转 | **下俯** (艇首下倾) | 仰首 (艇首上仰) | `pitch_deg` at offset 74 |
| **Yaw (ψ)** | 绕 Z 轴旋转 | **右转** (顺时针) | 左转 (逆时针) | `heading_deg` at offset 72 |

> **仿真 vs 实机对照**：  
> - 仿真默认值：`init_quat_wxyz: [1.0, 0.0, 0.0, 0.0]`（水平姿态）  
> - 实机可能范围：因压载不均，初始 Roll/Pitch 可有 ±3° 偏差  
> - **修复建议**：在 EKF 初始化前执行静止零偏校准（参见 `es_ekf.py:add_bias_calibration_sample`）

---

## 2. 执行器极性真值表

### 2.1 主推进器 (Main Motor / Thrust)

协议字段：`thrust_percent` 范围 `[-100, 100]`，映射为 `main_motor_rpm = thrust_percent × main_motor_rpm_scale`。

| `thrust_percent` 值 | RPM 极性 | 推力物理方向 | 载具运动 | 协议存储位置 |
|:---:|:---:|:---:|:---:|:---|
| **> 0** (正值) | 正转 | **向后** 喷水 → 载具**前进** (+X) | Surge 正向 | `packet[23:25]` (int16 BE) |
| **= 0** | 停止 | 无推力 | 惯性滑行 | 同上 |
| **< 0** (负值) | 反转 | **向前** 喷水 → 载具**后退** (-X) | Surge 反向 | 同上 |

**`linear.x` 与推力关系**：

| `cmd_vel.linear.x` 值 | 期望推力 | 说明 |
|:---:|:---:|:---|
| > 0 | 正推力 (前进) | Twist 线速度 +X 对应 thrust_percent > 0 |
| < 0 | 负推力 (后退) | Twist 线速度 -X 对应 thrust_percent < 0 |

> **仿真默认值**：`main_motor_rpm_scale: 15.0` (1% 推力 = 15 RPM)  
> **实机可能范围**：12.0 ~ 18.0（因批次电机 KV 值差异）  
> **暗病排查**：若实机推力方向与指令相反，检查螺旋桨安装旋向（CW vs CCW），而非修改代码。

### 2.2 四路鳍舵 (Four Fin Rudders)

协议字段：`right_fin_deg`, `top_fin_deg`, `left_fin_deg`, `bottom_fin_deg`，范围 `±30°`，协议中以 `0.1°` 为单位存储 (int16)。

| 舵面 | 安装位置 | 数值增加 → 物理偏转 | 产生的力矩 | 主导运动 |
|:---:|:---:|:---:|:---:|:---|
| **Right** | 右舷 (Y+) | 舵面**上缘向右舷**偏转 | 产生 **向左** 的水动力 (Y-) | **Yaw 右转** + Sway 左移 |
| **Top** | 顶部 (Z-) | 舵面**前缘向上**偏转 | 产生 **向下** 的水动力 (Z+) | **Pitch 下俯** + Heave 下沉 |
| **Left** | 左舷 (Y-) | 舵面**上缘向左舷**偏转 | 产生 **向右** 的水动力 (Y+) | **Yaw 左转** + Sway 右移 |
| **Bottom** | 底部 (Z+) | 舵面**前缘向下**偏转 | 产生 **向上** 的水动力 (Z-) | **Pitch 仰首** + Heave 上浮 |

**协议编码映射**（`build_downlink_packet` 中的 struct 打包）：

| 舵面 | 协议偏移 (offset) | 编码公式 | 符号约定 |
|:---:|:---:|:---:|:---|
| Left | 27 | `int16(round(deg × 10.0))` | 正值 → 左舷舵面上缘向左 |
| Right | 29 | `int16(round(deg × 10.0))` | 正值 → 右舷舵面上缘向右 |
| Top | 31 | `int16(round(deg × 10.0))` | 正值 → 顶部舵面前缘向上 |
| Bottom | 33 | `int16(round(deg × 10.0))` | 正值 → 底部舵面前缘向下 |

**`angular` 通道与鳍舵对应关系**：

| Twist 通道 | 物理含义 | 对应鳍舵组合 | 极性对照 |
|:---:|:---:|:---|:---|
| `angular.x` (Roll) | 绕 X 轴扭矩 | Top + Bottom 差动 | Top+ / Bottom- → 右倾 |
| `angular.y` (Pitch) | 绕 Y 轴扭矩 | Top + Bottom 同向 | 两者同 + → 下俯 |
| `angular.z` (Yaw) | 绕 Z 轴扭矩 | Right + Left 差动 | Right+ / Left- → 右转 |

> **仿真默认值**：`mappers.rudder.center_bias: 0.0`  
> **实机可能范围**：±3.0°（因机械连杆公差）  
> **暗病排查**：若 AUV 在零指令下持续右偏，说明 Right 舵面存在机械中位偏移，需增大 `center_bias` 或单独调整 Right 的 Trim。

### 2.3 侧推进器 (Side Motor)

协议字段：`side_motor_rpm`，当前架构中**未启用**（`zenoh_side_channel_enabled: false`）。  
保留用于未来横向平移 (Sway) 控制。

---

## 3. 传感器极性真值表

### 3.1 DVL (多普勒速度计)

| 协议字段 | 坐标系 | 正值物理含义 | 负值物理含义 | 存储精度 |
|:---:|:---:|:---:|:---:|:---|
| `vel_ned[0]` (X) | NED | 载具向 **北** 运动 | 载具向 **南** 运动 | `× 10` int16 |
| `vel_ned[1]` (Y) | NED | 载具向 **东** 运动 | 载具向 **西** 运动 | `× 10` int16 |
| `vel_ned[2]` (Z) | NED | 载具向 **下** 运动 (加深) | 载具向 **上** 运动 (变浅) | `× 10` int16 |
| `dvl_speed_mps` | 体轴 X | **前进** 速度 | **后退** 速度 | offset 82, `× 10` int16 |

> **仿真默认值**：DVL 在 NED 系中直接输出体轴速度  
> **实机可能暗病**：部分 DVL 固件输出的是 "水体相对速度"（含海流），符号与 "地速" 相反。  
> 必须验证：静止时 DVL 输出 ≈ 0，前进时 `vel_ned[0]` > 0。

### 3.2 IMU (惯性测量单元)

| 协议字段 | 坐标系 | 正值物理含义 | 负值物理含义 | 协议单位 |
|:---:|:---:|:---:|:---:|:---|
| `accel_ned[0]` (X) | NED | 加速度向 **北** | 加速度向 **南** | m/s² |
| `accel_ned[1]` (Y) | NED | 加速度向 **东** | 加速度向 **西** | m/s² |
| `accel_ned[2]` (Z) | NED | 加速度向 **下** | 加速度向 **上** | m/s² |
| `gyro_ned[0]` (p, Roll Rate) | 体轴 | **右倾** 角速度 | **左倾** 角速度 | rad/s |
| `gyro_ned[1]` (q, Pitch Rate) | 体轴 | **下俯** 角速度 | **仰首** 角速度 | rad/s |
| `gyro_ned[2]` (r, Yaw Rate) | 体轴 | **右转** 角速度 | **左转** 角速度 | rad/s |

> **仿真默认值**：`sigma_acc: 0.08`, `sigma_gyro: 0.01` (噪声标准差)  
> **实机可能范围**：`sigma_acc: 0.05 ~ 0.2`, `sigma_gyro: 0.005 ~ 0.03`  
> **暗病排查**：静止时 `accel_ned[2]` 应 ≈ -9.81 m/s²（重力在 NED 系中向下，但传感器测得的比力方向向上）。  
> 代码中 EKF 使用 `g_n = [0, 0, -g]` 作为重力向量，这与 IMU 比力测量一致。

### 3.3 深度计 (Pressure Depth Sensor)

| 协议字段 | 正值物理含义 | 负值含义 | 协议存储 |
|:---:|:---:|:---:|:---|
| `depth_m` | **水下深度** (正值 = 在水面以下) | 异常（应 ≥ 0） | offset 38, `uint16(× 10)` |

> **仿真默认值**：深度从 UE4 的 Z 坐标取负值转换（UE4 中 Z 负值 = 水下）  
> **实机可能暗病**：压力传感器未做海面归零，导致深度有一个固定偏移量。  
> **修复命令**：
> ```bash
> # 在海面静止时记录偏移，在 EKF 初始化中补偿
> ros2 param set /auv_localization_node seabed_proximity_margin_m 1.5
> ```

---

## 4. 完整协议帧字段极性速查

### 下行帧 $CKTH (72 字节, PC → AUV)

| Offset | 字段 | 类型 | 符号约定 | 仿真默认 | 实机注意 |
|:---:|:---|:---:|:---|:---:|:---|
| 5 | frame_number | uint8 | 递增计数器 | 0 | 丢帧检测用 |
| 7 | control_mode_byte | uint8 | 0x01=遥控, 0xEE=自主 | 0xEE | **切换控制权的关键字节** |
| 23-24 | main_motor_rpm | int16 | + = 前进 | 0 | `thrust_percent × 15` |
| 27-28 | left_fin_deg×10 | int16 | + = 左舷舵面外偏 | 0 | 极性需与安装方向一致 |
| 29-30 | right_fin_deg×10 | int16 | + = 右舷舵面外偏 | 0 | 同上 |
| 31-32 | top_fin_deg×10 | int16 | + = 顶部舵面上偏 | 0 | 产生下俯力矩 |
| 33-34 | bottom_fin_deg×10 | int16 | + = 底部舵面下偏 | 0 | 产生仰首力矩 |

### 上行帧 $AUV (145 字节, AUV → PC)

| Offset | 字段 | 类型 | 符号约定 | 仿真默认 | 实机注意 |
|:---:|:---|:---:|:---|:---:|:---|
| 38-39 | depth_m×10 | uint16 | + = 水下深度 | 0.0 | 不应为负 |
| 72-73 | heading_deg×10 | int16 | 0~360° 相对北 | 0.0 | 需与磁力计校准一致 |
| 74-75 | pitch_deg×10 | int16 | + = 下俯, - = 仰首 | 0.0 | 下潜时为正值 |
| 76-77 | roll_deg×10 | int16 | + = 右倾, - = 左倾 | 0.0 | 通常应接近 0 |
| 82-83 | dvl_speed_mps×10 | int16 | + = 前进 | 0.0 | 注意地速 vs 水速 |
| 102-103 | total_voltage_v×10 | uint16 | + = 电压值 | 48.0 | 压降检测用 |

---

## 5. 坐标转换链完整路径

```
[UE4 左手系 Z-Up]
        │
        ▼  pose_matrix_ue_to_ned()
        │
[NED 右手系 Z-Down]  ← 所有算法 (EKF / MPC / PID) 在此系中运算
        │
        ▼  body_vector_ue_to_ned()
        │
[体轴系 (Surge/Sway/Heave)]  ← 执行器指令在此系中生成
        │
        ▼  rudders_to_protocol_dict() + thrust_to_rpm()
        │
[协议 int16 值]  ← 打包为 $CKTH 帧发送给 AUV 固件
```

**调试命令 — 验证坐标转换是否正确**：

```bash
# 1. 查看 EKF 输出的位姿（应为 NED 系）
ros2 topic echo /auv/state/filtered --once | grep -A5 position

# 2. 查看上行遥测解码后的深度（应为正值 = 水下）
ros2 topic echo /auv/sensors/status --once | grep depth_m

# 3. 验证 IMU 加速度在静止时应为 [0, 0, -9.81] (NED)
ros2 topic echo /auv/sensors/imu --once
```
