# HoloOcean 后端完整基准测试报告

**日期**: 2026-06-18  
**目的**: 基于修复后的离线坐标语义，重新运行 HoloOcean 后端全栈录制与定位 benchmark，确认此前 `--no-coordinate-transform` 下约 24m 的 Z 坐标误差是否消除，并记录当前 HoloOcean benchmark 链路的可引用结论与遗留风险。

**阅读边界**: 本文件是 HoloOcean 后端 60s 工程基准测试报告，可作为“链路已跑通、坐标语义修复已验证、可视化 topic 可录制”的证据。由于本次决策状态保持在 `StandbyCheck`，不能解释为自主巡检闭环性能或最终论文统计结果。

---

## Step 0: 修复前置验证

本轮先执行了不依赖 ROS/MCAP 的坐标语义本地测试：

```bash
/usr/bin/python3 tests/test_offline_ekf_frame_semantics.py
```

结果：

```text
old_unfixed_z_error_m=24.000
fixed_z_error_m=0.000
offline_ekf_frame_semantics: PASS
```

结论：旧逻辑中 ROS z-up truth `z=-12` 与 NED/depth `z=+12` 直接比较会得到 24m 假误差；修复后 truth 被统一归一化到 benchmark NED，最小模拟用例中该误差消除。

---

## Step 1: HoloOcean 60s 全栈录制

运行命令：

```bash
env AUV_DATA_ROOT=/home/gwxie/master_work-tmp/AUV_Master_Project/.auv_data \
  SIM_DELAY_S=3 \
  BRAIN_READY_TOPIC=/auv/sensors/imu \
  BRAIN_READY_TIMEOUT_S=60 \
  BAG_FINALIZE_S=20 \
  bash scripts/start_experiment.sh \
    --sim-backend holoocean \
    --bridge-backend zenoh_json \
    --duration 60 \
    --record-bag \
    --bag-storage mcap \
    --wait-before-record 1 \
    --brain-ready-topic /auv/sensors/imu \
    --brain-ready-timeout 60 \
    --skip-layout
```

运行元数据：

```text
run_id=20260618_223705
sim_mode=both
brain_mode=stack
record_bag=true
bag_storage_id=mcap
run_duration_s=60
bag_finalize_s=20
brain_ready_topic=/auv/sensors/imu
launch_args=--sim-backend holoocean --bridge-backend zenoh_json --skip-layout
git_head=a81c9d7758026e521ba566ee1c9bfe0e8584126a
```

产物：

```text
.auv_data/bags/20260618_223705/metadata.txt
.auv_data/bags/20260618_223705/launcher.log
.auv_data/bags/20260618_223705/rosbag.log
.auv_data/bags/20260618_223705/rosbag/metadata.yaml
.auv_data/bags/20260618_223705/rosbag/rosbag_0.mcap 519198425 bytes
```

`rosbag.log` 显示 recorder 正常 flush：

```text
Writing remaining messages from cache to the bag. It may take a while
Recording stopped
```

结论：HoloOcean + Zenoh JSON + ROS2 stack 的 60s 全栈录制成功，MCAP 文件可被 `ros2 bag info` 和离线 benchmark 读取。

---

## Step 2: MCAP 完整性与 topic 覆盖

`ros2 bag info .auv_data/bags/20260618_223705/rosbag` 摘要：

```text
Bag size: 495.2 MiB
Storage id: mcap
Duration: 59.842853347s
Messages: 37682
```

核心传感/状态 topic：

| Topic | Count | 说明 |
|------|------:|------|
| `/auv/sensors/ground_truth` | 5962 | HoloOcean truth，经可视化桥发布为 ROS `PoseStamped` |
| `/auv/sensors/imu` | 2981 | IMU，约 49.8 Hz |
| `/auv/sensors/depth` | 2981 | 深度，约 49.8 Hz |
| `/auv/sensors/dvl` | 278 | DVL，约 4.6 Hz |
| `/auv/state/filtered` | 1197 | 在线定位输出 |
| `/auv/sensors/status` | 1197 | 传感器/安全状态 |
| `/auv/control/setpoint` | 599 | 决策 setpoint |
| `/auv/control/goal` | 599 | 控制目标 |
| `/auv/diagnostics` | 599 | 诊断信息 |

可视化 topic：

| Topic | Count | 说明 |
|------|------:|------|
| `/auv/visual/truth_marker` | 1198 | truth marker，ROS/Foxglove z-up |
| `/auv/visual/auv_body` | 1198 | AUV 本体 marker |
| `/auv/visual/cable_marker` | 1197 | 电缆 marker |
| `/auv/visual/seabed_mesh` | 1197 | 海床 mesh |
| `/auv/visual/seabed_cloud` | 1197 | 海床点云 |
| `/auv/visual/history_trail` | 1198 | 轨迹历史 |
| `/auv/visual/view_range` | 1198 | 视场/探测范围 |

异常或空 topic：

| Topic | Count | 判断 |
|------|------:|------|
| `/auv/sensors/altitude` | 0 | 仍未录到有效消息，需要继续查 bridge/topic 契约 |
| `/auv/state/raw_dr` | 0 | 当前在线栈未发布 raw DR，不影响本次离线 benchmark |
| `/auv/mission_command` | 0 | 本次未下发 mission command |
| `/auv/bridge/shadow_telemetry` | 0 | shadow 通道未启用或未产出 |
| `/auv/bridge/shadow_cmd` | 0 | shadow 通道未启用或未产出 |

结论：定位 benchmark 所需的 IMU/DVL/depth/truth topic 完整；HoloOcean 可视化 topic 也完整录制。`/auv/sensors/altitude` 仍为 0，不应在报告中宣称 altitude 链路已经打通。

---

## Step 3: 修复后离线 EKF benchmark

运行命令：

```bash
/usr/bin/python3 tools/offline_ekf_benchmark.py \
  --input .auv_data/bags/20260618_223705/rosbag/rosbag_0.mcap \
  --output-dir results/localization/holoocean_full_frame_fixed_20260618 \
  --no-coordinate-transform \
  --truth-frame auto \
  --sensor-frame ned \
  --verbose
```

关键读取信息：

```text
IMU samples:    2981
DVL samples:    278  (frame: world)
Depth samples:  2981
Truth samples:  7160  (topic: /auv/visual/truth_marker)
Duration: 59.8 s
IMU: 49.8 Hz, DVL: 4.6 Hz, Truth: 119.6 Hz
init_pos = [0.0, -0.0, 12.0]
```

指标：

| 算法 | XY RMSE (m) | Z RMSE (m) | 3D RMSE (m) | CEP50 (m) | Max Drift (m) | 平均耗时 (μs/frame) |
|------|------------:|-----------:|------------:|----------:|--------------:|--------------------:|
| Raw DR | 0.044 | 0.030 | 0.053 | 0.034 | 0.086 | 0.6 |
| Std EKF | 0.043 | 0.010 | 0.044 | 0.035 | 0.085 | 56.4 |
| ES-EKF | 0.043 | 0.013 | 0.045 | 0.031 | 0.084 | 60.2 |

生成产物：

```text
results/localization/holoocean_full_frame_fixed_20260618/benchmark_results.md
results/localization/holoocean_full_frame_fixed_20260618/trajectory_xy.png
results/localization/holoocean_full_frame_fixed_20260618/error_time.png
results/localization/holoocean_full_frame_fixed_20260618/error_components.png
results/localization/holoocean_full_frame_fixed_20260618/innovation_residual.png
```

判定：

- Z RMSE 已从旧逻辑的约 24m 降至 0.010-0.030m，坐标语义修复在真实 HoloOcean MCAP 上成立。
- `--no-coordinate-transform` 现在不再意味着“truth 不做语义归一化”，而是只禁用旧的 UE->NED 向量/姿态转换；truth 仍按 `--truth-frame auto` 归一到 benchmark NED。
- 本轮 ES-EKF 3D RMSE 为 0.045m，Raw DR 为 0.053m，改善幅度很小；脚本逻辑断言给出 warning：`ES-EKF RMSE should be significantly lower than DR RMSE - FAILED`。
- 该 warning 不表示坐标修复失败。当前 60s HoloOcean 场景整体漂移很小，Raw DR 本身只有 5cm 量级 3D RMSE，显著性断言不适合作为本场景的通过/失败标准。

---

## Step 4: 决策和闭环状态限制

`launcher.log` 中决策节点持续处于：

```text
mode=IDLE | behavior=StandbyCheck | goal_speed=0.00m/s | goal_depth=0.00m
```

因此本次 MCAP 适合作为：

- HoloOcean 后端传感链路验证；
- ROS2 bridge/topic 完整性验证；
- Foxglove/可视化 topic 录制验证；
- 离线定位 benchmark 坐标语义回归验证。

但不适合作为：

- 自主巡检任务完成率；
- 行为树任务切换效果；
- 控制闭环性能；
- MPC/PID 控制器最终对比。

后续若要形成论文级 HoloOcean 实验，应增加 mission command 或 auto activation，使决策树离开 `StandbyCheck`，并录制有明确轨迹、转弯和干扰的 120s 以上场景。

---

## Step 5: 日志噪声与遗留问题

### P1: `/auv/sensors/altitude` 仍为空

本轮 `rosbag2_recorder` 已订阅 `/auv/sensors/altitude`，但 `ros2 bag info` count 仍为 0。说明前一轮提到的 altitude/forward_sonar 契约问题仍未在完整录制结果中得到验证闭环。

后续建议：

1. 检查 HoloOcean 仿真侧是否持续发布 `rt/auv/sensors/altitude`。
2. 检查 `common.protocol.REQUIRED_BY_TOPIC` 与 bridge topic map 是否同时覆盖 altitude/forward_sonar。
3. 重新短录包确认 `/auv/sensors/altitude` count > 0。

### P1: 关闭阶段 ROS2 异常栈仍存在

实验主流程 exit 0，rosbag 正常停止，但 cleanup 阶段仍出现：

```text
rclpy.executors.ExternalShutdownException
rclpy._rclpy_pybind11.RCLError: failed to initialize wait set: the given context is not valid
```

这些异常发生在统一停止 ROS2 launch/node 时，不影响 MCAP 完整性，但会污染实验日志。正式演示前应优化 launcher 的 shutdown 顺序或在节点 main 中捕获 `ExternalShutdownException`。

### P2: 可视化 topic 体积较大

60s full visual bag 为 495.2 MiB。若扩展到 120s，预计接近 1GB。建议区分两类录制：

- 指标录制：只保留 benchmark 所需传感、状态和少量诊断 topic。
- 展示录制：保留 full visual topic，用于 Foxglove 或视频素材。

---

## 当前结论

本轮 HoloOcean 后端完整基准测试通过了“全栈录制 + MCAP 完整性 + 修复后离线 EKF benchmark”的工程验收。此前 `--no-coordinate-transform` 下约 24m 的 Z 坐标假误差已在本地模拟和真实 60s HoloOcean MCAP 上消除。

当前可引用的结果是：HoloOcean 后端能稳定生成定位 benchmark 所需数据，Z 轴指标恢复到厘米级，可视化 topic 可完整录制并服务毕设展示。当前不可引用为最终闭环性能结论，因为本轮决策状态仍为 `StandbyCheck`，且 altitude topic 与 shutdown 日志仍有待清理。
