# 02 - 硬件抽象层 (HAL) 关键参数审计与标定 SOP

> 本文件针对 `params.yaml` 中与硬件直接交互的参数，提供**实测标定标准操作流程 (SOP)**。  
> 仿真环境中这些参数均为理想值，实机部署时必须通过物理测量逐一替换。

---

## 1. 主推进器转速缩放系数 (`main_motor_rpm_scale`)

### 1.1 参数定义

| 字段 | 类型 | 仿真默认值 | 实机可能范围 | 代码位置 |
|:---|:---|:---:|:---:|:---|
| `bridge.main_motor_rpm_scale` | float | `15.0` | `10.0 ~ 20.0` | `params.yaml:10` |
| `mappers.thrust.rpm_per_percent` | float | `15.0` | `10.0 ~ 20.0` | `params.yaml:60` |

该系数定义 **1% 推力百分比 ↔ RPM** 的线性转换关系：

```
main_motor_rpm = thrust_percent × main_motor_rpm_scale
```

在 `build_downlink_packet` 中，推力字段以 RPM 格式打包：
```python
# protocol.py line 1115
main_motor_rpm = _clamp_int(round(thrust_percent * main_motor_rpm_scale), -32768, 32767)
```

### 1.2 系泊拉力试验 SOP

**目标**：确定实机 1% 推力对应的物理转速，从而标定 `main_motor_rpm_scale`。

**设备要求**：
- 系泊拉力传感器（量程 0~50 kgf，精度 ±0.1 kgf）
- 转速计（光电或霍尔，精度 ±1 RPM）
- 固定夹具（将 AUV 刚性固定在水池或水箱中）
- 直流电源监测仪（记录电压/电流）

**步骤**：

1. **准备阶段**：
   - 将 AUV 固定在系泊台上，确保螺旋桨完全浸没且无水流干扰
   - 连接拉力传感器到 AUV 尾部系泊点
   - 接通 PC104，启动 Jetson，确认 ROS2 节点正常运行
   - 将 `main_motor_rpm_scale` 设为临时值 `1.0`

2. **采集阶段**：

   | 推力指令 (%) | 记录项 | 目标 |
   |:---:|:---|:---|
   | 5 | RPM, 拉力 (kgf), 电压 (V) | 记录 3 秒均值 |
   | 10 | RPM, 拉力, 电压 | 同上 |
   | 20 | RPM, 拉力, 电压 | 同上 |
   | 30 | RPM, 拉力, 电压 | 同上 |
   | 50 | RPM, 拉力, 电压 | 同上 |
   | 75 | RPM, 拉力, 电压 | 同上 |
   | 100 | RPM, 拉力, 电压 | 同上 |

3. **计算阶段**：
   - 使用线性回归拟合 `RPM = k × thrust_percent + b`
   - 斜率 `k` 即为 `main_motor_rpm_scale` 的实测值
   - 截距 `b` 应接近 0（若显著非零，说明存在死区）

4. **验证阶段**：
   ```bash
   # 写入实测值
   ros2 param set /auv_bridge_node main_motor_rpm_scale <实测值>
   
   # 发送 50% 推力指令，验证 RPM 是否匹配预期
   ros2 topic pub /auv/control/cmd_vel geometry_msgs/msg/Twist \
     "{linear: {x: 0.5}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
   ```

5. **安全注意事项**：
   - 首次试验推力不超过 30%
   - 每次指令间等待 5 秒让电机冷却
   - 记录水温（影响水的密度，进而影响推力）

> **仿真默认**：`15.0`（固定理想值，无电机特性曲线）  
> **实机典型值**：`14.2 ~ 16.8`（因电机批次、水温、电池电压而异）  
> **暗病排查**：若实机推力不足，但 RPM 正确 → 检查螺旋桨螺距是否匹配仿真模型。

---

## 2. 推进器死区 (Thrust Deadzone)

### 2.1 参数定义

| 字段 | 类型 | 仿真默认值 | 实机可能范围 | 代码位置 |
|:---|:---|:---:|:---:|:---|
| `mappers.thrust.deadzone_percent` | float | `5.0` | `2.0 ~ 10.0` | `params.yaml:59` |

死区定义在 `mappers.py:thrust_to_rpm` 中：

```python
# 低于死区阈值时，输出最小有效 RPM（跳过静摩擦区）
if abs_thrust < deadzone_percent:
    rpm = deadzone_percent * rpm_per_percent  # 直接跳到死区边界 RPM
else:
    rpm = (abs_thrust - deadzone_percent + deadzone_percent) * rpm_per_percent
```

### 2.2 死区测量 SOP

**目标**：找到克服螺旋桨静摩擦力的最小启动推力百分比。

**步骤**：

1. 将 AUV 系泊固定，螺旋桨浸没
2. 从 0% 开始，以 0.5% 步进增加推力指令
3. 观察螺旋桨是否开始旋转（使用转速计或目视标记）
4. 记录首次旋转时的推力百分比 `p_start`
5. 从 100% 开始递减，记录首次停止时的推力百分比 `p_stop`
6. **死区值** = `(p_start + p_stop) / 2`

| 测量项 | 典型值 | 说明 |
|:---|:---|:---|
| `p_start` (正向) | 3.5% ~ 6.0% | 克服正向静摩擦 |
| `p_start` (反向) | 3.5% ~ 6.0% | 克服反向静摩擦 |
| `p_stop` (正向→零) | 2.0% ~ 4.0% | 低于此值电机停转 |

**标定命令**：
```bash
# 设置实测死区值
ros2 param set /auv_bridge_node deadzone_percent <测量值>
```

> **仿真默认**：`5.0`（仿真电机模型无静摩擦）  
> **实机暗病**：若死区设太小，低推力指令被电机吸收但不产生推力 → AUV "无响应"。  
> 若死区设太大，控制精度下降，定深时出现 "抖动"。

---

## 3. 舵机中位配平 (Fin Trim / `center_offset`)

### 3.1 参数定义

| 字段 | 类型 | 仿真默认值 | 实机可能范围 | 代码位置 |
|:---|:---|:---:|:---:|:---|
| `mappers.rudder.center_bias` | float | `0.0` | `-3.0 ~ 3.0` (°) | `params.yaml:55` |
| `mappers.rudder.gain` | float | `1.0` | `0.5 ~ 2.0` | `params.yaml:56` |
| `mappers.rudder.flip` | bool | `false` | `true/false` | `params.yaml:57` |
| `limits.fin_deg_max` | float | `15.0` | `10.0 ~ 30.0` | `params.yaml:65` |

在 `mappers.py:rudder_deg_to_protocol` 中应用 Trim：

```python
# line 71-74
adjusted_angle = angle_deg + center_bias  # Trim 偏移
scaled_angle = adjusted_angle * gain      # 增益调节
if flip:
    scaled_angle = -scaled_angle          # 极性翻转
```

### 3.2 中位配平测量 SOP

**目标**：补偿机械连杆安装误差，使舵面在零指令下保持中性位。

**设备要求**：
- 舵角角度尺或数字倾角仪（精度 ±0.1°）
- 固定夹具（AUV 水平放置）
- 螺丝刀/扳手（调整舵机连杆长度）

**步骤**：

1. **机械归零**：
   - 将所有舵机连杆长度调到设计值
   - 用角度尺测量每个舵面相对于水流方向的实际偏角
   - 记录偏角：`δ_R`, `δ_T`, `δ_L`, `δ_B`

2. **零指令测试**：
   - 发送全零舵角指令（`right=0, top=0, left=0, bottom=0`）
   - 观察 AUV 在静止水中的自然漂移方向
   - 若持续向右偏 → Right 舵面中位偏正 → 需要 `center_bias` 负值补偿

3. **Trim 值计算**：

   | 现象 | 偏移舵面 | `center_bias` 调整方向 |
   |:---|:---|:---|
   | 右偏航 | Right 偏正 / Left 偏负 | 设 `center_bias = -(δ_R - δ_L)/2` |
   | 左偏航 | Left 偏正 / Right 偏负 | 设 `center_bias = (δ_L - δ_R)/2` |
   | 下俯 | Top 偏正 / Bottom 偏负 | 设 `center_bias = -(δ_T - δ_B)/2` |
   | 仰首 | Bottom 偏正 / Top 偏负 | 设 `center_bias = (δ_B - δ_T)/2` |

4. **水面验证**：
   - 在静止水面发送零指令
   - 观察 30 秒，AUV 应保持航向且无明显偏航/偏俯
   - 若仍有偏移，微调 `center_bias`（每次 ±0.5°）

**标定命令**：
```bash
# 设置全局 Trim 偏移
ros2 param set /auv_bridge_node center_bias <值>

# 翻转特定舵面极性（如安装方向相反）
ros2 param set /auv_bridge_node flip true
```

> **仿真默认**：`center_bias: 0.0`（仿真舵面无机械误差）  
> **实机暗病**：每次拆装后机械连杆可能产生 0.5°~2° 的偏差，**必须重新标定**。  
> 建议使用 `center_bias` 软件补偿而非反复机械调整，可提高效率。

---

## 4. 舵面极限角度 (`fin_deg_max`)

### 4.1 参数定义

| 字段 | 类型 | 仿真默认值 | 实机可能范围 | 代码位置 |
|:---|:---|:---:|:---:|:---|
| `limits.fin_deg_max` | float | `15.0` | `10.0 ~ 30.0` (°) | `params.yaml:65` |

在 `mappers.py` 中的 `clamp_rudder_deg` 函数执行钳位（通过 `physics.py` 导入）：

```python
# 确保舵角不超过物理限位
clamped_deg = clamp(max(-fin_deg_max, min(fin_deg_max, raw_deg)))
```

### 4.2 极限角度测量 SOP

1. 手动旋转舵面到最大偏转位置
2. 记录卡死前的最大角度（避免舵面与壳体干涉）
3. 取测量值的 90% 作为 `fin_deg_max`（留安全余量）

**标定命令**：
```bash
ros2 param set /auv_bridge_node fin_deg_max <安全极限值>
```

---

## 5. 电压补偿参数 (Voltage Compensation)

### 5.1 参数定义

| 字段 | 类型 | 仿真默认值 | 实机可能范围 | 代码位置 |
|:---|:---|:---:|:---:|:---|
| `mappers.thrust.voltage_nominal` | float | `24.0` | `22.0 ~ 26.0` (V) | `params.yaml:61` |
| `mappers.thrust.voltage_compensation` | bool | `true` | `true/false` | `params.yaml:62` |

在 `mappers.py:thrust_to_rpm` 中：

```python
if voltage_compensation and feedback_voltage is not None and feedback_voltage > 0:
    voltage_ratio = voltage_nominal / feedback_voltage
    voltage_ratio = max(0.8, min(1.5, voltage_ratio))  # 限制在 0.8~1.5
    rpm *= voltage_ratio
```

### 5.2 标称电压标定

1. 在电池满电时，记录实际电压 `V_full`
2. 在电池欠压告警时，记录电压 `V_low`
3. 取典型工作电压（约 70% SOC 时）作为 `voltage_nominal`

**标定命令**：
```bash
ros2 param set /auv_bridge_node voltage_nominal <典型工作电压>
ros2 param set /auv_bridge_node voltage_compensation true
```

> **仿真默认**：电压恒为 `24.0V`（无电池模型）  
> **实机可能范围**：满电 `25.2V` (6S LiPo) → 欠压 `21.6V`  
> **暗病排查**：低电量时推力明显衰减，但代码计算未补偿 → 确认 `voltage_compensation` 为 `true`。

---

## 6. HAL 参数汇总对照表

| 参数名 | 仿真默认值 | 实机可能范围 | 标定频率 | 标定难度 |
|:---|:---:|:---:|:---:|:---:|
| `main_motor_rpm_scale` | 15.0 | 10.0 ~ 20.0 | 每次更换电机后 | ★★★★★ |
| `deadzone_percent` | 5.0 | 2.0 ~ 10.0 | 每次检修后 | ★★★☆☆ |
| `center_bias` | 0.0 | -3.0 ~ 3.0° | 每次拆装后 | ★★☆☆☆ |
| `gain` (舵面) | 1.0 | 0.5 ~ 2.0 | 调试阶段 | ★★☆☆☆ |
| `flip` (舵面) | false | true/false | 安装错误时 | ★☆☆☆☆ |
| `fin_deg_max` | 15.0° | 10.0° ~ 30.0° | 初始标定 | ★★☆☆☆ |
| `voltage_nominal` | 24.0V | 22.0V ~ 26.0V | 更换电池后 | ★☆☆☆☆ |
| `voltage_compensation` | true | true/false | - | ★☆☆☆☆ |
