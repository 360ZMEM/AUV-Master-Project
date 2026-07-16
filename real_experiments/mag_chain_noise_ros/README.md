# ADC-TMR 实测背景噪声 ROS 闭环对照

本目录是 32 号交接文档要求的 Linux 侧落地点：把 Mac 侧整理出的
`real_experiments/mag_chain_noise/data/noise_profile.json` 与两段 ADC-TMR
背景 NPZ 接入 ROS2 Direction A 解耦电缆闭环。

## 一键运行

```bash
bash real_experiments/mag_chain_noise_ros/run.sh
```

默认三臂：

- `none`：干净 Biot-Savart 磁观测；
- `covariance_gaussian`：使用同一背景记录协方差生成高斯噪声；
- `measured_replay`：循环回放两段实测背景噪声。

默认运行时长为 30 s，可用环境变量覆盖：

```bash
AUV_MAG_NOISE_ROS_DURATION=20 bash real_experiments/mag_chain_noise_ros/run.sh
```

若只跑某个模式：

```bash
AUV_MAG_NOISE_ROS_MODES="measured_replay" bash real_experiments/mag_chain_noise_ros/run.sh
```

## 输入

- 噪声 profile：`real_experiments/mag_chain_noise/data/noise_profile.json`
- 默认背景记录：
  - `hardware_wrappers/fangkong_adc/raw_data/1780675809_291477.npz`
  - `hardware_wrappers/fangkong_adc/raw_data/1780676130_241387.npz`
- ROS 闭环入口：`scripts/run_direction_a_decoupled_cable_sim.sh`
- 跟踪配置：`brain_linux/config/cable_tracking_direction_a.yaml`

## 输出

- `data/run_index.csv`：每个模式的原始 run、bag 与抽取产物索引；
- `data/summary.csv`：每个模式的横偏、置信度、噪声幅值与控制指令变化率摘要；
- `metrics.json`：机器可读完整汇总；
- `report.md`：论文/交接可读报告；
- `figures/mag_chain_noise_ros_comparison.{png,pdf}`；
- `docs/thesis/figures/experiments/mag_chain_noise_ros/`：论文图源副本与 `_SOURCE.md`。

原始 rosbag 默认写入：

```text
${AUV_DATA_ROOT:-results}/mag_chain_noise_ros/<timestamp>/<mode>/<run_id>/rosbag/
```

## 边界

- 噪声只叠加到 `/auv/sensors/magnetic` 的量测副本，不修改电缆、地形、流场或位姿真值。
- `measured_replay` 会在仿真时长超过 13.104 s 时循环回放，报告中保留 replay phase 和 sample index。
- 该实验是半实物观测回放/压力测试，不是完整 AUV 水下实测闭环。
