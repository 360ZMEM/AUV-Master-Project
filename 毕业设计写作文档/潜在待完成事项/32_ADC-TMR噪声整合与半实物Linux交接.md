# 32 ADC-TMR 噪声整合与半实物 Linux 交接

> 目的：本文件是 28 号文中“必须实验 2 / 尽量实验 2 / 尽量实验 4”与本轮新增实验包的 Linux 侧交接摘要。Linux 侧继续时优先读本文件，不需要完整通读 28 号文。
> 事实源：`real_experiments/cable_scan/`、`real_experiments/mag_chain_noise/`、`hardware_wrappers/fangkong_adc/raw_data/`、`thuthesis/data/auv-chap05.tex`、`thuthesis/data/auv-appendix-a.tex`。
> 当前平台状态：macOS 侧已完成离线复现、噪声整合、论文表述和图表资产；Linux 侧已完成 ROS2 父层磁观测接入、三模式闭环对照、图源归档和正文回填。

---

## 1. 一句话交接

本轮已经把 TMR8637--SK2301--宿舍环境背景噪声从 `raw_data/*.npz` 中抽成可一键复现的半实物噪声回放包，并把 45 Hz Biot--Savart 联合反演作为必须实验 2 的实物锚点复核完毕。Linux 侧已把 `noise_profile.json` 与两段原始背景记录接入 ROS2 父层磁观测源，在 Direction A 解耦电缆闭环中完成“清洁磁观测 / 协方差匹配高斯噪声 / 实测背景回放”三模式对照。

---

## 2. 已完成内容

### 2.1 必须实验 2：等效通电导线 Biot--Savart 联合反演

复现入口：

```bash
real_experiments/cable_scan/run.sh
```

核心输入：

```text
hardware_wrappers/fangkong_adc/raw_data/1783235358_205719.npz
hardware_wrappers/fangkong_adc/raw_data/relative_pose_log.txt
```

输出目录：

```text
hardware_wrappers/fangkong_adc/raw_data/joint_analysis/1783235358_205719/
```

本轮复跑结果：

| 项目 | 数值 |
|---|---:|
| ADC 三轴样本数 | 106821 |
| ADC 采样率 | 2000 Hz |
| ArUco 位姿帧数 | 832 |
| 锁相/位姿有效配对点 | 777 |
| 锁相频率 | 45.0 Hz |
| 固定模型峰值电流 | 2.614048 A |
| 复 I/Q 自由尺度 \(R^2\) | 0.8792 |
| 复 I/Q 固定电流 \(R^2\) | 0.8711 |
| 自由尺度等效电流 | 2.8789 A |

可写结论：

> 低频交流等效直导线的空间复 I/Q 响应与 Biot--Savart 模型一致；单三轴 TMR 在运动轨迹和位姿辅助下可以形成合成空间阵列，并完成可观测拟合。

边界：

- 不能写成多芯铠装海缆的绝对埋深实物计量。
- 不能写成完整水下 AUV 巡检验收。
- 后续若有滑轨/标尺扫描，只需沿用同一脚本，把位姿或横向位置输入换成可溯源几何真值。

### 2.2 尽量实验 2 / 4：全链路背景噪声整合与 45 Hz 注入回放

复现入口：

```bash
real_experiments/mag_chain_noise/run.sh
```

核心输出：

```text
real_experiments/mag_chain_noise/metrics.json
real_experiments/mag_chain_noise/report.md
real_experiments/mag_chain_noise/data/noise_profile.json
real_experiments/mag_chain_noise/data/record_metrics.csv
real_experiments/mag_chain_noise/data/noise_injection_metrics.csv
real_experiments/mag_chain_noise/figures/
docs/thesis/figures/hardware/mag_chain_noise/
```

默认背景记录：

```text
hardware_wrappers/fangkong_adc/raw_data/1780675809_291477.npz
hardware_wrappers/fangkong_adc/raw_data/1780676130_241387.npz
```

全量审计范围：

```text
hardware_wrappers/fangkong_adc/raw_data/*.npz
```

本轮复跑结果：

| 项目 | 数值 |
|---|---:|
| raw data 审计记录数 | 17 |
| 默认背景记录数 | 2 |
| 默认背景总时长 | 13.104 s |
| 45 Hz 向量锁相中位幅值 | 2.584 nT |
| 50 Hz 向量锁相中位幅值 | 169.284 nT |
| 80--300 Hz 矢量 ASD 中位数 | 0.133 nT/\(\sqrt{\mathrm{Hz}}\) |
| 线性去趋势后三轴矢量 RMS | 149.825 nT |

45 Hz Biot--Savart 注入回放：

| 背景记录 | 窗口数 | 清洁目标峰值 | 实测回放 RMSE | 协方差高斯 RMSE | 实测回放误差/峰值 |
|---|---:|---:|---:|---:|---:|
| `1780675809_291477.npz` | 59 | 2326.8 nT | 0.792 nT | 4.307 nT | 0.034% |
| `1780676130_241387.npz` | 164 | 2552.2 nT | 0.271 nT | 1.290 nT | 0.011% |

可写结论：

> 真实 ADC--TMR 全链路背景噪声已经可以作为观测层回放输入进入仿真链；45 Hz 受控目标频率能够与宿舍环境中的 50 Hz 工频项分离，并被同一锁相接口消费。

边界：

- 这是非屏蔽宿舍环境采集，不是实验室级本底噪声计量。
- 50 Hz 分量应写成环境工频干扰项。
- 45 Hz 是受控目标频率，沿用 `AUV-Master-Mag` 的避工频口径。
- 该实验支撑半实物噪声回放，不支撑“完整 AUV 实测闭环已完成”的表述。

### 2.3 AUV-Master-Mag 子仓验证

macOS 侧验证命令：

```bash
/tmp/auv-mag-py314-venv/bin/python -m unittest discover -s tests
/tmp/auv-mag-py314-venv/bin/python main_demo.py --case case3 --no-viz
```

结果：

- `unittest discover -s tests`：145 个用例全绿。
- `case3 --no-viz`：完成 200 s 高噪声无图仿真，最终 `track` 模式，最终置信度 1.00，捕获峰值 55 个。

环境备注：

- `AUV-Master-Mag` 需要 Python 3.10+，因为源码使用 PEP 604 类型标注。
- macOS 系统 Python 3.9 会在 `ProbeBurstThresholds | None` 这类标注处失败；这是环境问题，不是算法断言失败。
- Linux 侧建议使用 Python 3.10/3.11/3.12，并安装 `AUV-Master-Mag/requirements.txt` 与测试用 `pytest`。

---

## 3. 论文已同步位置

正文位置：

```text
thuthesis/data/auv-chap05.tex
```

已新增内容：

- §5.6.2 附近补入 ADC 子链与全链路噪声的衔接说明。
- 新增表 `tab:ch05-mag-chain-noise-replay`，题名为“ADC--TMR 全链路背景噪声回放与 45 Hz 半实物注入验证”。
- 表内已写明默认背景源、45/50 Hz 频率分离、宽带背景量级和半实物注入结果。

附录位置：

```text
thuthesis/data/auv-appendix-a.tex
```

已新增证据条目：

- `ADC--TMR 全链路宿舍背景回放`
- 写入 2 段默认背景、17 段 raw data 全量审计、45 Hz/50 Hz 锁相指标和注入 RMSE。

论文构建状态：

```bash
cd thuthesis
gtimeout 300 latexmk -g auv-thesis
```

结果：

- 构建成功。
- `auv-thesis.pdf` 为 173 页。
- 日志未发现 undefined reference、LaTeX Warning、Overfull hbox 或 Overfull vbox。

---

## 4. Linux 侧最短复跑顺序

进入仓库根目录后先复跑离线证据：

```bash
bash real_experiments/cable_scan/run.sh
bash real_experiments/mag_chain_noise/run.sh
```

预期输出关键行：

```text
对齐点数: 777
复 I/Q 无几何先验: R2=0.8792
复 I/Q 固定电流: R2=0.8711
[mag-chain-noise] records: 17
[mag-chain-noise] total background duration: 13.104 s
[mag-chain-noise] median 45 Hz lock-in: 2.584 nT
[mag-chain-noise] median 50 Hz lock-in: 169.284 nT
```

然后复跑 `AUV-Master-Mag`：

```bash
cd AUV-Master-Mag
python3 -m pip install -r requirements.txt pytest
python3 -m unittest discover -s tests
python3 main_demo.py --case case3 --no-viz
```

如果 Linux 默认 `python3` 不是 3.10+，先切换虚拟环境。不要为了通过 macOS 3.9 改子仓源码。

---

## 5. ROS 父层建议接入点

优先接入位置：

```text
brain_linux/src/auv_control/auv_decision_ros/decoupled_cable_sim_node.py
```

理由：

- 该节点已经发布 `/auv/sensors/magnetic`。
- `_publish_magnetic()` 当前先用 `compute_biot_savart_hvdc(...)` 生成清洁磁场，再发布 `sensor_msgs/MagneticField`。
- 下游 `cable_tracking_node.py` 已消费 `/auv/sensors/magnetic` 并转换为 nT block，因此上游只要保持话题和单位不变，下游不用改接口。

推荐最小改动：

1. 在 `decoupled_cable_sim_node.py` 增加参数：

```text
mag_noise_mode: none | covariance_gaussian | measured_replay
mag_noise_profile_path: real_experiments/mag_chain_noise/data/noise_profile.json
mag_noise_npz_paths:
  - hardware_wrappers/fangkong_adc/raw_data/1780675809_291477.npz
  - hardware_wrappers/fangkong_adc/raw_data/1780676130_241387.npz
mag_noise_seed: 20260821
```

2. 加一个小型噪声源类，不改变 ROS 消息结构：

```text
MeasuredMagNoiseReplay
  - 读取 NPZ 的 voltage、sample_rate_hz、sensitivity_mv_per_ut
  - voltage -> magnetic_ut -> magnetic_t
  - 每轴去均值或线性去趋势
  - 按仿真磁发布频率重采样或索引循环
  - 返回 3 轴 Tesla 噪声样本
```

3. 在 `_publish_magnetic()` 中保持原真值生成不变，只在发布前叠加噪声：

```text
b_ned_t = clean_biot_savart_field_t + replay_noise_t
```

4. 记录元数据：

```text
noise_mode
noise_source_npz
noise_profile_sha256 或 metrics.json 摘要
sample_index / replay_phase
```

接入注意：

- 噪声只能进入量测副本，不能修改电缆真值、地形真值、流场真值或位姿真值。
- 单位保持 Tesla；`cable_tracking_node.py` 内部会乘 `1e9` 转 nT。
- 真实噪声记录只有 13.104 s，闭环仿真若长于该时长必须显式写成循环回放。
- 先在 `decoupled_cable_sim_node.py` 接入；确认闭环指标后，再考虑是否扩展到 HoloOcean/PVS 原生磁观测生成器。

备选接入位置：

```text
brain_linux/src/auv_control/auv_decision_ros/magnetic_sensor_wrapper_node.py
```

适用场景：

- 想把“实测噪声回放”伪装成一个磁传感器 wrapper 模式。
- 需要同时发布 `/auv/sensors/magnetic_block`。

不作为首选的原因：

- wrapper 更接近真机硬件接入层；当前任务要验证仿真观测链的噪声注入，先改 `decoupled_cable_sim_node.py` 更小。

---

## 6. Linux 侧验证矩阵

第一层：ROS 话题与单位门禁

| 检查 | 通过标准 |
|---|---|
| `/auv/sensors/magnetic` 有持续输出 | 频率接近 `mag_rate_hz` |
| 单位 | Tesla，进入 `cable_tracking_node.py` 后为 nT block |
| clean/noisy 双模式 | `mag_noise_mode=none` 与 `measured_replay` 可切换 |
| 回放元数据 | 运行日志或 JSON 中可追溯到两个 NPZ 文件 |

第二层：状态估计对照

| 模式 | 目的 |
|---|---|
| `covariance_gaussian` | 与已有 R19 协方差匹配高斯口径一致 |
| `measured_replay` | 保留真实相关噪声、相位结构与 50 Hz 环境项 |

建议指标：

- distance RMSE
- distance p95
- z RMSE
- mag NIS mean / p95 / std
- seed 间标准差
- 回放周期与相位 seed

第三层：控制闭环对照

建议复用现有 UA-MPC / R22 因子矩阵口径，只新增一个噪声因子：

```text
mag_noise_mode = gaussian | measured_replay
```

必须保持其它因子不变：

- 电缆中心线真值不变。
- 地形/埋深真值不变。
- 横流真值不变。
- 控制器参数不变。

建议指标：

- 横向 p95
- 最小净空
- 回退次数
- 安全违规次数
- 控制变化率 RMS
- 求解耗时 p95/max

### 6.1 Linux 侧已完成的 ROS2 对照

落地入口：

```text
real_experiments/mag_chain_noise_ros/run.sh
scripts/run_direction_a_decoupled_cable_sim.sh
brain_linux/src/auv_control/auv_decision_ros/decoupled_cable_sim_node.py
brain_linux/src/auv_control/auv_decision_ros/mag_noise_replay.py
```

本次实跑采用 Direction A 解耦电缆闭环作为 ROS2 父层接入门禁，三臂各 20 s，前 4 s 作为 warmup 剔除；噪声只进入 `/auv/sensors/magnetic`，电缆、地形、流场、先验和控制参数保持不变。结果文件：

```text
real_experiments/mag_chain_noise_ros/metrics.json
real_experiments/mag_chain_noise_ros/data/summary.csv
real_experiments/mag_chain_noise_ros/report.md
docs/thesis/figures/experiments/mag_chain_noise_ros/mag_chain_noise_ros_comparison.png
docs/thesis/figures/experiments/mag_chain_noise_ros/mag_chain_noise_ros_comparison.pdf
docs/thesis/figures/experiments/mag_chain_noise_ros/_SOURCE.md
```

| 模式 | 横偏 p95/m | 平均置信度 | 噪声 p95/nT | 先验接受率 | 控制变化率 RMS |
|---|---:|---:|---:|---:|---:|
| `none` | 7.762 | 0.8472 | 0.0 | 1.00 | 0.06319 |
| `covariance_gaussian` | 7.766 | 0.8473 | 268.1 | 1.00 | 0.06329 |
| `measured_replay` | 7.767 | 0.8477 | 180.0 | 1.00 | 0.06346 |

判读：实测背景回放已经能以可追溯 metadata 进入 ROS2 闭环；在当前同配置门禁中，它主要改变观测噪声幅值与回放相位结构，没有改变闭环主导状态和安全边界结论。由于该轻量场景保留大横偏初始几何且未注入埋深方差，`industrial_ready` 与 `industrial_acceptance_pass` 均为 0，不作为行业验收通过率实验。

---

## 7. 可直接采用的论文措辞

保守正文表述：

> 为进一步缩小纯参数化噪声与实物采集链之间的差距，本文将 TMR8637--SK2301 全链路背景记录整理为可回放噪声源，并在 45 Hz 等效直导线磁场上完成半实物注入验证。该结果说明真实采集链噪声已能够以观测层输入形式进入仿真闭环；但由于记录来自非屏蔽宿舍环境，50 Hz 工频项显著，该实验只作为压力测试和半实物输入依据，不作为实验室级本底噪声计量。

Linux 完成 ROS2 父层闭环后采用：

> 在 ROS2 父层闭环中，本文进一步对比了清洁磁观测、协方差匹配高斯噪声与 ADC--TMR 实测背景回放三种磁观测输入。结果表明，在保持电缆、地形、流场、先验和控制器参数不变的条件下，实测回放能够以带来源、哈希和回放相位的 metadata 进入磁观测话题；在当前 Direction A 解耦闭环门禁中，该输入主要改变观测噪声幅值和短时相位结构，而未改变主线安全边界结论。

答辩口径：

> 我没有把宿舍噪声写成实验室噪声底，而是把它作为包含传感器、ADC、供电、接线和环境干扰的全链路压力输入。45 Hz 目标频率避开了 50 Hz 工频干扰，使同一套锁相接口可以同时服务等效导线实验和仿真观测回放。

---

## 8. 不应做的写法

- 不写“完成真实海缆埋深标定”。
- 不写“完成 AUV 水下实测闭环”。
- 不写“宿舍背景记录代表实验室本底噪声”。
- 不把 50 Hz 工频干扰当成目标激励。
- 不把实测噪声注入到真值层。
- 不为这一部分回写 `docs/thesis/paper/*.md`，当前论文事实源是 LaTeX。

---

## 9. Linux 完成后的回填清单

Linux 侧已完成 ROS 父层接入，回填文件如下：

```text
real_experiments/mag_chain_noise_ros/
  README.md
  config.yaml
  run.sh
  metrics.json
  report.md
  data/
  figures/
```

论文图源已落地：

```text
docs/thesis/figures/experiments/mag_chain_noise_ros/
```

论文已写回位置：

```text
thuthesis/data/auv-chap05.tex
```

已在当前 `tab:ch05-mag-chain-noise-replay` 后新增 ROS2 闭环对照表 `tab:ch05-mag-chain-noise-ros` 与图 `fig:ch05-mag-chain-noise-ros`，未重排第 5 章结构。

验收门禁：

```bash
cd thuthesis
timeout 300 make auv-thesis
```

检查项：

- PDF 构建通过。
- 无未定义引用。
- 无新增 overfull。
- 表述仍保持“半实物回放 / 压力测试”边界。
