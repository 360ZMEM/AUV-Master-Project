# ES-EKF 杆臂改正与传感器外参评估计划

## Summary

目标是在现有 ES-EKF/PVS 实验链路中加入“传感器安装错位”这一关键因素：IMU、DVL、深度计、磁传感器等相对 `base_link` 存在平移杆臂和旋转外参。第一阶段不追求从完全无知开始的完整状态增广，而是：

1. 先用纯脚本建立可快速 sweep 的真值外参、估计外参、标定误差和 ES-EKF 性能闭环。
2. 再把同一外参配置接入 PVS 传感器生成/录包/benchmark 链路。
3. 离线标定先给出外参初值，随后实现轻量在线修正或慢速自适应估计，不把外参扩进完整 ES-EKF 主状态。
4. 输出对比表：无错位、错位但不改正、错位且离线标定改正、错位且轻量在线修正。
5. 回填实验和论文文档，明确 ES-EKF 对外参误差的敏感性、标定收益和在线修正边界。

## Current State Analysis

### 已确认的代码现状

- `algorithm/es_ekf.py`
  - ES-EKF 状态为位置、速度、姿态四元数、加速度零偏、陀螺零偏，误差状态 15 维。
  - 现有观测接口：
    - `predict(imu_acc_body, imu_gyro_body, dt)`
    - `correct_dvl(dvl_vel_body)`
    - `correct_dvl_world(dvl_vel_world)`
    - `correct_depth(depth_m)`
    - `correct_gps(gps_xy)`
    - `correct_mag(mag_body_t, ...)`
  - 当前已存在 `mag_lever_arm_b` 配置占位，但只用于磁场弱观测的注释/预留，没有形成统一外参模型。
  - DVL、深度、IMU 默认等效安装在 `base_link` 原点，当前没有统一的杆臂/旋转外参修正。

- `brain_linux/src/auv_localization/auv_localization/auv_localization_node.py`
  - 已声明并发布静态 TF 偏移参数：
    - `imu_frame_offset_xyz`
    - `dvl_frame_offset_xyz`
    - `depth_frame_offset_xyz`
    - `camera_frame_offset_xyz`
    - `sonar_frame_offset_xyz`
  - 这些参数当前主要用于 TF 展示，没有参与 ES-EKF 观测模型。
  - localization node 从 `brain_linux/config/params.yaml` 的 `ekf:` 段加载 ES-EKF 配置。

- `tools/offline_ekf_benchmark.py`
  - 离线 benchmark 从 MCAP 读取 IMU、DVL、Depth、Truth，分别喂 Raw DR、Std EKF、ES-EKF。
  - ES-EKF wrapper `EseKfEngine` 直接调用 `correct_dvl_world()` 和 `correct_depth()`。
  - 当前命令支持 `--ekf-config`，适合做“估计外参配置”切换。
  - 目前不支持对 bag 传感器观测做“真值外参错位”重放注入，也不支持外参误差 sweep。

- `sim_holoocean/interfaces/pvs_sim_wrapper.py`
  - PVS wrapper `_build_state()` 当前返回理想同点传感器：
    - `PoseSensor`
    - `DVLSensor`
    - `IMUSensor`
    - `DepthSensor`
  - DVL 当前发布 world NED 速度，IMU 发布 UE/body 风格加速度和角速度，Depth 发布正向下深度。
  - 当前没有读取 scenario YAML 中的传感器外参字段。

- `sim_holoocean/interfaces/holoocean_physics_bridge.py`
  - 负责从仿真状态生成 Zenoh sensor packets，已有噪声、DVL 降采样、磁场、声纳等感知模型。
  - 是接入“PVS/HoloOcean 传感器真实错位”的合适位置之一。

- `sim_holoocean/interfaces/mock_amd_server.py`
  - protocol_udp/PVS 路径中会将仿真传感器快照编码成上行协议。
  - 已有 chaos 注入和多速率采样缓存；可扩展读取 scenario/config 中的外参扰动，但不应把复杂标定逻辑塞入这里。

- `scenarios/*.yaml`
  - 已有 `chaos`、`perception`、`flow` 配置段。
  - 可以新增 `sensor_extrinsics` 或 `extrinsics_fault` 段，保持默认缺省为零偏移，避免破坏现有实验。

- `tools/run_thesis_sweep.py`
  - 已支持 `--scenario` / `--seed` / `--mpc-mode`，并自动运行 `tools/offline_ekf_benchmark.py`。
  - 后续可扩展为传递外参 benchmark 参数，或先新增独立 extrinsics sweep 工具，避免污染现有定位 sweep。

### 关键约束

- 默认行为必须保持零外参偏移，与当前实验结果兼容。
- 第一阶段不做完整状态增广，不扩大 ES-EKF 主状态维度。
- 纯脚本和 PVS 使用同一外参配置结构，避免两套含义不同的参数。
- 外参“真值”和“估计值”必须分离：
  - 真值外参用于生成错位传感器观测。
  - 估计外参用于 ES-EKF 修正。
  - 两者差值即标定误差。
- 文档必须明确：杆臂改正不是简单 TF 展示，必须进入观测模型。

## Proposed Changes

### 1. 新增统一外参工具模块

文件：`common/sensor_extrinsics.py`

职责：

- 定义外参数据结构：
  - `translation_b_m`: 传感器原点相对 `base_link` 的 body-frame 平移，单位 m。
  - `rotation_rpy_deg`: 传感器坐标系相对 `base_link` 的 roll/pitch/yaw，单位 deg。
  - `rotation_matrix`: 由 RPY 派生的旋转矩阵。
- 提供 YAML 解析函数：
  - `load_sensor_extrinsics(cfg, prefix)` 或 `SensorExtrinsics.from_config(...)`
  - 支持缺省零偏移。
- 提供观测变换工具：
  - `base_velocity_to_sensor_body(v_base_b, omega_b, extrinsic)`
  - `sensor_velocity_to_base_body(v_sensor_s, omega_b, extrinsic)`
  - `base_position_to_sensor_world(p_base_n, R_nb, extrinsic)`
  - `depth_at_sensor(p_base, R_nb, extrinsic)`
- 提供小角度旋转误差注入：
  - 用于模拟估计外参与真值外参之间的旋转误差。

原因：

- ES-EKF、offline benchmark、PVS 传感器生成都需要同一套坐标和杆臂公式。
- 单独模块便于单元测试，避免把几何公式散落到多个入口。

### 2. 扩展 ES-EKF 外参配置与观测接口

文件：`algorithm/es_ekf.py`

新增配置结构：

```yaml
ekf:
  sensor_extrinsics:
    imu:
      translation_b_m: [0.0, 0.0, 0.0]
      rotation_rpy_deg: [0.0, 0.0, 0.0]
    dvl:
      translation_b_m: [0.0, 0.0, 0.0]
      rotation_rpy_deg: [0.0, 0.0, 0.0]
    depth:
      translation_b_m: [0.0, 0.0, 0.0]
      rotation_rpy_deg: [0.0, 0.0, 0.0]
    mag:
      translation_b_m: [0.0, 0.0, 0.0]
      rotation_rpy_deg: [0.0, 0.0, 0.0]
```

实现：

- 保留现有 `predict()`、`correct_dvl_world()`、`correct_depth()` 行为，默认外参为零时结果不变。
- 新增或扩展观测接口：
  - `correct_dvl_sensor(dvl_vel_sensor, gyro_body=None)`
  - `correct_depth_sensor(depth_m)`
  - `correct_mag_sensor(mag_sensor_t, ...)`
- DVL body/sensor 观测模型：
  - 状态中的 base 速度转到 body：`v_base_b = R_nb.T @ v`
  - 考虑杆臂处速度：`v_sensor_b = v_base_b + omega_b × r_dvl_b`
  - 考虑 DVL 传感器坐标旋转：`v_sensor_s = R_sb @ v_sensor_b`
  - ES-EKF 用估计外参预测 `h`，与传感器观测 `z` 比较。
- 深度观测模型：
  - 传感器世界位置：`p_sensor = p_base + R_nb @ r_depth_b`
  - 深度观测：`h = -p_sensor.z`，保持当前 ROS-up 内部约定。
- IMU 第一阶段处理：
  - 旋转外参先用于把 sensor-frame IMU 转到 base body frame。
  - 平移杆臂对 IMU 加速度的完整项需要角加速度 `alpha`：`a_s = a_b + alpha × r + omega × (omega × r)`。
  - 第一阶段不在 ES-EKF 主路径强行补 `alpha`，先在纯脚本中模拟并量化其影响；PVS/online 阶段可用差分 gyro 近似 `alpha`，并通过开关启用。
- NIS 记录：
  - 对 `dvl_sensor`、`depth_sensor`、`mag_sensor` 使用独立 `source`，便于后续残差分析。

兼容性：

- 外参全零时，`correct_dvl_sensor()` 应与现有 `correct_dvl()` 等价。
- 现有 `correct_dvl_world()` 继续保留，避免破坏 `offline_ekf_benchmark.py` 的当前默认行为。

### 3. 扩展 localization node 配置接入

文件：`brain_linux/src/auv_localization/auv_localization/auv_localization_node.py`

实现：

- 将已有 `imu_frame_offset_xyz`、`dvl_frame_offset_xyz`、`depth_frame_offset_xyz` 与 `ekf.sensor_extrinsics` 对齐。
- 增加旋转外参参数：
  - `imu_frame_rotation_rpy_deg`
  - `dvl_frame_rotation_rpy_deg`
  - `depth_frame_rotation_rpy_deg`
  - `mag_frame_rotation_rpy_deg`
- runtime 默认不改变当前话题接口。
- 在 `_on_imu()` 中将 IMU sensor-frame 数据按估计外参旋转到 base body frame 后缓存。
- 在 `_on_dvl()` 中保留当前 world-frame DVL 路径；如果后续 PVS 改成 sensor-frame DVL，则通过配置开关选择：
  - `dvl_measurement_frame: world`
  - `dvl_measurement_frame: sensor`
- 在 `_on_timer()` 中：
  - `world` 模式继续 `correct_dvl_world()`。
  - `sensor` 模式调用 `correct_dvl_sensor()`。
- 静态 TF 发布仍保留，用于可视化，但文档中明确 TF 不等同于滤波改正。

### 4. 新增纯脚本外参 benchmark

文件：`tools/es_ekf_extrinsics_benchmark.py`

功能：

- 不依赖 ROS/PVS，可快速运行。
- 生成一段确定性 AUV 轨迹：
  - 直线段、S-turn、深度变化段。
  - 生成真值 `p, v, q, omega, acc`。
- 根据“真值外参”生成传感器观测：
  - IMU sensor-frame acc/gyro。
  - DVL sensor-frame velocity。
  - Depth sensor depth。
  - 可选 mag sensor magnitude。
- 用“估计外参”运行 ES-EKF：
  - zero correction：估计外参全零。
  - calibrated：估计外参 = 真值 + 标定误差。
  - online-lite：从 calibrated 初值开始慢速修正。
- 输出：
  - `results.csv`
  - `summary_by_error_level.csv`
  - `extrinsics_report.md`
  - 轨迹/误差/NIS 图。

建议命令：

```bash
python3 tools/es_ekf_extrinsics_benchmark.py \
  --duration 120 \
  --seeds 0,1,2 \
  --true-profile light,medium,heavy \
  --estimation-modes none,calibrated,online_lite \
  --output-dir results/es_ekf_extrinsics/pure_script_smoke
```

指标：

- `xy_rmse`
- `z_rmse`
- `3d_rmse`
- `cep50`
- `max_drift`
- `dvl_nis_mean`
- `depth_nis_mean`
- `extrinsic_translation_error_m`
- `extrinsic_rotation_error_deg`
- `calibration_success`
- `online_correction_delta_norm`

### 5. 新增离线标定模拟工具

文件：`tools/calibrate_sensor_extrinsics_sim.py`

功能：

- 输入真值轨迹和错位传感器观测，模拟“标定过程”。
- 第一阶段只做仿真标定，不接真实标定板或实测 SOP。
- 标定目标：
  - DVL 旋转外参：通过 `v_sensor` 与 `v_base_body` 的 Wahba/Kabsch 对齐估计旋转。
  - DVL 平移杆臂：通过 `v_sensor_b - v_base_b ≈ omega × r` 最小二乘估计 `r`。
  - Depth 杆臂：通过 `depth_sensor - depth_base ≈ -(R_nb r)_z` 最小二乘估计 `r_z` 主项。
  - IMU 旋转外参：通过 gyro 序列对齐估计旋转；平移杆臂第一阶段只评估，不强求稳定估计。
- 输出估计外参 YAML：

```yaml
sensor_extrinsics_estimated:
  dvl:
    translation_b_m: [...]
    rotation_rpy_deg: [...]
  depth:
    translation_b_m: [...]
    rotation_rpy_deg: [...]
metadata:
  calibration_rmse: ...
  samples_used: ...
```

### 6. 轻量在线修正策略

文件：`algorithm/es_ekf.py` 或新增 `algorithm/extrinsics_online.py`

第一阶段不做完整状态增广。采用“离线标定初值 + 慢速残差驱动修正”：

- 只在线修正 DVL 的小角度旋转偏差和杆臂平移小量。
- 更新频率低于滤波频率，例如 1 Hz 或每 N 个 DVL update 一次。
- 更新量限幅：
  - 单步平移修正不超过 `1 mm`。
  - 单步旋转修正不超过 `0.01 deg`。
  - 总修正不超过标定先验窗口，例如 `±5 cm`、`±1 deg`。
- 使用 DVL innovation 和 NIS gate：
  - 仅在 DVL/Depth NIS 连续稳定时启用更新。
  - 高 NIS 或 chaos 场景中暂停在线修正，避免把传感器故障误学成外参。
- 输出 online 诊断：
  - 当前外参估计。
  - 修正量范数。
  - 是否处于 frozen/gated 状态。

建议配置：

```yaml
ekf:
  extrinsics_online:
    enabled: false
    update_hz: 1.0
    max_translation_delta_m: 0.05
    max_rotation_delta_deg: 1.0
    nis_gate: 7.81
```

### 7. PVS 传感器错位注入

文件：

- `sim_holoocean/interfaces/pvs_sim_wrapper.py`
- `sim_holoocean/interfaces/holoocean_physics_bridge.py`
- `sim_holoocean/interfaces/mock_amd_server.py`

实现策略：

- 在 PVS wrapper 中保留 base 真值状态，不直接污染 `PoseSensor`。
- 在传感器 packet 生成层应用“真值外参”：
  - DVL：由 base 速度、姿态和角速度生成 sensor-frame 或 world-frame 观测。
  - Depth：由 depth sensor 的世界位置生成深度。
  - IMU：先做旋转外参；平移加速度项通过配置开关启用。
  - Magnetic：在 sensor 位置采样磁场，而不是 base 位置。
- 配置命名区分：

```yaml
sensor_extrinsics_truth:
  dvl:
    translation_b_m: [0.20, 0.05, -0.03]
    rotation_rpy_deg: [0.5, -0.3, 1.0]
  imu:
    translation_b_m: [0.05, 0.00, 0.02]
    rotation_rpy_deg: [0.2, 0.1, -0.4]
  depth:
    translation_b_m: [0.10, 0.00, -0.15]
    rotation_rpy_deg: [0.0, 0.0, 0.0]
```

- ES-EKF 使用 `ekf.sensor_extrinsics` 作为“估计外参”，不直接读取 truth。

### 8. 新增场景 YAML

文件：

- `scenarios/scenario_extrinsics_light.yaml`
- `scenarios/scenario_extrinsics_medium.yaml`
- `scenarios/scenario_extrinsics_heavy.yaml`
- `scenarios/scenario_extrinsics_calibrated.yaml`
- `scenarios/scenario_extrinsics_online.yaml`

设计：

- `light`：平移 5 cm 级，旋转 0.5 deg 级。
- `medium`：平移 10-20 cm，旋转 1-2 deg。
- `heavy`：平移 30 cm，旋转 3-5 deg。
- `calibrated`：truth 与 estimated 接近，留少量标定误差。
- `online`：以 calibrated 初值启动 online-lite 修正。

默认 scenario 不加 `sensor_extrinsics_truth` 时保持零偏移。

### 9. 新增聚合工具或扩展现有聚合

优先新增独立工具，避免污染当前 thesis sweep：

文件：`tools/aggregate_extrinsics_benchmark.py`

输入：

- 纯脚本 benchmark 的 `results.csv`
- PVS sweep 的 `results.csv`
- 可选 `offline_ekf_benchmark.py` 输出目录

输出：

- `extrinsics_summary_by_profile_mode.csv`
- `extrinsics_status_counts.csv`
- `extrinsics_aggregate_report.md`

聚合维度：

- `profile`: none/light/medium/heavy
- `estimation_mode`: none/calibrated/online_lite
- `seed`

核心指标：

- ES-EKF `xy_rmse/z_rmse/cep50/max_drift`
- 相对 no-correction 的改善率
- 标定误差大小
- online 修正是否收敛

### 10. 文档回填

文件：

- `docs/experiment/experiment_gap_conduct_plan.md`
  - 增加“ES-EKF 杆臂/外参”实验阶段。
  - 记录命令、结果路径、结论边界。

- `docs/thesis/02_es_ekf_validation.md`
  - 增加外参误差敏感性实验。
  - 说明同点传感器假设的局限。

- `docs/thesis/paper/03_state_estimation.md`
  - 增加杆臂改正观测模型公式。
  - 写清 DVL/Depth/IMU 的外参进入方式。

- `docs/thesis/paper/05_experiments_and_discussion.md`
  - 增加外参误差对定位指标影响的结果表。
  - 区分“离线标定收益”和“轻量在线修正收益”。

- 可选新增：
  - `docs/user-guide/12_es_ekf_extrinsics.md`
  - 仅当该流程稳定到可复用命令后再新增 user-guide，避免把研究中间态写成用户 SOP。

## Assumptions & Decisions

- 用户已确认第一轮采用“并行设计”：计划同时覆盖纯脚本和 PVS，但执行先做纯脚本 smoke，再接 PVS。
- 用户已确认在线估计第一阶段采用“离线标定，随后轻量在线”，不是从完全无知开始的完整状态增广。
- 第一阶段不改变 ES-EKF 主状态维度，避免引入大规模可观性和协方差调参风险。
- 传感器外参分为两套：
  - `sensor_extrinsics_truth`: 仿真生成错位观测时使用。
  - `ekf.sensor_extrinsics`: ES-EKF 估计/修正时使用。
- 外参全零必须严格保持现有行为。
- PVS 接入不应破坏当前 `run_thesis_sweep.py` 的 baseline/dvl/mag/combined 场景。
- 现有 dirty worktree 中有多项未提交改动，执行阶段不得回滚无关文件。

## Implementation Order

### Phase A：纯脚本最小闭环

1. 新增 `common/sensor_extrinsics.py` 和单元测试。
2. 扩展 `algorithm/es_ekf.py`，增加外参解析和 sensor-frame DVL/Depth 修正接口。
3. 新增 `tools/es_ekf_extrinsics_benchmark.py`。
4. 新增 `tools/calibrate_sensor_extrinsics_sim.py`。
5. 跑短时 smoke：

```bash
python3 tools/es_ekf_extrinsics_benchmark.py \
  --duration 30 \
  --seeds 0 \
  --true-profile light \
  --estimation-modes none,calibrated \
  --output-dir results/es_ekf_extrinsics/smoke
```

成功标准：

- 外参全零时指标与当前 ES-EKF baseline 等价。
- `light` 错位且不改正时误差增大。
- calibrated 模式误差相对 no-correction 下降。

### Phase B：PVS 错位观测接入

1. 在 PVS/HoloOcean sensor packet 生成层接入 `sensor_extrinsics_truth`。
2. 新增 scenario YAML：light/medium/heavy/calibrated/online。
3. 短时 PVS smoke：

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios extrinsics_light \
  --seeds 0 \
  --mpc-modes ua \
  --duration 30 \
  --label extrinsics_light_smoke
```

成功标准：

- bag 中 IMU/DVL/Depth/Truth topic 齐全。
- `offline_ekf_benchmark.py` 能完成。
- 外参错位场景不会破坏 PVS 命令契约。

### Phase C：标定与 online-lite 联动

1. 标定工具输出 estimated extrinsics YAML。
2. benchmark 支持读取 estimated extrinsics。
3. online-lite 只在 calibrated 初值附近启用。
4. 对 light/medium/heavy 做 3 seed sweep。

建议命令：

```bash
python3 tools/es_ekf_extrinsics_benchmark.py \
  --duration 120 \
  --seeds 0,1,2 \
  --true-profile light,medium,heavy \
  --estimation-modes none,calibrated,online_lite \
  --output-dir results/es_ekf_extrinsics/main_3seed
```

### Phase D：文档和论文表

1. 聚合纯脚本结果。
2. 聚合 PVS 结果。
3. 回填 conduct plan 和 thesis docs。
4. 明确论文结论边界：
   - 外参误差会显著影响 ES-EKF，尤其 DVL 旋转误差和 depth 杆臂。
   - 离线标定能恢复大部分性能。
   - 轻量在线修正只适合作为小范围漂移补偿，不能替代完整标定。

## Verification Steps

### 静态检查

```bash
python3 -m py_compile \
  common/sensor_extrinsics.py \
  algorithm/es_ekf.py \
  tools/es_ekf_extrinsics_benchmark.py \
  tools/calibrate_sensor_extrinsics_sim.py \
  tools/aggregate_extrinsics_benchmark.py
```

### 单元测试建议

新增测试：

- `tests/test_sensor_extrinsics.py`
  - 零外参 identity。
  - 纯平移杆臂速度项 `omega × r`。
  - 纯旋转外参的正反变换。
  - depth sensor 杆臂深度公式。

- `tests/test_es_ekf_extrinsics.py`
  - 零外参下 `correct_dvl_sensor()` 与原 `correct_dvl()` 等价。
  - 零外参下 `correct_depth_sensor()` 与原 `correct_depth()` 等价。
  - 有外参且估计值等于真值时，创新小于不改正模式。

### 纯脚本验收

```bash
python3 tools/es_ekf_extrinsics_benchmark.py \
  --duration 30 \
  --seeds 0 \
  --true-profile light \
  --estimation-modes none,calibrated,online_lite \
  --output-dir results/es_ekf_extrinsics/smoke
```

验收：

- `results.csv` 存在。
- 三种 estimation mode 均有结果。
- calibrated 相比 none 的 `xy_rmse` 或 `3d_rmse` 有改善。
- online_lite 不发散，外参修正量在限幅内。

### PVS 验收

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios extrinsics_light \
  --seeds 0 \
  --mpc-modes ua \
  --duration 30 \
  --label extrinsics_light_smoke
```

验收：

- `results.csv` status 为 `ok`。
- MCAP 包含 IMU/DVL/Depth/Truth。
- benchmark report 能读到 ES-EKF 指标。

### 回归检查

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline \
  --seeds 0 \
  --mpc-modes ua \
  --duration 30 \
  --label extrinsics_regression_baseline
```

验收：

- baseline 在零外参默认配置下仍能完成。
- 指标不出现数量级回退。

## Risks & Mitigations

- 风险：IMU 平移杆臂需要角加速度，当前 ES-EKF 没有 `alpha` 状态。
  - 缓解：第一阶段只对 IMU 旋转外参做主线改正；平移杆臂先在纯脚本量化，并在 PVS 中用 gyro 差分近似作为可选项。

- 风险：DVL 当前 PVS 路径发布 world-frame 速度，sensor-frame 外参模型与现有 topic 语义冲突。
  - 缓解：保留 `dvl_measurement_frame=world` 默认；新场景显式启用 `sensor` 模式。

- 风险：在线估计把传感器故障误学成外参。
  - 缓解：只在 calibrated 初值附近、NIS 稳定窗口内低速更新，高 NIS/chaos 时冻结。

- 风险：PVS 调试成本高。
  - 缓解：纯脚本先闭环；PVS 只做 light smoke 后再扩展 medium/heavy。

- 风险：论文结论过度外推。
  - 缓解：文档中明确 online-lite 是小范围补偿，不替代完整标定；完整状态增广作为后续工作。
