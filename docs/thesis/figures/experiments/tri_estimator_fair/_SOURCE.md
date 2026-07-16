# 三估计器公平对比（E-2 / O-1）数据溯源

> 对应 24 号文档 §8.1 ②、§8.3；毕业设计写作侧事实源仍以 thuthesis LaTeX 正文为准，本目录仅作数据溯源。

## 目的

关闭两个不自洽点（均属 24 号 §8.3 判定的**类型 1·脚手架伪影**，非真实性能）：

1. 23 号 §8.1 的 "ES-EKF > Std-EKF > Raw DR" 排序矛盾；
2. 开发文档 `dvl_fixed_final` 的 "XY 改善 95%、达 0.9 m" vs 深度维 12 m 崩。

根因：`tools/offline_ekf_benchmark.py` 三引擎初始化口径不一致——Raw DR / Std EKF 用 truth 起点，ES-EKF 用首帧 DVL/depth 自对齐并手动翻 Z，制造系统性初始偏移伪影。

## O-1 修复（只改 benchmark 脚手架，不动 algorithm/es_ekf.py）

- 新增 `--es-ekf-init {fair,legacy-auto}`（默认 fair）。
- fair 模式：ES-EKF 关闭 `auto_init/use_first_dvl_for_init/use_first_depth_for_init`，直接采用 main 注入的 truth 起点位姿（位置+初速+初始四元数），与 Raw DR、Std EKF 共享同一 truth 起点、同一 NED frame；散落的内联翻 Z 补丁收敛为单一具名坐标变换 `_ros_up_to_ned`（`_ned_to_ros_up` 的精确逆）。
- legacy-auto 模式：保留历史自对齐行为，仅用于 A/B 复现，验证伪影来源。

## 复算命令

```bash
python3 tools/run_tri_estimator_fair_benchmark.py \
    --sweep-csv log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv \
    --out-root  $AUV_DATA_ROOT/results/state_estimation/e2_tri_estimator_fair \
    --summary-dir docs/thesis/figures/experiments/tri_estimator_fair \
    --init fair            # 或 --init legacy-auto 复现旧伪影
```

数据源：P1 sensor sweep（8 场景 × 3 种子 = 24 个 bag），与正文 §5.5.5 ES-EKF 24 次鲁棒性矩阵同源。

## 结果（pooled，24 次运行）

| 引擎 | 水平 RMSE (m) | 深度 RMSE (m) | 3D RMSE (m) |
|---|---|---|---|
| Raw DR | 3.197 ± 0.695 | 0.025 ± 0.001 | 3.197 ± 0.695 |
| Std EKF | 3.196 ± 0.692 | 0.110 ± 0.012 | 3.198 ± 0.691 |
| ES-EKF | 3.200 ± 0.692 | 0.203 ± 0.023 | 3.207 ± 0.690 |

（legacy-auto 对照见 `tri_estimator_legacy-auto_*`，其 ES-EKF 水平 3.187 m 的"微优"即自对齐伪影，公平口径下消失。）

## 可支撑结论 / 不可外推

- **水平维**：三引擎统计等价（±1σ 完全重叠）。这是**结构性可观性边界**：观测仅 DVL(测速) + depth(测 z)，x/y 无绝对位置量测项，`correct_gps` 未接入，任何滤波器都退化为速度积分漂移。→ 正文应以可观性分析正面论证，而非声张 ES-EKF 水平精度优越。
- **深度维**：12 m 恒偏伪影已消除（Z 落到 0.02–0.20 m 量级）。Raw DR 深度最小是因为它直接透传深度计读数、不做协方差融合；Std/ES-EKF 的略大 Z RMSE 来自协方差整定口径（深度 R 偏小、DVL R 过保守，见 §5.5.5 NIS 审计），属可整定项（O-3/O-4，须批准），**不构成"深度精度"结论**。
- **ES-EKF 真正的正贡献**：多扰动下 24/24 估计连续、协方差传播、分源 NIS 诊断、Huber 鲁棒性——而非点精度领先。
- **不可外推**：n=3 种子、30 s 片段、离线滤波误差≠控制侧 RMSE；数据为数字孪生代理，非真机检测噪声。

## 文件清单

- `tri_estimator_fair_raw.csv` / `tri_estimator_fair_summary.csv` / `tri_estimator_fair_pooled.json`：公平口径逐 run / 分场景均值±std / pooled。
- `tri_estimator_legacy-auto_*`：旧自对齐口径对照（证明伪影来源）。
