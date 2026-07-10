# 正式实验 Z 坐标语义回归测试计划

**日期**: 2026-06-18  
**目的**: 将修复后的 Z 坐标逻辑纳入正式实验跑批入口，并定义从 dry-run 到 HoloOcean/PVS smoke、再到论文级实验前的验收步骤。

**适用范围**:

- `tools/run_thesis_sweep.py`
- `scripts/run_dvl_sweep.sh`
- `scripts/run_mag_sweep.sh`
- `scripts/run_combined_sweep.sh`
- `tools/offline_ekf_benchmark.py`

---

## 1. 已纳入正式脚本的契约

`tools/run_thesis_sweep.py` 现在会在调用 `tools/offline_ekf_benchmark.py` 时显式传递：

```text
--truth-frame <auto|ned|ros-up|ue>
--sensor-frame <auto|ned|ue>
```

新增参数：

```bash
--benchmark-coordinate-transform auto|on|off
--benchmark-truth-frame auto|ned|ros-up|ue
--benchmark-sensor-frame auto|ned|ue
```

默认策略：

| sim backend | `--benchmark-coordinate-transform auto` 行为 | truth frame | sensor frame |
|---|---|---|---|
| `pvs` | 保持旧向量转换开关为 on | `auto` | `auto` |
| `holoocean` | 自动转为 `--no-coordinate-transform` | `auto` | `auto` |

说明：

- `--no-coordinate-transform` 只关闭旧 UE->NED 向量/姿态转换。
- truth 位置仍由 `--truth-frame auto` 归一化到 benchmark NED。
- HoloOcean ROS `PoseStamped` 与 `/auv/visual/truth_marker` 均按 ROS/Foxglove z-up 处理，再转换为 NED 对比域。
- 项目 ROS `/auv/sensors/{imu,dvl,depth}` 默认按 NED 传感语义处理。

---

## 2. C0: 静态与 dry-run 验证

目的：确认正式 sweep CLI 与 manifest 已记录 Z 语义参数，不启动仿真。

命令：

```bash
/usr/bin/python3 -m py_compile \
  tools/offline_ekf_benchmark.py \
  tools/run_thesis_sweep.py \
  tools/aggregate_thesis_sweep.py
```

```bash
/usr/bin/python3 tools/run_thesis_sweep.py \
  --sim-backend holoocean \
  --scenarios baseline \
  --seeds 0 \
  --mpc-modes ua \
  --duration 10 \
  --label zframe_holoocean_dryrun \
  --dry-run
```

验收：

- `py_compile` 全部通过。
- `log/thesis_sweep/*_zframe_holoocean_dryrun/manifest.json` 包含：

```json
"benchmark_coordinate_transform": "auto",
"benchmark_truth_frame": "auto",
"benchmark_sensor_frame": "auto",
"benchmark_frame_args": [
  "--truth-frame",
  "auto",
  "--sensor-frame",
  "auto",
  "--no-coordinate-transform"
]
```

---

## 3. C1: HoloOcean 20s 最小 smoke

目的：低成本验证正式 sweep 入口能在 HoloOcean 后端生成可分析 MCAP，且离线 benchmark 不再出现 24m Z 假误差。

命令：

```bash
env AUV_DATA_ROOT=/home/gwxie/master_work-tmp/AUV_Master_Project/.auv_data \
  SIM_DELAY_S=3 \
  BRAIN_READY_TOPIC=/auv/sensors/imu \
  BRAIN_READY_TIMEOUT_S=60 \
  BAG_FINALIZE_S=20 \
  /usr/bin/python3 tools/run_thesis_sweep.py \
    --sim-backend holoocean \
    --scenarios baseline \
    --seeds 0 \
    --mpc-modes ua \
    --duration 20 \
    --label zframe_holoocean_smoke20 \
    --start-arg=--bridge-backend \
    --start-arg=zenoh_json \
    --start-arg=--skip-layout \
    --benchmark-coordinate-transform auto \
    --benchmark-truth-frame auto \
    --benchmark-sensor-frame auto
```

验收：

- `results.csv` 有一行 `status=ok`。
- 对应 `benchmark_results.md` 中所有算法 `Z RMSE < 0.20 m`。
- 若 `Z RMSE` 接近 `24 m`，立即停止扩展实验，优先检查 truth topic 是否来自 ROS z-up 且是否走到 `--truth-frame auto`。
- `ros2 bag info` 中至少包含：
  - `/auv/sensors/imu`
  - `/auv/sensors/depth`
  - `/auv/sensors/dvl`
  - `/auv/sensors/ground_truth` 或 `/auv/visual/truth_marker`

---

## 4. C2: HoloOcean 60s 修复基线复现

目的：复现本轮已完成的 60s HoloOcean 修复基线，但通过正式 sweep 入口执行。

命令：

```bash
env AUV_DATA_ROOT=/home/gwxie/master_work-tmp/AUV_Master_Project/.auv_data \
  SIM_DELAY_S=3 \
  BRAIN_READY_TOPIC=/auv/sensors/imu \
  BRAIN_READY_TIMEOUT_S=60 \
  BAG_FINALIZE_S=20 \
  /usr/bin/python3 tools/run_thesis_sweep.py \
    --sim-backend holoocean \
    --scenarios baseline \
    --seeds 0 \
    --mpc-modes ua \
    --duration 60 \
    --label zframe_holoocean_baseline60 \
    --start-arg=--bridge-backend \
    --start-arg=zenoh_json \
    --start-arg=--skip-layout
```

验收：

- `results.csv` 中 `status=ok`。
- `z_rmse` 与手工 benchmark 的厘米级结果同量级，参考范围：`0.01-0.05 m`。
- `benchmark_results.md` 中不再出现 `RMSE_Z≈24m`。
- 记录 `run_dir`、`mcap`、`benchmark_dir`，并运行聚合：

```bash
/usr/bin/python3 tools/aggregate_thesis_sweep.py \
  --input log/thesis_sweep/<run>/results.csv \
  --output-dir results/thesis_sweep_aggregates/<run>
```

---

## 5. C3: PVS 回归 smoke

目的：确认新增 HoloOcean 坐标契约不会破坏 PVS 正式 sweep。

命令：

```bash
/usr/bin/python3 tools/run_thesis_sweep.py \
  --sim-backend pvs \
  --scenarios baseline \
  --seeds 0 \
  --mpc-modes ua \
  --duration 20 \
  --label zframe_pvs_regression20
```

验收：

- `results.csv` 有一行 `status=ok`。
- `manifest.json` 中 `benchmark_frame_args` 不包含 `--no-coordinate-transform`，除非显式指定 `--benchmark-coordinate-transform off`。
- `z_rmse` 不出现 24m 量级跳变。

---

## 6. C4: 扩展到正式论文实验前置条件

只有同时满足以下条件，才进入 DVL/Mag/Combined 多 seed 正式实验：

- C1、C2、C3 全部通过。
- HoloOcean 与 PVS 的 `benchmark_results.md` 均显示 Z RMSE 为小量级。
- `results.csv` 和 `manifest.json` 明确记录了 benchmark frame 参数。
- 当前实验目标明确区分：
  - 定位 benchmark：可使用 `run_thesis_sweep.py`。
  - 可视化展示：保留 HoloOcean full visual topic。
  - 控制闭环/行为树性能：需要 mission command 或 auto activation，使状态离开 `StandbyCheck`。

正式扩展命令示例：

```bash
bash scripts/run_dvl_sweep.sh \
  --sim-backend pvs \
  --duration 120 \
  --label zframe_dvl_main
```

```bash
/usr/bin/python3 tools/run_thesis_sweep.py \
  --sim-backend holoocean \
  --scenarios baseline \
  --seeds 0,1,2 \
  --mpc-modes ua \
  --duration 60 \
  --label zframe_holoocean_3seed \
  --start-arg=--bridge-backend \
  --start-arg=zenoh_json \
  --start-arg=--skip-layout
```

---

## 7. 暂停拍板条件

出现任一情况时，不应继续扩展多 seed：

- 任一 HoloOcean run 的 `Z RMSE > 1.0 m`。
- `benchmark_results.md` 再次出现接近 `24 m` 的 Z 误差。
- MCAP 缺 `/auv/sensors/imu`、`/auv/sensors/depth` 或可用 truth topic。
- `results.csv` 显示 `status=bench_failed` 且 bench log 指向 frame/truth 解析问题。
- HoloOcean 目标是闭环性能，但日志仍停留在 `mode=IDLE | behavior=StandbyCheck`。

---

## 8. 当前结论

修复后的 Z 坐标语义已经进入正式 sweep harness。后续通过 `tools/run_thesis_sweep.py` 生成的定位 benchmark 将显式记录 truth/sensor frame 参数，HoloOcean 后端在默认 `auto` 模式下会使用 `--no-coordinate-transform` 并保留 truth 到 NED 的归一化逻辑。

本计划建议先执行 C0-C3，再决定是否把 HoloOcean 后端扩展到 3 seed 或 120s 级正式数据。
