# Jetson Orin NX 在线算法实时性实验

本目录落实 `28_后续实物计划.md` 的“必须实验 4”，同时补齐“尽量实验 4”的 Jetson 一键复现入口。实验对象是目标计算平台上的 MPC 求解时序与资源状态；PC104 数据只作为通信侧到达间隔的独立证据，不能与求解耗时相加为端到端时延。

## 现有证据复算与出图

不启动新负载，只复算仓库中已经归档的 Jetson MPC 和 PC104 原始样本：

```bash
real_experiments/jetson_realtime/run.sh --existing
```

生成 `metrics.json`、`data/latency_summary.csv`、`figures/*.png|pdf` 和 `report.md`。该模式用于论文 grounding，不会把历史样本伪装成当前复测。

复算某次当前 run bundle 而不重新启动负载：

```bash
real_experiments/jetson_realtime/run.sh --run-dir \
  real_experiments/jetson_realtime/data/runs/20260822_165846
```

## Jetson 干净复测

关闭浏览器、桌面监控和非必要 ROS2 节点，确认软件安装、编译和文件索引任务已经结束，然后运行：

```bash
real_experiments/jetson_realtime/run.sh
```

默认先记录 5 s 空闲基线，再执行当前 Jetson 上的稳态 MPC `200` 次 cold/warm 求解与约束压力档 `50` 次 cold/warm 求解，同时以 0.5 s 周期记录整机 CPU、GPU、内存、负载和温度，并保留 `tegrastats` 原始日志。资源遥测是系统级占用，不是求解器进程独占归因。若检测到 `apt/dpkg`、系统升级或 `colcon build` 等竞争负载，脚本会拒绝把该轮标为 clean benchmark；诊断时可显式追加 `--allow-busy`，但结果会标记为 contaminated，不能进入论文正式表。

## 证据边界

- 稳态/压力档数据测量 `AUVMPCOptimizer.solve()` 的 wall time 与求解状态，是目标平台求解器微基准，不是 ADC→EKF→BT→控制→PC104 的全链路端到端时延。
- 历史 PC104 记录测量 host-relay/Docker 拓扑下 `$AUV` 上行包的到达间隔。缺少 firmware echo 或可信共享时钟时，不报告单向物理时延、RTT 或闭环时延。
- CPU/GPU/内存曲线只在新一轮 benchmark 模式产生；`--existing` 模式对不可观测字段明确写 `not_observed`。
- 约束压力档低成功率反映初始状态与约束组合难解/不可行，必须与 fallback、setpoint ramp 和可行性检查一起解释，不能归因成 Jetson 算力不足。

## 论文落点

- 第 2 章 §2.2 双脑架构：只补“为何把高算力非硬实时任务部署在 Jetson”的方法 grounding，不放结果图。
- 第 5 章 §5.6“面向实物的证据基础与迁移路径”：在“双脑通信与故障自救”之前新增“Jetson Orin NX 在线求解实时性实测”，放主结果表与一张组合图。
- 第 5 章 §5.7：保留微基准不等于全链路、压力档不可行以及资源曲线待 clean run 的边界。
- 第 6 章 §6.3：只保留 ADC/EKF/BT/ROS2 全栈 soak 和 firmware echo 等下一层验证，不重复已经完成的求解器结果。
