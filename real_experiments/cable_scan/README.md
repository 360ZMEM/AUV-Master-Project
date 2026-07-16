# 等效通电导线 Biot-Savart 联合反演

本目录对应 28 号文“必须实验 2：等效通电电缆磁场扫描实验”的当前可复现版本。

## 一键运行

```bash
real_experiments/cable_scan/run.sh
```

该命令直接复用 `hardware_wrappers/fangkong_adc/scripts/joint_biot_savart_analysis.py`，输入为：

- `hardware_wrappers/fangkong_adc/raw_data/1783235358_205719.npz`
- `hardware_wrappers/fangkong_adc/raw_data/relative_pose_log.txt`

当前脚本完成 45 Hz 锁相、ArUco 位姿对齐、多起点 Biot-Savart 直导线几何拟合和复 I/Q 固定电流对照。输出仍保存在：

```text
hardware_wrappers/fangkong_adc/raw_data/joint_analysis/1783235358_205719/
```

## 当前可写结论

- 106821 个 ADC 样本，2000 Hz，45 Hz 锁相；
- 832 帧 ArUco 相对位姿日志，得到 777 个有效锁相--位姿配对点；
- 三轴复 I/Q 自由尺度模型 \(R^2=0.8792\)；
- 固定峰值电流 \(2.6140\text{ A}\) 模型 \(R^2=0.8711\)。

## 边界

该实验验证单三轴 TMR 在运动轨迹和位姿辅助下可以形成合成空间阵列，并与直导线 Biot-Savart 模型形成可观测拟合。它不应写成多芯铠装真实海缆的绝对埋深计量，也不替代水下完整巡检验收。
