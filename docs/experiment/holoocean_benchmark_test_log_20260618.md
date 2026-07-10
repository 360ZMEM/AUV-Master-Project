# HoloOcean 后端基准测试 smoke 验证日志

**日期**: 2026-06-18  
**目的**: 按 `docs/user-guide/05_benchmarks.md` 与既有 benchmark 日志风格，验证基准测试体系从 PVS 推广到 HoloOcean 后端时的命令契约、可视化生成能力和阻塞点。

**阅读边界**: 本文件是一次 smoke/契约验证日志，不是正式论文统计结果。涉及性能结论时只能引用为“链路可运行/存在风险”，不能写成 HoloOcean 后端的最终 benchmark 结论。

---

## Step 0: 环境与依赖检查

```bash
/usr/bin/python3 -c "import holoocean; print('holoocean', getattr(holoocean, '__version__', 'unknown'))"
```

**结果**: 通过。

```text
holoocean 2.2.2
```

**结论**: 当前机器与旧日志 `experiment_modes_validation.md` 不同，已经具备 HoloOcean Python 包，能够继续做 HoloOcean 侧 smoke。

---

## Step 1: HoloOcean 仿真本体短启动

```bash
timeout 40 bash scripts/start_lin_sim.sh sim --sim-backend holoocean
```

**结果**: 通过，40s 内进入主循环并持续输出位姿、参考点和控制量。

关键输出：

```text
simulation_backend=holoocean
control_scheme=0 command=[right,top,left,bottom,thrust]
step=0000 t=0.00s pos=(0.00,-0.00,-12.00) ...
...
step=1050 t=35.00s pos=(37.96,-1.02,-12.10) ...
```

**结论**: HoloOcean 仿真本体可运行，`config/sim_params.yaml` 与 `start_lin_sim.sh --sim-backend holoocean` 的基础契约成立。

---

## Step 2: HoloOcean 全栈入口 no-bag smoke

```bash
AUV_DATA_ROOT=/home/gwxie/master_work-tmp/AUV_Master_Project/.auv_data \
bash scripts/start_experiment.sh \
  --sim-backend holoocean \
  --bridge-backend zenoh_json \
  --no-record-bag \
  --duration 10 \
  --skip-layout
```

**结果**: 入口可运行，但暴露两个组织问题。

1. `start_foxglove_holoocean_ros.sh` 默认 `SIM_DELAY_S=10`，10s smoke 在 brain 起稳前就进入 cleanup，不能用于判断 ROS topic 和 benchmark 数据完整性。
2. cleanup 后曾残留 ROS2 brain 子进程，需要手动清理：

```bash
pkill -INT -f "ros2 launch .../auv_stack.launch.py|zenoh_json_bridge_node|auv_localization_node|auv_controller_node|decision_node"
```

**结论**: HoloOcean 端做 benchmark 时，短实验必须显式覆盖 `SIM_DELAY_S` 或延长 duration；否则会得到“仿真运行了，但 bag 没有可分析 topic”的假阳性。

---

## Step 3: HoloOcean 全栈录制 MCAP

```bash
AUV_DATA_ROOT=/home/gwxie/master_work-tmp/AUV_Master_Project/.auv_data \
SIM_DELAY_S=3 \
BRAIN_READY_TOPIC=/auv/sensors/imu \
BRAIN_READY_TIMEOUT_S=45 \
BAG_FINALIZE_S=10 \
bash scripts/start_experiment.sh \
  --sim-backend holoocean \
  --bridge-backend zenoh_json \
  --duration 15 \
  --record-bag \
  --bag-storage mcap \
  --wait-before-record 1 \
  --brain-ready-topic /auv/sensors/imu \
  --brain-ready-timeout 45 \
  --skip-layout
```

**结果**: 通过，生成完整 MCAP。

产物：

```text
.auv_data/bags/20260618_221934/metadata.txt
.auv_data/bags/20260618_221934/rosbag.log
.auv_data/bags/20260618_221934/rosbag/metadata.yaml
.auv_data/bags/20260618_221934/rosbag/rosbag_0.mcap 128540825 bytes
```

`ros2 bag info` 摘要：

```text
Bag size: 122.6 MiB
Duration: 14.857989877s
Messages: 9362
/auv/sensors/ground_truth: 1480
/auv/sensors/imu: 740
/auv/sensors/depth: 740
/auv/sensors/dvl: 69
/auv/state/filtered: 297
/auv/visual/seabed_mesh: 296
/auv/visual/seabed_cloud: 298
/auv/visual/truth_marker: 296
```

**结论**: HoloOcean + Zenoh JSON 可生成 ES-EKF benchmark 所需核心 topic，且可同时保留可视化 topic。15s bag 已经 122.6 MiB，正式 60-120s 录制需要考虑可视化 topic 的体积。

---

## Step 4: ES-EKF 离线 benchmark

### 4.1 跳过坐标转换

```bash
python tools/offline_ekf_benchmark.py \
  --input .auv_data/bags/20260618_221934/rosbag/rosbag_0.mcap \
  --output-dir results/localization/holoocean_smoke_20260618 \
  --no-coordinate-transform \
  --verbose
```

**结果**: 可运行并生成报告/图，但 Z 误差异常。

```text
raw_dr  : RMSE_XY=0.016m  RMSE_Z=23.989m  RMSE_3D=23.989m
std_ekf : RMSE_XY=0.018m  RMSE_Z=23.982m  RMSE_3D=23.982m
es_ekf  : RMSE_XY=0.037m  RMSE_Z=24.001m  RMSE_3D=24.001m
```

### 4.2 默认坐标转换

```bash
python tools/offline_ekf_benchmark.py \
  --input .auv_data/bags/20260618_221934/rosbag/rosbag_0.mcap \
  --output-dir results/localization/holoocean_smoke_default_transform_20260618 \
  --verbose
```

**结果**: 可运行并生成报告/图，Z 误差恢复到小量级，但 ES-EKF 仍未优于 DR。

```text
raw_dr  : RMSE_XY=0.016m  RMSE_Z=0.031m  RMSE_3D=0.035m
std_ekf : RMSE_XY=0.018m  RMSE_Z=0.021m  RMSE_3D=0.028m
es_ekf  : RMSE_XY=0.035m  RMSE_Z=0.806m  RMSE_3D=0.807m
```

**发现**:
- HoloOcean bag 的 `/auv/sensors/ground_truth` 可以被 `offline_ekf_benchmark.py` 读取。
- 当前 HoloOcean smoke 下默认转换比 `--no-coordinate-transform` 更符合 Z 指标，但初始化日志出现 `Position offset from config: [0.0000, 0.0000, -23.9952]`，说明 truth、depth、滤波状态的 Z 符号/语义仍需单独核准。
- 15s 直线短窗口下 DR 几乎无漂移，不能用于证明 ES-EKF 改善。

**结论**: 定位 benchmark 代码可运行，但 HoloOcean 后端的坐标转换语义不能直接拍板。正式结果前需设计 60-120s、有转弯和漂移的 HoloOcean 场景，并固定 truth/depth 的 Z 约定。

---

## Step 5: 控制器 benchmark 命令契约

```bash
python tools/control_benchmark_module.py --output-dir results/control/holoocean_contract_smoke_20260618
```

**结果**: 进程 exit 0，但未生成任何产物。

**原因**: `tools/control_benchmark_module.py` 当前是库模块，没有 CLI main；文档中把它写成“主基准脚本”会造成假通过。

替代入口：

```bash
python tests/benchmark_pid_vs_mpc.py
```

**结果**: 当前环境失败。

```text
ModuleNotFoundError: No module named 'casadi'
```

**结论**: 控制器 benchmark 与 HoloOcean 后端无直接耦合，属于离线控制器/PVS 模型对比；当前不能作为 HoloOcean 后端通过与否的证据。文档已补充该命令契约缺口。

---

## Step 6: BT vs FSM benchmark 命令契约

```bash
AUV_DATA_ROOT=/home/gwxie/master_work-tmp/AUV_Master_Project/.auv_data \
PYTHONPATH=brain_linux/src/auv_decision \
python tests/benchmark_bt_vs_fsm.py
```

**结果**: 当前环境失败。

```text
TypeError: Axes.boxplot() got an unexpected keyword argument 'tick_labels'
```

未设置 `AUV_DATA_ROOT` 时还会因为默认写 `/auv_data` 报权限错误：

```text
PermissionError: [Errno 13] Permission denied: '/auv_data'
```

**结论**: BT vs FSM benchmark 与 HoloOcean 后端无直接耦合，但当前命令在本机 matplotlib 版本下不兼容。正式跑 benchmark 前应把 `tick_labels` 改为兼容旧 matplotlib 的 `labels`，并在文档中建议设置本地 `AUV_DATA_ROOT`。

---

## Step 7: HoloOcean 可视化生成能力

检查命令：

```bash
python tools/capture_holoocean_video.py --help
find log -maxdepth 2 -type f \( -name '*holoocean*' -o -name '*mcap_bundle*' \) -printf '%p %s bytes\n'
```

**结果**: 视频工具可解析参数，且仓库已有 HoloOcean 回放/捕获产物：

```text
log/mcap_bundle_curves.mp4
log/mcap_bundle_holoocean_agent.mp4
log/mcap_bundle_holoocean_viewport.mp4
log/test_holoocean_capture.mp4
log/test_holoocean_viewport_capture.mp4
```

**支持判断**:
- 可服务毕设中的系统展示、曲线动画、agent 视角和 viewport 视角素材。
- 当前素材更像工程验证视频；正式毕设展示建议固定一条 60-120s HoloOcean MCAP 后，用 `capture_holoocean_video.py --mcap-render-all` 批量导出。

---

## Step 8: 发现的问题与暂停拍板项

### P0/P1: HoloOcean 传感 topic 契约缺口（已补协议层）

运行 HoloOcean bridge 时反复出现：

```text
[bridge][warn] invalid payload for altitude (rt/auv/sensors/altitude): ['unsupported topic: rt/auv/sensors/altitude']
[bridge][warn] invalid payload for forward_sonar (rt/auv/sensors/forward_sonar): ['unsupported topic: rt/auv/sensors/forward_sonar']
```

原因是 `config/bridge_params.yaml` 和仿真侧会产生 `altitude`、`forward_sonar`，但当时 `common.protocol.REQUIRED_BY_TOPIC` 没有登记对应 topic。当前 ROS bag 中 `/auv/sensors/altitude` count=0。

**处理状态**: 已在 `common/protocol.py` 定义 `Z_PATH_ALTITUDE`、`Z_PATH_FORWARD_SONAR`、`KEY_ALTITUDE_M`、`KEY_SLOPE`、`KEY_LOOKAHEAD_M`，并加入 `REQUIRED_BY_TOPIC` 与类型校验。后续仍需重新跑 HoloOcean 录包确认 `/auv/sensors/altitude` 不再为 0。

### P1: HoloOcean benchmark 坐标语义待确认

`--no-coordinate-transform` 与默认转换的 Z 指标差异接近 24m。虽然默认转换能得到较小 Z RMSE，但初始化 offset 日志仍异常。该点在正式论文/毕设指标前需要暂停拍板。

### P1: 短实验默认时序不适合 HoloOcean benchmark

默认 `SIM_DELAY_S=10` 加上 brain build/launch 时间，会让 10-15s 实验很容易录不到足够 brain topic。HoloOcean smoke 建议显式：

```bash
SIM_DELAY_S=3 --brain-ready-topic /auv/sensors/imu --brain-ready-timeout 45
```

正式 benchmark 建议 duration 至少 60s。

### P2: 可视化 topic 体积较大

15s HoloOcean bag 已达 122.6 MiB。若保留 full visual，120s 可能接近 1GB。论文指标类录制可排除重型 visual topic；展示素材则单独保留 full visual。

### P2: cleanup 日志不干净

短实验 cleanup 后 ROS2 节点常以 `ExternalShutdownException` 形式退出，且 no-bag 10s smoke 曾残留 brain launch 进程。当前可手动清理，但正式脚本质量上应优化 launcher 进程组管理。

---

## 当前结论

HoloOcean 后端已经能跑仿真、进入全栈、生成 MCAP，并可被 ES-EKF 离线 benchmark 和可视化视频工具消费。它适合作为毕设可视化和短时高保真展示链路。

但现在不建议直接宣布“三个 benchmark 已正式推广到 HoloOcean 后端”。控制器与 BT/FSM 两个 benchmark 本身是离线/架构测试，当前还存在依赖或命令兼容问题；定位 benchmark 虽可运行，但 HoloOcean 的 altitude/forward_sonar topic 仍需重新录包确认，Z 坐标语义也仍需修正或拍板。
