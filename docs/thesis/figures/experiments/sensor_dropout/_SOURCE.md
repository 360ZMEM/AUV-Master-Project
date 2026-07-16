# 传感器退化多场景消融图（27 号文 P1-3）

本目录产物由 `tools/plot_sensor_dropout_ablation.py` 复算，是论文 §5.5.5 表
`tab:ch05-nis-eskf-multiscene` 的\ **可视化伴随**\ （不产生新数据，只汇聚已在盘的真实运行）。

## 复算命令

```bash
python3 tools/plot_sensor_dropout_ablation.py
```

## 数据来源（均为已提交的真实运行产物，可逐字节复算）

1. **定位侧**：`log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv`
   —— P1 sensor sweep，8 场景 × 3 种子 = 24 次真实 bag 回放；水平/深度 RMSE
   均值±样本标准差与正文表逐字节一致。
2. **一致性侧**：`results/uncertainty_aggregates/20260820_p1_nees/summary_by_scenario_mode.csv`
   —— 同一 sweep 的 NEES/NIS 聚合，取深度子空间 ANEES 与 95% 覆盖率。

## 图产物

- `figures/sensor_dropout_ablation.{png,pdf}`：三面板——
  (a) 水平 RMSE、(b) 深度 RMSE（按 DVL 丢包 / 磁畸变 / 声呐-综合三族着色+纹理），
  (c) 深度子空间 ANEES（对数轴，标注理论期望 ANEES=1）。
- `sensor_dropout_summary.{csv,json}`：逐场景聚合数值（含 n_ok 与 NEES）。

## 关键结论与诚实边界（必须与图同引）

- 水平 RMSE **非单调**：DVL 丢包 60%（2.89 m）反低于 30%（3.37 m），说明 30 s 片段、
  种子与观测时序主导数值差异，不能读作"丢包越重误差越大"。此为 §5.5.5 既有结论。
- 深度 ANEES 达数百量级、远大于 1 → **深度协方差被显著低估（过乐观）**，是如实呈现的
  负结果（对应 §5.5.5 NIS A/B 与语义审计），非精度断言。
- DVL 底锁测地速，横流不直接偏置其观测；横流对定位/观测的影响见声磁融合消融
  `current` 场景（`docs/thesis/figures/experiments/fusion_ablation/`）。
