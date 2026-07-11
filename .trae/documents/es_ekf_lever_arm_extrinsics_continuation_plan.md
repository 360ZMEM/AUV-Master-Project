# ES-EKF 杆臂改正与外参评估继续计划

## Summary

本计划用于继续推进 ES-EKF 杆臂改正和传感器外参错位评估。当前工作区已经有第一版实现痕迹：统一外参模块、ES-EKF sensor-frame DVL/Depth 接口、纯脚本 benchmark、仿真标定脚本和单元测试均已存在。但纯脚本 smoke 暴露了关键问题：`calibrated` 模式使用真值外参后，XY RMSE 仍比 `none` 更差，这不满足第一阶段验收标准。

后续执行应先把纯脚本闭环修正到可信，再接 PVS；不能在指标趋势不可信时继续扩展场景和文档结论。

目标闭环：

1. 保持默认零外参行为不变。
2. 明确真值外参与估计外参分离：
   - `sensor_extrinsics_truth` 只用于生成错位传感器观测。
   - `ekf.sensor_extrinsics` 只用于 ES-EKF 观测改正。
3. 纯脚本中验证：
   - 零外参兼容。
   - 错位但不改正会恶化。
   - 离线标定/真值外参改正能恢复或改善性能。
   - online-lite 不发散，且只作为小残差补偿。
4. PVS 后端接入同一套外参配置，默认不开启错位。
5. 输出聚合表和文档，支撑后续论文中“外参误差敏感性、标定收益、在线修正边界”的结论。

## Current State Analysis

### 已存在的相关文件

- `common/sensor_extrinsics.py`
  - 已定义 `SensorExtrinsics`、RPY/矩阵转换、速度杆臂、深度杆臂和小角度误差注入。
  - 坐标约定：`translation_b_m` 是传感器原点相对 `base_link` 的 body-frame 平移；`rotation_b_to_s` 将 base-frame 向量转到 sensor-frame。

- `algorithm/es_ekf.py`
  - 已从配置读取 `sensor_extrinsics`。
  - 已缓存 `_last_gyro_body`。
  - 已新增 `correct_dvl_sensor()` 和 `correct_depth_sensor()`。
  - `correct_dvl_sensor()` 当前使用：
    - `v_base_b = R_nb.T @ self.v`
    - `h = base_velocity_to_sensor(v_base_b, gyro, dvl_extrinsic)`
    - `H_v = R_b_to_s @ R_nb.T`
    - `H_att = R_b_to_s @ (-R_nb.T @ skew(v))`
  - 当前 DVL 线性化没有把姿态误差对 `omega × r` 杆臂速度项的影响纳入 `H_att`，需要在诊断中确认其影响是否是 smoke 失败原因之一。

- `tools/es_ekf_extrinsics_benchmark.py`
  - 已生成确定性轨迹和传感器观测。
  - `calibrated` 已设为估计外参等于真值外参。
  - 当前 smoke 结果中 `calibrated` 仍劣于 `none`：
    - `none` XY RMSE 约 `8.7806`
    - `calibrated` XY RMSE 约 `10.2438`
    - `online_lite` XY RMSE 约 `9.9035`
  - 这说明 benchmark/滤波闭环仍有坐标、噪声、姿态传播、观测更新频率或线性化问题。

- `tools/calibrate_sensor_extrinsics_sim.py`
  - 已实现 DVL rotation Kabsch、DVL lever arm 最小二乘和 depth z offset 的简单估计。
  - 当前估计质量需要在纯脚本闭环稳定后再作为 `calibrated_from_yaml` 模式纳入。

- `tests/test_sensor_extrinsics.py`
  - 已覆盖零外参、`omega × r`、旋转往返和深度杆臂。

- `tests/test_es_ekf_extrinsics.py`
  - 已覆盖零外参等价、匹配 DVL/Depth 外参时单步状态更新更小。
  - 这些测试是局部单步测试，不足以证明多步轨迹闭环正确。

- `sim_holoocean/interfaces/pvs_sim_wrapper.py`
  - 当前 `_build_state()` 输出：
    - `PoseSensor`: base pose。
    - `DVLSensor`: world NED 速度。
    - `IMUSensor`: body acceleration/gyro，经 UE/NED 兼容转换。
    - `DepthSensor`: base depth。
  - 注释中有“DVL速度转换：从body frame到world NED frame”，实际 `DVLSensor` 已不是 sensor-frame/body-frame DVL。

- `sim_holoocean/interfaces/holoocean_physics_bridge.py`
  - 当前 `_build_sensor_packet()` 从 wrapper 状态中取 DVL、IMU、Depth，再发布 Zenoh packets。
  - DVL packet 使用 `KEY_VEL_NED`，语义是 world/NED velocity。
  - 深度直接使用 base depth。
  - 磁场在 base 位置采样。

- `.trae/documents/es_ekf_lever_arm_extrinsics_plan.md`
  - 已有完整首版设计计划。
  - 本文件是继续计划，重点补充当前状态、验收失败后的排查顺序和执行收敛标准。

### 当前关键约束

- 当前轮计划阶段只允许读和写计划文件；执行阶段才能改业务代码、跑测试和跑实验。
- 不回滚现有 dirty worktree 中的无关改动。
- 第一阶段仍不做完整 ES-EKF 状态增广。
- PVS 默认必须保持现有行为：无 `sensor_extrinsics_truth` 时所有传感器等效在 base 原点。
- 纯脚本验收未通过前，不进入 PVS medium/heavy sweep，不写论文结论。

## Proposed Changes

### 1. 修正纯脚本 benchmark 可信性

文件：`tools/es_ekf_extrinsics_benchmark.py`

执行时先做诊断，再做最小修正：

1. 增加 `--debug-first-steps N` 或内部 debug 表，输出前若干步：
   - truth `p/v/q`
   - EKF `p/v/q`
   - DVL truth measurement
   - DVL predicted `h`
   - depth measurement
   - depth predicted `h`
   - innovation 和 NIS
2. 增加或临时使用 `--dvl-noise-std 0 --depth-noise-std 0` 的无噪声 sanity case。
3. 增加 `--profile none --estimation-modes none,calibrated` 的 identity case，要求两者数值一致。
4. 检查并修正以下高概率问题：
   - `estimated_profile()` 对 `calibrated` 返回同一对象，online-lite 修改是否可能污染 truth 或后续模式。
   - 预测步骤中 `predict(traj.acc_body[i], traj.gyro_body[i], dt)` 与真值轨迹的积分时间对齐是否错一拍。
   - `acc_body` 是否应包含或扣除重力，需与 `imu_acc_is_linear=True` 保持一致。
   - DVL 观测频率和 depth 高频更新是否导致 depth 过强、姿态/速度约束不足。
   - `correct_dvl_sensor()` 的观测雅可比是否缺失杆臂项对姿态误差的导数。
5. 对 benchmark 增加 `estimation_mode`：
   - `none`: EKF 外参全零。
   - `calibrated`: EKF 外参等于真值外参。
   - `calibrated_from_yaml`: 从标定工具输出 YAML 读取估计外参。
   - `online_lite`: 从小残差初值开始，以限幅方式靠近真值。
6. `online_lite` 不应直接每秒无条件融合真值。执行阶段改成“模拟在线修正器”的明确诊断输出：
   - 当前先允许 oracle-style 慢速靠近真值用于上限评估，但报告字段必须标明 `online_oracle=true`。
   - 真正 innovation-driven online 修正作为后续扩展，不混入第一轮论文结论。

验收标准：

- 无噪声、truth=estimate 的 `calibrated` 轨迹误差应接近滤波数值误差下限。
- `light` profile 下，`calibrated` 的 `xy_rmse` 或 `rmse_3d` 必须优于 `none`。
- 多 seed 下趋势稳定，不依赖单 seed 偶然性。

### 2. 收紧 ES-EKF 外参观测接口

文件：`algorithm/es_ekf.py`

执行阶段应在不破坏现有 API 的前提下做以下检查和必要修正：

1. 保留：
   - `correct_dvl()`
   - `correct_dvl_world()`
   - `correct_depth()`
   - `correct_dvl_sensor()`
   - `correct_depth_sensor()`
2. 为 `correct_dvl_sensor()` 增加更严格的单元测试：
   - 给定同一状态和同一估计外参，`z=h` 时 innovation 近零，多步 predict/correct 不应比 `none` 更差。
   - 非零 yaw/pitch/roll 下的 sensor-frame DVL 预测必须与 `common.sensor_extrinsics.base_velocity_to_sensor()` 一致。
3. 评估并修正 DVL sensor Jacobian：
   - 现有 `H_att` 只覆盖 `R_nb.T @ v` 对姿态误差的影响。
   - 如果把杆臂项写为 `R_b_to_s @ (R_nb.T v + omega × r)`，则姿态误差对 `omega × r` 可近似忽略，但 `omega` 使用测量值时这项不是状态函数。
   - 若 smoke 失败来自过强姿态更新，应优先降低/限制姿态列，或用有限差分单元测试确认符号。
4. `correct_depth_sensor()` 的 position Jacobian 当前写为 `[0,0,-1]`，需确认内部坐标是 ROS-up；对于 `h=-p_sensor.z` 该项合理。姿态项符号需用有限差分验证。
5. 不在本轮增广外参状态，不引入大范围协方差结构变化。

验收标准：

- `tests/test_es_ekf_extrinsics.py` 覆盖多姿态和有限差分符号。
- 零外参路径与原行为一致。
- sensor-frame 接口只在显式调用时影响结果。

### 3. 加强仿真标定工具与 benchmark 联动

文件：`tools/calibrate_sensor_extrinsics_sim.py`

执行阶段调整：

1. 输出 YAML 字段直接兼容 `ekf.sensor_extrinsics`：

```yaml
sensor_extrinsics:
  dvl:
    translation_b_m: [...]
    rotation_rpy_deg: [...]
  depth:
    translation_b_m: [...]
    rotation_rpy_deg: [...]
metadata:
  profile: light
  dvl_translation_error_m: ...
  dvl_rotation_error_deg: ...
```

2. 修正 DVL lever arm 最小二乘符号：
   - 模型是 `v_sensor_b - v_base_b = omega × r = -skew(omega) @ r`。
   - 保持该符号，并用无噪声测试验证能恢复真值可观部分。
3. depth 估计不要只返回 `z` offset 的均值，至少记录该估计的可观性限制：
   - 纯 yaw 轨迹下 depth 的 x/y 杆臂不可观。
   - 第一阶段只评估 depth z 主项。
4. benchmark 支持 `--estimated-extrinsics-yaml`，在 `calibrated_from_yaml` 模式下读取标定结果。

验收标准：

- 无噪声 light profile 下，DVL rotation error 和 depth z error 接近零或在明确阈值内。
- 有噪声 3 seed 下，`calibrated_from_yaml` 至少优于 `none`，不要求优于 oracle `calibrated`。

### 4. PVS 后端接入传感器错位

文件：

- `sim_holoocean/interfaces/pvs_sim_wrapper.py`
- `sim_holoocean/interfaces/holoocean_physics_bridge.py`
- `sim_holoocean/interfaces/mock_amd_server.py`，仅当实际协议路径需要补透传时修改
- `common/sensor_extrinsics.py`

配置结构：

```yaml
sensor_extrinsics_truth:
  dvl:
    translation_b_m: [0.05, 0.02, -0.01]
    rotation_rpy_deg: [0.2, -0.1, 0.5]
  depth:
    translation_b_m: [0.04, 0.0, -0.05]
    rotation_rpy_deg: [0.0, 0.0, 0.0]
  imu:
    translation_b_m: [0.02, 0.0, 0.01]
    rotation_rpy_deg: [0.1, 0.0, -0.1]

perception:
  dvl_measurement_frame: world
```

默认：

- `sensor_extrinsics_truth` 缺省时等价全零。
- `dvl_measurement_frame` 缺省继续为 `world`，保持当前 `KEY_VEL_NED` 语义。

执行策略：

1. 在 `PVSSimWrapper._build_state()` 保留 base truth pose，不污染 `PoseSensor`。
2. 对 depth：
   - 使用 `depth_at_sensor(base_position, R_nb, depth_truth)` 生成 `DepthSensor`。
3. 对 IMU：
   - 第一阶段只启用旋转外参，把 base-frame accel/gyro 转成 sensor-frame 再交给 bridge。
   - IMU 平移杆臂加速度项需要角加速度，先作为可选开关，不默认开启。
4. 对 DVL：
   - 如果 `dvl_measurement_frame=world`，先保持现有 world velocity 语义，只在 metadata 中记录 truth extrinsics，不改变旧路径。
   - 如果 `dvl_measurement_frame=sensor`，使用 `base_velocity_to_sensor(v_base_b, omega_b, dvl_truth)` 输出 sensor-frame，并确保后续 localization/offline benchmark 使用 `correct_dvl_sensor()`。
5. 在 `holoocean_physics_bridge.py` 中避免二次坐标转换：
   - 当前 `extract_body_velocity()` 和 `body_vector_ue_to_ned()` 假设 wrapper DVL 是 UE/body 风格，但 PVS 实际给的是 world NED。执行阶段需要先把 DVL frame 语义理清，再接 sensor-frame 模式。

验收标准：

- baseline 场景不带 `sensor_extrinsics_truth` 时，PVS smoke 仍 `ok`。
- `extrinsics_light` 场景能生成 MCAP，IMU/DVL/Depth/Truth topic 齐全。
- 不破坏现有 `run_thesis_sweep.py` 命令契约。

### 5. Scenario YAML 与 sweep

文件：

- `scenarios/scenario_extrinsics_light.yaml`
- `scenarios/scenario_extrinsics_medium.yaml`
- `scenarios/scenario_extrinsics_heavy.yaml`
- `scenarios/scenario_extrinsics_calibrated.yaml`，可选
- `scenarios/scenario_extrinsics_online.yaml`，可选

设计：

- `light`: 平移 5 cm 级，旋转 0.5 deg 级。
- `medium`: 平移 10-20 cm，旋转 1-2 deg。
- `heavy`: 平移 30 cm，旋转 3-5 deg。
- 场景 YAML 只写 truth 外参和必要 perception 开关。
- EKF 估计外参通过 benchmark config 或工具参数传入，避免 scenario 同时承担 truth 和 estimate 两种语义。

第一轮命令：

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios extrinsics_light \
  --seeds 0 \
  --mpc-modes ua \
  --duration 30 \
  --label extrinsics_light_smoke
```

通过后再扩展：

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios extrinsics_light,extrinsics_medium,extrinsics_heavy \
  --seeds 0,1,2 \
  --mpc-modes ua \
  --duration 60 \
  --label extrinsics_main_3seed
```

### 6. 聚合工具

文件：`tools/aggregate_extrinsics_benchmark.py`

输入：

- 纯脚本 `results.csv`
- 可选 PVS sweep `results.csv`

输出：

- `extrinsics_metrics_by_run.csv`
- `extrinsics_summary_by_profile_mode.csv`
- `extrinsics_status_counts.csv`
- `extrinsics_aggregate_report.md`

核心字段：

- `profile`
- `estimation_mode`
- `seed`
- `xy_rmse`
- `z_rmse`
- `rmse_3d`
- `cep50`
- `max_drift`
- `dvl_nis_mean`
- `depth_nis_mean`
- `extrinsic_translation_error_m`
- `extrinsic_rotation_error_deg`
- `improvement_vs_none_pct`
- `online_correction_delta_norm`

验收标准：

- 对 smoke 和 main 结果都能运行。
- report 明确列出每个 profile 下 calibrated/online_lite 相对 none 的改善率。
- 缺失字段时输出 `NaN`，不崩溃。

### 7. 文档回填

文件：

- `docs/experiment/experiment_gap_conduct_plan.md`
  - 增加 ES-EKF 杆臂/外参阶段的执行记录、命令、结果路径和当前结论边界。

- `docs/thesis/02_es_ekf_validation.md`
  - 增加外参误差敏感性实验说明。

- `docs/thesis/paper/03_state_estimation.md`
  - 增加 DVL/Depth 杆臂改正公式：
    - `v_s = R_b_to_s (R_nb^T v_n + omega_b × r_b_s)`
    - `d_s = -(p_n + R_nb r_b_s)_z`

- `docs/thesis/paper/05_experiments_and_discussion.md`
  - 增加结果表和讨论，区分：
    - 未改正外参误差影响。
    - 离线标定收益。
    - online-lite 的有限收益和风险。

- 可选新增 `docs/user-guide/12_es_ekf_extrinsics.md`
  - 只有当命令稳定、输出格式稳定后再新增用户指南。
  - 不把研究中间态包装成 SOP。

## Assumptions & Decisions

- 第一轮执行顺序：纯脚本 smoke 修正 -> 标定联动 -> PVS light smoke -> 3 seed sweep -> 聚合和文档。
- 在线估计第一阶段采用“离线标定后轻量在线”，不做完整状态增广。
- `online_lite` 第一轮只作为小残差修正或 oracle upper bound，必须在结果中标注语义。
- IMU 平移杆臂一阶段不作为主线默认启用；IMU 旋转外参先接入。
- DVL frame 语义必须先理清：
  - 当前 PVS wrapper 输出 world NED velocity。
  - ES-EKF sensor-frame 改正需要显式 `dvl_measurement_frame=sensor`。
- 外参全零时，所有 baseline 和旧场景必须保持兼容。

## Verification Steps

### 只读前置确认

执行阶段开始前先读本文件和首版计划：

```bash
sed -n '1,260p' .trae/documents/es_ekf_lever_arm_extrinsics_continuation_plan.md
sed -n '1,260p' .trae/documents/es_ekf_lever_arm_extrinsics_plan.md
```

### 静态检查

```bash
python3 -m py_compile \
  common/sensor_extrinsics.py \
  algorithm/es_ekf.py \
  tools/es_ekf_extrinsics_benchmark.py \
  tools/calibrate_sensor_extrinsics_sim.py \
  tools/aggregate_extrinsics_benchmark.py
```

### 单元测试

```bash
pytest -q \
  tests/test_sensor_extrinsics.py \
  tests/test_es_ekf_extrinsics.py
```

新增或加强测试后要求：

- identity extrinsics 等价。
- DVL sensor-frame 观测预测在非零姿态下正确。
- depth sensor 杆臂 Jacobian 通过有限差分。
- 匹配真值外参的多步 synthetic case 不劣于不改正。

### 纯脚本 smoke

先跑无噪声 sanity：

```bash
python3 tools/es_ekf_extrinsics_benchmark.py \
  --duration 30 \
  --seeds 0 \
  --true-profile light \
  --estimation-modes none,calibrated,online_lite \
  --dvl-noise-std 0 \
  --depth-noise-std 0 \
  --output-dir results/es_ekf_extrinsics/smoke_no_noise
```

再跑默认噪声 smoke：

```bash
python3 tools/es_ekf_extrinsics_benchmark.py \
  --duration 30 \
  --seeds 0 \
  --true-profile light \
  --estimation-modes none,calibrated,online_lite \
  --output-dir results/es_ekf_extrinsics/smoke
```

验收：

- `calibrated` 的 `xy_rmse` 或 `rmse_3d` 优于 `none`。
- `online_lite` 不发散。
- `summary_by_error_level.csv` 和 `extrinsics_report.md` 生成。

### 标定联动 smoke

```bash
python3 tools/calibrate_sensor_extrinsics_sim.py \
  --profile light \
  --seed 0 \
  --duration 120 \
  --output results/es_ekf_extrinsics/smoke/estimated_extrinsics.yaml
```

随后：

```bash
python3 tools/es_ekf_extrinsics_benchmark.py \
  --duration 60 \
  --seeds 0 \
  --true-profile light \
  --estimation-modes none,calibrated,calibrated_from_yaml \
  --estimated-extrinsics-yaml results/es_ekf_extrinsics/smoke/estimated_extrinsics.yaml \
  --output-dir results/es_ekf_extrinsics/calibration_smoke
```

验收：

- `calibrated_from_yaml` 优于 `none`。
- 若不优于 `none`，报告必须保留标定误差和不可观性说明，不进入 PVS 扩展。

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

- 两个 sweep 的 `results.csv` 中 status 为 `ok`。
- baseline 零外参不出现数量级回退。
- extrinsics light 的 MCAP 包含 IMU/DVL/Depth/Truth。

### 聚合与文档验收

```bash
python3 tools/aggregate_extrinsics_benchmark.py \
  --results results/es_ekf_extrinsics/main_3seed/results.csv \
  --output-dir results/es_ekf_extrinsics/main_3seed_aggregate
```

验收：

- 聚合 CSV 和 Markdown 报告生成。
- conduct plan、thesis validation、paper state-estimation 和 experiments 文档都回填。
- 文档中明确当前结论边界，不把 online-lite 写成完整在线标定。

## Risks & Mitigations

- 风险：纯脚本 calibrated 仍不优于 none。
  - 缓解：停留在纯脚本诊断，优先检查坐标、IMU 输入、DVL/Depth H 矩阵和时间对齐，不进入 PVS。

- 风险：PVS DVL frame 语义混乱。
  - 缓解：默认保留 world NED；sensor-frame 只在显式配置时启用，并同步 offline/localization 调用路径。

- 风险：IMU 平移杆臂需要角加速度，PVS/ES-EKF 当前没有稳定来源。
  - 缓解：第一轮只默认启用 IMU 旋转外参，平移杆臂作为可选实验项记录。

- 风险：online-lite 误把传感器故障学成外参。
  - 缓解：第一轮只做小残差、低速、限幅、带 NIS gate 的修正；结果报告标注边界。

- 风险：文档结论过度。
  - 缓解：所有报告同时列出 no-correction、calibrated、calibrated_from_yaml、online_lite，并说明每种模式的含义。
