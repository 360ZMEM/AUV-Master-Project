# ThuThesis 全量图片统一与可复现审计计划

## 1. 目标与成功标准

本计划只覆盖 `thuthesis/auv-thesis.tex` 实际纳入的 `auv-chap*.tex` 正文图片，不处理仓库中未被论文引用的历史输出。当前共 44 幅：

- 30 幅程序绘图（Matplotlib 或基于 Matplotlib 的示意图）；
- 10 幅 draw.io 架构图；
- 2 幅 Foxglove/系统界面截图；
- 2 幅 TMR8637 报告扫描件。

执行状态（2026-08-23）：本轮 44 幅正文图的来源登记、Mac/Linux 分流、统一重绘、严格校验、正文 PDF 接入和 188 页论文视觉验收均已完成。

完成标准：

1. 每幅正文图片均有明确的输出文件、生成源、输入数据、复现命令、平台约束和论文引用位置。
2. 30 幅程序图统一使用 3.3 inch 单栏或 6.8 inch 通栏宽度、中文标注、STIX 数学字体、固定色盲友好语义色、轻量主网格和统一导出接口。
3. 不改变数据处理、实验数据、数值结论和算法关系；仅调整可视化层和必要的“从归档中间结果重绘”入口。
4. 10 幅 draw.io 图保持技术语义和数据流不变，画布不超过 1650 px，字号维持四级以内，连接线不穿过节点，无明显交叉或遮挡。
5. Matplotlib 图优先生成 PDF，同时保留 600 dpi PNG 供审计；论文改用 PDF。截图和扫描件保留原始栅格证据。
6. 在 macOS 上重绘所有具备仓内数据或确定性模型的图；缺少原始 Linux 数据的图明确交接，不以 PDF 反向描线或手工伪造数据。
7. 完整构建 `thuthesis/auv-thesis.pdf`，逐页检查图片、图注、页边界、字体和元素遮挡。

## 2. 当前状态审计

### 2.1 已有统一能力

- `tools/thesis_plot_style.py` 已提供基础颜色、字体和 `save_figure()`，但当前字号偏大、固定 `figsize` 不符合 3.3/6.8 inch 规范，且多数旧脚本未接入。
- macOS 已安装 `/Applications/draw.io.app`，可用 CLI 导出 PDF/SVG/PNG。
- XeLaTeX、latexmk、pdftoppm、pdfinfo 可用。
- macOS 可用中文字体为 `Songti SC`、`STSong`、`PingFang SC`；数学字体可用 `STIXGeneral`。
- NumPy 已验证可无 pickle 读取正文相关 NPZ：
  - `hardware_wrappers/fangkong_adc/raw_data/1780675809_291477.npz`
  - `hardware_wrappers/fangkong_adc/raw_data/enob/20260809T161036/ch4_enob_capture.npz`
  - `hardware_wrappers/fangkong_adc/raw_data/joint_analysis/1783235358_205719/aligned_timeseries.npz`
- 正文相关 CSV/JSON/Markdown 均可在 macOS 以 UTF-8 读取。

### 2.2 Matplotlib 图族与来源

| 图族 | 正文输出 | 生成源 | 数据源 | Mac 状态 |
|---|---|---|---|---|
| 磁场物理 3 图 | `docs/thesis/figures/magnetics/*` | `tools/independent/plot_*field*.py` | 确定性解析/数值模型 | 可直接重绘 |
| 海缆感知方法 2 图 | `docs/thesis/figures/architecture/cable_*.pdf` | `tools/render_cable_*_figure.py` | 图内常量/结构定义 | 可直接重绘 |
| ES-EKF 灵敏度 | `experiments/state_estimation/eskf_param_sensitivity.*` | `tools/plot_es_ekf_sensitivity.py` | `results/tuning/ekf_comprehensive/tuning_report.md` | 可直接重绘 |
| 地形跟踪 2 图 | `terrain_following/terrain_*.pdf` | `tools/plot_terrain_following_figures.py` | Linux MCAP + 仓内 summary | 原始时序缺失，需 Linux |
| R13 控制 3 图 | `experiments/control/r13_v2_*.{png,pdf}` | `tools/plot_r13_v2_formal_audit.py` | `results/control_aggregates/20260810_r13_v2_full/` | 使用 `--skip-mcap` 可重绘 |
| 海缆验收评分卡 | `cable_acceptance/cable_dlt1278_scorecard_fresh1.*` | `tools/plot_cable_dlt1278_scorecard.py` | `results/cable_ops_report/.../inspection_summary.json` | 可直接重绘 |
| PVS 闭环恢复 2 图 | `cable_acceptance/pvs_closedloop_*.{png,pdf}` | `tools/plot_pvs_closedloop_recovery.py` | `results/cable_ops_report/closedloop_e2e/` | 可直接重绘 |
| PC104 时序 1 图 | `hardware/pc104_timing/*` | `tools/plot_pc104_firmware_echo_timing.py` | 仓内 timing CSV/JSON | 可直接重绘 |
| PC104 故障 1 图 | `hardware/pc104_fault_injection/*` | `tools/plot_pc104_fault_injection.py` | 仓内 formal bundle | 可直接重绘 |
| PC104 跨层 2 图 | `hardware/pc104_cross_layer/*` | `tools/plot_pc104_cross_layer_evidence.py` | 仓内 cross-layer bundle | 可直接重绘 |
| Jetson MPC | `real_experiments/jetson_realtime/figures/*` | `run_jetson_realtime.py --existing` | 仓内已归档 CSV/JSON | 可直接重绘，不重跑硬件 |
| ADC ENOB 2 图 | `hardware/adc_enob/*` | 原生成脚本未入库 | ENOB NPZ + JSON | 新增只读重绘脚本后可重绘 |
| ADC-TMR ROS 对照 | `experiments/mag_chain_noise_ros/*` | `analyze_mag_noise_ros_run.py` | 原始 `/auv_data` 缺失；仓内 `summary.csv` 完整 | 增加 summary-only 后可复刻图 |
| 磁外参残差 | `mag_lever_arm_fullflow.../*` | `tools/plot_mag_extrinsics_validation.py` | 仓内 residual CSV/summary JSON | 可直接重绘 |
| 磁联合分析 2 图 | `experiments/magnetic_joint/*` | `joint_biot_savart_analysis.py` | 仓内 aligned NPZ/fit JSON | 增加 render-only 后可复刻图 |
| BT/FSM 2 图 | `decision_bt_vs_fsm/*` | `tests/benchmark_bt_vs_fsm.py` | 仓内源码及已归档 benchmark JSON | 以归档结果重绘，避免重跑实验改变数值 |
| 归一化覆盖 | `coverage/normalized_coverage_time_tradeoff.*` | `tools/normalized_coverage_sweep.py` | 确定性参数扫描 | 可直接重绘 |
| MPC 控制摘要 | `control_mpc/05_mpc_combined_summary.*` | `tools/mpc_test.py` | PVS 确定性仿真 | 安装 PVS 后重绘 |
| PID/PVS 对比 | `control_pid_pvs/05_pid_pvs_profile_comparison.*` | `tools/pid_pvs_tracking_plots.py` | PVS 确定性仿真 | 安装 PVS 后重绘 |

### 2.3 draw.io 图族

正文引用 10 幅：

- `auv_system_autonomy_functional_loop`
- `auv_system_verification_deployment_ladder`
- `auv_thesis_technical_route`
- `auv_v2_behavior_tree_illustration`
- `auv_v2_dual_brain_async_hardware`
- `auv_v2_emergency_transition`
- `auv_v2_five_layer_functional_architecture`
- `auv_v2_mission_lifecycle_flow`
- `auv_v2_mission_state_machine`
- `auv_v2_uncertainty_highway`

其中 9 幅由 `docs/thesis/figures/architecture/generate_architecture_diagrams.py` 生成；技术路线图保留独立 `.drawio` 权威源。当前画布为 1380--1580 px，尺寸合规；主要问题是连接线宽 2.4/3.2 px 偏粗、单图辅助色数量偏多，以及源文件时间晚于部分导出文件，需要重新导出并验收。

### 2.4 非程序证据图

- `docs/thesis/figures/system/foxglove_*.png`：系统界面证据，只核对源记录、清晰度和论文版面，不翻译或重绘界面内容。
- `docs/thesis/figures/hardware/tmr8637_test_report/*.jpg`：厂家报告扫描证据，只核对裁切、可读性、出处和引用，不改变扫描内容。

## 3. 实施方案

### 3.1 Python 环境

1. 使用 Python 3.14 创建仓库本地 `.venv`（已由 `.gitignore` 忽略）。
2. 安装并记录：`numpy`、`matplotlib`、`scipy`、`pandas`、`pyyaml`、`pillow`、`mcap`、`mcap-ros2-support`、`rosbags`。
3. 尝试从固定 Git 提交安装 `PythonVehicleSimulator`；若上游不兼容 Python 3.14，则建立 Python 3.12 环境或将该项转入 Linux 清单，不修改 PVS 数值模型。
4. 新增 `requirements-thesis-figures.txt`，版本取实际验证成功值。

### 3.2 统一 Matplotlib 样式

修改 `tools/thesis_plot_style.py`：

- 提供 `SINGLE_COLUMN_WIDTH = 3.3`、`FULL_WIDTH = 6.8` 和受控高度函数，宽高比默认不低于 1.4。
- 单栏：label 9 pt、tick/legend 8 pt；通栏：label 10 pt、tick/legend 9 pt。
- 中文字体按 `Songti SC -> STSong -> Noto Serif CJK SC -> SimSun -> WenQuanYi Zen Hei` 检测；数学字体固定 STIX。
- 语义色固定为：
  - Proposed/Ours `#0072B2`
  - Baseline 1 `#E69F00`
  - Baseline 2 `#009E73`
  - Baseline 3 `#7E57C2`
  - Reference `#333333`
  - Error/Warning `#D55E00`
- 主线 1.7 pt、次线 1.4 pt、轴框 0.9 pt、marker 4.5 pt。
- 仅启用轻量 major grid；统一图例顺序、简洁 frame、中文物理量与标准单位。
- `save_figure()` 同时输出矢量 PDF 和 600 dpi PNG，使用 `bbox_inches="tight"`。

逐个迁移 21 个活跃绘图入口，只改布局、显示文本、颜色、线型、字号、单位、图例和导出，不改数据计算。多子图统一 `(a)`、`(b)`、`(c)` 标识；删除重复大标题，将主要说明留给 LaTeX caption。

### 3.3 来源 manifest 与一键重绘

新增：

- `docs/thesis/figures/thesis_figure_manifest.json`
- `tools/render_thesis_figures.py`
- `tools/validate_thesis_figures.py`

manifest 每项包含：

- `id`、`chapter`、`latex_source`
- `output_pdf`、`output_png`
- `kind`：`matplotlib` / `drawio` / `screenshot` / `scan`
- `generator`、`inputs`、`command`
- `reproducibility`：`mac_full` / `mac_render_only` / `linux_required` / `evidence_only`
- `expected_width`、`language_policy`、`notes`

渲染器提供：

- `--check`：只检查输入、依赖、输出和平台；
- `--render mac`：重绘 macOS 可完成项；
- `--render drawio`：生成并导出 draw.io；
- `--id ...`：重绘单图族；
- Linux 项默认跳过并给出明确原因，不能静默使用旧输出。

校验器从 `auv-chap*.tex` 反查图片，保证 44 幅全部被 manifest 覆盖；检查缺文件、重复源、PNG 分辨率、PDF 页面尺寸、英文显示文本白名单和 draw.io 画布/字号/线宽。

### 3.4 补齐缺失的只读重绘入口

1. 新增 `hardware_wrappers/fangkong_adc/scripts/plot_enob_results.py`，只读取现有 ENOB NPZ/JSON，复刻 ENOB-OSR 和噪声谱密度图。
2. 为 `analyze_mag_noise_ros_run.py` 增加 `--summary-csv`，从已归档汇总值重绘；不声称完成原始 ROS 数据再分析。
3. 为 `joint_biot_savart_analysis.py` 增加从 `aligned_timeseries.npz` 与 `fit_summary.json` 重绘的入口。
4. 为 `benchmark_bt_vs_fsm.py` 增加 `--render-existing`，读取原 benchmark JSON，仅重绘论文采用的 03/04 图。
5. 将 `tools/mpc_test.py` 的 `/auv_data` 默认输出改为 CLI 可覆盖且默认仓库结果目录；不改变仿真模型。

### 3.5 draw.io 归一化

修改 `generate_architecture_diagrams.py` 与必要的 `.drawio` 源：

- 普通图 1400x800 左右，复杂图不超过 1600x1000；
- L1/L2/L3/L4 分别约 22/19/16/14；
- 主连接 1.8 px，强调连接不超过 2.0 px；
- 中文宋体，必要缩写保留英文；
- 感知浅蓝、信号处理浅青、估计浅橙、控制浅绿、硬件浅灰、环境白底灰线；
- 正交连接优先，重新布线消除穿节点、交叉和文字压线；
- 不新增渐变、阴影、3D、图标或装饰。

使用 draw.io CLI 从 `.drawio` 同步导出 PDF、SVG、PNG，运行现有 `validate_drawio_architecture.py` 和新增 manifest 校验。

### 3.6 论文接入

- 将所有可重绘 Matplotlib 图的 `\includegraphics` 改为 PDF。
- 截图和扫描件保持 PNG/JPG。
- 不改变正文结论；仅在文件扩展名、必要的 caption 中英文一致性和版面高度上做小改。
- 完整构建后检查图表页是否独占、越界、遮挡、文字过小或图注分离。

## 4. Linux/ROS2 必须完成的边界

### 4.1 地形跟踪 2 图：必须 Linux

Mac 缺少以下原始 MCAP；仓内 `bag_path.txt` 指向 `/auv_data/...`，只有汇总统计不足以重建时序和三维轨迹：

- `terrain_tz_tracking_pid_mpc.pdf`
- `terrain_3d_pid_terrain_trajectory.pdf`

Linux 执行要求：

```bash
source /opt/ros/humble/setup.bash
source brain_linux/install/setup.bash
python3 tools/render_thesis_figures.py \
  --id ch05_terrain_tz \
  --id ch05_terrain_3d \
  --render linux
python3 tools/validate_thesis_figures.py \
  --id ch05_terrain_tz \
  --id ch05_terrain_3d
```

验收：

- 必须读取 manifest 记录的 MCAP SHA256；
- 数值轨迹、采样点和统计量与旧图一致；
- 仅显示层变化；
- 输出 PDF + 600 dpi PNG；
- 不允许从旧 PDF 反向描线。

### 4.2 ADC-TMR ROS 原始分析链：Linux 才能重算，Mac 可重绘

Mac 缺少三组 `/auv_data/mag_chain_noise_ros/.../tracking.jsonl` 与 MCAP。Mac 只从仓内 `summary.csv` 重绘相同统计值。若要审计“原始数据 -> 指标 -> 图”的完整链路，Linux 执行：

```bash
source /opt/ros/humble/setup.bash
source brain_linux/install/setup.bash
python real_experiments/mag_chain_noise_ros/scripts/analyze_mag_noise_ros_run.py \
  --run-index real_experiments/mag_chain_noise_ros/data/run_index.csv \
  --output-dir real_experiments/mag_chain_noise_ros
python3 tools/validate_thesis_figures.py --id ch05_mag_noise_ros
```

验收时比较新旧 `summary.csv`，所有论文使用指标必须在预设数值容差内一致。

### 4.3 PVS 兼容性兜底

优先在 macOS 安装并运行 `PythonVehicleSimulator`。只有上游依赖不支持可用的 macOS Python，才将 MPC/PID 两图转为 Linux：

```bash
source .venv/bin/activate
python tools/render_thesis_figures.py --id control_mpc --render linux
python tools/render_thesis_figures.py --id control_pid_pvs --render linux
```

不得使用手工平滑、抽样或旧图数字化替代 PVS。

### 4.4 Linux 执行记录（2026-08-23，深度控制复核后）

1. **执行边界**
   - Linux 新接手 `ch04_pid_pvs`、`ch05_terrain_tz` 与 `ch05_terrain_3d`，因为三者分别依赖 PVS 和最新 ROS2 MCAP/sidecar。
   - 当前图 5.4 是 R13-v2 三联图，不是地形轨迹；仅按用户明确要求把三个源图的 legend 改为不透明白底，数据和结论未改。
   - 其余 `mac_full`、`mac_render_only`、draw.io、截图和扫描件不在 Linux 侧重绘。
2. **正式地形 MCAP 与 sidecar 固化**
   - 结果目录：`results/control/terrain_following_20260823_215036`。
   - PID terrain MCAP SHA256：`0ea51e9f49a7b4675e176c3c11ab197f6e1443480a652043a34fb56d6da1f407`。
   - MPC terrain MCAP SHA256：`e465d0b9cf80b54e77693b5654d6ef9f4dbeea1021603404206793b4e65a5014`。
   - PID/MPC sidecar SHA256：`51989db27eb0c1ad3788c452aaf6ccb50f62bdf2e1acf70dc6a138698af5fe42` / `d8d8689858d4d1cfe2a72aa109462400d5d50d61874e0d9e36da4980778b2cdb`。
   - manifest 定向渲染前强制复核上述哈希与 terrain YAML 哈希，不匹配即终止。
3. **执行链与结果**
   - 四相统一使用 `/auv/control/mpc_cmd → arbiter → 0xEE → PVS depthHeadingAutopilot`；PID 与 MPC 共用同一 PVS 内层。
   - PID/MPC terrain 的净空 RMSE 为 `0.419/0.605 m`，最小净空为 `2.2/1.7 m`，低于 1.5 m 的比例均为零。
   - 相对 PVS 可行参考 `z_d` 的 RMSE 为 `0.217/0.197 m`；MPC fallback 为零，terrain 求解耗时 p95 为 `13.10 ms`。
4. **PVS 默认迟钝与显示层修复**
   - 严格原生默认参数 `Kp_z=0.1`、`wn_d_z=0.02 rad/s`、`deltaMax=15 deg`；任务匹配 profile 与 adapter-local anti-windup 不修改上游 PVS 源码。
   - 图 4.7 已改用严格原生默认基线；深度阶跃/正弦 RMSE 由 `3.491/1.132 m` 降至 `1.453/0.202 m`。
   - 图 5.2 显示海底、3 m 几何目标、实际下发命令、PVS `z_d` 和 AUV 真值深度五层信号；legend 使用白色不透明底和灰边框。
   - 图 5.3 使用 PVS 真值轨迹；重建海床与 DVL 沿程海床校核为 `r=1.00`、RMS `0.03 m`。旧滤波轨迹的近常量偏置不再混入图中。
5. **论文级验收**
   - manifest 对 `ch04_pid_pvs`、`ch05_terrain_tz`、`ch05_terrain_3d` 的源哈希校验与自动重绘通过。
   - 清除跨平台不兼容辅助文件后，Linux TeX Live/Biber 完成 188 页 A4 PDF 构建；最终日志无 undefined command/citation/reference、float too large 或 overfull。
   - 图 4.7、表 5.8、图 5.2、图 5.3 分别位于正文第 82、96、97、98 页，图表与图注同页且无裁切、越界或遮挡。

### 4.5 最终跨平台边界

- 图 5.2、图 5.3 与表 5.8 的执行链、数据和显示层已收口，无需再次重跑。
- 当前四相仍为每相 `n=1`。如要把调优后的原生 PVS 配置写成稳健统计结论，PID/MPC terrain 至少各补三次重复；既有低/中/高三档多种子矩阵使用 `kinematic_setpoint` 后端，不能替代该重复。
- ADC--TMR 原始链保持既有哈希审计结论；Mac 可继续从冻结 `summary.csv` 做确定性重绘。
- 除图 5.4 legend 的明确样式修复外，不覆盖 Mac 侧其他已完成图件。

## 5. 验证步骤

1. `python tools/validate_thesis_figures.py --check-sources`
2. `python tools/render_thesis_figures.py --check`
3. `python tools/render_thesis_figures.py --render mac`
4. 数值快照对比：绘图前后输入文件 SHA256 不变，关键统计 JSON/CSV 不变。
5. `python docs/thesis/figures/architecture/validate_drawio_architecture.py`
6. `python -m py_compile` 检查所有修改脚本。
7. `git diff --check`
8. `cd thuthesis && make auv-thesis`
9. 检查 LaTeX 日志无 undefined reference、float too large、图片缺失。
10. 将 PDF 图片页渲染为审计 PNG，检查：
    - 最终插入尺寸文字清晰；
    - 中文和必要英文缩写一致；
    - 图例不遮挡数据；
    - 子图、单位和线型一致；
    - 无裁切、越界、叠字、箭头穿节点；
    - 灰度下仍可通过线型、边框和标签区分。

### 5.1 macOS 最终执行记录（2026-08-23）

1. `.venv/bin/python tools/render_thesis_figures.py --render mac` 成功处理 38 个 `mac_full`、`mac_render_only` 与 draw.io 条目；2 个 Linux 条目和 4 个证据图按 manifest 分类处理。
2. 重绘后关键数值保持不变：三相中心窗口 RMS 最大偏差 `1.545%`；ES-EKF 基线水平 RMSE `9.0636 m`、`\sigma_dvl` Pearson 系数 `+0.7788`；MPC 四项 RMSE 为 `2.384 m`、`0.705 m`、`0.399 rad`、`0.147 rad`。
3. `.venv/bin/python tools/validate_thesis_figures.py --strict` 通过：44 幅正文图，0 warning。
4. 正文 40 幅可重绘图全部引用 PDF；仅 2 幅系统截图和 2 幅厂家扫描件保留 PNG/JPG。
5. 清理跨平台旧辅助文件后，TeX Live 2026、Biber 2.21 完成 188 页 A4 全量构建。最终日志无 undefined command/citation/reference、重复标签、float too large 或 overfull。
6. 构建过程中发现跨页 `longtable` 重复写入两个 UA-MPC 表标签，已通过首屏表头与续页表头分离修复；表格数据、编号和引用键未变。
7. 按图目录抽取 37 个实际含图页面并逐页检查：图 2.7 不再独占一页；所有图与图注同页，无图片裁切、越界、叠字、图例遮挡或浮动体异常。
8. 本任务范围 `git diff --check` 通过；全仓检查仅报告任务外 `csd_vx6.8_lastest/DataProcess.h` 与 `com.c` 的既有尾随空格，本轮未改动。
9. 追加快速排版复核：图 5.13 的两个源图由错误的 6.8 inch 通栏画布改为 3.3 inch 半栏画布，并同步将 manifest 标记改为 `single`，图例统一移到绘图区上方；图 4.3 高度由 4.35 inch 压缩为 3.95 inch，收紧 2×3 GridSpec 行列间距，并将重复图例归并为右上子图空白带内的单一图例。全文并排图片扫描未发现第二处通栏源图缩入半栏的尺寸错配。定向重绘后严格校验仍为 44 幅、0 warning；188 页论文重建日志无 overfull、float too large、未定义引用或引文，最终物理第 87 页和第 147 页视觉检查通过。

## 6. 约束与决策

- 活跃正文图片是唯一实施范围；未引用历史图不批量重绘。
- 截图与报告扫描件是原始证据，不做“中文化重制”。
- 数据处理和实验结论被冻结；发现异常只报告，不以视觉调整掩盖。
- 有原始数据但缺分析依赖时补依赖；没有原始数据时明确 Linux 交接，不伪造。
- 已存在的用户改动和未提交工作不回退。


## 附录：原始要求

你正在为thuthesis里面的所有图片（包含matplotlib和draw.io）。你可以少量更改，但是下面的是遵循的关键要素，目前图片存在各自单独生成，风格不太清晰，以及存在少量中英文换咋等问题。请找出所有可视化的数据和图片来源，确认是不是mac可以读取所有的数据，把所有的绘图脚本都绘制出来，或者可以复刻（根据已有的manifest？）。做出修改后避免相关的元素遮挡。先进行相关计划和审计，生成计划后直接继续。 
 
 # 所有来源于matplotlib的参考下面 
 
 **1. Figure size** 
 
 * 单栏图默认长度（也就是figsize的第一个参数）统一为3.3inch。 
 * 双栏/通栏图长度为6.8inch。 
 * 不要使用 notebook 风格的大尺寸图片，如 `(10, 6)`、`(12, 8)`。谨慎让长度/高度的比值小于1.4。 
 
 **2. Font** 
 
 * 图中文字以论文最终插入尺寸可直接阅读为原则。 
 * 单栏图：axis label/title 9 pt，tick 8 pt，legend 8 pt。 
 * 双栏图：axis label/title 10 pt，tick 9 pt，legend 9 pt。 
 * 数学公式字体保持 Times/STIX 风格。 
 * 所有内容都用中文 
 * 不要使用超大的 title；通常优先取消图内 title，将说明放在论文 caption 中。 
 * 如果内容塞不下，可以考虑重新组织或者删去不分不重要内容。 
 
 **3. Line and marker** 
 
 * 主实验曲线 `linewidth=1.6~1.8`。 
 * 次要曲线 `linewidth=1.3~1.6`。 
 * 坐标轴边框约 `0.8~1.0`。 
 * marker 大小一般 `4~5`。 
 * 不使用异常粗的曲线或过大的 marker。 
 
 **4. Color** 
 整个论文使用固定且色盲友好的配色，不允许每张图随机选择颜色。 
 同一算法、变量或实验条件在所有图中必须始终使用相同颜色。 
 
 默认语义： 
 
 * Proposed/Ours：蓝色； 
 * Baseline 1：橙色； 
 * Baseline 2：绿色； 
 * Baseline 3：紫色； 
 * Ground Truth/reference：黑色或深灰； 
 * Error/failure/warning：红色； 
 * uncertainty/confidence region：对应主色的低 alpha 填充或浅灰。 
 
 同时通过 solid / dashed / dash-dot / dotted 等线型帮助区分曲线，确保黑白打印仍可辨认。 
 
 **5. Axes and grid** 
 
 * 坐标轴必须明确写出物理量和单位，例如 `Time (s)`、`Magnetic Field (μT)`。 
 * 不要重复在标题、legend 和 axis label 中表达同一信息。 
 * 默认使用轻量 major grid；不要使用浓重网格。 
 * 不默认绘制 minor grid，除非分析确实需要。 
 * 科学计数法、有效数字、小数位数在相同类型图中保持统一。 
 
 **6. Legend** 
 
 * legend 不遮挡重要数据。 
 * 优先放在图内空白区域；只有图内没有空间时才放到图外。 
 * legend 顺序在整个论文中保持一致，例如始终 Ours → Baseline A → Baseline B。 
 * legend frame 保持简洁，避免厚重边框。 
 
 **7. Layout** 
 
 * 使用 `constrained_layout=True` 或正确调用 `tight_layout()`，避免文字截断。 
 * subplot 之间保持合理间距。 
 * 多子图使用 `(a)`, `(b)`, `(c)` 等统一标识。 
 * 共享相同变量时尽量使用 shared axis，避免冗余标签。 
 * 不为了装饰加入无意义的背景色、阴影、3D 效果或渐变。 
 
 **8. Export** 
 论文最终图片优先保存为 PDF/SVG 等矢量格式： 
 `plt.savefig(..., bbox_inches="tight")` 
 
 如果必须输出 PNG，则至少使用： 
 `dpi=300`，推荐 `dpi=600`。 
 
 **9. Existing figures** 
 如果是在修改已有绘图代码： 
 
 * 首先保留原始数据处理、计算过程和实验结论； 
 * 只统一 visualization 部分； 
 * 不得为了让图“更漂亮”而修改、平滑、裁剪或重新缩放原始数据，除非我明确要求。 
 * 如果发现不同图中的同一算法颜色、字号、线宽、命名或单位不一致，应主动统一。 
 
 **10. Overall style** 
 目标不是制作宣传海报，而是生成简洁、克制、专业、适合硕士毕业论文和学术论文的 scientific figure。 
 
 在生成代码前，优先检查当前项目是否已经存在统一的 plotting style、rcParams 或颜色定义。如果存在，应复用和整理，而不是创建另一套冲突的配置。 
 
 
 # 所有来源于draw.io的图像 
 
 
 ## 1. 首先确定最终论文尺寸 
 
 任何绘图开始前，先判断该图属于： 
 
 * 单栏简单图； 
 * 通栏普通架构图； 
 * 通栏复杂架构图。 
 
 默认优先采用“通栏普通架构图”。 
 
 推荐画布： 
 
 * 单栏简单图：约 `800–1000 × 450–600` 
 * 通栏普通架构图：约 `1400 × 800` 
 * 通栏复杂架构图：约 `1600 × 900~1000` 
 
 正常通栏图画布宽度原则上不得超过约 `1650`。 
 
 禁止通过无限扩大画布解决节点过多的问题。 
 
 如果当前内容无法在推荐画布内清晰排布，应依次： 
 
 1. 减少无意义空白； 
 2. 优化节点排列； 
 3. 缩短节点中的文字； 
 4. 将节点组织为功能分区； 
 5. 合并冗余节点； 
 6. 必要时拆分为“总体架构图 + 子系统详细图”。 
 
 不得直接把画布扩大到 2000、2500、3000 以上，同时维持原字号。仍然注意，不要产生任何意义上的元素和线条互相遮挡。 
 
 ## 2. 字号必须与画布尺寸绑定 
 
 不得只设置固定字号而任意改变画布。 
 
 全文架构图原则上只使用以下四级字号： 
 
 * L1：系统或大区域标题； 
 * L2：主要模块标题； 
 * L3：普通节点文字； 
 * L4：辅助文字、箭头标签、参数。 
 
 普通通栏架构图默认： 
 
 * L1 = 22 
 * L2 = 18–19 
 * L3 = 15–16 
 * L4 = 13–14 
 
 复杂架构图可采用： 
 
 * L1 = 22–24 
 * L2 = 19–20 
 * L3 = 16–17 
 * L4 = 13–14 
 
 简单图可整体降低约 1–2 级： 
 
 * L1 ≈ 20 
 * L2 ≈ 17 
 * L3 ≈ 15 
 * L4 ≈ 13 
 
 不得为了塞入更多内容将普通节点字号降低到 10–11。 
 
 如果需要小于 L4 的字号才能容纳全部内容，应优先重新布局或拆图。 
 
 同一张图中不得出现大量无规则字号，例如 10/11/12/13/14/15/16/18/20/22 混用。 
 
 ## 3. 文字风格 
 
 采用简洁、专业的 scientific diagram 风格。 
 
 * 同一级模块使用完全一致的字体和字号； 
 * 中文字体保持统一； 
 * 英文和数字保持统一字体； 
 * 不使用粗体突出所有文字； 
 * 仅 L1/L2 或真正重要的节点允许适度加粗； 
 * 普通节点采用 regular； 
 * 文字尽量保持 1–2 行； 
 * 一个普通节点原则上不要写完整长句； 
 * 优先使用名词短语，例如“磁场测量”“特征提取”“状态估计”，而不是说明性长句。 
 
 图内语言必须统一。若当前论文主要使用中文架构图，则默认使用中文，仅保留 TMR、SBP、ADC、Jetson、ROS 等必要英文缩写。 
 
 ## 4. 模块和形状 
 
 默认主要采用圆角矩形。 
 
 保持一致的： 
 
 * corner radius； 
 * padding； 
 * border width； 
 * text alignment。 
 
 不要仅为了美观随机混合： 
 
 * rectangle； 
 * capsule； 
 * ellipse； 
 * hexagon； 
 * 3D box； 
 * cloud。 
 
 只有存在明确语义时才使用特殊形状。 
 
 大功能区使用 container / group 表示，但不要加入厚重背景或明显装饰效果。 
 
 ## 5. 线条 
 
 主连接线统一采用约 `1.5–2 px`。 
 
 推荐语义： 
 
 * 实线单向箭头：主要数据流或控制流； 
 * 虚线箭头：辅助、反馈、可选或间接信息； 
 * 双向箭头：真正双向通信； 
 * 无箭头线：物理或结构连接。 
 
 优先使用 orthogonal connectors，即水平/垂直折线。 
 
 禁止： 
 
 * 大量随机曲线； 
 * 箭头穿过节点； 
 * 不必要的线条交叉； 
 * 不同箭头尺寸随机变化。 
 
 如果出现大量 crossing edges，应优先重新排列节点。 
 
 ## 6. 布局 
 
 优先建立明确的数据流方向： 
 
 * 从左到右；或 
 * 从上到下。 
 
 一张图中尽量不要同时存在多个互相冲突的主方向。 
 
 同层节点应： 
 
 * 对齐； 
 * 等间距； 
 * 高度相近； 
 * padding 相近。 
 
 节点大小应由内容和层级决定，而不是随机变化。 
 
 多个并列模块尽量使用相同尺寸。 
 
 模块之间的间距通常应明显大于模块内部文字 padding，以形成层次。 
 
 ## 7. 配色 
 
 采用克制的学术配色。 
 
 整张图原则上不超过： 
 
 * 1 个主要颜色； 
 * 2–3 个辅助浅色； 
 * 灰色； 
 * 白色。 
 
 颜色必须有语义，而不是随机装饰。 
 
 同一类功能模块在全文所有图中使用相同颜色。 
 
 例如可以统一： 
 
 * Sensors / Measurement：浅蓝； 
 * Signal Processing：浅青； 
 * Estimation / Fusion：浅橙； 
 * Planning / Control：浅绿； 
 * Hardware / Vehicle：浅灰； 
 * Environment：白色或灰色虚线边框。 
 
 使用浅色 fill + 深色文字。 
 
 除特殊强调外，不使用彩色文字。 
 
 必须保证黑白打印时仍能通过： 
 
 * 模块位置； 
 * 边框； 
 * 线型； 
 * 标签 
 
 识别结构关系，不能只依赖颜色。 
 
 ## 8. 避免装饰性设计 
 
 这是硕士毕业论文 scientific figure，而不是商业宣传图。 
 
 默认禁止： 
 
 * gradient； 
 * heavy shadow； 
 * glow； 
 * 3D effect； 
 * 大面积深色背景； 
 * 彩虹配色； 
 * 过度圆角； 
 * 无意义图标； 
 * emoji； 
 * 装饰性插画。 
 
 如果使用 AUV、传感器、Jetson 等图标，只用于快速说明对象类别，并保持风格一致、尺寸克制。 
 
 ## 9. 架构层次 
 
 对于复杂系统图，应优先形成： 
 
 System 
 → Functional Block 
 → Module 
 
 三级结构。 
 
 不要把所有组件平铺在同一级。 
 
 例如： 
 
 Perception 
 
 * TMR sensing 
 * SBP 
 * Signal processing 
 
 Estimation 
 
 * Feature extraction 
 * Sensor fusion 
 * Cable state estimation 
 
 Decision & Control 
 
 * Behavior tree 
 * Path planning 
 * Tracking controller 
 
 Vehicle 
 
 * AUV 
 * Thrusters 
 
 应通过 container、位置和字号表达层级，而不是仅通过颜色。 
 
 ## 10. AI 修改已有 draw.io 图时 
 
 如果是在修改已有 draw.io 文件： 
 
 * 不改变原始技术含义； 
 * 不删除必要的数据流； 
 * 不为了排版改变算法关系； 
 * 首先统计当前画布大小、字号、颜色、线宽和节点样式； 
 * 找出不一致项； 
 * 将其归一化到上述规范； 
 * 保持同一技术对象在不同图中的名称、颜色和风格一致。 
 
 如果发现当前图只有通过明显扩大画布才能排下，不要直接扩大画布；应首先重构布局。 
 
 ## 11. 输出前自检 
 
 完成绘图后必须检查： 
 
 1. 按论文最终尺寸缩放后文字是否仍清晰； 
 2. 是否有字号过小的节点； 
 3. 是否存在超过四级的无意义字号； 
 4. 是否因为内容增加而异常扩大画布； 
 5. 同级节点是否尺寸、字号、颜色一致； 
 6. 是否存在箭头穿过节点或大量交叉； 
 7. 是否有过度留白； 
 8. 是否有节点距离过近； 
 9. 颜色是否具有稳定语义； 
 10. 中英文是否统一； 
 11. 所有物理量、缩写、模块名称是否正确； 
 12. 图是否能够脱离颜色，在灰度打印时仍基本读懂。 
 
 最终目标是：在 A4 中文硕士毕业论文中以约 16 cm 宽度插入后，文字清晰、层次稳定、风格统一，并具有简洁专业的 scientific diagram 风格。 
