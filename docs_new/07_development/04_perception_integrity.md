# 04 - 感知层噪声与"暗病"隔离 (Perception Integrity)

> 本文件针对 EKF 滤波器和传感器链路中的关键噪声源，提供实机部署时的防御性配置指南。  
> 仿真环境中所有传感器都是"干净"的（固定高斯噪声），实机环境中则面临气泡干扰、磁场畸变、时钟漂移等多重挑战。

---

## 1. 杆臂补偿 (Lever Arm Effect)

### 1.1 问题定义

EKF 预测阶段使用 IMU 测量值更新状态，但 IMU 安装在载体的某个物理位置，而非重心 (CG)。当 AUV 旋转时，IMU 会测到额外的离心加速度，这部分加速度不是由推进力产生的，但会被 EKF 误认为是线性加速度，导致位置积分漂移。

**杆臂向量**：从重心 (CG) 到传感器的位移向量 `r_cg_to_sensor = [dx, dy, dz]`。

### 1.2 参数定义

| 参数名 | 类型 | 仿真默认值 | 实机可能范围 | 代码位置 |
|:---|:---|:---:|:---:|:---|
| `imu_frame_offset_xyz` | str | `"0.0,0.0,0.0"` | `±0.5` (m) | `auv_localization_node.py:127` |
| `dvl_frame_offset_xyz` | str | `"0.0,0.0,0.0"` | `±0.5` (m) | `auv_localization_node.py:128` |
| `depth_frame_offset_xyz` | str | `"0.0,0.0,0.0"` | `±0.3` (m) | `auv_localization_node.py:129` |

在 `AUVLocalizationNode.__init__` 中解析：
```python
self.imu_frame_offset_xyz = _parse_xyz(self.get_parameter('imu_frame_offset_xyz').value)
self.dvl_frame_offset_xyz = _parse_xyz(self.get_parameter('dvl_frame_offset_xyz').value)
```

### 1.3 测量 SOP

**目标**：精确测量各传感器相对于重心的物理偏移。

**步骤**：

1. **确定重心 (CG) 位置**：
   - 将 AUV 吊装至水中，找到平衡点（悬挂法）
   - 或以 CAD 模型计算理论 CG
   - 在壳体上标记 CG 参考点

2. **测量各传感器位置**：
   - IMU：通常位于电子舱中心，用卷尺测量 CG 到 IMU 中心的偏移
   - DVL：位于底部，测量 CG 到 DVL 换能器面的偏移
   - 深度计：位于顶部，测量 CG 到压力传感器开孔的偏移

3. **记录偏移值**（体轴系，单位：米）：

   | 传感器 | dx (前+) | dy (右+) | dz (下+) | 典型实机值 |
   |:---|:---:|:---:|:---:|:---|
   | IMU | 0.0 | 0.0 | -0.15 | CG 上方 15cm |
   | DVL | -0.1 | 0.0 | +0.25 | CG 下方 25cm，靠后 10cm |
   | 深度计 | 0.15 | 0.0 | -0.20 | CG 上方 20cm，靠前 15cm |

### 1.4 补偿公式推导

当载具以角速度 `ω = [p, q, r]` 旋转时，传感器测到的加速度包含杆臂效应项：

```
a_sensor = a_cg + α × r + ω × (ω × r)
```

其中：
- `a_cg`：重心处的真实线性加速度（EKF 需要的量）
- `α = [ṗ, q̇, ṙ]`：角加速度
- `ω = [p, q, r]`：角速度（来自 IMU 陀螺仪）
- `r = [dx, dy, dz]`：杆臂向量

补偿计算（在 EKF predict 阶段应用）：

```python
# 从 IMU 测得的比力中扣除杆臂效应
a_cg = a_sensor - np.cross(alpha, r) - np.cross(omega, np.cross(omega, r))
```

> **仿真默认**：偏移全为零（仿真中传感器就在 CG 上）  
> **实机暗病**：若 IMU 偏离 CG 10cm，在 30°/s 的旋转下，会产生约 0.027 m/s² 的虚假加速度，积分 10 秒后位置误差 > 1.3m。  
> 
> **当前代码状态**：`auv_localization_node.py` 中声明了 `*_frame_offset_xyz` 参数但尚未在 EKF 预测链中应用补偿。**这是已知的仿真/实机差异点**，需要在部署前将偏移值传递给 `es_ekf.py:predict` 方法。

**配置命令**：
```bash
# 设置 IMU 相对于 CG 的偏移（体轴系）
ros2 param set /auv_localization_node imu_frame_offset_xyz "0.0,0.0,-0.15"

# 设置 DVL 偏移
ros2 param set /auv_localization_node dvl_frame_offset_xyz "-0.1,0.0,0.25"

# 设置深度计偏移
ros2 param set /auv_localization_node depth_frame_offset_xyz "0.15,0.0,-0.20"
```

---

## 2. EKF 噪声门限 (Gating) — `sigma_dvl` 动态调整

### 2.1 参数定义

| 字段 | 类型 | 仿真默认值 | 实机可能范围 | 代码位置 |
|:---|:---|:---:|:---:|:---|
| `ekf.sigma_dvl` | float | `0.03` | `0.01 ~ 0.30` (m/s) | `params.yaml:154` |
| `ekf.sigma_depth` | float | `0.05` | `0.02 ~ 0.20` (m) | `params.yaml:155` |
| `ekf.sigma_acc` | float | `0.08` | `0.05 ~ 0.20` (m/s²) | `params.yaml:150` |
| `ekf.sigma_gyro` | float | `0.01` | `0.005 ~ 0.03` (rad/s) | `params.yaml:151` |

在 `es_ekf.py:correct_dvl` 中（line 373）：
```python
self._correct(z, h, h_mat, (self.sigma_dvl ** 2) * np.eye(3))
```

### 2.2 物理意义

`sigma_dvl` 定义了 EKF 对 DVL 速度观测的**信任程度**：

| `sigma_dvl` 值 | 对 DVL 的信任度 | EKF 行为 |
|:---:|:---|:---|
| **小 (0.01)** | 高度信任 | 观测修正权重高，状态快速跟随 DVL |
| **中 (0.03)** | 适度信任 | 观测与 IMU 预测平衡 |
| **大 (0.30)** | 低信任 | 主要依赖 IMU 积分，DVL 修正微弱 |

### 2.3 水域条件参数对照表

| 水域类型 | DVL 工作条件 | `sigma_dvl` 建议 | 调整方向 |
|:---|:---|:---:|:---|
| **清水水域** (能见度 > 5m) | DVL 四波束锁定，底跟踪稳定 | `0.02 ~ 0.05` | 信任 DVL |
| **浑浊水域** (含沙量高) | 波束衰减，底跟踪偶尔丢失 | `0.10 ~ 0.20` | 降低信任 |
| **气泡密集区** (推进器气泡回流) | 声波散射，速度跳跃 | `0.20 ~ 0.30` | 大幅降低信任 |
| **深水 (> 100m)** | 超出底跟踪量程，仅水跟踪 | `0.15 ~ 0.25` | 降低信任（水跟踪精度低） |
| **DVL 完全丢失** | 无有效速度观测 | `> 1.0` 或禁用 | 纯 IMU 航位推算 |

### 2.4 动态调整策略

```python
# 伪代码：根据 DVL 质量动态调整 sigma_dvl
def compute_adaptive_sigma_dvl(dvl_beam_consistency, dvl_altitude):
    """根据 DVL 波束一致性和离底高度动态调整噪声。"""
    base_sigma = 0.03
    
    # 波束一致性差 → 增大噪声
    if dvl_beam_consistency < 0.7:
        base_sigma *= 3.0
    elif dvl_beam_consistency < 0.9:
        base_sigma *= 1.5
    
    # 离底高度太低（< 0.5m）或太高（> 100m）→ 增大噪声
    if dvl_altitude < 0.5 or dvl_altitude > 100:
        base_sigma *= 2.0
    
    return base_sigma
```

**调试命令**：
```bash
# 浑浊水域：降低对 DVL 的信任
ros2 param set /auv_localization_node sigma_dvl 0.15

# 清水水域：增加对 DVL 的信任
ros2 param set /auv_localization_node sigma_dvl 0.02

# 深度计噪声调整（压力传感器受波浪扰动时增大）
ros2 param set /auv_localization_node sigma_depth 0.15
```

> **仿真默认**：固定 `sigma_dvl: 0.03`  
> **实机暗病**：浑浊水域中若未增大 `sigma_dvl`，EKF 会信任被噪声污染的 DVL 数据 → 速度估计跳跃 → MPC 参考轨迹突变 → 舵面剧烈摆动。

---

## 3. 时间戳偏移 (Clock Skew)

### 3.1 问题定义

AUV 系统中存在多个独立时钟源：

| 组件 | 时钟源 | 典型精度 | 漂移率 |
|:---|:---|:---:|:---|
| **Jetson** (运行 ROS2 / EKF) | 板载晶振 | ±20 ppm | ~1.7 ms/min |
| **PC104** (AMD 固件) | 独立晶振 | ±50 ppm | ~3.0 ms/min |
| **传感器 (IMU/DVL)** | 内部晶振 | ±10 ppm | ~0.6 ms/min |

随着运行时间增加，Jetson 与 PC104 之间的时钟偏移逐渐累积：

```
t = 0 min:   偏移 ≈ 0 ms
t = 30 min:  偏移 ≈ 50 ms (Jetson 快于 PC104)
t = 60 min:  偏移 ≈ 100 ms
```

### 3.2 对系统的影响

| 影响链路 | 偏移 > 50ms 的后果 | 代码中的缓解措施 |
|:---|:---|:---|
| **DVL → EKF** | 速度修正使用过时数据 → 状态估计偏差 | `correct_dvl_with_timestamp` 增大观测噪声 |
| **IMU → EKF** | 加速度与角速度时间不匹配 → 姿态误差 | IMU 频率高 (200Hz)，影响较小 |
| **PC104 → Jetson 遥测** | 上行链路时间戳过期 → 仲裁器判断"数据不新鲜" | `guard_max_uplink_age_ms: 200.0` |
| **MPC → 执行器** | 优化结果到达时已过时 → 控制指令过期 | `mpc_timeout_s: 0.5` |

### 3.3 EKF 中的延迟补偿

在 `es_ekf.py:correct_dvl_with_timestamp`（line 384-411）中：

```python
dt_delay = current_timestamp - dvl_timestamp
if dt_delay > 0.050:  # 延迟超过 50ms
    delay_factor = min(dt_delay / 0.200, 2.0)  # 线性增长，最大 2x
    dvl_noise_inflation = (self.sigma_dvl ** 2) * (1.0 + delay_factor)
    r = dvl_noise_inflation * np.eye(3)
```

这意味着：
- 延迟 50ms → `sigma_dvl` 有效值 × 1.25
- 延迟 100ms → `sigma_dvl` 有效值 × 1.5
- 延迟 200ms → `sigma_dvl` 有效值 × 2.0（上限）

### 3.4 时钟同步 SOP

**目标**：最小化 Jetson 与 PC104 之间的时钟偏移。

**方法 1：NTP 同步（推荐）**

```bash
# 在 Jetson 上配置 NTP 客户端
sudo apt install ntp
sudo systemctl enable ntp
sudo systemctl start ntp

# 验证同步状态
ntpq -p
chronyc tracking  # 如果使用 chrony

# 期望：偏移 < 5ms
```

**方法 2：PTP 精确时间协议（高精度需求）**

```bash
# 安装 PTP 支持
sudo apt install linuxptp

# 启动 PTP 客户端（需要交换机支持 PTP）
sudo ptp4l -i eth0 -s
sudo phc2sys -s eth0 -w
```

**方法 3：软件补偿（无外部时钟源时）**

```bash
# 在启动脚本中定期手动同步
# 添加到 /etc/cron.d/auv_sync
*/5 * * * * root ntpdate -s <NTP_SERVER_IP>
```

**测量当前时钟偏移**：

```bash
# 查看 Mock AMD 时间戳与系统时间的差值
ros2 topic echo /auv/sensors/status --once | grep mock_amd_timestamp_us
# 与当前 Unix 时间对比
python3 -c "import time; print(int(time.time() * 1e6))"
```

> **仿真默认**：时钟完美同步（同一进程内运行）  
> **实机可能范围**：偏移 0 ~ 500ms（取决于是否配置 NTP/PTP）  
> **暗病排查**：若 AUV 在长航时后定位精度逐渐下降，最可能原因是时钟漂移导致 EKF 延迟补偿不断增大。

---

## 4. EKF 初始化与零偏校准

### 4.1 参数定义

| 字段 | 类型 | 仿真默认值 | 实机建议 | 代码位置 |
|:---|:---|:---:|:---:|:---|
| `ekf.auto_init` | bool | `true` | `true` | `params.yaml` (通过代码逻辑) |
| `ekf.enable_bias_calibration` | bool | `true` | `true` | `es_ekf.py:148` |
| `ekf.bias_calibration_samples` | int | `50` | `50 ~ 200` | `es_ekf.py:149` |
| `ekf.init_P_diag` | list | 15 个值 | 见下表 | `params.yaml:163` |

### 4.2 初始化协方差矩阵 (`init_P_diag`)

```yaml
init_P_diag: [0.5, 0.5, 0.5,    # 位置 x,y,z (m²)
              0.5, 0.5, 0.5,    # 速度 vx,vy,vz (m²/s²)
              0.2, 0.2, 0.2,    # 姿态 roll,pitch,yaw (rad²)
              0.05, 0.05, 0.05, # 加速度零偏 ba (m²/s⁴)
              0.05, 0.05, 0.05] # 陀螺零偏 bg (rad²/s²)
```

### 4.3 零偏校准 SOP

在 `es_ekf.py:add_bias_calibration_sample` 中（line 154-193）：

```python
# 加速度零偏：静止时加速度应等于重力向量
mean_acc = np.mean(bias_calibration_buffer_acc, axis=0)
self.b_a = mean_acc - self.g_n  # 估计加速度零偏

# 陀螺零偏：静止时角速度应为零
self.b_g = np.mean(bias_calibration_buffer_gyro, axis=0)
```

**步骤**：

1. 将 AUV 放置在静止水面或固定台上
2. 确保所有传感器上电并发送数据
3. EKF 自动收集 50 个样本（约 2.5 秒 @ 20Hz）
4. 校准完成后，`b_a` 和 `b_g` 被更新

**验证命令**：
```bash
# 查看 EKF 协方差输出
ros2 topic echo /auv/state/covariance --once

# 检查滤波后的位姿是否稳定
ros2 topic echo /auv/state/filtered --once
```

> **仿真默认**：`init_P_diag` 假设已知初始位置（仿真从 (0,0,0) 开始）  
> **实机可能暗病**：若初始位置未知，应增大 `init_P_diag` 前三个值到 `5.0~10.0`，让 EKF 通过 DVL/深度观测收敛。

---

## 5. 传感器状态诊断

### 5.1 SensorStatus 关键字段

| 字段 | 含义 | 正常范围 | 异常处理 |
|:---|:---|:---:|:---|
| `confidence` | 电缆识别置信度 | 0.5 ~ 1.0 | < 0.5 切换 ZigZag 搜索 |
| `leak_level` | 漏水等级 | 0 (无漏水) | > 0 触发紧急上浮 |
| `battery_low` | 低电标志 | false | true → 紧急上浮 |
| `seabed_penetration_warning` | 穿底警告 | false | true → 紧急上浮 |
| `total_voltage_v` | 总电压 | 48.0V ± 2V | < 44.8V 标记低电 |

### 5.2 仿真 vs 实机感知对照汇总

| 噪声源 | 仿真处理 | 实机处理 | 参数 |
|:---|:---|:---|:---|
| IMU 噪声 | 固定高斯 σ=0.08/0.01 | 根据传感器数据手册标定 | `sigma_acc`, `sigma_gyro` |
| DVL 气泡干扰 | 无 | 增大 `sigma_dvl` 或禁用 | `sigma_dvl` |
| 深度波浪噪声 | 无 | 增大 `sigma_depth` | `sigma_depth` |
| 时钟偏移 | 无 (同一进程) | NTP 同步 + 延迟补偿 | `correct_dvl_with_timestamp` |
| 杆臂效应 | 无 (传感器在 CG) | 测量偏移并应用补偿 | `*_frame_offset_xyz` |
| 磁场畸变 | 理想磁力计 | 忽略磁力计，依赖 IMU+DVL | - |
| 传感器丢包 | 无 | 自适应噪声增大 | 动态 sigma 调整 |
