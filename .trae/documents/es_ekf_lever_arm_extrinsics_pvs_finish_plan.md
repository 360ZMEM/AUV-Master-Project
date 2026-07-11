# ES-EKF 杆臂外参 PVS 收口计划

## Summary

本计划用于继续完成 ES-EKF 杆臂改正与传感器外参错位评估的收口阶段。当前仓库中已经存在外参核心模块、ES-EKF sensor-frame DVL/Depth 接口、纯脚本 benchmark、仿真标定工具、PVS truth 外参接入、extrinsics 场景和聚合工具。只读核查显示，纯脚本 light smoke 已经满足第一阶段趋势：`calibrated` 和 `online_lite` 均略优于 `none`，标定 YAML 聚合也优于 `none`。

当前阻塞点不再是纯脚本趋势，而是 PVS `extrinsics_light` smoke 的 MCAP 录制为空。`offline_ekf_benchmark` 失败日志显示读取 `/auv_data/bags/20260613_161921/rosbag/rosbag_0.mcap` 时触发 `mcap.exceptions.EndOfFile`，该文件大小为 `0` 字节。因此执行阶段应先修复 PVS sweep 的录包有效性和 benchmark 防御，再做外参 PVS 指标扩展与文档回填。

## Current State Analysis

### 已确认的实现状态

- `common/sensor_extrinsics.py`
  - 已定义 `SensorExtrinsics`、RPY/矩阵转换、`base_velocity_to_sensor()`、`sensor_velocity_to_base()`、`base_position_to_sensor_world()`、`depth_at_sensor()` 和小角度扰动。
  - 默认 identity 外参保持零偏移行为。

- `algorithm/es_ekf.py`
  - 已读取 `sensor_extrinsics`。
  - 已缓存 `_last_gyro_body`。
  - 已提供 `correct_dvl_sensor()` 和 `correct_depth_sensor()`。
  - 只读核查到当前 `correct_depth_sensor()` 使用 `depth_at_sensor()`，姿态雅可比使用 `e_z @ skew(lever_world)`。

- `tools/es_ekf_extrinsics_benchmark.py`
  - 已支持 `none`、`calibrated`、`online_lite`、`calibrated_from_yaml`。
  - 已支持 `--estimated-extrinsics-yaml`、`--debug-first-steps`、DVL/depth 噪声配置。
  - 当前 `results/es_ekf_extrinsics/smoke/summary_by_error_level.csv`：
    - `none`: `xy_rmse=2.2571`, `z_rmse=0.0495`, `rmse_3d=2.2576`
    - `calibrated`: `xy_rmse=2.1947`, `z_rmse=0.0030`, `rmse_3d=2.1947`
    - `online_lite`: `xy_rmse=2.1900`, `z_rmse=0.0031`, `rmse_3d=2.1900`

- `tools/calibrate_sensor_extrinsics_sim.py`
  - 已输出兼容 `sensor_extrinsics` 的 YAML。
  - 已使用 dedicated multi-axis calibration motion。
  - `results/es_ekf_extrinsics/calibration_smoke_aggregate/extrinsics_aggregate_report.md` 显示：
    - `calibrated` 相对 `none` 改善约 `4.3793%`
    - `calibrated_from_yaml` 相对 `none` 改善约 `1.2390%`

- `sim_holoocean/apps/run_zenoh_bridge.py`
  - 已通过 `AUV_SCENARIO_FILE` 合入 scenario override。
  - 已支持 `sensor_extrinsics_truth`、`perception`、`flow`、`chaos` override。

- `sim_holoocean/interfaces/pvs_sim_wrapper.py`
  - 已读取 `sensor_extrinsics_truth`。
  - 已按 `perception.dvl_measurement_frame` 输出 world 或 sensor DVL。
  - 已对 depth 使用传感器位置计算深度。
  - 默认 `dvl_measurement_frame=world`，保持旧路径语义。

- `sim_holoocean/interfaces/holoocean_physics_bridge.py` 与 `sim_holoocean/interfaces/mock_amd_server.py`
  - 已读取 `DVLFrame`，避免 world DVL 被二次 body 转换。

- `scenarios/scenario_extrinsics_light.yaml`
  - 已定义 light truth 外参和 `perception.dvl_measurement_frame: world`。

- `tools/aggregate_extrinsics_benchmark.py`
  - 已能聚合纯脚本 `results.csv` 并输出 by-run、summary、status 和 Markdown 报告。

### 当前失败事实

PVS `extrinsics_light` smoke 最近结果：

```csv
scenario,status,mcap,error
extrinsics_light,bench_failed,/auv_data/bags/20260613_161921/rosbag/rosbag_0.mcap,offline_ekf_benchmark exit=1
```

对应 benchmark log：

```text
mcap.exceptions.EndOfFile
```

对应 MCAP 文件：

```text
-rw-r--r-- 1 root root 0 Jun 13 16:19 /auv_data/bags/20260613_161921/rosbag/rosbag_0.mcap
```

结论：PVS 场景启动和 sweep 写表完成，但 rosbag 未写入有效 MCAP。下一步优先检查录制进程生命周期、topic 是否实际发布、run 结束时是否过早进入 benchmark、以及 `run_thesis_sweep.py` 对空 MCAP 的错误分类。

### 当前约束

- 当前仍处于计划模式，除本计划文件外不修改代码、不运行写入型实验。
- 执行阶段不得回滚工作树中用户或此前任务产生的无关改动。
- 默认无外参配置必须保持旧行为。
- `online_lite` 仍按 oracle-style upper-bound 或小残差修正标注，不能写成完整在线标定。
- PVS 指标结论必须建立在非空 MCAP 和成功 offline benchmark 上。

## Proposed Changes

### 1. 先修复 PVS 录包有效性

文件：

- `tools/run_thesis_sweep.py`
- `scripts/start_experiment.sh`
- 必要时检查 ROS2 launch/record 相关脚本，不先改 ES-EKF 主逻辑

执行步骤：

1. 读取 `tools/run_thesis_sweep.py` 中启动实验、等待结束、定位 MCAP、调用 `offline_ekf_benchmark.py` 的流程。
2. 读取 `scripts/start_experiment.sh` 中 rosbag record 的启动和退出清理逻辑。
3. 对最近失败 run 的主日志做只读定位：
   - `log/thesis_sweep/20260613_161921_extrinsics_light_smoke/logs/extrinsics_light__seed0__ua.log`
   - 查找 rosbag record 启动、topic discovery、进程退出、signal trap、timeout、kill 顺序。
4. 执行阶段做最小修正：
   - 若 benchmark 在 rosbag flush 前启动，则在实验脚本或 sweep 中等待 MCAP 文件大小稳定且大于 0。
   - 若 rosbag 进程被过早杀掉，则调整停止顺序，先给 recorder 软退出和短等待，再清理仿真/bridge。
   - 若 topics 未发现，则在脚本中增加启动前 topic wait 或记录失败原因。
5. 在 `run_thesis_sweep.py` 中增加空 MCAP 防御：
   - MCAP 不存在或大小为 0 时，状态写为 `bag_empty` 或 `bench_failed` 的明确错误，不直接调用 offline benchmark。
   - `results.csv` 保留 `mcap`、`run_dir`、`error`，方便后续聚合排查。

验收标准：

- 同样的 `extrinsics_light` smoke 不再产生 0 字节 MCAP。
- 如果录包失败，`results.csv` 明确写出 `bag_empty` 或等价可诊断状态。
- 不破坏已有 baseline/其他 scenario 的命令契约。

### 2. 回归 baseline PVS，排除外参场景特异问题

文件：

- `tools/run_thesis_sweep.py`
- `scenarios/scenario_baseline.yaml`
- `scenarios/scenario_extrinsics_light.yaml`

执行步骤：

1. 先运行 baseline UA smoke：

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline \
  --seeds 0 \
  --mpc-modes ua \
  --duration 30 \
  --label extrinsics_regression_baseline
```

2. 再运行 extrinsics light UA smoke：

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios extrinsics_light \
  --seeds 0 \
  --mpc-modes ua \
  --duration 30 \
  --label extrinsics_light_smoke
```

3. 对两个 run 检查：
   - `results.csv` 状态。
   - MCAP 文件大小。
   - benchmark 输出是否生成。
   - log 中是否有 bridge/scenario override 异常。

验收标准：

- baseline smoke `status=ok`。
- extrinsics light smoke 至少能成功录包并完成 offline benchmark。
- 若 baseline 也空包，则判定为通用录包生命周期问题；若只有 extrinsics light 空包，再聚焦 scenario override/PVS wrapper。

### 3. 验证 PVS 外参语义和默认兼容

文件：

- `sim_holoocean/interfaces/pvs_sim_wrapper.py`
- `sim_holoocean/interfaces/holoocean_physics_bridge.py`
- `sim_holoocean/interfaces/mock_amd_server.py`
- `sim_holoocean/apps/run_zenoh_bridge.py`

执行步骤：

1. 为 PVS wrapper 做轻量单元或脚本级 sanity：
   - 无 `sensor_extrinsics_truth` 时 depth 与旧 base depth 一致。
   - `sensor_extrinsics_truth.depth.translation_b_m` 非零时 depth 按传感器位置变化。
   - `dvl_measurement_frame=world` 时 DVL 继续输出 world NED。
   - `dvl_measurement_frame=sensor` 时 DVL 输出 sensor-frame，并带 `DVLFrame=sensor`。
2. 检查 bridge 侧转换：
   - `DVLFrame=world` 时不做 body-to-NED 二次转换。
   - `DVLFrame=sensor` 时仍按 sensor/body vector 转换，后续使用方必须显式调用 sensor-frame 修正路径。
3. 对 `scenario_extrinsics_light.yaml` 保持 `dvl_measurement_frame: world`，把第一轮 PVS 重点放在 depth/IMU/metadata 外参错位，不强行改 DVL 数据语义。

验收标准：

- 默认 baseline 行为不变。
- light/medium/heavy 场景能被 `AUV_SCENARIO_FILE` 合入 bridge config。
- DVL frame 语义在代码和文档里一致。

### 4. 补齐 offline benchmark 与 EKF 外参配置联动

文件：

- `tools/offline_ekf_benchmark.py`
- 可能涉及 localization/benchmark EKF config 加载路径
- `tools/es_ekf_extrinsics_benchmark.py` 仅在需要保持字段一致时修改

执行步骤：

1. 读取 `offline_ekf_benchmark.py` 的 EKF 初始化配置来源，确认是否已有命令行或 YAML 入口可传入 `sensor_extrinsics`。
2. 如果没有，新增最小参数：
   - `--estimated-extrinsics-yaml <path>`，读取其中 `sensor_extrinsics` 并合入 EKF config。
   - 或 `--ekf-config-yaml <path>`，优先复用已有 config 风格。
3. 保持 truth 和 estimate 分离：
   - PVS scenario 只表达 `sensor_extrinsics_truth`。
   - offline benchmark 只表达 `ekf.sensor_extrinsics` 或 estimated YAML。
4. 第一轮 PVS metric 可先评估：
   - `none`: 不传 estimated extrinsics。
   - `calibrated_from_yaml`: 传仿真标定工具输出 YAML。
   - oracle `calibrated` 仅在明确生成真值 estimate YAML 时使用。

验收标准：

- PVS offline benchmark 能在同一 MCAP 上跑不同估计外参配置。
- `results.csv` 或独立 extrinsics aggregate 能区分 `estimation_mode`。
- 旧 benchmark 命令不传外参参数时行为不变。

### 5. 扩展外参主实验

文件：

- `scenarios/scenario_extrinsics_light.yaml`
- `scenarios/scenario_extrinsics_medium.yaml`
- `scenarios/scenario_extrinsics_heavy.yaml`
- `tools/run_thesis_sweep.py`
- `tools/aggregate_extrinsics_benchmark.py`

执行步骤：

1. PVS light smoke 通过后，执行短主实验：

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios extrinsics_light,extrinsics_medium,extrinsics_heavy \
  --seeds 0,1,2 \
  --mpc-modes ua \
  --duration 60 \
  --label extrinsics_main_3seed
```

2. 如果 PVS 外参不同估计模式需要多次 offline benchmark，则采用命令友好的后处理工具，而不是重复仿真：
   - 一次 PVS sweep 生成 truth-misaligned MCAP。
   - 后处理对每个 MCAP 运行 `none/calibrated_from_yaml/calibrated` 多个 offline EKF 配置。
3. 聚合输出：
   - `extrinsics_metrics_by_run.csv`
   - `extrinsics_summary_by_profile_mode.csv`
   - `extrinsics_status_counts.csv`
   - `extrinsics_aggregate_report.md`

验收标准：

- 3 profile × 3 seed 至少多数成功；失败 run 有明确状态和 log。
- 聚合报告按 profile/mode 给出 RMSE、CEP50、max drift、改善率。
- 结果足够支撑“外参错位影响”和“标定可恢复部分性能”的有限结论。

### 6. 文档回填与结论边界

文件：

- `docs/experiment/experiment_gap_conduct_plan.md`
- `docs/thesis/02_es_ekf_validation.md`
- `docs/thesis/paper/03_state_estimation.md`
- `docs/thesis/paper/05_experiments_and_discussion.md`
- 可选：`docs/user-guide/12_es_ekf_extrinsics.md`

执行步骤：

1. 在 conduct plan 中补充：
   - 纯脚本 smoke 结果路径。
   - 标定 YAML 联动结果路径。
   - PVS smoke 和主实验命令。
   - PVS 空包问题的修复记录。
2. 在 thesis validation 中补充：
   - `sensor_extrinsics_truth` 与 `ekf.sensor_extrinsics` 的语义分离。
   - pure-script 与 PVS 两类证据。
3. 在 paper state-estimation 中补充公式：

```text
v_s = R_b_to_s (R_nb^T v_n + omega_b x r_b_s)
d_s = -(p_n + R_nb r_b_s)_z
```

4. 在 experiments/discussion 中写结论边界：
   - `none` 表示估计器忽略安装错位。
   - `calibrated_from_yaml` 表示离线标定估计外参。
   - `online_lite` 当前是上限/小残差修正，不等同完整在线外参状态增广。
5. 只有当命令和输出稳定后，才新增 user-guide；否则只回填 experiment/thesis 文档。

验收标准：

- 文档中所有路径和数值来自实际输出。
- 不把 PVS 未完成结果写成已完成。
- 不把 `online_lite` 夸写成完整在线标定。

## Assumptions & Decisions

- 当前执行优先级：PVS 录包有效性 > baseline 回归 > extrinsics light smoke > offline benchmark 外参配置联动 > 3 seed 主实验 > 文档。
- 纯脚本侧已通过最小趋势验收，不再作为主要阻塞；仅保留 py_compile、pytest、smoke 作为回归。
- 第一轮 PVS 保持 `dvl_measurement_frame=world`，避免 DVL sensor-frame 语义同时扩大变量；sensor-frame DVL 作为显式配置和单元测试验证。
- 不进行完整 ES-EKF 外参状态增广。
- 不回滚工作树中的无关改动。

## Verification Steps

### 静态检查

```bash
python3 -m py_compile \
  common/sensor_extrinsics.py \
  algorithm/es_ekf.py \
  tools/es_ekf_extrinsics_benchmark.py \
  tools/calibrate_sensor_extrinsics_sim.py \
  tools/aggregate_extrinsics_benchmark.py \
  tools/offline_ekf_benchmark.py \
  tools/run_thesis_sweep.py
```

### 单元测试

```bash
python3 -m pytest -q \
  tests/test_sensor_extrinsics.py \
  tests/test_es_ekf_extrinsics.py
```

### 纯脚本回归

```bash
python3 tools/es_ekf_extrinsics_benchmark.py \
  --duration 30 \
  --seeds 0 \
  --true-profile light \
  --estimation-modes none,calibrated,online_lite \
  --output-dir results/es_ekf_extrinsics/smoke
```

验收：`calibrated` 的 `rmse_3d` 或 `xy_rmse` 优于 `none`，`online_lite` 不发散。

### 标定联动回归

```bash
python3 tools/calibrate_sensor_extrinsics_sim.py \
  --profile light \
  --seed 0 \
  --duration 120 \
  --output results/es_ekf_extrinsics/smoke/estimated_extrinsics.yaml
```

```bash
python3 tools/es_ekf_extrinsics_benchmark.py \
  --duration 60 \
  --seeds 0 \
  --true-profile light \
  --estimation-modes none,calibrated,calibrated_from_yaml \
  --estimated-extrinsics-yaml results/es_ekf_extrinsics/smoke/estimated_extrinsics.yaml \
  --output-dir results/es_ekf_extrinsics/calibration_smoke
```

验收：`calibrated_from_yaml` 相对 `none` 有改善或报告清楚说明标定不可观/误差来源。

### PVS smoke

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline \
  --seeds 0 \
  --mpc-modes ua \
  --duration 30 \
  --label extrinsics_regression_baseline
```

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios extrinsics_light \
  --seeds 0 \
  --mpc-modes ua \
  --duration 30 \
  --label extrinsics_light_smoke
```

验收：

- MCAP 文件存在且大小大于 0。
- `offline_ekf_benchmark.py` 不再因 `EndOfFile` 失败。
- `results.csv` 状态为 `ok`，或失败状态具备可诊断原因。

### PVS 主实验与聚合

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios extrinsics_light,extrinsics_medium,extrinsics_heavy \
  --seeds 0,1,2 \
  --mpc-modes ua \
  --duration 60 \
  --label extrinsics_main_3seed
```

```bash
python3 tools/aggregate_extrinsics_benchmark.py \
  --results results/es_ekf_extrinsics/main_3seed/results.csv \
  --output-dir results/es_ekf_extrinsics/main_3seed_aggregate
```

最终验收：

- PVS 和纯脚本都有可追溯结果。
- 聚合报告生成。
- 文档回填完成，并且结论边界准确。

