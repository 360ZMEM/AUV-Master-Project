# 状态估计实验图像来源

## R18/R19/R20 补强实验图

- R18/R19 生成脚本：`tools/es_ekf_long_horizon_replay.py`
- R20 生成脚本：`tools/es_ekf_r_strategy_benchmark.py`
- 源结果目录：
  - `results/state_estimation/r18_long_horizon/20260809_r18/`
  - `results/state_estimation/r19_measured_noise_replay/20260809_r19/`
  - `results/state_estimation/r20_filter_strategies/20260809_r20/`

## 论文压缩降级记录（2026-08-18，L2/L3 表-图去重）

- `r18_timing_duration_sensitivity.png`（原 `fig:ch05-r18-timing-duration`）：从正文降级归档。理由：R18 的 60/120/300 s RMSE、最大漂移和 DVL 相位对照已经由 `tab:ch05-r18-long-horizon` 给出，正文结论也已说明“误差随时长累积、相位是独立实验变量”。
- `r19_gaussian_vs_measured_replay.png`（原 `fig:ch05-r19-noise-replay`）：从正文降级归档。理由：参数化高斯与实测背景回放的 RMSE、跨种子标准差、p95 和 NIS 均已由 `tab:ch05-r19-noise-replay` 给出，图只重复“均值接近、实测回放离散更大”的表格结论。
- `r20_filter_strategy_comparison.png`（原 `fig:ch05-r20-filter-strategy`）：从正文降级归档。理由：标准 EKF、固定 R、全局/分源 R、Huber 与时间戳膨胀的脉冲/延迟 RMSE、NIS 和覆盖率已由 `tab:ch05-r20-filter-strategy` 给出，图只重复策略排序。

图片文件保留在本目录不删；正文数值权威源分别为 `tab:ch05-r18-long-horizon`、`tab:ch05-r19-noise-replay` 和 `tab:ch05-r20-filter-strategy`。

## 参数敏感性入正文（2026-08-20，27 号文 P2-2）

- `eskf_param_sensitivity.png` / `.pdf`（正文 `fig:ch05-eskf-param-sensitivity`，§5.5.5）：
  ES-EKF 噪声参数敏感性双面板图（左：各噪声参数与水平 RMSE 的皮尔逊相关系数，仅 DVL 强相关 0.779；
  右：单参数扫描下水平 RMSE 相对基线偏移，全程 < 22 mm、停留在 9.06 m 量级）。
- 生成脚本：`tools/plot_es_ekf_sensitivity.py`（走 `tools/thesis_plot_style.py`，中文字体 / 黑白可辨 / 300 dpi）。
- **数据来源（复用，不重跑）**：冻结报告 `results/tuning/ekf_comprehensive/tuning_report.md`
  （`tools/es_ekf_comprehensive_tuner.py` 于 2026-05-03 在单包 `log/experiments/20260503_144254/rosbag/rosbag_0.mcap`
  上 308 次离线评估的产物）。脚本只**解析**该报告的 §3 单参数扫描表与 §6.1 相关系数表并重排版，
  零重跑：因 `algorithm/es_ekf.py` 分源门控已于 2026-08 细化，重跑会与冻结产物漂移。
- **诚实边界**：该敏感性探针为单包（$n=1$）离线扫描，仅作``水平不可观''机制佐证；
  水平精度的多种子统计主结果仍以 `tab:ch05-eskf-robustness` 与公平口径三估计器对比为准。
- 复算命令：`python3 tools/plot_es_ekf_sensitivity.py`（`--check` 只解析打印摘要不出图）。
