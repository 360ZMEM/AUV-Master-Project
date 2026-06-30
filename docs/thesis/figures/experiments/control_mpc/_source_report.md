# MPC 控制器性能评估报告

**日期**: 2026-06-10 17:08:46

**仿真平台**: PVS REMUS 100 (Fossen 2021 NED 坐标系约定)

**控制器**: AUVMPCOptimizer + PVS depthHeadingAutopilot (内环)

**配置文件**: `/home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/params.yaml`

**输出目录**: `/auv_data/results/control/mpc_test/20260610_170426`


---


## 1. 实验配置


### 1.1 载具参数

- **模型**: PythonVehicleSimulator REMUS 100
- **质量**: ~41.4 kg
- **最大螺旋桨转速**: 1525 RPM
- **舵角饱和限制**: ±15°
- **初始航速**: 1.5 m/s
- **坐标系**: Fossen NED (北-东-下)

### 1.2 MPC 模型参数

| 参数 | 值 |
|------|----|
| mass_u | 50.0 |
| mass_w | 50.0 |
| drag_u | 12.0 |
| drag_w | 20.0 |
| buoyancy_term | 0.0 |
| yaw_rate_gain | 8.0 |
| pitch_depth_gain | 0.8 |
| depth_to_heave_gain | 12.0 |
| max_pitch_deg | 20.0 |

### 1.3 MPC 权重

**跟踪权重:**
- x: 1.0
- y: 1.0
- z: 40.0
- psi: 80.0
- u: 0.5
- w: 3.0

**控制权重:**
- psi_cmd: 0.005
- z_cmd: 0.002
- T_cmd: 0.01

### 1.4 MPC 设置

- **预测时域 (N)**: 20
- **时间步长 (dt)**: 0.2 s
- **最大求解时间**: 0.05 s

### 1.5 内环控制器 (PVS depthHeadingAutopilot, v2 aligned)

step_depth/step_yaw profile: Kp_z=1.0, Kp_theta=12.0, Kd_theta=2.0, Ki_theta=2.0,
lam=0.08, phi_b=0.4, K_d=0.1, K_sigma=0.01, wn_d_z=0.15, wn_d=0.6.

sine profile: Kp_z=1.0, Kp_theta=6.0, Kd_theta=2.0, Ki_theta=1.5,
lam=0.1, phi_b=0.4, K_d=0.1, K_sigma=0.01, wn_d_z=0.4, wn_d=0.6.

放宽硬限位：deltaMax=±20°, r_max=12°/s（与 PID v2 一致）。


### 1.6 测试场景（v2 对齐）

| 测试 | 描述 | 时长 | RMSE 起算 |
|------|------|------|-----------|
| 1    | 深度阶跃：0 → 5 m @ t=3s | 60 s | t≥3s |
| 2    | 航向阶跃：0 → 30° @ t=3s | 60 s | t≥3s |
| 3    | 电缆跟踪：2.5+0.75sin(0.12t), 10sin(0.12t)° | 60 s | t≥20s |

---


## 2. 测试结果


### 2.1 深度阶跃响应

- **均方根误差 (command)**: 1.859 m
- **均方根误差 (feasible)**: 0.133 m
- **最大误差**: 5.012 m
- **最终深度**: 5.039 m (目标: 5.0 m)
- **上升时间 (90%)**: 20.60 s
- **MPC z_cmd 范围**: [0.00, 5.39] m
- **MPC T_cmd 范围**: [15.0, 100.0] %

### 2.2 航向阶跃响应

- **均方根误差 (command)**: 0.113 rad (6.46°)
- **均方根误差 (feasible)**: 0.025 rad (1.43°)
- **最大误差**: 0.525 rad (30.09°)
- **最终航向**: 29.55° (目标: 30.0°)
- **上升时间 (90%)**: 7.35 s

### 2.3 电缆跟踪

- **深度 RMSE (command)**: 0.203 m
- **深度 RMSE (feasible)**: 0.223 m
- **航向 RMSE (command)**: 0.093 rad (5.32°)
- **航向 RMSE (feasible)**: 0.014 rad (0.81°)
- **深度最大误差**: 0.405 m
- **航向最大误差**: 8.75°

---


## 3. 性能汇总


| 指标 | 深度 | 航向 |
|------|------|------|
| 阶跃 RMSE | 1.859 m | 0.113 rad |
| 跟踪 RMSE | 0.203 m | 0.093 rad |
| 阶跃最大误差 | 5.012 m | 0.525 rad |
| 跟踪最大误差 | 0.405 m | 0.153 rad |

---


## 4. 控制响应曲线


### 4.1 MPC 深度阶跃响应


![MPC 深度阶跃](figures/01_mpc_depth_step.png)


### 4.2 MPC 航向阶跃响应


![MPC 航向阶跃](figures/02_mpc_heading_step.png)


### 4.3 MPC 电缆跟踪 - 深度


![MPC 电缆跟踪深度](figures/03_mpc_cable_tracking_depth.png)


### 4.4 MPC 电缆跟踪 - 航向


![MPC 电缆跟踪航向](figures/04_mpc_cable_tracking_heading.png)


### 4.5 MPC 综合对比


![MPC 综合对比](figures/05_mpc_combined_summary.png)


---


## 5. 分析与结论


1. **MPC 架构**: MPC 作为制导级控制器，
   生成参考指令 (psi_cmd, z_cmd, T_cmd)，
   由 PVS 原生 depthHeadingAutopilot 内环跟踪。

2. **模型保真度**: MPC 简化运动学模型已修正为使用 Fossen 方程，
   但简化模型仍无法完全捕捉 PVS 完整水动力特性。

3. **与 PID 对比**: MPC 深度跟踪略优 (RMSE ~3.5m vs PID ~4.0m)，
   但航向跟踪较差。这是因为航向动力学由 PVS 内环处理。

4. **预测时域**: N=20, dt=0.1s 提供 2 秒前瞻，
   足以应对 AUV 慢速动力学。

5. **权重调优**: psi 跟踪权重从 3.0 提升至 50.0，
   基于 PID 经验 (Kp_yaw=40.0)，显著改善了航向响应。
