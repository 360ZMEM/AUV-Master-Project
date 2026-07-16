# ADC-TMR 全链路噪声整合实验图源

## background_lockin_spectrum.png
- 生成命令：`real_experiments/mag_chain_noise/run.sh`
- 源数据：
  - `hardware_wrappers/fangkong_adc/raw_data/1780675809_291477.npz`
  - `hardware_wrappers/fangkong_adc/raw_data/1780676130_241387.npz`
- 论文副本路径：`docs/thesis/figures/hardware/mag_chain_noise/background_lockin_spectrum.png`
- SHA256：`d1460a1275fe5c5396bdf5c28d7bf5919bc66d360495c4590ccddfd59b1e03a6`
- 说明：宿舍环境 ADC-TMR 全链路背景记录的矢量幅度谱密度，45 Hz 为可控目标频率，50 Hz 为环境工频干扰。

## noise_record_metric_summary.png
- 生成命令：`real_experiments/mag_chain_noise/run.sh`
- 源数据：`hardware_wrappers/fangkong_adc/raw_data/*.npz`
- 论文副本路径：`docs/thesis/figures/hardware/mag_chain_noise/noise_record_metric_summary.png`
- SHA256：`e9223852c3c1636bf8ee69ae5df38677be6dad8d59150e77432d25ddca85ce8a`
- 说明：17 段三轴原始记录的去趋势 RMS、45 Hz 锁相幅值和 50 Hz 锁相幅值摘要，用于区分背景、45 Hz 激励与运动/标定记录。

## noise_injected_biot_savart_replay.png
- 生成命令：`real_experiments/mag_chain_noise/run.sh`
- 源数据：
  - 噪声记录：`hardware_wrappers/fangkong_adc/raw_data/1780675809_291477.npz`
  - 解析目标：45 Hz 无限长直导线 Biot-Savart 模型，`I_peak=2.614048 A`，`height=0.20 m`
- 论文副本路径：`docs/thesis/figures/hardware/mag_chain_noise/noise_injected_biot_savart_replay.png`
- SHA256：`e147682128303ec2a3d33098480b8979b9ef7bf5e69e534289278797f59d37dd`
- 说明：将实测背景噪声叠加到 45 Hz Biot-Savart 目标信号后的锁相恢复结果，用于支撑“真实噪声进入仿真观测链”的半实物实验口径。
