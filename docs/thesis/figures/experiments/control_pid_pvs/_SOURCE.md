# 数据来源

- 源 run：`results/control/pid_pvs_tuning/20260823_221627`
- 生成时间：2026-08-23
- 生成脚本：`tools/pid_pvs_tracking_plots.py`
- 仿真对象：`/root/PythonVehicleSimulator/src/python_vehicle_simulator/vehicles/remus100.py`

## Profile 口径

- `pvs_native_default`：严格使用上游 PVS 默认值，深度参数为
  `Kp_z=0.1, Kp_theta=5.0, Kd_theta=2.0, Ki_theta=0.3, wn_d_z=0.02`，
  舵角上限为 `15 deg`。
- `step_tuned_v2`：面向阶跃响应的运行时 profile。
- `sine_tuned_v2`：面向平滑地形跟随的运行时 profile，也是正式 terrain benchmark 使用的内层配置。
- 三组均运行同一 `remus100` 六自由度模型；RMSE 相对原始指令计算，包含 PVS 参考模型延迟。
- 调优值通过本地 adapter 注入，不修改上游 PVS 包；terrain 正式链路另启用 adapter-local anti-windup。

## 关键结果

| 工况 | PVS 原生默认 | 阶跃调优 | 正弦调优 |
| --- | ---: | ---: | ---: |
| 深度阶跃 RMSE（m） | 3.491 | 1.453 | 1.805 |
| 航向阶跃 RMSE（deg） | 17.740 | 6.390 | 6.471 |
| 深度正弦 RMSE（m） | 1.132 | 0.351 | 0.202 |
| 航向正弦 RMSE（deg） | 8.433 | 1.995 | 2.325 |

重跑命令：

```bash
python3 tools/pid_pvs_tracking_plots.py
```
