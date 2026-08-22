# Jetson Orin NX 部署主线上下文

本文是当前仓库在 **Jetson Orin NX** 上的部署接手入口，目标是让后续开发者或 AI 在不翻完整历史聊天的前提下，快速理解“仿真电缆巡检”和“全链路仿真测试”目前在本机上处在什么状态、从哪里运行、哪些结论可以说、哪些结论不能说。

适用边界：

- 机器：Jetson Orin NX。
- 当前复核配置：`nvpmodel = 25W`，8 核在线，ROS2 Humble，PVS 主线可用。
- 主要命令契约：PVS + `protocol_udp` + ROS2 brain stack + cable tracking + rosbag + DL/T 1278 风格产物。
- 本文不是通用 PC/HoloOcean 环境说明；HoloOcean 依赖在当前 Jetson 环境中未安装。

## 1. 当前主线定位

本仓库是 AUV 毕设工程主仓，当前主线不是单点算法 demo，而是一条从数字孪生到报告产物的闭环证据链：

```text
PVS/HoloOcean 仿真
  -> protocol_udp 或 Zenoh 桥接
  -> ROS2 brain stack
  -> cable_tracking_node 调用 AUV-Master-Mag
  -> /auv/control/setpoint 受控制器和仲裁器保护
  -> rosbag 记录 magnetic/tracking/diagnostics/setpoint
  -> JSONL/CSV/Markdown/PNG 产物
  -> DL/T 1278 风格评分和多 run 聚合验收
```

当前 Jetson 上优先级最高的主线是：

1. PVS + `protocol_udp` 的仿真电缆巡检。
2. `/auv/sensors/magnetic` 旁路进入 ROS2 cable tracking。
3. `/auv/cable/tracking`、`/auv/cable/diagnostics` 和 typed topics 的可视化与 bag 取证。
4. `tools/dlt1278_cable_report.py` 生成 DL/T 1278 风格报告。
5. distorted-prior 闭环恢复：在线先验修正默认关闭，但在满足磁观测前提的数字孪生配置中可开启并复现 mid/heavy 各 3/3 ready/pass。

## 2. Jetson 本机验证结论

### 2.1 依赖状态

已确认可用：

- `python3`、`pip`、`colcon`、`xelatex`、`latexmk`、`biber`、`git-lfs`
- ROS2 Humble：`ros2`、`ros2 bag`、`mcap` storage 后端
- Python 主线依赖：`numpy`、`scipy`、`pandas`、`matplotlib`、`yaml`、`pytest`、`py_trees`、`PySide6`、`zenoh`
- PVS 真实包名：`python_vehicle_simulator`
- ROS2 workspace 构建产物：`brain_linux/install/setup.bash`、`auv_interfaces`

已确认缺失或不作为当前主线依赖：

- `holoocean`：当前 Jetson 未安装；不要把 HoloOcean 3D 仿真作为本机主线可运行结论。
- `pvs`：旧模块名不可导入，但这不是问题；真实包名是 `python_vehicle_simulator`。

仓库依赖分层：

| 层级 | 依赖 | 当前用途 |
|---|---|---|
| Jetson mainline 必需 | ROS2 Humble、`rosbag2_storage_mcap`、`numpy`、`scipy`、`pandas`、`matplotlib`、`yaml`、`py_trees`、`PySide6`、`zenoh`、`python_vehicle_simulator` | PVS/protocol_udp 电缆巡检、bag、DL/T 1278 产物 |
| 实物部署调试 | `telnet`、`expect`、`tcpdump`、`screen`、`minicom`、`jq`、`ss`、`sudo -n` | PC104/VxWorks shell、fan-out、UDP 抓包、串口/JSON 辅助 |
| MPC / 磁探测 / 视频回放支线 | `casadi`、`tqdm`、`imageio`、`moviepy`、`rosbags`、`openpyxl` | MPC microbench、AUV-Master-Mag 扫参、视频/离线回放和表格导出 |
| 文档构建 | `pandoc`、`wkhtmltopdf`、`xelatex`、`latexmk`、`biber`、`git-lfs` | Markdown/PDF 与 `thuthesis/auv-thesis.pdf`；构建前需确认 LFS 图像不是指针 |
| 暂不纳入 Jetson 主线 | `holoocean` | 3D 仿真后端，需按官方流程单独安装 |

Jetson 上实物 fan-out 的特殊注意事项：

- `scripts/start_pc104_fanout_concurrent.sh` 需要 `sudo -n`，因为 fan-out 是唯一绑定本机 `21/udp` 的进程。
- 若用 `sudo` 启动 Python 工具，必须确保依赖安装到全局系统 Python，而不是普通用户 site-packages；否则会出现普通用户 `import zenoh/PySide6/serial/scapy/configobj` 成功，但 `sudo /usr/bin/python3` 失败。
- 建议安装 Python 包时使用 `sudo -H /usr/bin/python3 -m pip install ...`，并同时验证普通用户和 sudo Python 导入。

2026-07-13 依赖修复记录：

- 误把全局 `numpy` 升到 `2.2.6` 后，系统 `pandas 1.3.5`、`matplotlib 3.5.1`、`cv2 4.5.4` 出现 NumPy 1.x/2.x ABI 不兼容，典型错误包括 `numpy.dtype size changed`、`_ARRAY_API not found`、`numpy.core.multiarray failed to import`。
- 已回退并验证稳定组合：`numpy==1.24.4`、`moviepy==1.0.3`、`Pillow==12.3.0`、`casadi==3.7.2`、`tqdm==4.68.4`。
- 普通用户和 `sudo /usr/bin/python3` 均已验证可导入 `numpy`、`scipy`、`pandas`、`matplotlib`、`cv2`、`casadi`、`tqdm`、`imageio`、`moviepy`、`rosbags`、`openpyxl`、`PySide6`、`serial`、`scapy`、`configobj`、`zenoh`。
- `pip check` 在普通用户和 sudo 下均为 `No broken requirements found`。
- 后续全局安装视频/MPC相关包时，必须固定 `numpy<1.25` 或显式使用 `numpy==1.24.4`，避免重新打破 Ubuntu 22.04 系统二进制 Python 包。

2026-07-13 pip 源和 DNS 记录：

- 当前环境没有 `http_proxy`、`https_proxy`、`all_proxy` 环境变量，pip 也没有配置 proxy。
- PyPI、清华、阿里、华为云、腾讯云源均可直连；USTC 源 HTTP 有跳转，但 `pip index versions numpy` 返回 `No matching distribution found`，本机不推荐使用 USTC 作为 pip 源。
- 曾出现所有 pip 源同时失败，根因是 `usb2` 链路 DNS 被 DHCP 指到不可用的 `10.13.248.54`，不是 pip 源问题。临时修复命令：

```bash
sudo resolvectl dns usb2 223.5.5.5 8.8.8.8
sudo resolvectl domain usb2 '~.'
```

ROS2 Python 测试和节点导入必须先 source 环境：

```bash
source /opt/ros/humble/setup.bash
source brain_linux/install/setup.bash
```

若不 source `brain_linux/install/setup.bash`，会出现 `ModuleNotFoundError: auv_interfaces`。这属于 ROS2 工作区环境未激活，不是依赖缺失。

### 2.2 静态和轻量测试

已通过：

```bash
bash scripts/run_integration_test.sh
```

结果：上位机-Jetson-AMD 链路静态联调脚本通过，语法、核心模块导入、Mock AMD 结构和行为树基础检查无残余错误。

已通过：

```bash
source /opt/ros/humble/setup.bash
source brain_linux/install/setup.bash
python3 -m pytest -q \
  tests/test_pvs_time_scale_config.py \
  tests/test_pvs_kinematic_setpoint.py \
  tests/test_cable_prior_adapter.py \
  brain_linux/src/auv_control/test/test_cable_guidance_limits.py \
  brain_linux/src/auv_control/test/test_cable_tracking_node.py
```

结果：`16 passed`。

磁外参状态测试的注意事项：

- `brain_linux/src/auv_bridge/auv_bridge/bridge_node.py` 源码中已有 `_build_magnetic_extrinsics_static_status()` 和 `_publish_magnetic_extrinsics_status()`。
- 若直接从旧 `brain_linux/install` 导入，可能看到旧安装产物缺方法；这是 install 空间陈旧/未重建问题。
- 用本地源码优先或重建后，`brain_linux/src/auv_bridge/test/test_magnetic_extrinsics_status.py` 可通过。

### 2.3 25W/8 核 PVS 电缆巡检 smoke

复核命令：

```bash
AUV_SKIP_BRAIN_BUILD=1 bash scripts/start_experiment.sh \
  --preflight-clean \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --duration 60 \
  --record-bag \
  --bag-profile cable_acceptance \
  --wait-before-record 8 \
  --bag-finalize 15 \
  --auto-activate \
  --skip-layout \
  --brain-arg enable_cable_tracking:=true \
  --brain-arg enable_cable_mission_autostart:=true \
  --brain-arg cable_tracking_config:=/home/auv_dev/AUV-Master-Project/brain_linux/config/cable_tracking.yaml
```

最新复核 run：

```text
Bag: /auv_data/bags/20260713_002921/rosbag
Wall time: 1m19.947s
Bag duration: 59.406705384s
Bag size: 5.7 MiB
Messages: 21048
/auv/sensors/magnetic: 2704
/auv/cable/tracking: 452
/auv/control/setpoint: 891
```

对照 run：

```text
Bag: /auv_data/bags/20260713_002210/rosbag
Bag duration: 59.324156679s
Messages: 19972
/auv/sensors/magnetic: 2471
/auv/cable/tracking: 435
/auv/control/setpoint: 865
```

结论：

- Jetson Orin NX 在 25W/8 核下可以跑通 PVS/protocol_udp 电缆巡检主链路。
- 业务段接近 1:1；60 s bag 实际覆盖约 59.4 s。
- 第一次短 run 看起来慢，主要被前序 `colcon build` 污染：20 s duration 时 brain 还在构建，未进入有效业务运行。
- 正式 smoke/benchmark 应使用 `AUV_SKIP_BRAIN_BUILD=1`，并先单独完成或确认 `colcon build`。

### 2.4 CPU 和功耗判断

当前机器已确认：

```text
NV Power Mode: 25W
nproc: 8
online CPU: 0-7
CPU max MHz: 1984
```

运行时 CPU 余量偏紧，但不是“跑不动”的依赖问题。采样时可见较重负载：

- 主链路：`zenoh_viz_bridge_node`、`cable_tracking_node`、`decision_node`、`zenoh_json_bridge_node`、`auv_localization_node`、`ros2 bag record`
- 外部桌面负载：Firefox、GNOME Shell、Xorg

blame：

- 性能压力主要来自多 ROS2 Python 节点 + 可视化桥 + 桌面/浏览器并发。
- 25W/8 核解决了 15W/4 核下的明显 CPU 约束，但并不代表有大量余量。
- 若要做正式指标，建议关闭 Firefox、减少桌面可视化负载，并考虑禁用非必要 viz bridge。

### 2.5 当前仍需处理的问题

- `scripts/start_foxglove_holoocean_ros.sh` 收尾阶段出现过 `BRIDGE_PID: unbound variable`。该问题没有阻止 bag 生成，但属于 cleanup 脚本健壮性问题，后续应修。
- `foxglove_bridge not started because install/local_setup.bash was not found`：当前 smoke 使用 `--skip-layout`，且不依赖 Foxglove bridge；如果需要实时 Foxglove，可视化 workspace 需单独补构建/安装。
- HoloOcean 当前未安装；README 不应再宣称当前 Jetson 可直接跑 HoloOcean 3D。

### 2.6 依赖修复后 smoke 复测

2026-07-13 在完成实物调试命令、MPC、视频回放依赖安装，并将 `numpy` 回退到 `1.24.4` 后，重新运行 Jetson 60 s smoke：

```bash
AUV_SKIP_BRAIN_BUILD=1 timeout 240 bash scripts/start_experiment.sh \
  --preflight-clean \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --duration 60 \
  --record-bag \
  --bag-profile cable_acceptance \
  --wait-before-record 8 \
  --bag-finalize 15 \
  --auto-activate \
  --skip-layout \
  --brain-arg enable_cable_tracking:=true \
  --brain-arg enable_cable_mission_autostart:=true \
  --brain-arg cable_tracking_config:=/home/auv_dev/AUV-Master-Project/brain_linux/config/cable_tracking.yaml
```

复测结果：

```text
Bag: /auv_data/bags/20260713_011233/rosbag
Wall time: 1m19.789s
Bag duration: 59.398134256s
Bag size: 5.7 MiB
Messages: 21204
/auv/sensors/magnetic: 2725
/auv/cable/tracking: 454
/auv/control/setpoint: 896
```

结论：

- 依赖修复后，PVS/protocol_udp 电缆巡检主链路仍正常。
- `numpy==1.24.4` 下 `scipy`、`pandas`、`matplotlib`、`cv2`、ROS2 bag 读取和 cable tracking 链路未出现 ABI 错误。
- 60 s smoke 总墙钟、bag 时长和关键 topic 数与前一次 25W/8 核复核基本一致。
- 日志仍出现 `BRIDGE_PID: unbound variable`；ROS2 节点在 launcher 停止时出现 `ExternalShutdownException`/process died 日志，属于当前 shutdown 噪声，不影响 bag 取证。

### 2.7 Jetson MPC 求解压测

2026-08-22 当前正式入口与主证据为：

```bash
# 新建 clean run；先记录 5 s idle baseline
real_experiments/jetson_realtime/run.sh

# 不启动负载，复算正式 run bundle
real_experiments/jetson_realtime/run.sh --run-dir \
  real_experiments/jetson_realtime/data/runs/20260822_165846
```

该轮固定 origin 基线 `84196911aedf272a4faeb99d8a0058707dee665a`、25 W、8 核，preflight 未命中已知竞争进程。正式 wall-time 结果：

| 场景 | 模式 | n | mean ms | p50 ms | p95 ms | p99 ms | max ms | success |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| steady | cold | 200 | 34.257 | 34.246 | 36.560 | 37.088 | 37.212 | 1.000 |
| steady | warm | 200 | 32.596 | 32.381 | 34.118 | 34.968 | 36.581 | 1.000 |
| constraint stress | cold | 50 | 81.161 | 81.095 | 122.342 | 140.531 | 142.144 | 1.000 |
| constraint stress | warm | 50 | 74.706 | 69.666 | 119.795 | 139.957 | 142.265 | 1.000 |

短时整机资源共 60 个样本、30.224 s：CPU mean/p95/max 为 39.9%/60.0%/75.1%，内存 mean/max 为 4838.2/4918.6 MiB，最高温度 57.4 °C，采样间隔 p95 为 0.505 s。idle/steady/stress 的 CPU mean 为 34.3%/42.6%/38.3%。CPU/GPU、内存和温度均为整机遥测，不是求解器进程独占归因；该短时 run 不替代真实 ADC--EKF--BT--控制--PC104 全栈或 30 min thermal soak。

结论：同一 commit/功耗/核数下共有 3 轮兼容 clean run，稳态 warm/cold p95 跨轮范围为 33.948--35.464/33.642--36.560 ms，压力档为 119.795--122.230/122.342--123.691 ms，各轮各档成功率均为 100%。稳态只关闭当前独立求解器微基准的 20 Hz 周期余量；压力档 p95 约 120 ms，仍需 deadline、降阶或 fallback。不得把求解 wall time 与 PC104 上行到达间隔相加为端到端时延。

以下 2026-07-13 数据保留为历史回归警示。该历史包缺少与当前同完整度的 git/config/environment 快照，不能与 2026-08-22 clean run 混算，也不再作为论文主表：

工具入口：

```bash
python3 tools/mpc_solve_microbench.py \
  --iters 200 \
  --output-dir results/mpc_solve_microbench/jetson_20260713_steady_200

python3 tools/mpc_solve_microbench.py \
  --iters 50 \
  --start-depth 8.0 \
  --output-dir results/mpc_solve_microbench/jetson_20260713_depth_stress
```

MPC 配置：

```text
params: brain_linux/config/params.yaml
horizon N: 20
dt: 0.2 s
CasADi: 3.7.2
numpy: 1.24.4
```

稳态巡航 microbench，`start_depth=target_depth=3.0`，200 次：

| 模式 | timing | n | mean ms | p50 ms | p95 ms | max ms | success |
|---|---|---:|---:|---:|---:|---:|---:|
| cold | wall | 200 | 62.5720 | 62.4065 | 64.1977 | 66.8352 | 1.0000 |
| cold | solver internal | 200 | 61.2522 | 61.1066 | 62.8273 | 65.5262 | 1.0000 |
| warm | wall | 200 | 35.6226 | 35.3648 | 36.1816 | 63.7977 | 1.0000 |
| warm | solver internal | 200 | 28.2442 | 27.9616 | 28.7595 | 62.3251 | 1.0000 |

压力档，`start_depth=8.0`、`target_depth=3.0`，50 次：

| 模式 | timing | n | mean ms | p50 ms | p95 ms | max ms | success |
|---|---|---:|---:|---:|---:|---:|---:|
| cold | wall | 50 | 518.0725 | 546.1403 | 604.1342 | 618.8983 | 0.1000 |
| warm | wall | 50 | 528.8595 | 557.4166 | 608.5938 | 616.2670 | 0.0600 |

压力档主失败状态：

```text
Maximum_Iterations_Exceeded
```

MPC blame：

- 正常稳态/温启动工况下，Jetson Orin NX 对当前 `N=20, dt=0.2s` MPC 有明显实时余量；warm-start p95 约 36 ms，远低于 200 ms 控制周期。
- 约束压力工况下，求解时间退化到 0.5-0.6 s，且成功率仅 6%-10%。这不是 CasADi 安装失败，也不是简单 CPU 满载问题，而是初始状态与目标/约束组合导致 NLP 难解或不可行，触发 IPOPT 最大迭代。
- 真机闭环若启用 MPC，必须保留 fallback 策略，并对深度/航向大阶跃做 setpoint ramp、可行性预检查或放宽/重构约束，不能把压力档失败解释为 Jetson 无法运行 MPC。
- `tools/mpc_xy_yaw_extreme_benchmark.py` 是全场景全变体论文级离线 sweep，规模较大；本次未作为即时 smoke 压测主证据。

### 2.8 origin、Git LFS 与论文构建基线

- `origin` URL：`https://github.com/360ZMEM/AUV-Master-Project.git`；它服务仿真/论文主体，不是 Jetson 专用分支，Jetson 脏工作树禁止直接 blind pull。同步流程见根目录 `AGENTS.md` §7。
- 2026-08-22 fetch 后，本地 `HEAD` 与 `origin/main` 均为 `84196911aedf272a4faeb99d8a0058707dee665a`，ahead/behind=`0/0`。该对象的作者日期为 2026-07-16、提交者日期为 2026-08-22，必须以哈希识别。
- 仓库论文图像使用 Git LFS；仅有约百字节 pointer 时 XeLaTeX 会报 `Unable to load picture`。本机已安装 `git-lfs 3.0.2` 并执行 `git lfs pull origin main`。
- LFS 拉取后，2026-08-22 在 `thuthesis/` 执行 `timeout 300 make auv-thesis` 成功，输出 177 页；最终日志为 0 undefined、0 multiply-defined、0 overfull h/vbox。Jetson 实时性内容实际落在 §5.6.2、表 5.24、图 5.8。

## 3. 必读入口

新接手时按这个顺序读，不要从零散实验日志开始：

| 顺序 | 文件 | 用途 |
|---:|---|---|
| 1 | `README.md` | 仓库结构、顶层命令、文档入口 |
| 2 | `docs/INDEX.md` | 明线、暗线、论文、实物部署的索引 |
| 3 | `docs/internals/12_cable_tracking_mag_integration.md` | 电缆跟踪集成、在线先验修正、PVS 位形响应 |
| 4 | `docs/real_deployment/08_cable_inspection_io_contract.md` | 电缆巡检 I/O 契约、真机禁止输入、部署边界 |
| 5 | `docs/thesis/12_cable_mag_dlt1278_fullflow.md` | 首次全流程打通和 limited 结论 |
| 6 | `docs/thesis/14_cable_acceptance_multirun.md` | 多 run 验收口径 |
| 7 | `docs/thesis/16_cable_dlt1278_scoring_and_operator_products.md` | ready/pass、DL/T 风格评分、运维产物 |
| 8 | `docs/experiment/cable_distorted_prior_closedloop_20260707.md` | distorted-prior 从失败到正结果的探索历史 |

## 4. 代码与配置地图

| 层级 | 关键路径 | 说明 |
|---|---|---|
| 仿真 | `sim_holoocean/interfaces/pvs_sim_wrapper.py` | PVS 后端，包含 `kinematic_setpoint` 运动学响应 |
| 仿真桥接 | `sim_holoocean/interfaces/mock_amd_server.py` | protocol_udp mock AMD，同时发布磁力计 Zenoh side-channel |
| ROS2 桥 | `brain_linux/src/auv_bridge/auv_bridge/bridge_backends.py` | side-channel magnetic 转 ROS2 `/auv/sensors/magnetic` |
| 电缆节点 | `brain_linux/src/auv_control/auv_decision_ros/cable_tracking_node.py` | 接 mission、nav、mag，调用 `AUV-Master-Mag` 并发布 tracking/setpoint |
| 先验适配 | `brain_linux/src/auv_control/auv_decision_ros/cable_prior_adapter.py` | 加载 CSV/GeoJSON/YAML 电缆先验，可用于 distorted-prior 变体 |
| 制导限幅 | `brain_linux/src/auv_control/auv_decision_ros/cable_guidance_limits.py` | 将 cable guidance 限制在车辆运动包线内 |
| 主配置 | `brain_linux/config/cable_tracking.yaml` | cable tracking canonical 配置，在线先验修正默认关闭 |
| PVS 桥配置 | `config/bridge_params.protocol_udp.pvs.yaml` | PVS + protocol_udp 默认桥接配置 |
| 报告抽取 | `tools/extract_cable_tracking_jsonl.py` | rosbag -> tracking JSONL |
| DL/T 报告 | `tools/dlt1278_cable_report.py` | JSONL -> CSV/JSON/Markdown 验收产物 |
| 多 run 聚合 | `tools/aggregate_cable_acceptance_runs.py` | 单 run summary -> 聚合 ready/pass |
| 诊断图 | `tools/plot_cable_tracking_fullflow.py` | 工程诊断图 |
| 运维图 | `tools/plot_cable_operator_products.py` | 面向操作员的图像产物 |

`AUV-Master-Mag/` 是磁探测专属模块线。主仓负责车辆安全、仲裁、通信传输、控制器执行、仿真管线和可视化；`AUV-Master-Mag` 负责电缆感知、route progress、埋深估计、guidance intent 和质量字段。

## 5. 常用运行命令

### 5.1 最小 PVS 仿真

```bash
bash scripts/start_experiment.sh --sim-backend pvs --duration 120
```

Jetson 上若只是确认本机可运行，优先用 60 s smoke：

```bash
AUV_SKIP_BRAIN_BUILD=1 bash scripts/start_experiment.sh \
  --preflight-clean \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --duration 60 \
  --record-bag \
  --bag-profile cable_acceptance \
  --wait-before-record 8 \
  --bag-finalize 15 \
  --auto-activate \
  --skip-layout \
  --brain-arg enable_cable_tracking:=true \
  --brain-arg enable_cable_mission_autostart:=true \
  --brain-arg cable_tracking_config:=/home/auv_dev/AUV-Master-Project/brain_linux/config/cable_tracking.yaml
```

### 5.2 电缆巡检验收 run

```bash
bash scripts/start_experiment.sh \
  --preflight-clean \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --duration 120 \
  --record-bag \
  --bag-profile cable_acceptance \
  --wait-before-record 8 \
  --bag-finalize 15 \
  --brain-arg enable_cable_tracking:=true \
  --brain-arg enable_cable_mission_autostart:=true \
  --brain-arg cable_tracking_config:=/home/auv_dev/AUV-Master-Project/brain_linux/config/cable_tracking.yaml
```

关键约束：

- `--arbiter-profile` 必须保留，否则 protocol_udp 侧 magnetic side-channel 可能不会打开。
- `--preflight-clean` 是 PVS 验收 run 的推荐前置，避免继承 stale process、DDS shared-memory、Zenoh shared-memory 或 Foxglove 端口状态。
- `--bag-profile cable_acceptance` 用于控制 bag 体积并保留 cable 取证核心 topic。

### 5.3 单 run 产物链

```bash
python3 tools/extract_cable_tracking_jsonl.py \
  --bag /auv_data/bags/<TS>/rosbag \
  --output-jsonl results/cable_ops_report/fullflow_<TS>/tracking.jsonl \
  --summary-json results/cable_ops_report/fullflow_<TS>/extract_summary.json

python3 tools/dlt1278_cable_report.py \
  --tracking-jsonl results/cable_ops_report/fullflow_<TS>/tracking.jsonl \
  --output-dir results/cable_ops_report/fullflow_<TS> \
  --max-route-offset-target-m 2.0 \
  --mean-route-offset-target-m 1.0 \
  --confidence-target 0.65 \
  --max-burial-sigma-m 0.15 \
  --min-valid-burial-ratio 0.8 \
  --min-tracking-samples 300

python3 tools/plot_cable_tracking_fullflow.py \
  --tracking-jsonl results/cable_ops_report/fullflow_<TS>/tracking.jsonl \
  --output-dir results/cable_ops_report/fullflow_<TS>

python3 tools/plot_cable_operator_products.py \
  --report-dir results/cable_ops_report/fullflow_<TS>
```

### 5.4 多 run 聚合

```bash
python3 tools/aggregate_cable_acceptance_runs.py \
  results/cable_ops_report/fullflow_<TS1> \
  results/cable_ops_report/fullflow_<TS2> \
  results/cable_ops_report/fullflow_<TS3> \
  --output-dir results/cable_ops_report/acceptance_multirun_<TS>
```

### 5.5 distorted-prior 闭环恢复

```bash
bash scripts/run_cable_closedloop_distorted.sh
bash scripts/score_cable_closedloop_recovery_runs.sh
```

产物入口：

```text
results/cable_ops_report/closedloop_e2e/run_manifest.tsv
results/cable_ops_report/closedloop_e2e/_agg_mid_recovery/acceptance_runs_summary.json
results/cable_ops_report/closedloop_e2e/_agg_heavy_recovery/acceptance_runs_summary.json
```

这条链路用于验证“先验扭曲能否被磁观测驱动的在线先验修正吸收”。它不是普通 clean-prior 验收 run，也不能替代真实海缆海试。

## 6. 验收字段和判定口径

单 run 主判定文件是：

```text
results/cable_ops_report/<RUN>/inspection_summary.json
```

关键字段：

| 字段 | 含义 |
|---|---|
| `industrial_conclusion_readiness` | `ready`、`limited` 或 `invalid` |
| `industrial_acceptance_pass` | 是否通过全部工业验收检查 |
| `acceptance_checks` | 每个门槛的 PASS/FAIL |
| `data_quality_flags` | 数据证据缺口 |
| `quality_flag_counts` | 感知/质量 flags 统计 |
| `acceptance_flag_counts` | 单样本验收 flags 统计 |
| `route_offset_p95_m` | 横偏 95 分位 |
| `confidence_p05` | 置信度 5 分位 |
| `valid_burial_ratio` | 有效 `burial_sigma_m` 样本比例 |

默认工程逻辑：

- 无 tracking 样本：`invalid`。
- 产物完整但任一关键门槛失败：`limited`。
- 样本量、横偏、置信度、埋深 sigma、flags、起点健康全部满足：`ready`。

DL/T 风格状态和工业验收是两层结论：

- DL/T 风格评分回答“这段海缆状态如何，触发哪些扣分项”。
- 工业验收 ready/pass 回答“本次数字孪生产物证据是否完整且满足工程阈值”。
- `ready/pass=true` 不等于“无扣分”，也不等于“真实海缆检测精度验收已通过”。

## 7. 严格边界

在线电缆 tracking 禁止消费：

- `ground_truth.cable_closest_ned`
- `ground_truth.cable_distance_m`
- 任何 `evaluation_*` 或仅仿真器可见的真值电缆状态
- 真机上的 `sensor_extrinsics_truth.*`
- 用高频广播原始传感器相对位置替代部署标定配置

distorted-prior 正结果的边界：

- 结论限定在数字孪生确定性电缆先验、人工静态位姿扭曲、满足直线埋缆磁观测前提、有效巡检窗口内、n=3/档。
- 磁导出横偏基于无限长直线模型和已知电缆走向；弯段、远离段、真实背景场、真实检测噪声仍需单独验证。
- 在线先验修正默认关闭。真机启用前必须先证明磁观测前提成立，并完成去地磁背景、去噪、外参标定和 bag 证明。

## 8. 全链路测试分层

建议按以下层级推进，不要跳过证据不足的前置层：

| 层级 | 目标 | 推荐命令或入口 |
|---|---|---|
| L0 静态检查 | 语法、导入、单元测试 | `pytest tests/test_cable_prior_adapter.py tests/test_pvs_kinematic_setpoint.py` |
| L1 轻量集成 | 上位机-Jetson-AMD 链路静态联调 | `bash scripts/run_integration_test.sh` |
| L2 单 run 仿真 | PVS/protocol_udp 电缆巡检，产出 bag | `bash scripts/start_experiment.sh ... --bag-profile cable_acceptance` |
| L3 离线报告 | 从 bag 生成 JSONL、CSV、Markdown、PNG | `extract_cable_tracking_jsonl.py` + `dlt1278_cable_report.py` |
| L4 多 run 统计 | >=3 run 聚合，输出 pass ratio 和 readiness 分布 | `tools/aggregate_cable_acceptance_runs.py` |
| L5 扭曲先验恢复 | mid/heavy distorted-prior 闭环恢复 | `run_cable_closedloop_distorted.sh` + `score_cable_closedloop_recovery_runs.sh` |
| L6 真机准入 | 标定、I/O 契约、急停、bag 证明 | `docs/real_deployment/08_cable_inspection_io_contract.md` |

## 9. 当前 blame 分析

已经闭合的责任归因：

- Jetson 上首次 20 s smoke 只录到 `/rosout` 的根因是 `colcon build` 占用了主要窗口，brain 未进入有效 launch；不是 PVS 或 cable tracking 依赖缺失。
- 25W/8 核复跑 60 s smoke 生成了 59.4 s 有效 bag，说明当前主链路能在 Jetson Orin NX 上运行。
- 早期 fullflow 不发布 tracking/setpoint 的根因是 protocol_udp 路径缺少 magnetic side-channel，不是 cable node mission 逻辑本身。
- (3d) 在线修正全拒的根因是磁观测前提不成立，电缆与车辆近乎共面导致 `Bz/By` 主导并放大横偏，不是 EKF 接线错误。
- PVS 闭环早期无法展示横向恢复的根因是 mock 车体对 Y/yaw setpoint 没有真实位形响应，已通过 `kinematic_setpoint` 路径补齐。
- ready/pass 达成不是放宽阈值，而是修正物理门控、制导振荡和有效巡检窗口口径。

仍未闭合的责任边界：

- Jetson CPU 余量偏紧；正式 benchmark 应关闭 Firefox/桌面可视化负载，或拆分仿真、brain、可视化到不同机器。
- cleanup 脚本 `BRIDGE_PID: unbound variable` 需要修复，避免收尾误报或残留进程。
- 真实海缆环境下的背景场去除、检测噪声、多种子统计和硬件实物证据仍未替代数字孪生证据。
- 在线先验修正的工程可用性依赖磁观测前提和传感器外参标定，不能默认迁移到真机。
- 若后续 run 出现 `limited`，应优先查看 `inspection_summary.json` 的 failed checks、quality flags、acceptance flags 和 start-health，而不是只看 DL/T 风格状态文本。

## 10. 后续建议

短期建议：

1. 修复 `scripts/start_foxglove_holoocean_ros.sh` cleanup 中的 `BRIDGE_PID` 未绑定问题。
2. 正式实验前固定 SOP：`nvpmodel -q` 确认 25W、`nproc` 确认 8 核、关闭 Firefox、使用 `AUV_SKIP_BRAIN_BUILD=1`。
3. 把 60 s smoke 固化为 Jetson preflight：运行后必须检查 `/auv/sensors/magnetic`、`/auv/cable/tracking`、`/auv/control/setpoint` 三类 topic 非零。
4. 若要跑 120 s 或 distorted-prior 多 run，先单独执行一次 `colcon build` 或让首轮 warm-up run 专门承担构建成本，不纳入性能判断。

中期建议：

1. 给 `start_experiment.sh` 增加可选 `--skip-viz-bridge` 或 profile，降低 Jetson 单机 CPU 压力。
2. 为 Jetson smoke 增加自动 summary：输出 wall time、bag duration、message counts、关键 topic counts、是否出现 `BRIDGE_PID`/`ERROR`。
3. 将正式验收分为两档：`jetson_smoke_60s` 用于本机可运行性，`acceptance_120s` 用于论文/验收证据，避免混用口径。
