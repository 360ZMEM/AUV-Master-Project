# AUV 项目配置状态与设置（2026-03-21）

本文档面向当前 `AUV_Master_Project` 的联调场景，解释 `config/sim_params.yaml` 与 `config/bridge_params.yaml` 的实际含义，并重点说明哪些参数值得调整、调了会影响什么。

## 1. 配置文件在哪里

- `config/sim_params.yaml`：仿真主配置，控制仿真时间步、载具初始状态、控制律、轨迹、评估指标和 ES-EKF 实验参数。
- `config/bridge_params.yaml`：仿真桥接配置，控制 Zenoh topic 映射、收发超时、传感器噪声和电缆/声呐感知模型。
- `config/real_params.yaml`：真实设备或硬件在环配置，当前主要作为占位和后续扩展入口。

## 2. 启动脚本如何使用这些配置

### `scripts/start_lin_sim.sh`
- `SIM_CFG` 指向 `config/sim_params.yaml`。
- `BRIDGE_CFG` 指向 `config/bridge_params.yaml`。
- `bridge` 模式用于只启动 Zenoh 仿真桥接。
- `both` 模式会同时拉起桥接与主仿真。

### `scripts/start_lin_brain.sh`
- 强制使用系统 Python：`/usr/bin/python3`。
- 通过 `--cmake-clean-cache` 避免旧 CMake 缓存污染。
- 启动 `brain_linux/launch/auv_stack.launch.py`，并通过 launch 参数控制节点开关。

## 3. `sim_params.yaml` 当前结构说明

### 3.1 `stage`
- `name`：实验/任务阶段名。
- 作用：用于区分不同 stack 入口、不同实验流程。
- 调参建议：通常不要频繁改动，除非你要切换任务版本或记录不同实验批次。

### 3.2 `simulation`
- `world`：场景名，例如 `Dam`。
- `package_name`：HoloOcean 场景包名。
- `agent_name`：载具实例名，通常和仿真场景中的 agent 对应。
- `show_viewport`：是否显示仿真窗口。
- `verbose`：是否输出更多仿真内部日志。
- `ticks_per_sec` / `dt`：仿真主循环频率与步长。
- `max_steps`：最大仿真步数。

#### 值得调整的参数
- `ticks_per_sec` / `dt`：这是最值得先看的参数之一。
  - 提高频率：传感器更新更密，但 CPU 压力更大。
  - 降低频率：调试更轻松，但控制和感知响应会变慢。
  - 经验建议：如果你在做联调，优先保持 `30 Hz ~ 50 Hz` 这个区间，不要一上来就堆太高。
- `show_viewport`：如果只做回归或批量测试，保持 `false`。
  - 改成 `true` 只适合你需要看画面、排查姿态问题时使用。
- `max_steps`：
  - 做短回归测试时可以限制步数，避免长时间运行。
  - 做稳定性测试时可以适当放大，但不要无限制占资源。

### 3.3 `agent`
- `type`：载具模型类型，例如 `TorpedoAUV`。
- `control_scheme`：控制模式编号。
- `location`：初始位置，z 为负值表示水下。
- `rotation`：初始姿态。
- `sensors`：挂载的传感器列表，目前包括 `PoseSensor`、`DepthSensor`、`IMUSensor`、`DVLSensor`。

#### 值得调整的参数
- `location`：如果你发现刚启动就贴边或越界，先调这个。
  - 典型用途是把初始深度和轨迹起点对齐。
- `rotation`：如果一启动姿态就明显不对、路径发散，优先检查这里。
- `sensors`：如果某个话题没有数据，先确认传感器是否挂载。

### 3.4 `limits`
- `fin_deg_max`：舵角上限。
- `thrust_min` / `thrust_max`：推力上下限。
- `env_min` / `env_max`：允许活动的环境边界。
- `safety_margin_xy` / `safety_margin_z`：接近边界时的安全余量。

#### 值得调整的参数
- `thrust_min` / `thrust_max`：这是第二个很关键的调参点。
  - 如果推进响应太弱，先看这里有没有把控制量卡死。
  - 如果动作过猛，先别急着改控制器增益，先确认是不是限幅过大。
- `fin_deg_max`：舵机动作上限。
  - 过小会导致转向不灵活。
  - 过大可能导致控制过冲。
- `env_min` / `env_max`：场景边界。
  - 如果航迹经常碰边，先扩边界还是改轨迹，要看你的实验目标。
  - 联调阶段通常保持保守边界，避免误把出界当控制失效。

### 3.5 `control`
- `target_u`：目标航速。
- `u0`：初始参考速度。
- `u_min`：最小允许速度。
- `feedforward_trim_deg`：俯仰前馈补偿。
- `depth`：深度环 PID。
- `pitch`：俯仰环 PID。
- `yaw`：航向环 PID。
- `speed`：速度环 PID 和前馈拟合。

#### 值得调整的参数
- `speed.kp` / `speed.ki` / `speed.kd`：优先级最高。
  - 现象：如果速度长时间达不到目标、或一加速就明显震荡，基本从这里入手。
  - 建议：先调 `kp`，再微调 `ki`，最后才考虑 `kd`。
- `depth.kp` / `depth.ki` / `depth.kd`：第二优先级。
  - 现象：深度跟踪慢、上下摆动大、潜深不稳定，都和它相关。
  - 建议：如果深度环过于“软”，先适度增大 `kp`，再看是否需要小幅增加 `ki`。
- `yaw.kp` / `yaw.ki` / `yaw.kd`：决定转向灵敏度和稳定性。
  - 航向抖动大时，通常先降 `kp` 或增加阻尼。
- `pitch.kp` / `pitch.ki` / `pitch.kd`：影响俯仰响应。
  - 如果俯仰角变化过快或容易冲顶，先看这里。
- `target_u` / `u_min`：
  - 如果巡检任务要求“稳一点”，可稍微降 `target_u`。
  - 如果是高动态场景，才考虑提高。
- `feedforward_trim_deg`：
  - 适合做小范围修正，不建议拿它替代整个控制器调参。

### 3.6 `guidance`
- `lookahead_distance`：前视距离。
- `nearest_search_window`：最近点搜索窗口。
- `cross_track_gain`：横向误差修正增益。

#### 值得调整的参数
- `lookahead_distance`：这是轨迹跟踪最容易直接感受到的参数。
  - 大一点：轨迹更平滑，但拐弯可能偏保守。
  - 小一点：跟踪更“贴线”，但更容易抖。
- `cross_track_gain`：
  - 轨迹偏离大、回线慢，可以适当提高。
  - 轨迹来回摆、修正太激烈，则要降低。
- `nearest_search_window`：
  - 如果轨迹很长或形状复杂，可以加大，避免最近点搜索失败。
  - 但太大也会增加计算量。

### 3.7 `trajectory`
- `kind`：轨迹类型，这里是 `cable_like_3d`。
- `duration`：轨迹时长。
- `dt`：轨迹采样步长。
- `start`：轨迹起点。
- `surge_speed`：纵向推进速度。
- `length`：轨迹长度。
- `lateral_amplitude` / `lateral_wavenumber`：横向摆动幅度与波数。
- `depth_base` / `depth_amplitude` / `depth_wavenumber`：深度变化基线与振幅。
- `min_turn_radius`：最小转弯半径。

#### 值得调整的参数
- `lateral_amplitude`：模拟巡检路径左右摆动程度。
  - 适合用来测试横向控制能力。
  - 太大时会让控制难度显著增加。
- `depth_amplitude`：模拟海缆起伏或任务深度波动。
  - 适合检验深度环与导引耦合能力。
- `min_turn_radius`：
  - 如果轨迹太“尖”，很容易让控制器吃满。
  - 联调时建议先保守一点，保证可控性。
- `surge_speed`：
  - 是任务节奏参数。
  - 如果速度设太高，控制器和传感器延迟都会被放大。

### 3.8 `debug`
- `print_every_n_steps`：每隔多少步打印一次状态。
- `event_print`：是否打印事件类日志。

#### 值得调整的参数
- `print_every_n_steps`：联调排查时建议调小，稳定运行时可调大。
  - 太小会刷屏，太大又不利于定位问题。

### 3.9 `evaluation`
- `rms_threshold_m`：轨迹误差 RMS 阈值。
- `axis_ratio_threshold`：轴向误差比例阈值。
- `sat_ratio_warn_threshold`：饱和比例报警阈值。

#### 值得调整的参数
- 这些更像“验收门槛”，通常不要随意改。
- 只有在场景规模、任务类型、或载具性能发生明显变化时，才考虑重新定义。

### 3.10 `plot`
- `save_main_plot` / `save_sysid_plot`：图像输出文件名。
- `dpi`：主图清晰度。
- `interactive`：是否交互显示。
- `3d`：是否启用 3D 绘图。
- `interactive_dpi`：交互图清晰度。

#### 值得调整的参数
- `interactive`：做批处理时通常保持 `false`。
- `dpi`：如果你要在报告里放图，可以提高，但文件会更大。

### 3.11 `es_ekf_experiment`
- 这是定位/融合算法的独立实验配置，不属于主联调必改项。
- 包含：初始位姿、噪声模型、GPS 门限、DVL 坐标系、航点列表、初始协方差等。

#### 值得调整的参数
- `sigma_acc` / `sigma_gyro` / `sigma_dvl` / `sigma_depth` / `sigma_gps_xy`：这是 EKF 调参的核心。
  - 如果滤波结果太抖，先检查噪声是不是设得过小。
  - 如果滤波过于迟钝，可能是噪声设得过大。
- `gps_depth_gate`：仅在需要模拟浅水/GPS 逻辑时重要。
- `dvl_frame`：决定速度观测在哪个坐标系下解释。
  - 若坐标系不一致，滤波会表现得很怪，这是优先排查项。
- `init_P_diag`：初始不确定性。
  - 如果初始收敛慢，可以适当放大部分状态的初始方差。

## 4. `bridge_params.yaml` 当前结构说明

### 4.1 `stage`
- `name`：桥接阶段名称。
- 一般只用于区分运行场景，不是高频调参项。

### 4.2 `simulation`
- `ticks_per_sec` / `dt`：桥接侧仿真频率。
- `max_steps`：桥接运行上限，`0` 表示无限。

#### 值得调整的参数
- `ticks_per_sec`：这是桥接吞吐量的核心参数。
  - 50 Hz 比较适合当前的传感器发布频率。
  - 如果你要压测 ROS2 和 Zenoh 的稳定性，可以再调高一点；但先确保 CPU 和消息处理跟得上。
- `dt`：与 `ticks_per_sec` 保持匹配。
  - 两者不一致会让日志和时序判断变得混乱。

### 4.3 `agent`
- 与 `sim_params.yaml` 保持一致，避免同一任务下仿真和桥接使用不同载具定义。

#### 值得调整的参数
- `location` / `rotation`：桥接只要与仿真启动位置一致即可，通常不单独改。

### 4.4 `limits`
- 与仿真侧一致，用于保护控制输出。

#### 值得调整的参数
- `fin_deg_max` / `thrust_min` / `thrust_max`：联调时如果经常发现控制信号被夹住，可以先检查这里。

### 4.5 `bridge`
- `rate_hz`：桥接处理频率。
- `cmd_timeout_s`：命令超时时间。
- `require_first_cmd`：是否必须先收到控制命令。
- `default_command`：没有上游命令时使用的默认输出。
- `fin_abs_max` / `thrust_min` / `thrust_max`：桥接输出限幅。
- `max_steps`：桥接步数限制。

#### 值得调整的参数
- `cmd_timeout_s`：这是联调时最容易影响体验的参数之一。
  - 太短：上游稍有抖动就会触发超时。
  - 太长：异常控制能保持太久，不利于安全。
  - 当前 0.5 s 是一个比较平衡的起点。
- `require_first_cmd`：
  - 调试时通常设 `false` 更方便。
  - 如果做安全性验证，可以改为 `true`，验证“无命令不动作”。
- `rate_hz`：
  - 与仿真和 ROS2 节点频率保持一致更容易理解日志。
  - 如果桥接消息积压，优先看这里是否太高。
- `default_command`：
  - 没收到控制时的默认状态，建议保持保守。

### 4.6 `zenoh`
- `session`：Zenoh 会话参数，当前为空表示使用默认配置。
- `downlink_cmd_key`：控制命令下行键。
- `uplink_keys`：传感器数据上行键。

#### 值得调整的参数
- `downlink_cmd_key` / `uplink_keys`：这是最关键的“字段对接点”。
  - 如果 topic 不通，先不要怀疑控制器，先查 key 是否一致。
  - 一旦改名，要确保 sim、bridge、ROS2 三端同步。
- `session`：只有在需要跨机器、跨网络、或定制 Zenoh 网络参数时再动。

### 4.7 `cable_path`
- `points_ned`：电缆路径点，NED 坐标系下的参考点。

#### 值得调整的参数
- 这是任务场景参数，不是底层桥接参数。
- 如果你要复现不同海缆走向，先改这里，而不是改控制器。

### 4.8 `perception`
- `hvdc_current_amp`：电缆电流模型强度。
- `noise`：磁场、DVL、深度噪声。
- `sonar`：声呐采样和峰值形状参数。

#### 值得调整的参数
- `noise.magnetic_sigma`：磁测噪声。
  - 做磁场检测鲁棒性评估时很有用。
- `noise.dvl_sigma` / `noise.depth_sigma`：
  - 是定位/状态融合中最直接影响观测质量的参数。
  - 如果你想看滤波器抗噪性能，就从这里改。
- `sonar.n_bins` / `sonar.max_range_m`：
  - 影响声呐分辨率和探测距离。
  - 做远距离巡检测试时，优先看 `max_range_m`。
- `sonar.peak_gain` / `sonar.peak_width_bins`：
  - 影响声呐回波峰的强弱和宽度。
  - 如果目标识别过“硬”或过“糊”，这两个参数是首选。

## 5. 哪些参数最值得优先调整

按联调价值排序，建议优先调这几类：

1. `control.speed.*`
   - 直接决定速度能不能稳住。
   - 现象最直观，最容易暴露控制问题。

2. `control.depth.*`
   - 决定是否能稳定巡航在目标深度。
   - 深度不稳时，后面的行为树和任务策略都不好看。

3. `guidance.lookahead_distance` 与 `guidance.cross_track_gain`
   - 决定轨迹是否“贴线”、是否振荡。
   - 是轨迹跟踪阶段最实用的一组参数。

4. `trajectory.lateral_amplitude` / `trajectory.depth_amplitude` / `trajectory.min_turn_radius`
   - 决定任务场景有多难。
   - 这是测试控制器能力的“环境旋钮”。

5. `bridge.cmd_timeout_s` / `bridge.rate_hz`
   - 决定桥接是否稳定、是否容易超时。
   - 用于排查“ROS2 看起来没问题，但仿真动作掉了”的情况。

6. `perception.noise.*` 与 `es_ekf_experiment.sigma_*`
   - 决定传感器与滤波器的鲁棒性。
   - 用于做“抗噪能力”测试，而不是普通联调第一步。

## 6. 不建议轻易改的参数

- `stage.name`
- `zenoh.downlink_cmd_key` / `zenoh.uplink_keys`，除非你准备同步改三端
- `simulation.package_name` / `agent.type`，除非你换了场景或模型
- `evaluation.*`，除非你在重新定义验收标准

## 7. 推荐的调参顺序

1. 先保证通路正确：`bridge` topic 通、`/auv/sensors/*` 能出、`/cmd_vel` 能回传。
2. 再调时序：`ticks_per_sec`、`rate_hz`、`cmd_timeout_s`。
3. 再调控制：速度环、深度环、航向环。
4. 最后调任务难度：轨迹振幅、波数、声呐噪声、EKF 噪声。

## 8. 参考命令

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
cat config/sim_params.yaml
cat config/bridge_params.yaml
python3 - <<'PY'
import yaml
from pprint import pprint
with open('config/sim_params.yaml', 'r', encoding='utf-8') as f:
    pprint(yaml.safe_load(f)['control'])
PY
```

## 9. 小结

- `sim_params.yaml` 更像“任务和控制的总开关”，优先看控制、导引、轨迹和边界。
- `bridge_params.yaml` 更像“通信与感知层开关”，优先看 key、频率、超时和噪声。
- 真正最值得调整的参数，通常不是“越多越好”，而是先调少数关键参数把链路跑稳，再逐步扩展任务难度。
