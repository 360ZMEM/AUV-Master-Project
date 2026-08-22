# PC104 telnetd 故障注入与跨层同步安全证据

## 1. 结论

2026-08-22 在真实 PC104/VxWorks 执行脑上完成零执行器故障注入。正式矩阵持续
79.67 s，解析 1197 帧 $AUV 上行且无解析错误；5 次自然心跳中断和 3 次
telnetd 强制 watchdog 超时均触发 Bit14 与 Remote 降级，并在恢复零命令心跳后
清除。30% 丢包与 200 ms 排队延迟阶段均未触发错误降级；Bit5 软件故障位能够
由上行观测并在撤销后清除。全程上行两路推进反馈和 telnet 观测到的电机/四舵
命令均为零，结束后板端恢复到 Remote、故障字零和原始 DVL 运行时字段。

在上述分层证据基础上，随后把 PC104 `Sys_Abnorm_Inf` 的 Bit5/Bit13/Bit14
接入生产 bridge、CommandArbiter 与行为树，并在同一 rosbag 时间轴完成真实
PC104--ROS2--BT 同步验证。修正后的短时运行 18/18 项通过；另一次独立运行完成
1800 s 零执行器稳态区间。由此“必须实验 5”可提升为“真实执行脑到任务层的同步
零执行器安全链已验证”，但仍不构成非零执行机构动态响应或整艇水域闭环试验。

## 2. 实验对象与安全边界

- PC104：192.168.0.101:21/udp，VxWorks telnetd 为 192.168.0.101:23/tcp。
- 数据路径：container sender -> Mac host relay -> PC104；上行沿反向路径返回。
- 所有 $CKTH 在发送前均由协议解析器复核，主推、侧推和四舵命令必须全零。
- telnet 快照监测 UI 两路电机、UI 四舵命令和 MCU 两路电机目标；非零即失败。
- DVL BD_Check=2、BD_Height=5 m 仅用于隔离“无 DVL”先触发 Bit13 的耦合，结束后恢复。
- 上行四舵字段恒为 +/-180 deg，来源是 FMCU 未连接/默认原始位置字为零后的反馈换算，
  不是 PC104 下发命令，故保留为诊断量但不作为零命令判据。

正式数据：

    results/control/pc104_fault_injection_formal_v2_20260822/

复现入口：

    python3 tools/probe_pc104_fault_injection.py --execute \
      --natural-trials 5 --forced-timeout-trials 3 \
      --loss-rate 0.30 --loss-duration-s 10 \
      --delay-ms 200 --delay-duration-s 10 --seed 20260822 \
      --output-dir results/control/pc104_fault_injection_formal_v2_20260822

## 3. 真实 PC104 故障结果

| 项目 | 结果 |
|---|---:|
| 时长 / 已解析上行 / 解析错误 | 79.672 s / 1197 / 0 |
| 自然断链检测 | 5/5 |
| 自然 Bit14 触发 p50/p95 | 1044.111/1056.357 ms |
| 自然切换 Remote p50 | 1044.111 ms |
| 恢复 Jetson 模式 p50/p95 | 223.207/238.896 ms |
| Bit14 清除 p50/p95 | 537.003/552.728 ms |
| telnet 强制超时检测 | 3/3 |
| 强制超时触发 p50/p95 | 183.648/337.845 ms |
| 强制超时恢复 p50/p95 | 363.717/459.826 ms |
| 固定种子丢包 | 30/100，30.0% |
| 排队延迟 p50/p95 | 200.979/203.996 ms |
| Bit5 观测/清除 | 是/是 |
| 丢包/延迟阶段 Bit14 帧 | 0/0 |
| Bit13 干扰帧 | 0 |
| 非零推进反馈 / 非零 telnet 命令快照 | 0/0 |
| 清理后 Remote+zero | 通过 |

自然断链时延从最后一个心跳生成阶段结束计到首次上行 Bit14，包含 relay 中在途帧，
所以约为 1.02--1.06 s，符合 1.0 s watchdog 与上行离散采样的组合预期。强制超时
先静默 0.6 s 排空在途帧，再把计数写为 10；45--355 ms 的触发离散度来自 0.5 s
EmergencyTask 调度相位，而不是网络 RTT。

## 4. 受控 impairment 与错误反馈

丢包阶段在容器 sender 到 host relay 之前，以固定种子随机选择 100 个逻辑帧中的
30 个并丢弃，因此配置率和实现率均为 30.0%。200 ms 延迟阶段使用单调时钟队列，
生成至发送时延 p50/p95 为 200.979/203.996 ms。这两项是应用路径注入，不是
Ethernet PHY 丢包率或经共享时钟测得的单向传播时延。两阶段均保持 10 Hz 逻辑
心跳中的最大连续空隙低于 PC104 1.0 s 门限，因而 Bit14 帧数均为零，这一结果
验证的是对给定 impairment 的容忍，而不是任意突发丢包下都不会降级。

Bit5 用 telnetd 同时写入 FMCU 反馈故障字和 PC104 汇总故障字，并在 3 s 窗口内
周期维持，随后撤销。上行可见 Bit5 从 0 变为 1 并恢复为 0。它验证了故障位打包、
回传与主机解析链，不代表真实 MCU 硬件故障已经发生。

![PC104 故障注入统一时间线](../../results/control/pc104_fault_injection_formal_v2_20260822/figures/pc104_fault_timeline.png)

![受控丢包、排队延迟与安全计数](../../results/control/pc104_fault_injection_formal_v2_20260822/figures/pc104_impairment_summary.png)

## 5. ROS2 仲裁、行为树与真实 PC104 同步证据

生产 CommandArbiter 的 10 ms 确定性时间回放位于：

    results/control/arbiter_timeout_evidence_20260822/

其结果为：MPC 命令超过 0.5 s 后在 510 ms 观测到 SAFETY_FALLBACK，执行量全零；
PC 心跳在 1.01 s 进入 WEAK，在 1.51 s 进入 LOST，并于同一采样切到 Remote 零输出。
审计同时发现并修复了本地 force_remote 误刷新 PC 心跳时间戳的问题；修复后 LOST
在本地降级包持续发送期间保持，直至显式 PC 指令重新授权。该实验直接执行生产
CommandArbiter，但不包含 ROS executor 调度，故时间量化精度为 10 ms。

行为树证据位于：

    results/decision/bt_fault_injection/reproducible_20260822/

27 组场景/种子回放全部有效、漏报和假阳性均为零；漏水、低电与穿底进入
RETURN_OR_ABORT，感知丢失进入 RELOCALIZATION，授权丢失进入 SAFE_HOVER，
求解超时代理进入 DEGRADED_MODE。脚本已把进程随机化的 Python hash 替换为
CRC32 稳定场景种子；两次独立运行的 behavior_tree.csv 与 fault_records.csv
SHA-256 完全一致。

独立回放用于固定规则边界，真实同步实验则关闭此前的跨层接线缺口。bridge 解析
`Sys_Abnorm_Inf` 后把原始故障字及 Bit5/Bit13/Bit14 发布到
`/auv/arbiter/status`；decision node 将 Bit5/Bit14 映射为
`communication_link_ok=false`，将 Bit13 映射为
`velocity_aiding_valid=false`。其中 Bit5/Bit14 触发
`COMM_LINK_FAILURE`、Remote 零输出和行为树 `IDLE`；Bit13 不撤销自治授权，而是
使精确跟踪条件失败并进入 `ZIGZAG_SEARCH`。

修正后的同步故障运行位于：

    results/control/pc104_cross_layer_fault_sync_20260822_225436/

该运行在同一时间线上记录真实 `$AUV` 故障字、ArbiterStatus、ControlGoal、
Setpoint、BT 状态、shadow command 与板端快照，18/18 项通过。主机观测的
Bit13 到仲裁/行为树时延分别为 65.097/349.100 ms；Bit5 到 DENIED/IDLE 分别为
102.532/188.463 ms；暂停 bridge 下行后由真实 PC104 watchdog 产生的 Bit14 到
DENIED 为 1071.706 ms。故障清除后系统保持 DENIED，必须收到显式零命令授权才
恢复 ACTIVE；Bit14 的物理清除由独立恢复入口发送经协议反解确认的 Remote
零执行器包完成，仍经过 fan-out 的最终安全门。

30 min 稳态运行位于：

    results/control/pc104_cross_layer_fault_sync_20260822_222112/

其 1800 s `active_soak` 区间完整执行，124841 个 ArbiterStatus 样本的 ACTIVE
比率为 1.000000，Bit5/Bit13/Bit14 目标故障状态样本为 0，30 个分钟级运行采样
全部完成；fan-out 记录上/下行 27323/35843 帧、阻断 0 帧，非零板端命令快照和
非零上行推进反馈均为 0。该原始 bundle 在稳态结束后的旧 Bit14 clear-hold
附加序列有 1 项调度竞争失败，因此整包 `failed_acceptance` 状态保持不变；
`active_soak_stable=true` 只证明完整稳态子区间通过。修正后的 18/18 故障序列
由前述 `225436` 独立运行提供，二者不得写成同一次全部通过的长时故障实验。

![PC104--ROS2--行为树同步故障时间线](../../results/control/pc104_cross_layer_evidence_20260822/figures/pc104_cross_layer_fault_timeline.png)

![PC104--ROS2 零执行器全栈 30 min 稳态](../../results/control/pc104_cross_layer_evidence_20260822/figures/pc104_cross_layer_soak_30min.png)

上述时延均为容器单调时钟上的主机观测跨层触发时间，不是共享时钟下的单向物理
网络时延。台架上行电压为 0.0 V，本通信链实验把电源 guard 阈值隔离为 -1.0 V，
故不构成电源健康验收。DVL 的 `BD_Check=2`、`BD_Height=5 m` 是避免固件 DVL
失锁自救分支产生 300 RPM 目标的临时安全隔离值，Bit13 结果只验证状态映射，不
验证真实 DVL 或该自救分支的执行效果。

## 6. 产物索引

- 原始时间线：fault_timeline.csv（2310 行，含表头）。
- 板端前后状态：board_state.json。
- 汇总与契约：summary.json、metrics.csv、status.json、run_manifest.json。
- 逐轮派生指标：figures/fault_trial_metrics.csv。
- 图：pc104_fault_timeline、pc104_fault_latency_trials、pc104_impairment_summary，均有 PNG/PDF。
- 同步故障 run：pc104_cross_layer_fault_sync_20260822_225436，18/18 通过。
- 30 min 稳态 run：pc104_cross_layer_fault_sync_20260822_222112，
  `active_soak_stable=true`，原包后置附加序列 17/18。
- split-run 汇总：pc104_cross_layer_evidence_20260822，含
  aggregate_summary.json、derived_metrics.csv 及两张 PNG/PDF。
- 工具：tools/probe_pc104_fault_injection.py、tools/plot_pc104_fault_injection.py、
  tools/run_arbiter_timeout_evidence.py、tools/run_bt_fault_injection.py、
  tools/run_pc104_cross_layer_fault_sync.py、
  tools/plot_pc104_cross_layer_evidence.py。

结论：现有 VxWorks 符号、watchdog 和上行故障字已满足本轮验证需求，未修改
csd_vx6.8_lastest。跨层状态接线与 30 min 零执行器稳态已经完成；剩余工作是
真实电压/DVL、共享时钟、非零执行机构、ADC--EKF--控制全执行量闭环与水域试验，
不能由本轮通信安全证据替代。
