# PID/PVS Inner-Loop Tracking Figures

Generated: 2026-06-10T14:23:27

## Profiles

Shared relaxed plant limits (runtime, not source edit): deltaMax=20.0 deg, r_max=12.0 deg/s, wn_d=0.6.

- step depth: `Kp_z=1.0, Kp_theta=12.0, Kd_theta=2.0, Ki_theta=2.0, wn_d_z=0.15`
- step yaw: `lam=0.08, phi_b=0.4, K_d=0.1, K_sigma=0.01`
- sine depth: `Kp_z=1.0, Kp_theta=6.0, Kd_theta=2.0, Ki_theta=1.5, wn_d_z=0.4`
- sine yaw: `lam=0.1, phi_b=0.4, K_d=0.1, K_sigma=0.01`

## Metrics

| case | metrics |
| --- | --- |
| `depth_step` | rmse=1.453, rmse_feasible=0.345, mae=0.631, maxe=5.006, final_err=0.020, final=5.020, overshoot=0.020 |
| `yaw_step` | rmse=6.390, rmse_feasible=1.488, mae=2.527, maxe=29.994, final_err=-0.244, final=29.756, overshoot=0.000 |
| `depth_sine` | rmse=0.202, rmse_feasible=0.049, mae=0.184, maxe=0.290, final_err=0.281 |
| `yaw_sine` | rmse=2.325, rmse_feasible=1.750, mae=2.111, maxe=3.444, final_err=3.094 |

## Figures

| figure | path |
| --- | --- |
| `depth_step` | `/auv_data/results/control/pid_pvs_tuning/20260610_142323/figures/01_pid_pvs_depth_step.png` |
| `yaw_step` | `/auv_data/results/control/pid_pvs_tuning/20260610_142323/figures/02_pid_pvs_yaw_step.png` |
| `depth_sine` | `/auv_data/results/control/pid_pvs_tuning/20260610_142323/figures/03_pid_pvs_depth_sine.png` |
| `yaw_sine` | `/auv_data/results/control/pid_pvs_tuning/20260610_142323/figures/04_pid_pvs_yaw_sine.png` |
| `profile_comparison` | `/auv_data/results/control/pid_pvs_tuning/20260610_142323/figures/05_pid_pvs_profile_comparison.png` |
