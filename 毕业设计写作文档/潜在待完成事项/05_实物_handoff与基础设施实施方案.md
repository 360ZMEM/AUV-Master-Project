# 05 实物 handoff 与基础设施实施方案

## 1. 目的

本文把待办拆成“本机立即完成、补基础设施、Jetson/PC104 handoff、TMR 顺手采集、
必须器材”五类，并为后三类提前固定输入、命令、记录、验收和回填字段。现场实验
不得只返回截图或一句“跑通”，必须返回可复核的数据包和环境信息。

## 2. 总边界表

类别的完整进入条件、禁止外推与转类条件以
`04_章节级实验方向与执行顺序.md` §1 为唯一分类依据；R03 的频率字段和定点审计
以 `07_R03_五类实验边界与45_50Hz频率语义契约.md` 为准。本表只保留 handoff
实施速查，不另行定义分类语义。

| 类别 | 是否需要用户现场 | 是否需要新增代码 | 是否需要专用器材 | 可进入论文的证据 |
|---:|---|---|---|---|
| 1 立即可做 | 否 | 通常否 | 否 | 仿真统计、重分析、图表 |
| 2 补基础设施 | 否 | 是 | 否 | 算法对比、原生场景、分析方法 |
| 3 handoff | 是 | 少量封装 | Jetson/PC104/AUV | 真机算力、链路与闭环 |
| 4 传感器顺手做 | 是 | 分析器需完善 | TMR8637 + SK2301 | 真实噪声、复增益、磁卫生 |
| 5 器材苛刻 | 是 | 数据接口已有 | 转台/电流源/台架/仪器 | 计量标定、绝对精度 |

## 3. 类别 1：本机立即执行

| 任务 | 现有入口 | 最低规模 | 验收 |
|---|---|---:|---|
| NIS/R 图重生成 | uncertainty aggregates | 8 场景×3 seed | 阈值带、触发率、分位数齐全 |
| 六代理极端场景扩种子 | proxy YAML + sweep | 6×2×3，建议 5 seed | 有效运行率、RMSE、控制变化率、安全违规 |
| BT/FSM 基准重跑 | `tests/benchmark_bt_vs_fsm.py` | 1000 延迟 + 500 组合故障 | 不只报复杂度，加入失败遗漏率 |
| UA-MPC 深层探针 | P-1/P-2/H4 基础 | 3 场景×3 seed/机制 | 初值、约束、热启动和当前失败 wall time |
| 扫描覆盖率 | 轨迹生成器 | 波束宽度×速度×间距网格 | 覆盖率/航程/时间三指标 |
| 45 Hz 短背景重分析 | NPZ + NumPy | 59 个滑窗 | 矩形/Hann/带通对照、p95/p99 |

本类执行完即可消除 §3.4、§4.3、§4.5、§5.7 的主要占位。

## 4. 类别 2：基础设施补充

### 4.1 Tex 写作与构建基础设施

Batch 0 已完成：

- `thuthesis/data/*.tex` 与 `ref/auv-references.bib` 已固定为唯一可信源；
- Makefile 已移除 Markdown→Tex 迁移和参考文献同步的隐式检查；
- GB/T 7714 `gbtypeflag` 已改为兼容当前 TeX Live 2022 的写法；
- `make auv-thesis` 已增加非空 PDF 与 undefined citation/reference/rerun 门控；
- 清理辅助文件后的完整构建和增量构建均成功，当前基线为 175 页；
- Biber 实际条目 90，undefined command/citation/reference 为 0。

剩余非阻断项：

1. `[R01 已完成]` 六章 Tex 文件头已清除 Markdown canonical source 声明；
2. 占位符尚未清零，因此静态占位扫描暂不设为硬失败，待 R31 启用；
3. `zh_CN.UTF-8` 未安装，只产生 Perl locale 回退警告，不影响 PDF；
4. 跨平台切换后若辅助文件版本不兼容，先执行 `make clean-auv-thesis`；
5. 旧迁移/同步脚本只作历史工具，不得写入当前 Tex/Bib。

### 4.2 统一实验清单与产物契约（R04 已完成）

每次运行目录统一包含：

```text
run_manifest.json
config_snapshot/
metrics.csv
status.json
failure_events.csv
environment.txt
report.md
figures/
```

`run_manifest.json` 至少记录：

- Git commit 和子模块 commit；
- dirty worktree 摘要；
- 场景、模式、seed、持续时间；
- 数据层级；
- 控制器/估计器关键参数；
- 启动与结束时间；
- 运行是否有效及无效原因。

当前 `tools/experiment_contract.py` 已接入 thesis/proxy sweep，并由
`tools/validate_experiment_bundle.py BUNDLE` 执行提交前门控。无法观测的字段必须
写 `not_observed`，此时 `contract_complete=false` 且校验命令返回非零；不得用
进程退出码或非空 MCAP 绕过。

### 4.3 45 Hz/DLIA 分析基础设施（R06 已完成）

无头入口为 `tools/analyze_tmr_recording.py`，输出目录由命令行显式指定，不覆盖
`raw_data/figures`：

```text
input NPZ
  -> 电压转 μT
  -> 可选九参数
  -> detrend
  -> window/bandpass
  -> coherent I/Q
  -> ENBW correction
  -> amplitude/phase/ASD/threshold
  -> JSON + CSV + PNG/PDF
```

必须支持：

- `--frequency 45`；
- `--window rect|hann|blackmanharris`；
- `--window-sec`、`--hop-sec`；
- `--bandpass-low/high`；
- `--output-dir`；
- `--headless`；
- 空载/注入两组比较；
- p50/p95/p99、假警率、检测概率和置信区间。

每份分析摘要必须单独写入 `data_source_id`、`excitation_hz`、`reference_hz`、
`frequency_source`、`reference_type` 和 `frequency_provenance`。空载记录的
`excitation_hz` 为 `null`；不得用当前软件默认的 50 Hz 推断旧 NPZ 的历史频率。

### 4.4 实测噪声 replay

把 NPZ 切成去均值/去趋势的片段库，仿真中按固定 seed 复用。必须同时保留：

- 原始三轴相关性；
- 低频漂移；
- 45 Hz 邻域噪声；
- 通道不同幅相响应；
- replay 与参数化高斯噪声两个对照。

### 4.5 原生声磁耦合场景

场景生成器至少统一以下变量：

- 电缆中心线与曲率；
- 电缆埋深/裸露段；
- 地形高程；
- AUV 高度与姿态；
- 声呐可见性；
- 磁场生成与背景噪声；
- 横流；
- DVL dropout；
- 通信时延。

每个变量都有 truth（仅评价）和 measurement（算法可见）两条通道，禁止在线节点
消费 truth。

### 4.6 MPC 可解性诊断

新增每周期诊断：

- 初值与上一解差；
- 初始约束违反量；
- 最终最大约束残差；
- 活跃约束类型；
- IPOPT 迭代数；
- 当前 wall time；
- warm-start 是否使用；
- fallback 类型；
- 控制周期是否被阻塞。

重点对照：

1. 现有硬约束；
2. slack soft constraint；
3. setpoint ramp；
4. feasibility restoration；
5. 终端停止/保持约束。

## 5. 类别 3：Jetson/PC104 handoff

### 5.1 handoff 前由本机准备

- 一键脚本，不要求用户手工拼长命令；
- 运行前检查 `nvpmodel`、CPU 核数、磁盘、ROS2、CasADi；
- 自动关闭或记录 Firefox/桌面可视化负载；
- 同步记录 `tegrastats`、`ps`、ROS2 topic 频率和 rosbag；
- 每条命令带 `timeout`；
- 收尾不允许 `BRIDGE_PID: unbound variable`；
- 失败也保存日志和环境。

### 5.2 Jetson clean benchmark

实验矩阵：

| 工况 | 时长 | 重复 | 记录 |
|---|---:|---:|---|
| idle brain | 5 min | 3 | CPU/RSS/功耗/温度 |
| PVS baseline | 10 min | 3 | 全栈 + bag |
| combined stress | 10 min | 3 | 全栈 + bag |
| MPC steady warm | 200 solve | 3 | p50/p95/p99 |
| MPC constraint stress | 50 solve | 3 | 成功率、失败时间 |
| 30 min thermal soak | 30 min | 1–3 | 温度、频率、降频事件 |

回填字段：

- nvpmodel、JetPack/Ubuntu/ROS2/CasADi 版本；
- CPU/GPU/EMC/功耗/温度 p50/p95/max；
- 节点 CPU/RSS；
- MPC/EKF 运行周期 p50/p95/p99；
- bag 消息数、时长、丢帧；
- 失败状态分布。

### 5.3 PC104 UDP handoff

按 `scripts/real_deployment/00..05` 分阶段：

1. S0 静态自检；
2. S1 链路审计；
3. S2 执行器极性/死区；
4. S3 影子导航；
5. S4 单点闭环；
6. S5 全自主。

必须先完成：

- fan-out 是 21/udp 唯一持有者；
- 关闭仿真转发，避免 52364–52366 污染；
- 确认字节序、scale、序列号；
- KS 急停全程可用；
- `MANUAL_OVERRIDE` 只能由 `CLEAR_FAULT (0x91)` 解锁。

S1 输出表：

| 指标 | 最低要求 |
|---|---|
| 下行/上行包数 | 非零且序列连续 |
| 单向/往返时延 | p50/p95/p99 |
| 抖动 | 标准差和 p99-p50 |
| 丢包 | 比例与连续丢失长度 |
| 字节序/scale | 每字段逐项确认 |
| 故障位 | DVL、Jetson、漏水等注入可观察 |

### 5.4 handoff 返回包

用户执行后必须返回：

```text
handoff_<timestamp>/
  environment.txt
  command.txt
  stdout.log
  tegrastats.log
  process_metrics.csv
  rosbag/
  udp_capture.pcap
  stage_result.json
  notes.md
```

不得只返回截图。截图可作补充，但不能替代日志和机器可读数据。

## 6. 类别 4：TMR/SK2301 顺手采集

### 6.1 最小采集矩阵

全部使用 2000 Hz 原始采样，目标频率固定 45 Hz：

| 编号 | 状态 | 时长 | 重复 | 目的 |
|---|---|---:|---:|---|
| M0 | ADC 输入短接/等效零输入 | 5 min | 3 | ADC/前端本底 |
| M1 | TMR 接入、静置、无电缆 | 10 min | 3 | 传感器+环境背景 |
| M2 | 隔离电源开/关对照 | 5 min | 3 | 供电纹波 |
| M3 | Jetson/电机/舵机不同状态 | 5 min/状态 | 3 | 车体磁卫生 |
| M4 | 45 Hz 已知小信号注入 | 每档 2 min | ≥5 档 | 幅值线性与检测下限 |
| M5 | 45 Hz 电缆，固定距离 | 5 min | ≥5 距离 | \(1/r\) 与检测概率 |
| M6 | 45 Hz 电缆，ArUco 运动 | 1–2 min | ≥5 轨迹 | 几何拟合复验 |
| M7 | 频率 44–46 Hz 扫描 | 每档 1 min | 9–21 档 | 频偏鲁棒性 |

### 6.2 元数据

每个 NPZ 必须记录：

- 采样率、通道、灵敏度；
- 开始时间、持续时间；
- TMR 序列号；
- SK2301 配置；
- 电源、接地、隔离状态；
- 电机/Jetson/舵机状态；
- 电流 RMS、频率、参考相位（若有）；
- 标准字段 `excitation_hz`、`reference_hz`、`frequency_source`、
  `reference_type` 和 `frequency_provenance`；
- 距离、姿态、ArUco 标定；
- 环境温度；
- calibration profile 名称。

### 6.3 验收指标

- 三轴 ASD；
- 45 Hz I/Q 均值、标准差、p95/p99；
- 窗函数和带通对结果的影响；
- 相邻通道相位差；
- 空载假警率；
- 注入检测概率；
- 幅值偏差和相位偏差；
- 检测下限随积分时间的变化；
- Allan deviation 或至少分段稳定性。

### 6.4 可快速进入论文的结果

只要 M0/M1/M4 完成，就能形成：

1. 完整链路短期噪声图；
2. 45 Hz Lock-in 前后对比；
3. 检测阈值与注入幅值曲线；
4. “0.05 nT 是否达到”的实测判定；
5. 仿真噪声注入参数。

### 6.5 R08 可执行入口

R08 已提供 `hardware_wrappers/fangkong_adc/scripts/run_tmr_handoff.py`，单次调用
依次执行 M0×3、M1×3 和 M4 至少五档，并生成 `run_manifest.json`、原始 NPZ、
`metrics.csv`、`failure_events.csv`、日志、状态门控和 R06 分析命令。

真实运行必须填写 TMR 序列号、供电/接地/隔离状态、45 Hz 频率来源和 M4 注入
幅值来源。仅当所有计划项有效时 `contract_complete=true`。完整现场命令、
返回目录和 ADC ENOB 证据边界见
`09_R08_TMR_SK2301最小采集handoff与ADC_ENOB证据.md`。

## 7. 类别 5：必须器材

### 7.1 九参数转台标定

器材：

- 非磁转台或已知姿态夹具；
- 稳定均匀磁场，条件允许时用 Helmholtz 线圈；
- 可靠姿态真值；
- 完整 TMR+前端+ADC 链。

输出：

- bias 3 参数；
- 软铁/非正交 3×3 矩阵；
- 标定前后球面残差；
- 交叉验证轨迹；
- 温漂；
- profile JSON 及不确定度。

若没有均匀可控磁场，只能称“椭球拟合标定”，不能称计量级转台标定。

### 7.2 大电流缩比电缆/埋深台

器材：

- 隔离可控 45 Hz 电流源；
- 黄金电阻或电流探头；
- 可重复距离/埋深网格；
- 单导体、回流导体和可选铠装/屏蔽样件；
- 非磁支架和位置真值。

实验矩阵：

- 电流；
- 垂直距离；
- 横向偏移；
- 电缆方向；
- 单线/双线回流；
- 裸露/覆盖介质；
- 可选坡莫合金屏蔽；
- 传感器姿态。

主结果：

- \(1/r\) 或偶极 \(1/r^2\) 模型选择；
- 电流—距离尺度耦合；
- FWHM 埋深偏差；
- SNR—埋深 RMSE 曲线；
- 屏蔽衰减系数与相位滞后；
- 模型失配残差。

### 7.3 电气与磁卫生计量

器材：

- 示波器/频谱仪；
- 差分探头；
- 电流探头；
- 可选磁屏蔽/磁通门参考。

测量：

- ±15 V 隔离电源纹波；
- 共模/差模噪声；
- 接地方式对 45 Hz 邻域的影响；
- Jetson、推进器、舵机开关磁噪声；
- ADC ENOB 和输入短接噪声。

## 8. 正文回填规则

| 结果状态 | Tex 处置 |
|---|---|
| 类别 1/2 完成且统计充分 | 进入对应方法/实验小节 |
| 类别 3 handoff 完成 | 替换 emulated/待真机表述 |
| 类别 4 有短时实测 | 写“传感器/链路实测”，明确持续时间和配置 |
| 类别 5 未做 | 只在 §6.2/§6.3 保留一项，不在方法章反复提示 |
| 负结果已归因并修复 | 正文写最终因果；过程放 §5.6/附录 |
| 负结果未归因 | 不隐藏，进入 §5.6 的假设与下一探针表 |

## 9. 完成里程碑

### M1：论文不再有占位

- 所有显式占位删除；
- 可立即实验全部完成；
- 第 5 章负结果集中到 §5.6；
- Tex 可从零构建 PDF。

### M2：仿真证据 thorough

- 关键结果至少 3–5 seed；
- 每项主实验有机制消融、失败探针和边界扫描；
- 实测噪声 replay 与原生耦合场景完成。

### M3：真机 handoff 闭合

- Jetson clean benchmark；
- PC104 S1/S2；
- 端到端延迟和热稳定；
- 结果自动回填表。

### M4：传感器链闭合

- M0/M1/M4/M5；
- 45 Hz 检测阈值；
- 三轴复增益；
- 真实噪声仿真模型。

### M5：器材实验闭合

- 九参数标定；
- 大电流/埋深；
- 电源纹波和磁卫生；
- 最终系统级误差预算。
