# PID/PVS 内环跟踪图像

生成时间：2026-08-23T22:16:31

## 配置剖面

PVS 严格原生默认：`Kp_z=0.1, Kp_theta=5.0, Kd_theta=2.0,
Ki_theta=0.3, wn_d_z=0.02, deltaMax=15 deg`。

共享的放宽版被控对象限制（运行时配置，不是源码修改）：deltaMax=20.0 deg，r_max=12.0 deg/s，wn_d=0.6。

- step depth: `Kp_z=1.0, Kp_theta=12.0, Kd_theta=2.0, Ki_theta=2.0, wn_d_z=0.15`
- step yaw: `lam=0.08, phi_b=0.4, K_d=0.1, K_sigma=0.01`
- sine depth: `Kp_z=1.0, Kp_theta=6.0, Kd_theta=2.0, Ki_theta=1.5, wn_d_z=0.4`
- sine yaw: `lam=0.1, phi_b=0.4, K_d=0.1, K_sigma=0.01`

## 指标

| case | 指标 |
| --- | --- |
| `depth_step` | rmse=1.453, rmse_feasible=0.345, mae=0.631, maxe=5.006, final_err=0.020, final=5.020, overshoot=0.020 |
| `yaw_step` | rmse=6.390, rmse_feasible=1.488, mae=2.527, maxe=29.994, final_err=-0.244, final=29.756, overshoot=0.000 |
| `depth_sine` | rmse=0.202, rmse_feasible=0.049, mae=0.184, maxe=0.290, final_err=0.281 |
| `yaw_sine` | rmse=2.325, rmse_feasible=1.750, mae=2.111, maxe=3.444, final_err=3.094 |

## 完整 Profile 对比（相对原始指令的 RMSE）

| case | PVS 原生默认 | 阶跃调优 v2 | 正弦调优 v2 |
| --- | ---: | ---: | ---: |
| `step_depth` | 3.491 | 1.453 | 1.805 |
| `step_yaw` | 17.740 | 6.390 | 6.471 |
| `sine_depth` | 1.132 | 0.351 | 0.202 |
| `sine_yaw` | 8.433 | 1.995 | 2.325 |

## 图像

| 图像 | 路径 |
| --- | --- |
| `depth_step` | `results/control/pid_pvs_tuning/20260823_221627/figures/01_pid_pvs_depth_step.png` |
| `yaw_step` | `results/control/pid_pvs_tuning/20260823_221627/figures/02_pid_pvs_yaw_step.png` |
| `depth_sine` | `results/control/pid_pvs_tuning/20260823_221627/figures/03_pid_pvs_depth_sine.png` |
| `yaw_sine` | `results/control/pid_pvs_tuning/20260823_221627/figures/04_pid_pvs_yaw_sine.png` |
| `profile_comparison` | `results/control/pid_pvs_tuning/20260823_221627/figures/05_pid_pvs_profile_comparison.pdf` |
