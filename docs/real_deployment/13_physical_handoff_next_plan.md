# 13 — 实物 handoff 下一步计划与论文边界映射

> 状态：执行计划，不是已完成实验报告。本文用于把 `docs/real_deployment/01_stage1_link_audit.md` 到 `05_stage5_full_autonomy.md` 的五阶段 SOP，与当前毕业设计仍未验证的实物边界对齐。

---

## 1. 当前基线

截至当前进度，实物相关证据分为三层：

| 层级 | 已完成 | 能支持什么 | 不能外推什么 |
|---|---|---|---|
| native PVS 执行链 | `CONTROL-NATIVE-PVS-EXECUTION-CHAIN-SMOKE`，约 50 s constant-depth/heading smoke | ROS2 controller/MPC/arbiter 可经 `protocol_udp` 与 Mock AMD AUTO dispatch 进入 PVS `depthHeadingAutopilot()`，且未走 `kinematic_setpoint` proxy | 不能替代 PC104/VxWorks 真机接收、调度、执行器响应、R22 native PVS 性能矩阵或海试 |
| Jetson 求解器与短时资源 | Orin NX 25 W/8 核 clean run，稳态 cold/warm 各 200 次、压力档各 50 次 | 稳态 warm/cold p95 为 34.118/36.560 ms 且成功率 100%；压力档越过 50 ms 周期的边界已量化 | 独立求解器微基准不是 ROS2 全栈调度；当前容器--PC104 的 30 min 稳态也不替代 Jetson `tegrastats` thermal soak |
| PC104 UDP、故障同步与长时稳态 | 300 s 正常链路、79.67 s 板端故障矩阵、18/18 跨层同步故障 run，以及独立 1800 s 零执行器稳态区间 | 真实 PC104 双向链路、应用路径 RTT、内部处理时间、Bit5/13/14 到 ROS2 仲裁与 BT 的同步映射、显式重授权和 30 min 通信/软件栈稳态均可报告 | 无共享时钟时不能拆分单向物理时延；未覆盖真实电压/DVL、非零执行器响应或 Jetson 热稳定 |
| handoff 基础设施 | R08/R09 dry-run、`scripts/real_deployment/00..05`、`docs/real_deployment/01..05` | 现场执行脚本、返回包结构、阶段化安全流程已具备 | dry-run 不是 Jetson 热稳定、TMR 完整链路或 S1/S2 实物验收 |

因此，下一步 handoff 的任务不是“重新证明算法正确”，而是把已经建立的算法与仿真证据迁移到真实硬件接口上，逐层关闭以下论文边界：

1. Jetson 目标平台的短时求解器与资源曲线已闭合；当前拓扑已完成 30 min PC104--ROS2 零执行器稳态，但 Jetson 温度、频率和功耗口径的 thermal soak 仍待验证；
2. PC104/VxWorks 的 S1 零执行器通信、watchdog、故障位与 PC104--ROS2--BT 同步安全链已完成半实物验收；S2 急停和执行器极性仍未执行；
3. TMR/SK2301 完整采集链仍停留在 R08 dry-run 与 ADC 子链路 ENOB，尚无 M0/M1/M4 真采集 bundle；
4. S3/S4/S5 水中影子导航、单回路闭环和全自主巡检仍是部署 SOP，不是已完成实物结果；
5. firmware echo 已给出 host-relay 应用路径 RTT；单向物理时延仍须共享时钟或双向时间同步，不得由 RTT 或到达间隔拆分替代。

---

## 2. 与 01-05 五阶段 SOP 的对应关系

`docs/real_deployment/01..05` 定义的是现场部署阶梯；本计划定义的是每一级完成后能关闭哪条论文边界。

| SOP 阶段 | 文档 | 现场动作 | 直接对应的论文边界 | 完成后可写 | 仍不能写 |
|---|---|---|---|---|---|
| S1 通信审计 | [01_stage1_link_audit.md](01_stage1_link_audit.md) | 不插电机电缆；审计 `$AUV/$CKTH`、字节序、scale、frame gap、故障位和零推力下行 | R25 的通信半边；补强 `HARDWARE-PC104-UDP-TIMING-PROBE` | 真实 PC104 链路可解析、可安全下行、上行抖动分布可报告 | 单向物理 latency、执行器响应、闭环控制 |
| S2 静态执行器 | [02_stage2_static_actuator.md](02_stage2_static_actuator.md) | 上架不入水；短时非零通道极性、死区、ESTOP 验证 | R25 的执行器基础半边 | 舵机/推进器极性、死区和急停链路完成上架验收 | 水动力响应、深度/航向闭环、海试安全 |
| S3 影子导航 | [03_stage3_shadow_navigation.md](03_stage3_shadow_navigation.md) | 入水人驾；Jetson 只计算 shadow command，不下发控制 | 真实传感器噪声、EKF Q/R、算法运行稳定性 | Jetson 决策控制栈可在真实水中在线运行并产生可比较 shadow 输出 | Jetson 已接管、闭环控制性能 |
| S4 单回路闭环 | [04_stage4_closed_loop_single.md](04_stage4_closed_loop_single.md) | 恒定 depth/heading/speed setpoint；首次 Jetson 接管 | 真实闭环接口、内外层控制响应 | 在受控围隔中完成单回路闭环，给出超调、稳态误差、响应时间和急停记录 | 全自主巡检、复杂路径、海缆检测验收 |
| S5 全自主巡检 | [05_stage5_full_autonomy.md](05_stage5_full_autonomy.md) | 行为树释放，`ros2 bag record -a` | 最终系统级部署证据 | 仅当 S1-S4、TMR/任务参数和安全窗口均通过后，才可写受限全自主实物演示 | 工业海试验收、长期可靠性、所有海况 |

阶段推进规则：

1. S1/S2 是 R25 的核心，不依赖 TMR 采集完成；
2. S3/S4 需要 R23 Jetson 真机稳定性先返回，否则无法区分算法问题和平台热/算力问题；
3. S5 不是当前论文的硬性收口项，除非 S1-S4 都返回完整 bundle，且现场具备安全水域、急停和任务窗口；
4. R24/R26 的 TMR 采集链可与 S1/S2 并行，但不得把 TMR 未完成作为阻塞 PC104 基础链路的理由。

---

## 3. 下一步优先级

### H0：handoff 包冻结

目的：把现场执行从“照文档操作”变成“按固定 bundle 返回”。

执行项：

1. 确认 `scripts/real_deployment/00_static_preflight.sh` 到 `05_full_autonomy.sh` 均可 `--dry-run`；
2. 固定现场 run id 命名：`YYYYMMDD_HHMMSS_<stage>_<target>`；
3. 每次返回必须包含 `command.txt`、`environment.txt`、`network_snapshot.txt`、`config_snapshot/`、`logs/`、`status.json`、`report.md`；
4. 禁止只返回截图或口头结论。

退出条件：

- mock dry-run 产物路径和 report 结构可读；
- 现场操作者只需要替换 target、时长和 IP 参数。

### H1：PC104--ROS2 30 min 稳态已完成，继续 Jetson thermal soak

对应边界：Jetson 真机短时 clean benchmark 已完成；当前容器--PC104 拓扑另已
完成 1800 s ROS2 bridge/decision/fan-out/rosbag 零执行器稳态，124841 个
ArbiterStatus 样本的 ACTIVE 比率为 1.0，目标故障状态样本和非零推进反馈均为 0。
这关闭的是当前通信与控制软件栈的 30 min 稳态边界，不提供 Jetson `tegrastats`
温度、频率或进程独占功耗，故 Jetson thermal soak 仍需在目标机上执行。

最小矩阵：

| 项 | 条件 | 时长 | 产物 |
|---|---|---:|---|
| baseline short | 25 W / 8 核 | 120 s | bag、solver trace、`tegrastats` |
| combined short | 25 W / 8 核 | 120 s | 同上 |
| MPC steady | 固定工作点 | 200 samples | solver wall time、iteration、fallback |
| MPC stress | 约束压力工作点 | 50 samples | solver tail latency |
| PC104--ROS2 zero-actuator soak | 当前容器/relay/真实 PC104 | 30 min | 已完成；bag、状态、上行帧率、零输出和旧根进程 RSS |
| Jetson combined thermal soak | 25 W / 8 核目标机 | 30 min | 待执行；`tegrastats` 温度、频率、功耗、进程树与 bag |

完成后可写：

- 当前容器--PC104 通信与控制软件栈在零执行器条件下的 30 min 稳态；
- Jetson thermal soak 完成后，目标平台在指定功耗/核心配置下的热稳定与完整资源曲线。

仍不能写：

- PC104 链路时延；
- 执行器响应；
- 海试或真实巡检验收。

### H2：R25-S1 PC104 通信审计复核

对应 SOP：S1。

已有 300 s host-relay 固件回显结果完成正常链路基线；最终 Jetson 原生部署仍需按下表复核：

| 子项 | 要求 |
|---|---|
| 时长 | 300 s 优先；条件不足时至少 60 s |
| 下行 | 10 Hz 安全零推力 `$CKTH`，记录发送帧数 |
| 上行 | `$AUV` frame counter、parse error、p50/p95/p99/p99.9 到达间隔 |
| 旁路 | 宿主机 `tcpdump` 或 relay 原始日志；记录 relay 命令 |
| 拓扑 | 保存 PC104 IP、host IP、容器端口映射、relay/fan-out 选择 |
| 版本 | 保存 VxWorks 程序版本、commit 或二进制生成记录 |

完成后可写：

- 真实 PC104/VxWorks 在最终拓扑下的上行频率、到达间隔、丢包/连续丢包、parse error；
- 零推力下行可经宿主机 relay 进入 PC104。

仍不能写：

- 单向物理时延；
- 非零执行器响应；
- S3/S4 闭环性能。

firmware echo 已完成，只能给出应用路径 RTT。若论文必须讨论单向 latency，
还必须额外增加以下任一机制：

1. 共享时钟：Jetson/PC104 PTP/NTP 可信同步，并记录同步误差；
2. 双向时间同步：估计 offset、skew 与不对称路径误差；
3. 宿主机网卡硬件时间戳：作为旁路证据，但仍需解释端到端定义。

### H3：R25-S2 静态执行器与急停

对应 SOP：S2。

最小执行项：

| 通道 | 观测 | 完成判据 |
|---|---|---|
| left/right rudder | heading 或目视方向 | 极性与配置一致，反向必须写入 config 差异 |
| top/bottom rudder | pitch 或目视方向 | 极性与配置一致 |
| thrust | rpm 或水外短时响应 | 起转点和死区可估计 |
| ESTOP | kill switch 独立发送 | 执行器回零，日志可追踪 |

安全约束：

- 上架不入水，推进器周边 1 m 清空；
- 每路短时注入，路与路之间发回零帧；
- 非零执行器必须有现场人工确认，不允许无人值守脚本长时间运行。

完成后可写：

- PC104 接收非零控制语义后，五路执行器极性、死区和急停链路完成基础验收；
- 仿真与实物参数差异可以回填 `07_param_diff_sim_vs_real.md`。

仍不能写：

- 水中控制性能；
- 稳态深度/航向误差；
- 全自主作业安全。

### H4：S3 入水影子导航

对应 SOP：S3。

目标：不夺权，只让 Jetson 在真实传感器和真实水动力环境下运行完整估计、决策和控制计算。

最低返回：

| 产物 | 作用 |
|---|---|
| `shadow_diff.csv` | 人驾命令与 Jetson shadow command 的差异 |
| `rosbag/*.mcap` | 真实传感器与状态估计回放 |
| EKF innovation / health | 调整 Q/R，检查失锁 |
| operator notes | 人驾动作、异常、急停、环境条件 |

完成后可写：

- Jetson 决策控制栈在真实水中可稳定在线运行；
- 真实传感器噪声和人驾轨迹可用于 EKF 参数初值修订。

仍不能写：

- Jetson 接管成功；
- 闭环控制优于人驾；
- 全自主巡检完成。

### H5：S4 单回路闭环

对应 SOP：S4。

进入条件：

1. H1 Jetson soak 无热降频或不可解释进程崩溃；
2. H2 S1 通信链路 parse error 为 0 或故障原因可解释；
3. H3 S2 极性、死区和急停通过；
4. H4 S3 shadow RMSE 未越过安全阈值，或已完成参数修订后复跑。

推荐顺序：

1. depth-only，小幅阶跃；
2. heading-only，小幅阶跃；
3. depth + heading；
4. depth + heading + speed 低速组合。

完成后可写：

- Jetson 经 PC104/VxWorks 的真实单回路闭环在受控水域内成立；
- 可给出超调、稳态误差、响应时间、急停成功和异常样本。

仍不能写：

- 电缆巡检闭环已实物验收；
- 复杂路径或横流能力；
- 海试和长期可靠性。

### H6：S5 全自主巡检

对应 SOP：S5。

S5 只在以下条件全部满足时推进：

1. S4 单回路闭环至少完成 depth、heading 和组合 setpoint；
2. 行为树急停、超时、低电、漏水、DVL 失锁降级均已在仿真和静态链路中可复核；
3. 任务水域具备安全边界、人工接管和回收条件；
4. 若要宣称“海缆巡检”，TMR/SK2301 或替代观测源必须返回可用质量指标，否则只能写作“自主航行/任务框架演示”。

当前论文收口建议：

- 若 S5 未返回，不影响当前论文 pass 2；
- 未返回时只在展望中写“分阶段部署路线已建立，实物全自主验收待 S1-S5 逐级完成”；
- 不应把 PVS/digital twin 的 S5-like 结果写成真实海试。

---

## 4. 与 TMR/SK2301 handoff 的并行关系

TMR/SK2301 不是 S1/S2 的前置，但它是“海缆巡检验收”的前置。

| 任务 | 当前状态 | 下一步 | 论文影响 |
|---|---|---|---|
| R24 M0/M1/M4 | R08 已完成 dry-run；ADC CH4 ENOB 子证据已有 | 现场采集 M0 三次、M1 三次、M4 五档 | 可从“ADC 子链路”升级为“TMR+ADC+DLIA 最小链路短期噪声与检测概率” |
| R26 扩展采集 | 未开始 | 隔离电源、车载负载、距离、运动轨迹、44--46 Hz 频偏矩阵 | 决定真实噪声 replay、频偏鲁棒性和车体自生磁场边界 |
| R27 九参数标定 | 待器材 | 转台/椭球/温漂 | 关闭杆臂、硬铁、软铁外场标定边界 |
| R28 埋深台架 | 待器材 | 可控电流、距离、埋深 | 关闭 0.2 m 埋深精度和 FWHM 几何模型实测边界 |
| R29 电源/屏蔽 | 部分证据已有 | 供电、地环路、电机/舵机扰动、屏蔽衰减 | 关闭磁卫生和电磁兼容边界 |

若 R24 未返回，S5 即使完成也只能写“自主航行/任务框架”，不能写“真实海缆磁探测闭环验收”。

---

## 5. 返回包契约

每个 handoff run 的最低目录结构：

```text
<RUN_ID>/
  command.txt
  environment.txt
  network_snapshot.txt
  git_snapshot.txt
  config_snapshot/
  logs/
  rosbag/
  raw/
  metrics.csv
  failure_events.csv
  status.json
  report.md
```

字段要求：

| 文件 | 必填内容 |
|---|---|
| `command.txt` | 完整命令、target、duration、IP、端口、是否 `--i-have-physical-auv` |
| `environment.txt` | 主机类型、OS、Jetson power mode、CPU/GPU/内存、时间同步状态 |
| `network_snapshot.txt` | PC104/Jetson/宿主机 IP、端口映射、relay/fan-out 命令、`ping` 或 `tcpdump` 摘要 |
| `git_snapshot.txt` | 主仓 commit、dirty 文件摘要、子模块 commit |
| `config_snapshot/` | brain、bridge、feature flags、real deployment 参数 |
| `logs/` | stack、relay、fan-out、probe、kill switch、VxWorks/UdpLogger |
| `metrics.csv` | 每阶段核心指标；没有指标时必须解释原因 |
| `failure_events.csv` | 失败时间、触发条件、处置、是否安全退出 |
| `status.json` | `contract_complete`、`valid_run_count`、`blocking_failures`、`one_way_latency_claim` |
| `report.md` | 人可读结论、边界、下一步 |

`status.json` 至少包含：

```json
{
  "stage": "S1_link_audit",
  "target": "real",
  "contract_complete": false,
  "valid_run_count": 0,
  "one_way_latency_claim": false,
  "round_trip_latency_claim": false,
  "safe_shutdown_confirmed": false,
  "blocking_failures": []
}
```

只有当关键原始文件、指标文件、日志和安全退出记录均存在时，才允许 `contract_complete=true`。

---

## 6. 论文回填口径

### 6.1 可直接吸收的结果

| 返回项 | 回填位置 | 可写口径 |
|---|---|---|
| R23 Jetson bundle | 第 2 章双脑架构、第 5.3/5.5.9、第 6 章局限 | 目标平台算力、热稳定、MPC solver tail 与控制周期预算 |
| R25-S1 通信审计 | 第 2.5、第 5.3、第 5.7.7、附录 A.7 | PC104 真链路上行到达间隔、丢包、parse error、零推力下行 |
| R25-S2 执行器静态 | 第 2.5、第 5.3 | 执行器极性、死区、急停链路基础验收 |
| R24 TMR 最小采集 | 第 2.3、第 3.2、第 5.3/5.4、第 6 章 | 完整采集链短期噪声、M4 检测概率、假警率 |
| S3 shadow | 第 5.5.9/5.6 | 真实水中在线运行与参数整定证据 |
| S4 single-loop | 第 5.3/5.5.9 | 受控水域单回路闭环性能 |

### 6.2 仍需禁止的表述

即使 H1-H5 全部完成，仍禁止以下写法，除非另有专项证据：

1. “通过真实海缆巡检工业验收”；
2. “系统单向物理时延为 xx ms”；
3. “UA-MPC 在所有真实不确定性场景下提升精度”；
4. “CBF 已消除所有极端场景安全违约”；
5. “TMR/SK2301 整机达到 0.05 nT 绝对精度”；
6. “native PVS smoke 等价于 R22 native PVS 全因子性能矩阵”；
7. “S4 单回路闭环等价于 S5 全自主巡检或海试”。

### 6.3 未返回时的收口策略

若最终论文提交前 handoff 未返回：

| 未返回项 | 论文处理 |
|---|---|
| R23 | 保留 Jetson dry-run 为基础设施，不写真机算力/热稳定结论 |
| R24/R26 | 保留 ADC ENOB 和 TMR 模组报告，不写完整采集链验收 |
| R25 故障/执行器部分 | 保留 PC104 host-relay 300 s 固件回显正常链路，不写故障安全闭环或 S2 执行器验收 |
| S3/S4/S5 | 写为分阶段部署路线，不写实物闭环或全自主结果 |
| 共享时钟 | 保留 firmware echo 应用 RTT，不报告单向物理 latency |

---

## 7. 推荐执行顺序

```text
H0 handoff 包冻结
  -> H1 R23 Jetson thermal soak（PC104--ROS2 零执行器 30 min 已完成）
  -> H2 R25-S1 PC104 300 s 通信审计
  -> H3 R25-S2 静态执行器与急停
  -> H4 S3 影子导航
  -> H5 S4 单回路闭环
  -> H6 S5 全自主巡检（条件满足才推进）

并行线：
R24 TMR M0/M1/M4
  -> R26 扩展采集
  -> R27/R28/R29 器材型计量实验
```

抢占规则：

1. R23 一旦返回，优先回填算力与热稳定，因为它影响双脑架构可信度；
2. R25-S1/S2 一旦返回，优先回填通信与安全执行层，但不反向修改算法矩阵结论；
3. R24 一旦返回，优先更新磁采集链和真实噪声 replay 口径；
4. S3/S4 返回后只更新“部署接口与受控闭环”边界，不直接升级为“海试验收”。

---

## 8. 与现有文档的分工

| 文档 | 角色 |
|---|---|
| [00_principles.md](00_principles.md) | 安全原则、影子测试、协议单元化和黑匣子化 |
| [01_stage1_link_audit.md](01_stage1_link_audit.md) | S1 现场通信审计 SOP |
| [02_stage2_static_actuator.md](02_stage2_static_actuator.md) | S2 静态执行器 SOP |
| [03_stage3_shadow_navigation.md](03_stage3_shadow_navigation.md) | S3 影子导航 SOP |
| [04_stage4_closed_loop_single.md](04_stage4_closed_loop_single.md) | S4 单回路闭环 SOP |
| [05_stage5_full_autonomy.md](05_stage5_full_autonomy.md) | S5 全自主巡检 SOP |
| [06_kill_switch.md](06_kill_switch.md) | 全阶段急停操作 |
| [07_param_diff_sim_vs_real.md](07_param_diff_sim_vs_real.md) | 真机参数差异回填位置 |
| [10_sim_vs_real_link_and_wrapper_map.md](10_sim_vs_real_link_and_wrapper_map.md) | 仿真/真机链路和 wrapper 分层 |
| [12_pc104_timing_port_forward_and_fanout.md](12_pc104_timing_port_forward_and_fanout.md) | PC104 timing、host relay 与 fan-out 拓扑 |
| 本文 | 把上述 SOP 映射到论文未验证边界、handoff 优先级和返回包契约 |

本文不替代 01-05 的操作细节；现场执行仍应从对应阶段 SOP 进入。
