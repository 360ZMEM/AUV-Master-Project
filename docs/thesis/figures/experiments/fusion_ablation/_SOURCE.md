# 声磁协同融合消融（27 号文 组 C / P0-C + P1-3）

本目录产物由 `tools/run_fusion_ablation.py` 复算，对应论文 §5.5 声磁融合消融。

## 复算命令

```bash
python3 tools/run_fusion_ablation.py \
    --output-dir docs/thesis/figures/experiments/fusion_ablation \
    --seeds 0,1,2 --duration 120
```

- 数据层：合成可复现巡缆轨迹（无 bag 承载活跃磁通道，与 R19 实测回放同口径）；
  驱动\ **未改动**\ 的 `algorithm/es_ekf.py` 的 `correct_dvl/correct_depth/correct_mag`。
- 每臂共享同一轨迹 / 种子 / 逐样本噪声，成对对比公平。
- 样式统一走 `tools/thesis_plot_style.py`（中文字体 / 黑白可辨 / 300 dpi，P1-4）。

## 六消融臂

| 臂 | 含义 | 磁 | 声呐 | R 策略 |
|---|---|---|---|---|
| 1_imu_dvl | IMU+DVL+深度 | ✗ | ✗ | global |
| 2_imu_dvl_mag | +磁弱深度观测 | ✓ | ✗ | global |
| 3_imu_dvl_sonar | +声呐感知置信 | ✗ | ✓ | global |
| 4_imu_dvl_mag_sonar | 磁+声呐 | ✓ | ✓ | global |
| 5_fusion_fixed_r | 声磁融合·固定 R | ✓ | ✓ | fixed |
| 6_fusion_adaptive_r | 声磁融合·自适应 R | ✓ | ✓ | per_source |

## 场景

`baseline / sonar_occlusion / mag_weak / em_noise / current / combined`。其中
`current`（P1-3 新增）以 0.3 m/s 稳态横流 → 欠驱动横向站位偏移 → 磁\ *斜距*\ 系统性
偏置建模（`_crossflow_standoff_m`），DVL 底锁不受横流直接偏置。

## 图产物

- `figures/fusion_ablation_summary.{png,pdf}`：六臂 × 六场景 3D RMSE 与目标丢失占比。
- `figures/fusion_adaptive_vs_fixed_r.{png,pdf}`（P1-3）：臂⑤固定 R vs 臂⑥自适应 R
  的成对对比（3D RMSE / 磁反演距离 RMSE / 磁 NIS 均值）。

## 关键结论（3 种子均值）

- **自适应 R 的一致性收益**：磁 NIS 均值在失配场景显著回落——em_noise 7.43→3.06、
  combined 2.71→1.66、current 1.26→1.00、mag_weak 1.88→1.32；理想/遮挡场景无失配则
  两臂等价（NIS 不变）。3D RMSE 在 em_noise、combined 亦有小幅改善。
- **横流系统性偏置**：`current` 场景磁反演距离\ *有符号偏置*\ 为 +0.225 m（噪声-only
  场景近 0），佐证横流通过斜距而非噪声进入观测——是可被自适应 R 识别的失配。
- **诚实边界**：3D RMSE 绝对值受水平不可观下界主导（见 §5.5.5 三估计器等价结论），
  故融合的正贡献界定为\ *磁观测一致性与目标保持*\ ，而非水平点位精度领先；声呐为
  感知置信输入、非独立 EKF 量测，臂③与臂①状态 RMSE 相等属结构性预期。
