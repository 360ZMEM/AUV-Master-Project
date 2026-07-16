# ADC-TMR 全链路噪声整合实验

本目录是 28 号文“尽量实验 4：Jetson 端一键复现实验包”的最小落地版本，同时服务“尽量实验 2：真实磁数据 + 仿真 AUV 轨迹闭环实验”的前置噪声建模。

## 一键运行

```bash
real_experiments/mag_chain_noise/run.sh
```

运行后生成：

- `metrics.json`：完整机器可读指标；
- `data/record_metrics.csv`：`raw_data` 全部 npz 的噪声、锁相和频谱摘要；
- `data/noise_profile.json`：默认背景噪声 profile；
- `data/noise_injection_metrics.csv`：真实背景噪声注入 45 Hz Biot-Savart 信号后的恢复误差；
- `figures/`：频谱、全记录摘要和注入回放图；
- `report.md`：论文可读的实验说明。

## 数据口径

默认背景噪声使用：

- `hardware_wrappers/fangkong_adc/raw_data/1780675809_291477.npz`
- `hardware_wrappers/fangkong_adc/raw_data/1780676130_241387.npz`

这两段记录未呈现强 45 Hz 目标激励，适合作为宿舍环境下的 ADC-TMR 全链路背景回放。其 50 Hz 分量来自真实环境工频干扰，应写为环境项，而不是实验室级本底噪声。

45 Hz 注入仿真使用解析 Biot-Savart 直导线模型生成可控目标，再叠加上述实测背景噪声并做同一 1 s / 0.05 s 锁相恢复。该实验验证“真实噪声可进入仿真观测链并被同一数字锁相接口消费”，不等同于真实海缆巡检验收。

## 与必须实验 2 的关系

必须实验 2 的 45 Hz 电缆--TMR--ArUco 联合反演由现有脚本：

```bash
cd hardware_wrappers/fangkong_adc
python3 scripts/joint_biot_savart_analysis.py --adc raw_data/1783235358_205719.npz
```

完成。本实验包读取该脚本输出的 `fit_summary.json`，在报告中复核 `777` 个对齐点、复 I/Q 自由尺度与固定电流两种 \(R^2\) 指标，从而把“等效电缆反演”和“真实噪声回放”放在同一复现实验口径下。

## Linux 待接点

本目录不修改 ROS2 父层节点。后续在 Linux 平台继续时，应把 `data/noise_profile.json` 和原始背景段作为磁观测噪声源，接入 ROS2/PVS/HoloOcean 的磁观测生成器或回放节点，再重跑状态估计与 UA-MPC 闭环矩阵。
