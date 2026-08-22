# Jetson Orin NX 在线算法实时性证据报告

## 结论

在 Jetson Orin NX 25 W / 8 核的当前 clean benchmark 中，当前 `N=20, dt=0.2 s` MPC 的稳态 warm-start wall-time p95 为 34.118 ms，cold-start p95 为 36.560 ms，成功率分别为 100.0%/100.0%。相对 20 Hz ROS 控制周期，warm/cold p95 占用分别为 68.2% 和 73.1%。本轮 warm/cold p95 均低于 50 ms；这只证明独立求解器微基准具备 20 Hz 预算余量，不代表完整 ROS2 控制链已经满足 20 Hz。

约束压力档中，warm/cold wall-time p95 分别为 119.795/122.342 ms，成功率为 100.0%/100.0%。本轮主状态均为 `Solve_Succeeded`，全部样本收敛，但 p95 超过 20 Hz 周期；压力档只能按低频/异步规划或配合降阶、deadline 与 fallback 使用。该档位反映更困难工况下的求解行为，不能简化为“Jetson 算力不足”。

同一 commit/功耗/核数下共有 3 轮兼容 clean run：稳态 warm/cold p95 跨轮范围为 33.948--35.464/33.642--36.560 ms，压力档为 119.795--122.230/122.342--123.691 ms。

PC104 的 30 s host-relay 零推力记录包含 300 帧下行和 450 帧可解析上行，解析错误 0，上行到达间隔 p50/p95/p99 为 57.983/85.710/85.944 ms。帧号审计中有 150 次零增量（重复帧号），大于 1 的前向跳号为 0、估算丢帧为 0；因此原摘要中的 `sequence_gap_count=150` 应解释为重复计数，而非 150 帧丢失。该量是 host-relay/Docker 路径后的到达间隔，不是 Jetson--PC104 单向物理时延、RTT 或端到端闭环时延。

## 资源与完整链路状态

本轮复算现有 `data/runs/20260822_165846`，未启动新负载；其 clean/contaminated 状态以该目录的 `environment.json` 为准。

短时 clean run 共 60 个资源样本、30.224 s；CPU mean/p95/max=39.9/60.0/75.1%，GPU mean/p95/max=46.6/80.6/96.4%，内存 mean/max=4838.2/4918.6 MiB，最高温度=57.4 °C，采样间隔 p95=0.505 s。分阶段 CPU mean 为 idle/steady/stress=34.3/42.6/38.3%。这些是 Jetson 整机遥测而非求解器进程独占归因，且该短时负载剖面不替代 30 min 全栈 thermal soak。

## 图表

- `figures/jetson_mpc_latency_and_success.png`：稳态/压力档 wall-time 分布与成功率。
- `figures/jetson_solver_budget_occupancy.png`：稳态 p95 相对 20 Hz、10 Hz 与 `dt=0.2 s` 周期预算的占用率。
- `figures/jetson_resource_profile.png`：本轮 clean benchmark 的 CPU/GPU、内存和温度时序。
- `figures/pc104_uplink_interarrival.png`：真实 PC104 上行到达间隔时序与经验分布，标题中显式保留非单程时延边界。

## 论文落点

主结果进入第 5 章 §5.6“面向实物的证据基础与迁移路径”，新增“Jetson Orin NX 在线求解实时性实测”子节；第 2 章只保留双脑职责与周期预算的设计依据；微基准、压力档和通信口径限制收束到 §5.7；尚未完成的 ADC/EKF/BT/ROS2 全栈 30 min soak 与 firmware echo 进入第 6 章 §6.3。
