# ES-EKF 状态估计

## 设计动机

AUV 水下导航面临多源传感器频率和精度差异极大的挑战：

- **IMU**：100Hz 高频，短期精确但长期漂移
- **DVL**：~10Hz，提供速度但有延迟
- **深度传感器**：~10Hz，精确但仅垂直方向
- **GPS**：仅水面可用

**误差状态扩展卡尔曼滤波器（ES-EKF）** 的解决方案：

> IMU 高频（100Hz）预测 + DVL/深度/GPS 低频修正 → 连续高精度位姿估计

ES-EKF 相比传统 EKF 的优势：
- 误差状态始终接近零，线性化更精确
- 姿态用小角度近似，避免奇异性
- IMU 数据直接驱动预测，无需运动模型

---

## 状态定义

### 名义状态（16 维）

| 分量 | 维度 | 符号 | 说明 |
|------|------|------|------|
| 位置 | 3 | p = [px, py, pz] | 世界坐标系位置 (m) |
| 速度 | 3 | v = [vx, vy, vz] | 世界坐标系速度 (m/s) |
| 姿态 | 4 | q = [qw, qx, qy, qz] | 姿态四元数 |
| 加速度零偏 | 3 | b_a = [bax, bay, baz] | IMU 加速度计零偏 (m/s²) |
| 陀螺零偏 | 3 | b_g = [bgx, bgy, bgz] | IMU 陀螺仪零偏 (rad/s) |

### 误差状态（15 维）

| 分量 | 维度 | 符号 | 说明 |
|------|------|------|------|
| 位置误差 | 3 | δp | 位置偏差 |
| 速度误差 | 3 | δv | 速度偏差 |
| 姿态误差 | 3 | δθ | 小角度旋转向量 |
| 加速度零偏误差 | 3 | δb_a | 零偏估计偏差 |
| 陀螺零偏误差 | 3 | δb_g | 零偏估计偏差 |

> 注意：姿态误差使用 3 维小角度向量而非 4 维四元数，因此误差状态为 15 维而非 16 维。

---

## 预测步 (predict)

每收到一次 IMU 数据（100Hz）执行一次预测：

### 四元数积分

```python
omega = gyro - b_g                           # 去零偏角速度
delta_q = small_angle_quat(omega * dt)       # 增量四元数
q_new = quaternion_multiply(q, delta_q)      # 姿态更新
q_new = normalize(q_new)                     # 归一化
```

### 速度积分

```python
R = quaternion_to_rotation_matrix(q)         # 当前旋转矩阵
a_world = R @ (accel - b_a)                  # 去零偏、转世界系
v_new = v + a_world * dt + g * dt            # 速度更新（g为重力向量）
```

### 位置积分

```python
p_new = p + v * dt
```

### 协方差传播

```python
F = compute_jacobian(q, accel, b_a, dt)      # 状态转移雅可比 (15×15)
Q = process_noise_covariance(sigma_acc, sigma_gyro, dt)
P = F @ P @ F.T + Q                          # 协方差传播
```

---

## 修正步 (correct)

当低频传感器数据到达时执行修正：

### DVL 体坐标系修正

DVL 测量体坐标系速度 [u, v, w]：

```python
v_body_predicted = R.T @ v                   # 预测体速度
innovation = dvl_measurement - v_body_predicted
H = [0_{3x3}, R.T, ...]                     # 观测雅可比
```

### DVL 世界系修正

若 DVL 已转换至世界系：

```python
innovation = dvl_world - v
H = [0_{3x3}, I_{3x3}, 0_{3x9}]            # 观测雅可比
```

### 深度修正

```python
innovation = depth_measurement - p[2]        # 仅修正 z 分量
H = [0, 0, 1, 0, ..., 0]                   # 1×15
```

### GPS XY 修正

仅水面可用，修正水平位置：

```python
innovation = [gps_x - p[0], gps_y - p[1]]
H = [[1,0,0, 0,...,0],
     [0,1,0, 0,...,0]]                      # 2×15
```

### 通用修正流程

```python
# 卡尔曼增益
S = H @ P @ H.T + R_meas
K = P @ H.T @ np.linalg.inv(S)

# 误差状态修正
delta_x = K @ innovation

# 注入名义状态
p += delta_x[0:3]                            # 位置直接加
v += delta_x[3:6]                            # 速度直接加
q = quaternion_multiply(q, small_angle_quat(delta_x[6:9]))  # 姿态用小角度四元数乘
b_a += delta_x[9:12]                         # 零偏直接加
b_g += delta_x[12:15]                        # 零偏直接加

# 协方差更新
P = (I - K @ H) @ P
```

---

## 增强特性

### 自动初始化

首次收到 DVL/深度数据时自动完成状态对齐：

- 首帧深度 → 初始化 `p[2]`
- 首帧 DVL → 初始化 `v`（体→世界转换）
- 首帧 GPS → 初始化 `p[0], p[1]`

无需手动设置初始状态，上电即收敛。

### 零偏预校准

系统启动后静止期间（检测加速度方差 < 阈值）：

```python
b_a_init = mean(accel_samples) - [0, 0, g]  # 加速度零偏
b_g_init = mean(gyro_samples)                # 陀螺零偏
```

提供比在线估计更准确的初始零偏值。

### DVL 延迟补偿

DVL 数据存在固有延迟（~50ms），采用带时间戳的异步修正：

1. 记录每次 IMU 预测的状态快照
2. DVL 到达时，根据时间戳回溯到对应预测时刻
3. 在历史状态上执行修正
4. 重新积分至当前时刻

---

## 推荐参数

经三步调优（粗调 → 细调 → 验证）得到的最终参数：

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `sigma_acc` | 0.1 m/s² | 加速度计噪声标准差 |
| `sigma_gyro` | 0.01 rad/s | 陀螺仪噪声标准差 |
| `sigma_dvl` | 0.05 m/s | DVL 测量噪声 |
| `sigma_depth` | 0.02 m | 深度传感器噪声 |

### 最终性能

- **3D RMSE**：1.523m（在标准测试轨迹上）
- 测试条件：水下连续航行，DVL 偶发丢失，无 GPS

---

## 辅助函数说明

| 函数 | 功能 |
|------|------|
| `small_angle_quat(theta)` | 小角度向量 → 四元数：`[1, θ/2]` 归一化 |
| `quaternion_multiply(q1, q2)` | 四元数乘法（Hamilton 约定） |
| `quaternion_to_rotation_matrix(q)` | 四元数 → 3×3 旋转矩阵 |
| `normalize(q)` | 四元数归一化 |
| `compute_jacobian(...)` | 计算误差状态转移雅可比 F |
| `process_noise_covariance(...)` | 构建过程噪声矩阵 Q |
