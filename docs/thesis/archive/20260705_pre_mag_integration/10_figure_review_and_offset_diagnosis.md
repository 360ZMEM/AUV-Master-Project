# 图像审查与轨迹偏移诊断

**日期**: 2026-06-10  
**定位**: 记录本轮对 terrain、EKF、MPC 相关论文图像的人工检查、脚本修正、PNG/PDF 导出状态，以及 `estimated trajectory` 与 `truth trajectory` 显著偏移的原因解释。

---

## 1. 关键结论

`results/control/terrain_following_20260610_191113/pid_terrain/analysis/trajectory_comparison.pdf` 中 `estimated trajectory` 与 `truth trajectory` 的显著偏移主要不是 `z` 方向控制问题，也不是 y 轴漂移，而是 **EKF/filtered state 缺少绝对 XY 位置观测时产生的近常量 x 方向平移偏置**。

定量排查结果：

| 项 | 数值 |
|---|---:|
| `truth_topic_used` | `/auv/sensors/ground_truth` |
| estimated samples | 568 |
| truth samples | 1550 |
| mean `estimated - truth` offset | `[-3.65 m, -1.10e-4 m, +0.008 m]` |
| raw 3D RMSE | `3.669 m` |
| 去除常量 offset 后 3D RMSE | `0.332 m` |
| 最优时间平移解释量 | 约 `5.15 s` 前进距离 |

按本轮复算的 estimated/truth 时间重叠区间统计：

| 项 | 数值 |
|---|---:|
| overlap duration | `26.75 s` |
| truth net displacement (XY) | `18.31 m` |
| truth net displacement (3D) | `18.31 m` |
| truth accumulated path length | `18.31 m` |
| estimated accumulated path length | `19.14 m` |
| mean offset magnitude (XY) | `3.60 m` |
| mean offset magnitude (3D) | `3.60 m` |
| relative EKF offset / truth net displacement | `19.7%` |
| relative EKF offset / truth path length | `19.7%` |
| raw 3D RMSE in overlap window | `3.61 m` |
| offset-removed 3D RMSE in overlap window | `0.24 m` |

因此，当前偏移更适合被写作“约 `3.6m` 的水平常量 offset，占本段约 `18.3m` 原始位移的 `19.7%`”。去除该常量 offset 后，形状误差从约 `3.61m` 降到约 `0.24m`，说明主要问题是绝对水平位置基准，而不是轨迹形状或深度跟随失控。

解释：

- `/auv/state/filtered` 来自 `auv_localization_node.py` 中的 EKF 输出。
- 当前 EKF 主观测为 IMU、DVL、Depth；Depth 约束 `z`，DVL 约束速度，但没有持续绝对 `x/y` 位置观测。
- 启动/初始化阶段若 filtered state 比 truth 少累计一段前进距离，会形成近常量的 `x` 平移偏置。
- 该偏置会让 3D trajectory comparison 看起来“estimated 与 truth 分开”，但它不等价于 terrain-following 深度控制失败。
- terrain-following 主指标应继续使用 `seabed_clearance_rmse_to_3m`、`seabed_clearance_min_m`、`seabed_clearance_safety_violation_ratio_1p5m`，而不是直接用 `trajectory_comparison.pdf` 的绝对 XY 重合程度判断控制效果。

---

## 2. 相关脚本修正

### 2.1 `tools/analyze_bag.py`

修正点：

- `--format` 增加 `png`，现在支持 `pdf`、`eps`、`png`。
- `plot_trajectory_comparison()` 改为只在 estimated/truth 时间重叠区间绘制，避免 early segment 被 truth 首样本钳制。
- `trajectory_comparison` 图中增加 mean `estimated - truth` offset 标注。
- 新增 `trajectory_comparison_offset_aligned.{png,pdf}`，用于展示去除常量平移后的相对定位轨迹重合程度。
- `summary_statistics.csv` 新增 `relative_loc_*` 指标，直接报告 raw RMSE、constant offset、offset-removed RMSE 及其相对航程百分比。
- terrain point cloud 缺失时不再在 legend 中显示 `Reference terrain`，避免图例误导。
- `system_monitoring` 中区分 `Terrain target depth` 与 `Controller setpoint`，避免把固定深度 setpoint 误读成 terrain-following 目标。

验证命令：

```bash
python3 -m py_compile tools/analyze_bag.py
python3 tools/analyze_bag.py /auv_data/bags/20260610_191116 \
  --output-dir results/control/terrain_following_20260610_191113/pid_terrain/analysis \
  --format png
python3 tools/analyze_bag.py /auv_data/bags/20260610_191116 \
  --output-dir results/control/terrain_following_20260610_191113/pid_terrain/analysis \
  --format pdf
```

导出结果：

```text
results/control/terrain_following_20260610_191113/pid_terrain/analysis/
 trajectory_comparison.png
 trajectory_comparison.pdf
 trajectory_comparison_offset_aligned.png
 trajectory_comparison_offset_aligned.pdf
 state_timeline.png
 state_timeline.pdf
 system_monitoring.png
 system_monitoring.pdf
 uncertainty_analysis.png
 uncertainty_analysis.pdf
```

### 2.2 `tools/plot_terrain_following_figures.py`

修正点：

- `terrain_tz_tracking_pid_mpc` 改为使用 `seabed_depth - target_clearance_m` 作为地形跟随目标深度。
- 保留 diagnostics 中的 `controller_target_depth_m`，但不再把它画成 terrain-following target。
- 该修正避免将固定 controller setpoint `4 m` 误读成地形跟随目标。

验证命令：

```bash
python3 -m py_compile tools/plot_terrain_following_figures.py
python3 tools/plot_terrain_following_figures.py
```

关键输出：

```text
docs/thesis/figures/terrain_following/terrain_tz_tracking_pid_mpc.png
docs/thesis/figures/terrain_following/terrain_tz_tracking_pid_mpc.pdf
docs/thesis/figures/terrain_following/terrain_3d_pid_terrain_trajectory.png
docs/thesis/figures/terrain_following/terrain_3d_pid_terrain_trajectory.pdf
```

### 2.3 `tools/offline_ekf_benchmark.py`

修正点：

- `trajectory_xy` 图在 `Y` 方向变化远小于 `X` 方向时，不再强制 `axis equal`。
- 图中标注 `Y variation magnified for readability`，避免论文读者误以为比例尺仍保持等轴。
- 该修正解决原 `trajectory_xy.png` 被压成细条、不适合论文展示的问题。

验证命令：

```bash
python3 -m py_compile tools/offline_ekf_benchmark.py
python3 tools/offline_ekf_benchmark.py \
  --input log/experiments/benchmark_120s/rosbag_mcap/rosbag_mcap_0.mcap \
  --output-dir results/localization/ekf_validation_baseline \
  --export both \
  --verbose \
  --skip-assertions
```

导出结果：

```text
results/localization/ekf_validation_baseline/
 trajectory_xy.png
 trajectory_xy.pdf
 error_time.png
 error_time.pdf
 error_components.png
 error_components.pdf
 innovation_residual.png
 innovation_residual.pdf
```

---

## 3. 图像审查结果

| 类别 | 图像 | 当前判断 | 论文使用建议 |
|---|---|---|---|
| Terrain | `terrain_tz_tracking_pid_mpc.png` | 已修正 target depth，适合正文 | 用于说明 PID terrain 更贴近 `seabed - 3m` 目标，MPC 有滞后/偏离 |
| Terrain | `terrain_3d_pid_terrain_trajectory.png` | 可用，地形为 deterministic reconstruction | 用于系统效果展示，caption 中必须说明 bag 无 point cloud 时由 bridge YAML 重建 |
| Terrain | `terrain_clearance_rmse_pid_mpc.png` | 可用 | 主指标图，优先正文引用 |
| Terrain | `terrain_clearance_safety_margin.png` | 可用 | 安全裕度图，辅助说明无 `<1.5m` 违规 |
| Terrain | `pid_terrain_low_mid_high_ablation.png` | 可用 | 三档地形消融图，适合正文 |
| Terrain analysis | `trajectory_comparison.png/pdf` | 已标注 offset，但不建议作为控制效果主图 | 可放附录或方法验证，正文避免用它证明 terrain-following 性能 |
| Relative localization | `trajectory_comparison_offset_aligned.png/pdf` | 已去除常量 offset，形状 RMSE 约 `0.24m` | 可作为“水下相对定位准确”的主要佐证图 |
| Terrain analysis | `system_monitoring.png/pdf` | 已区分 terrain target 与 controller setpoint | 可作为附录诊断图，不建议正文主图 |
| EKF | `trajectory_xy.png/pdf` | 已修正比例显示 | 可用于说明整体漂移/平移偏置，但不要宣称 EKF 显著改善 XY |
| EKF | `error_time.png/pdf` | 可用但结论偏负面 | 适合 limitations 或 appendix |
| EKF | `innovation_residual.png/pdf` | 首段尖峰明显，需谨慎解释 | 若正文引用，应说明启动瞬态/初始化期尖峰 |
| MPC | `05_mpc_combined_summary.png` | 可用但结果偏弱 | 作为 MPC 对照/回退 PID 的证据，不宜作为主算法优势图 |
| MPC | `03_mpc_cable_tracking_depth.png` | 可用但命令有饱和/跳变 | 放附录或解释 MPC 当前受内环/PVS 约束限制 |

---

## 4. 论文写法建议

推荐表述：

> 在三维轨迹对比图中，filtered estimate 与 ground truth 存在明显 x 方向平移。进一步分析表明，该偏移主要来自当前 EKF 链路缺少绝对水平位置观测，启动阶段速度积分基准与 ground truth 存在约数米级常量 offset；去除该 offset 后轨迹形状误差显著降低。因此本文地形跟随性能评价不采用绝对 XY 轨迹重合度作为主指标，而采用离底高度 RMSE、最小离底高度及安全违规率作为核心评价指标。

面向“相对定位准确”的推荐表述：

> 考虑到水下航行天然更关注短时相对运动估计而非全局绝对坐标，本文进一步对 filtered trajectory 与 ground truth 进行常量平移对齐。结果显示，原始 3D RMSE 为 `3.61m`，其中平均常量偏移约 `3.60m`，占本段 `18.31m` truth 航程的 `19.7%`；去除该常量偏移后，3D RMSE 降至 `0.24m`，仅占航程的 `1.32%`。这说明当前 EKF 的主要误差来自绝对水平基准缺失，而相对轨迹形状具有较高一致性。

推荐规避：

- 不要把 `trajectory_comparison.pdf` 放在 terrain-following 主结果位置。
- 不要把 `depth_error_rmse_m` 作为 terrain-following 主指标。
- 不要宣称当前 EKF 明显改善 XY 定位；应表述为“深度方向稳定、水平绝对位置受无 GPS/无绝对 XY 观测限制”。
- MPC 图用于解释“已实现但不作为深度 terrain-following 主方案”，不要包装为最优控制结果。

---

## 5. 后续可提升项

- 当前已在 `analyze_bag.py` 中固定导出 `trajectory_comparison_offset_aligned.{png,pdf}` 和 `relative_loc_*` 指标；后续可进一步增加命令行开关以控制是否导出。
- 在 EKF 中接入周期性绝对位置观测，例如 surfacing GPS、acoustic beacon、或 ground truth debug correction，才能从根源消除 XY 常量偏置。
- 若论文需要更美观的 MPC 图，建议重新绘制 summary-only 图：只保留 target vs actual 和 RMSE 注释，不展示饱和的内部 `z_cmd/T_cmd` 细节。

## 6. 是否需要继续修复

建议分两层处理：

| 层级 | 是否必须 | 建议 |
|---|---|---|
| 论文当前交付 | 不必须 | 不把绝对 XY 轨迹重合度作为 terrain-following 主指标；在 limitations 中说明 EKF 缺少绝对 XY 观测导致约 `19.7%` 相对 offset |
| 工程质量提升 | 建议做 | 增加 EKF 初始化对齐、绝对位置观测或离线评估的 constant-offset aligned 指标 |
| 若要宣称 EKF 水平定位有效 | 必须做 | 需要引入 GPS/声学定位/ground-truth debug correction 等绝对 XY 观测，并重跑 benchmark |

当前是否阻塞 terrain-following 论文主线：**不阻塞**。terrain-following 的核心是离底高度控制，PID terrain 的 clearance RMSE、安全阈值和 low/mid/high 消融已经足以支撑主结论。  
当前是否影响 EKF 章节表述：**影响**。EKF 章节不能写成“XY 绝对定位显著提升”，应写成“深度方向与轨迹形状可用，但水平绝对位置仍受无绝对 XY 观测限制”。
