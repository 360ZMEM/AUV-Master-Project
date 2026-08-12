# R08 TMR/SK2301 最小采集 handoff 与 ADC ENOB 证据

## 1. 状态与边界

R08 已完成基础设施交付，真实 M0/M1/M4 采集仍属于 R24 handoff：

| 项目 | 状态 | 证据 |
|---|---|---|
| M0/M1/M4 单命令编排 | 完成 | `hardware_wrappers/fangkong_adc/scripts/run_tmr_handoff.py` |
| macOS/Linux 指定网卡绑定 | 完成 | `network/tcp_client.py` 及 `tests/test_tcp_client.py` |
| 频率与硬件元数据写入 NPZ | 完成 | dry-run manifest、CLI 测试 |
| 失败样本与有效样本契约 | 完成 | `metrics.csv`、`failure_events.csv`、`status.json` |
| R06 无头分析命令生成 | 完成 | `analysis_commands.sh` |
| M0/M1/M4 真实长时采集 | 待 R24 | dry-run 不冒充实测 |
| ADC CH4 短接 ENOB 子证据 | 已有实测 | `raw_data/enob/20260809T161036/` |

R08 是类别 2 基础设施任务，完成后使类别 4 的 R24 可直接 handoff。R08 的
`contract_complete=false` dry-run 只证明编排和产物结构，不证明传感器性能。

## 2. 最小采集矩阵

默认矩阵固定原始采样率 2000 Hz、软件解调参考 45 Hz：

| 阶段 | 条件 | 时长/次 | 重复或档位 | 单次样本 | 最低总样本 |
|---|---|---:|---:|---:|---:|
| M0 | ADC 三通道等效零输入/短接 | 300 s | 3 次 | 600000 | 1800000 |
| M1 | TMR 接入、静置、无电缆激励 | 600 s | 3 次 | 1200000 | 3600000 |
| M4 | 已知 45 Hz 小信号注入 | 120 s | 至少 5 档 | 240000 | 1200000 |

最低返回量为 11 个 NPZ、6600000 个三通道时刻样本。M4 五档默认仅是命令模板，
现场必须用实际可复核的峰值磁场替换，并通过 `--injection-provenance` 记录电流、
距离、线圈常数或标准场来源。

## 3. 现场命令

在 `hardware_wrappers/fangkong_adc` 下运行：

```bash
PYTHONPATH=. python3 scripts/run_tmr_handoff.py \
  --host 192.168.0.12 \
  --port 1600 \
  --bind-interface en9 \
  --tmr-serial "<TMR8637序列号>" \
  --power-state "<电源型号、电压与状态>" \
  --grounding-state "<接地拓扑>" \
  --isolation-state "<隔离模块与开关状态>" \
  --temperature-c "<环境温度>" \
  --calibration-profile "<profile路径或none>" \
  --frequency-provenance "<45Hz源的仪器设置或记录路径>" \
  --injection-provenance "<五档nT峰值的标定或计算记录>" \
  --m4-levels-nt-peak 0.01,0.02,0.05,0.1,0.2
```

命令依次提示操作者准备 M0、M1 和每个 M4 档位。只有固定装置已经能够按外部 SOP
自动切换时才使用 `--yes`。任何失败都会进入 `failure_events.csv`；默认首个失败后
停止，需有意识保留后续运行时才使用 `--continue-on-error`。

现场网络已知条件是 ADC `192.168.0.12:1600`、macOS 网卡 `en9`。命令显式绑定
接口，避免主网卡和 ADC 网卡处于同一子网时由系统路由选错出口。

## 4. 返回 bundle 契约

```text
<timestamp>/
  run_manifest.json
  command.txt
  environment.txt
  config_snapshot/
  raw/
    M0_r01.npz
    ...
    M4_l05_r01.npz
  logs/capture.log
  metrics.csv
  failure_events.csv
  status.json
  analysis_commands.sh
  report.md
  figures/
```

每个 NPZ 同时保存原始 24 bit 码、浮点电压、采样率、通道、灵敏度、开始时间和
`experiment_metadata_json`。元数据包含：

- `data_source_id`、`stage`、`repeat`、`setup`；
- `excitation_hz`、`reference_hz`、`frequency_source`、
  `reference_type`、`frequency_provenance`；
- M4 的 `injection_nt_peak` 和 `injection_provenance`；
- TMR 序列号、供电、接地、隔离、温度和 calibration profile；
- ADC 寄存器状态、通道错位计数和有效样本数。

只有 11 个计划项全部具有 NPZ、有效样本数达到预期、通道错位为 0 且无失败事件时，
`status.json` 才会写 `contract_complete=true`。

基准 dry-run 位于：

```text
results/magnetic_handoff/20260809_r08_tmr_minimal_handoff_dry_run/
```

其计划项为 11、有效运行数为 0、`contract_complete=false`，这是预期门控行为。

## 5. ADC ENOB 与 0.05 nT

### 5.1 实测数据

权威输入：

```text
hardware_wrappers/fangkong_adc/raw_data/enob/20260809T161036/
```

CH4 差分输入短接，每档采集 10 s。ADC 满量程跨度为 20 V，标称 24 bit；噪声
ENOB 使用

\[
N_{\mathrm{ENOB,noise}}
=\log_2\frac{V_{\mathrm{FS}}}{\sqrt{12}\,\sigma_v}
\]

计算。该指标是短接静态噪声估计，不是满量程正弦输入下由 SINAD 获得的动态 ENOB。

| 条件 | 电压 RMS | 噪声 ENOB | 45 Hz 等效磁噪声 |
|---|---:|---:|---:|
| 2000 Hz 原始采样 | 47.974 µV | 16.877 bit | 矢量 RMS 0.1237 nT |
| 16000 Hz、OSR=8、输出 2000 Hz | 17.375 µV | 18.342 bit | 矢量 RMS 0.0230 nT |
| 同上，I/Q 单分量 3σ | — | — | 0.0514 nT |

实测 ENOB 提升 1.440 bit，接近独立白噪声下 OSR=8 的理论 1.500 bit；继续提高
OSR 后收益开始受相关噪声、窄带干扰和漂移限制。

### 5.2 亚 LSB 估计的含义

20 V/24 bit 的标称 LSB 为 1.192093 µV。按 20 mV/µT 名义传感器灵敏度换算，
单个 ADC 码约等于 0.059605 nT，略大于 0.05 nT。多样本超采样、噪声抖动和
1 s 相干积分可以形成亚 LSB 的窄带估计，因此得到 0.0230 nT 矢量 RMS 并不违反
量化原理。

这也是该廉价 24 bit ADC 的论文价值：标称位数不高估，先承认原始宽带噪声只有
约 16.88 bit ENOB，再通过采样率与目标频带协同设计得到约 18.34 bit 的噪声 ENOB
和亚单码窄带估计。亮点是“系统处理释放廉价器件的窄带检测能力”，不是“ADC 具有
24 bit 精度”。

### 5.3 灵敏度、分辨率和准确度

| 概念 | 本实验可否给出 | 当前表述 |
|---|---|---|
| 标称分辨率 | 可以 | 24 bit、1.192093 µV/LSB |
| 噪声 ENOB | 可以 | 给定短接、采样率和 OSR 下为 16.877--18.342 bit |
| 45 Hz 灵敏度量级 | 部分可以 | 1 s 窄带矢量 RMS 0.0230 nT，单分量 3σ 0.0514 nT |
| 绝对精度 | 不可以 | 缺少可溯源标准场和完整不确定度预算 |
| 整机 0.05 nT 符合性 | 不可以 | 尚未包含 TMR、模拟前端、温漂、环境和标定误差 |

因此正文只能写：

> 在短接输入、16 kHz 采样、8 倍块平均至 2 kHz 以及 1 s 相干积分条件下，
> ADC 子链路的 45 Hz 等效磁噪声进入 0.05 nT 灵敏度量级，说明所选低成本采集
> 方案具备窄带检测的实现基础。该结果不构成整机绝对精度或标准符合性结论。

不能写“整机精度达到 0.05 nT”或“24 bit ADC 具有 24 bit 有效精度”。

机器可读复核位于：

```text
results/magnetic_analysis/20260809_r08_adc_enob_alignment/
```

## 6. 论文图片选择

| 优先级 | 图片 | 建议落点 | 用途 |
|---:|---|---|---|
| 1 | `raw_data/enob/20260809T161036/ch4_enob_vs_osr.png` | §5.3 采集链路噪声表征 | 主图，展示 OSR 与 ENOB 的可解释增益 |
| 2 | `raw_data/joint_analysis/1783235358_205719/complex_iq_fit.png` | §5.4 联合反演 | 主图，展示三轴 I/Q 测量与模型拟合 |
| 3 | `raw_data/enob/20260809T161036/ch4_noise_spectral_density.png` | §5.6 或附录 | 诊断非白噪声和窄带尖峰，不作为达标图 |
| 4 | `raw_data/joint_analysis/1783235358_205719/trajectory_colored_by_b.png` | §5.4 或附录 | 展示运动轨迹形成的空间采样 |

当前图中文字为英文且风格与论文图系尚未完全统一。R10 可先直接引用 PDF/PNG，
最终 R31 前再统一字号、配色、中文图注和矢量输出；不得重新绘图时改变原始数值。

## 7. 后续入口

1. R24 在 Mac/传感器现场执行本 handoff，返回 `contract_complete=true` bundle；
2. M0 与现有 ENOB 结果交叉检查 ADC 本底的重复性；
3. M1 给出完整 TMR+前端+环境背景，决定 0.05 nT 是否仍有系统余量；
4. M4 以 M1 阈值计算逐档检测概率、假警率、幅值偏差和检测下限；
5. R10 将 ENOB 与联合 I/Q 结果学术化写入 Tex，不写实现变量或绝对路径；
6. R29 只将“ADC 短接 ENOB”子项标为已有证据，供电、接地、车载负载和屏蔽计量
   仍未完成。

