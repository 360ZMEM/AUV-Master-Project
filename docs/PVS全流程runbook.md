# PVS 全流程 Runbook

本文档说明如何在当前仓库里完成一次 PVS 后端的完整联调、产物阅读、rosbag 回放、分析图生成和视频生成。它面向“先跑通、再分析、再复现”的日常使用方式。

## 适用范围

- 仿真后端选择 `pvs`
- 保留 ROS2、Mock AMD、Foxglove、录包与回放流程
- 使用 `log/experiments/` 下的实验 bundle 作为主要产物目录
- 使用 `tools/analyze_bag.py` 和 `tools/replay_mcap_video.py` 处理录制数据

## 先决条件

- 已进入工作区 `/home/gwxie/master_work-tmp/AUV_Master_Project`
- 已配置 Python 环境，当前可用解释器为 `/usr/bin/python3`
- ROS 2 Humble 可用，且 `ros2 bag` 支持 `mcap`
- 如果要跑整链路，需要 Foxglove bridge、brain、仿真侧都能启动

## 最常用入口

### 1. PVS 纯仿真

```bash
bash scripts/start_pvs_sim.sh sim
```

该入口会自动选择 PVS 专属配置：

- `config/sim_params.pvs.yaml`
- `config/bridge_params.pvs.yaml`

当前 PVS 纯仿真验证结果：

- `rms=1.2539m`
- `axis_ratio=1.9438%`
- `pass_rms=True`
- `pass_axis_ratio=True`

### 2. PVS + Foxglove + ROS2 联调

```bash
bash scripts/start_foxglove_pvs_ros.sh
```

如果你想记录实验产物，推荐走实验入口：

```bash
bash scripts/start_experiment.sh --sim-backend pvs --duration 120
```

这会在 `log/experiments/<run_id>/` 下生成完整 bundle。

## 实验 bundle 目录结构

典型目录如下：

- `metadata.txt`
- `launcher.log`
- `rosbag/`
- `rosbag.log`
- `analysis_pvs/` 或 `analysis_figures/`
- `replay.gif`
- `sniffer.log`
- `bridge_telemetry.jsonl`
- `arbiter_status.log`
- `execution_report_*.md`

推荐阅读顺序是：

1. `metadata.txt`
2. `launcher.log`
3. `rosbag/`
4. `sniffer.log` 和 `bridge_telemetry.jsonl`
5. `analysis_pvs/` 或 `analysis_figures/`
6. `replay.gif`

## 怎么读产物

### `metadata.txt`

先确认这些字段：

- `sim_mode`
- `brain_mode`
- `record_bag`
- `bag_storage_id`
- `run_duration_s`
- `launch_args`
- `git_head`

如果这里的后端不是 `pvs`，后面的日志就不是你要看的这条链路。

### `launcher.log`

这是最关键的时间线。优先搜索：

- `Starting main simulation`
- `Starting simulation bridge`
- `simulation_backend=pvs`
- `backend open`
- `depthHeadingAutopilot`
- `rosbag record`
- `requested duration reached`

### `sniffer.log`

这个文件用来检查协议报文有没有按预期发出。当前代码已经支持更可读的 ASCII 摘要，重点看：

- `$CKTH`
- `$AUV`
- 控制字节和电机相关字段

### `bridge_telemetry.jsonl`

这个文件适合做时间序列核对。常见字段关注：

- `control_mode`
- `cmd_timeout`
- `cmd_source`
- `note`
- `protocol_udp`

### `rosbag/`

这里保存的是 MCAP/rosbag2 录包。后续分析、回放、视频生成都直接从这里取数据。

## rosbag 回放

### 直接播放

```bash
ros2 bag play log/experiments/<run_id>/rosbag --clock
```

### 如果要配 Foxglove

先启动 Foxglove bridge，再播放 bag。这样时间轴、轨迹、状态监控都能跟着回放。

## 数据分析

### 生成分析图

```bash
/usr/bin/python3 tools/analyze_bag.py log/experiments/<run_id>/rosbag --output-dir log/experiments/<run_id>/analysis_pvs
```

脚本会输出：

- `summary_statistics.csv`
- `state_durations.csv`
- `state_transitions.csv`
- `trajectory_comparison.pdf`
- `state_timeline.pdf`
- `system_monitoring.pdf`
- `uncertainty_analysis.pdf`
- `magnetic_signature.pdf`

### 只看统计，不出图

```bash
/usr/bin/python3 tools/analyze_bag.py log/experiments/<run_id>/rosbag --stats-only
```

### 已验证的分析结果

对 `log/experiments/20260411_162254/rosbag/rosbag_0.mcap` 的分析结果：

- 时长：`106.233 s`
- estimated samples：`2087`
- diagnostics samples：`1007`
- BT status samples：`773`
- magnetic samples：`5271`
- truth samples：`1032`
- lateral error RMSE：`0.6587 m`

## 视频生成

### 生成 GIF

```bash
/usr/bin/python3 tools/replay_mcap_video.py log/experiments/<run_id>/rosbag --output log/experiments/<run_id>/replay.gif --format gif --fps 12
```

### 生成 MP4

如果机器上装了 ffmpeg，可以改成：

```bash
/usr/bin/python3 tools/replay_mcap_video.py log/experiments/<run_id>/rosbag --output log/experiments/<run_id>/replay.mp4 --format mp4 --fps 12
```

### 已验证的输出

对 `log/experiments/20260411_162254/rosbag/` 的视频生成已成功，输出文件为：

- `log/experiments/20260411_162254/replay.gif`

## 基准测试脚本

### 运行方式

```bash
bash scripts/run_sim_equivalence_check.sh --timeout 120
```

### 脚本作用

这个脚本会调用：

- 旧链路 `Master毕业设计代码实现/auv_project_new/AUV_Software_Stack/4_codes/main.py`
- 新链路 `AUV_Master_Project/sim_holoocean/apps/main.py`

并把两边的输出解析成可比对指标。

### 当前已验证结果

脚本已能正常执行并输出 JSON 摘要，但在默认配置下，当前 unified 侧没有通过等价阈值：

- legacy：`rms=0.9127`, `axis_ratio=0.017683`, `pass_rms=True`, `pass_axis_ratio=True`
- unified：`rms=33.3015`, `axis_ratio=0.610884`, `pass_rms=False`, `pass_axis_ratio=False`
- 结论：`equivalent=false`

这不是脚本故障，而是默认对比配置本身不满足等价条件，后续要用指定配置再做业务层判断。

## 推荐排查顺序

1. 看 `metadata.txt`，确认跑的是不是 PVS。
2. 看 `launcher.log`，确认仿真、桥接、brain 都启动了。
3. 看 `rosbag/`，确认有 `.mcap` 文件。
4. 看 `analysis_pvs/` 或 `analysis_figures/`，确认分析脚本有输出。
5. 看 `replay.gif`，确认回放视频生成成功。
6. 如果要比较旧新链路，再看 `scripts/run_sim_equivalence_check.sh` 的输出和 `log/phase2_5_legacy.log`、`log/phase2_5_unified.log`。

## 常见问题

### 1. 录包目录为空

通常是 `ros2 bag record` 没起、ROS 环境没 source，或者实验在录包前就退出了。

### 2. `python: command not found`

当前仓库的基准脚本已经改为使用 `/usr/bin/python3`，如果你本地环境不同，优先跟着当前工作区约定走。

### 3. 视频脚本报缺依赖

`tools/replay_mcap_video.py` 需要 `matplotlib`、`numpy`，生成 MP4 还需要 `ffmpeg`。

### 4. 分析结果和预期不一致

先确认你看的是真实的 `rosbag_0.mcap`，不是空目录，也不是别的 run_id 的产物。

---

## Shadow 模式与 Raw Dead-Reckoning 基准

### 什么是 Shadow 模式

Shadow 模式是 bridge 的一种运行状态，启用后 bridge **不会真正下发给仿真器/实物**，而是：

1. 接收来自决策侧的控制指令（`/auv/control/setpoint` 或 `/cmd_vel`）。
2. 在 `/auv/bridge/shadow_cmd` 上发布「本该下发」的指令快照。
3. 在 `/auv/bridge/shadow_telemetry` 上镜像仿真/实物返回的遥测。
4. 继续正常发布 bridge 自身状态和 arbiter 状态。

这相当于让脑端在「旁观者」模式下运行，不影响仿真/实物侧行为，但产出完整的影子数据供离线比对。

### 启动 Shadow 模式

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/brain_linux
source /opt/ros/humble/setup.bash
ros2 launch auv_stack auv_stack.launch.py passive_mode:=true
```

或通过 arbiter stack launch（自动启用 protocol_udp + arbiter profile）：

```bash
bash scripts/start_lin_brain.sh stack --arbiter-profile --passive-mode
```

### Shadow 模式输出 Topic

| Topic | 类型 | 说明 |
| --- | --- | --- |
| `/auv/bridge/shadow_cmd` | `std_msgs/String` | 本该下发的指令快照（JSON） |
| `/auv/bridge/shadow_telemetry` | `std_msgs/String` | 镜像遥测快照（JSON） |
| `/auv/arbiter/status` | `auv_interfaces/ArbiterStatus` | 仲裁器状态（不受 passive 影响） |

### Raw Dead-Reckoning 基准

为了让控制器的状态来源可选择「滤波后(EKF)」或「原始推算(raw DR)」，localization 节点支持发布原始推算里程计：

**启用方法：**

```bash
ros2 launch auv_stack auv_stack.launch.py publish_raw_state:=true bypass_ekf:=true
```

或使用 arbiter stack launch（默认已启用 `publish_raw_state`）：

```bash
bash scripts/start_lin_brain.sh stack --arbiter-profile
```

**相关 Topic：**

| Topic | 类型 | 说明 |
| --- | --- | --- |
| `/auv/state/filtered` | `nav_msgs/Odometry` | EKF 滤波后的状态（默认） |
| `/auv/state/raw_dr` | `nav_msgs/Odometry` | 原始推算里程计（bypass_ekf=true 时使用） |

**控制器行为：**
- `bypass_ekf:=false`（默认）：使用 `/auv/state/filtered`。
- `bypass_ekf:=true`：优先使用 `/auv/state/raw_dr`；如果 raw DR 不可用，自动回退到 filtered 并在日志中记录 fallback。

### 用途

Shadow + raw DR 组合可以：
1. 在不干扰仿真/实物的情况下，对比 EKF vs raw DR 的控制效果。
2. 离线分析 shadow_cmd 时间序列，评估决策输出的合理性。
3. 作为回归测试的基准数据源。

---

## 决策回放（Decision Replay）

决策回放功能允许在没有真实传感器/仿真的情况下，端到端测试行为树决策逻辑。

### 回放流程

1. 准备 `$AUV` 格式的海试文本日志。
2. 启动 `decision_replay.launch.py`，它自动启动：
   - `mock_sensor_input`：读取日志 → 发布 `/auv/sensors/status`
   - `decision_node`：订阅传感状态 → 运行行为树 → 发布 `/auv/control/goal`

### 启动命令

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/brain_linux
source /opt/ros/humble/setup.bash
ros2 launch auv_decision_ros decision_replay.launch.py
```

### 使用自定义日志

```bash
ros2 launch auv_decision_ros decision_replay.launch.py \
  log_file:=/path/to/your/AUV_log.txt
```

### 仓库内置样例日志

```
/home/gwxie/master_work-tmp/Console上位机软件/auv_console_python/20020101103632.txt
```

如果不传 `log_file`，`mock_sensor_input` 会自动在仓库中搜索该文件。

### 主要参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `log_file` | 自动搜索 | 海试日志路径 |
| `publish_hz` | `10.0` | 回放频率 |
| `confidence_threshold` | `0.7` | 行为树置信度阈值 |
| `battery_low_voltage_threshold` | `95.0` | 低电压阈值 (V) |
| `seabed_depth_m` | `15.0` | 海底参考深度 (m) |

### 验证

```bash
# 确认决策输出有数据
ros2 topic echo /auv/control/goal --once

# 观察行为树日志
# 终端应出现 Summary: 和 BehaviorTree: 相关输出
```

详细参数说明和 Topic 列表见 [brain_linux/src/auv_control/README.md](../brain_linux/src/auv_control/README.md)。

## 本次迁移的验证结论

- PVS 纯仿真链路可启动并稳定跑完。
- PVS 实验 bundle 能正常落盘。
- rosbag 分析脚本能读 MCAP 并导出图表。
- 视频生成脚本能把 bag 回放成 GIF。
- 基准脚本能运行，但默认 unified 对比结果不通过，需要结合具体配置再判定等价性。
