# PC104/VxWorks 固件回显与双脑 UDP 时序实测

## 1. 目的与结论边界

本文记录真实 PC104/VxWorks 固件烧录后的双脑 UDP 时序验证。实验通过 macOS
宿主机 full-duplex relay，把容器中的安全零执行器 `$CKTH` 下行转发至
`192.168.0.101:21`，并把 PC104 生成的 145 B `$AUV` 上行送回容器。

本实验可验证：

- 真实 PC104 的 `$CKTH` 接收与 `$AUV` 回传链路；
- PC104 相对运行时间戳的有效性和单调性；
- 固件下行接收事件的帧号与 uptime 回显；
- 主机侧发送到首次收到对应固件回显的往返时间；
- PC104 从记录下行接收到首次打包 `$AUV` 的内部处理时间。

本正常链路实验不能单独验证：

- Jetson 与 PC104 的严格单向物理时延，因为两端没有共享时钟；
- 执行机构动作响应时间，因为下行始终保持零执行器；
- 心跳丢失、控制器超时、错误反馈及行为树安全降级；这些项目已由后续
  [telnetd 故障注入与分层安全实验](15_pc104_fault_injection_and_layered_safety.md)
  分层补齐；
- DVL 时间戳对 ES-EKF 的实物收益，除非本轮存在有效 DVL BI 数据。

## 2. 拓扑与安全约束

```text
容器 probe 0.0.0.0:21
  |  $CKTH, 72 B, zero actuator
  v
Mac host 192.168.65.254:10022
  |  pc104_udp_host_relay.py
  v
Mac physical NIC 192.168.0.11:21
  |  full-duplex UDP
  v
PC104/VxWorks 192.168.0.101:21
```

relay 默认拒绝非零执行器下行。本轮 probe 使用
`control_mode_byte=0xEE`、`work_instruction=0`、主推/侧推和四舵量均为零。

## 3. 固件时间字段

提交 `46fc798d42eeec621417affb526dab86978f7d2c` 引入 PC104 相对时间基准：

- `$AUV Para3`：上行帧打包时的 PC104 uptime，单位 ms；
- `$AUV Para4`：最近一次 DVL BI 数据解析时的 PC104 uptime，单位 ms；
- `$AUV Para12=0x5453`：时间字段有效标志。

后续固件回显扩展增加：

- `$AUV Spare1=0x4543`：下行回显有效标志；
- `$AUV Spare2`：最近一次有效 `$CKTH` 的帧号；
- `$AUV Para1`：PC104 收到该 `$CKTH` 时的 uptime，单位 ms。

因此可以计算

\[
t_{\mathrm{rx\rightarrow pack}}
=t_{\mathrm{PC104,pack}}-t_{\mathrm{PC104,rx}},
\]

并在主机单调时钟上计算从某下行帧发出到首次收到对应固件回显的
first-echo RTT。相同 echo 会被后续多个 `$AUV` 帧重复携带，统计时必须按
`(echo_frame, rx_uptime_ms)` 去重，并且只保留每个固件接收事件的首次上行回显。

## 4. 连接确认

烧录后确认：

- 容器到 `192.168.0.101` 的 ICMP 可达；
- `192.168.0.101:23/tcp` 返回 VxWorks telnet 协商字节；
- `192.168.0.101:21/tcp` 返回 Wind River FTP 6.5 banner；
- Mac 物理口 `192.168.0.11:21/udp` 可观测到来自
  `192.168.0.101:21` 的 145 B `$AUV`；
- 单向 `socat` 能看到 PC104 上行，但 Docker publish 未稳定把该上行送入容器；
- 切换到 `scripts/pc104_udp_host_relay.py` 后，容器与 PC104 的双向 UDP 链路打通。

## 5. 30 s 固件回显结果

原始证据目录：

```text
results/control/pc104_udp_timing/20260822_194343/
```

主要结果：

| 指标 | 结果 |
|---|---:|
| 实验时长 | 30 s |
| 安全零执行器 `$CKTH` 下行 | 300 帧 |
| 已解析 `$AUV` 上行 | 450 帧 |
| 解析错误 | 0 |
| 上行观测频率 | 15.000 Hz |
| 上行到达间隔 p50/p95/p99 | 58.005/85.646/85.974 ms |
| PC104 uptime 有效率 | 100% |
| firmware echo 有效率 | 100% |
| 上行估计丢帧 | 0 |

逐 `$AUV` 直接统计会把同一 echo 的重复携带计为多个 RTT 样本，得到约
`513.770 ms` 的 p95；该值表示 echo 样本在连续上行帧中的年龄，不应作为
首次回显 RTT。按固件接收事件去重并排除启动时继承的旧 echo 后，共得到
100 个有效 first-echo 样本：

| 指标 | p50 | p95 | 最大值 |
|---|---:|---:|---:|
| 主机 first-echo RTT | 313.011 ms | 314.148 ms | 314.847 ms |
| PC104 receive-to-first-pack | 16 ms | 16 ms | 16 ms |

first-echo RTT 包含容器调度、Docker Desktop、宿主机 relay、双向以太网、
VxWorks 收包与周期性上行调度，不等于任一方向的单向物理传播时间。

## 6. 300 s 长时结果

使用修正后的探针连续运行 300 s，原始证据目录为：

```text
results/control/pc104_udp_timing_echo_300s_20260822/
```

探针发送 3000 帧安全零执行器 `$CKTH`，解析 4505 帧 `$AUV`，全程无解析错误。
PC104 uptime 和 firmware echo 的有效率均为 100%，uptime 无倒退；12 次
`$AUV` 8 位帧号回卷和 11 次 echo 帧号回卷均被正确处理。

| 指标 | 300 s 结果 |
|---|---:|
| `$CKTH` 下行发送间隔 p50/p95/p99/p99.9 | 99.933/116.151/120.173/123.211 ms |
| `$AUV` 上行到达间隔 p50/p95/p99/p99.9 | 58.005/85.721/86.095/86.630 ms |
| `$AUV` 前向序号缺口/估计丢帧 | 0/0 |
| `$AUV` 重复帧 | 1501 |
| 唯一/可配对固件接收事件 | 1002/1001 |
| 固件观测下行覆盖率 | 1001/3000，33.37% |
| 固件接收事件间隔 | 300 ms，1000/1000 个间隔一致 |
| first-echo RTT p50/p95/p99/p99.9/max | 264.678/313.965/315.607/316.536/318.550 ms |
| PC104 receive-to-first-pack p50/p95/p99/max | 16/16/16/16 ms |

receive-to-first-pack 实际只出现 `1 ms` 和 `16 ms` 两档，样本数分别为 500 和
501，反映了 60 Hz `tickGet()` 量化与收发任务相位。固件接收事件严格每
`300 ms` 出现一次，与 `main.c` 中 `Net_Recv_Task_Period=3` 及 0.1 s 基准周期
一致。因此 33.37% 是“10 Hz 下行中被当前 3.33 Hz 固件接收任务记录并回显的
比例”，不是以网卡抓包为依据的物理网络丢包率。

`$AUV` 上行帧中有 1501 个重复序号，但没有大于 1 的前向跳变。其含义是同一
控制状态被周期性重复上送，而不是丢失了 1501 帧；原始统计若把所有
`gap != 1` 都记为丢包会混淆这两类事件，修正后的探针已分别报告 duplicate
和 forward gap。

![PC104 双脑 UDP 周期统计](../../results/control/pc104_udp_timing_echo_300s_20260822/figures/pc104_packet_cadence.png)

![PC104 固件时间戳回显统计](../../results/control/pc104_udp_timing_echo_300s_20260822/figures/pc104_firmware_echo_timing.png)

PC104 uptime 与容器接收单调时钟的线性拟合斜率显示，300 s 内 PC104 相对速率
约为容器时钟的 `1.000962` 倍，即约 `+962 ppm`。拟合绝对残差 p95 为
`0.774 ms`，说明短时节拍稳定，但单次锚定且固定斜率为 1 的跨设备时间映射会
在长时间运行中累积偏差。该速率差只作为当前 host-relay 实验的时钟映射诊断，
不能外推为所有温度、供电和部署条件下的固定晶振参数。

图与派生统计由以下脚本从逐包 CSV 确定性生成：

```bash
python3 tools/plot_pc104_firmware_echo_timing.py \
  --bundle results/control/pc104_udp_timing_echo_300s_20260822
```

## 7. 对 ES-EKF 的信息价值

`46fc798` 的时间字段不是只用于日志。当前代码路径为：

```text
VxWorks DVL BI parse uptime
  -> $AUV Para4
  -> common.protocol parse
  -> bridge map_pc104_uptime_to_ros_seconds()
  -> DVL TwistStamped.header.stamp
  -> auv_localization_node
  -> ES_EKF.correct_dvl_world_with_timestamp()
```

该路径为 ES-EKF 提供两类有效信息：

1. PC104 上行打包 uptime 为同一 `$AUV` 派生的 IMU/状态消息提供统一时序锚点，
   避免把容器收包时间误当成设备侧数据时刻；
2. DVL BI parse uptime 给出最近 DVL 观测相对上行打包时刻的陈旧度，
   ES-EKF 可据此在延迟超过 50 ms 时膨胀 DVL 观测噪声。

当前实现仍有两项边界：

- uptime 到 ROS 时间采用首帧锚定的仿射平移，没有在线估计两端时钟频率偏差；
- ES-EKF 当前只按时间差膨胀观测噪声，没有执行历史状态回溯和延迟状态更新。

300 s 实测的 `+962 ppm` 相对速率差进一步表明：对于 PC104 内部 DVL
陈旧度，打包 uptime 与 DVL parse uptime 来自同一时钟域，二者作差仍然有效；
对于 PC104 与 Jetson 磁场/声呐等跨时钟域观测的长期融合，则应把
`map_pc104_uptime_to_ros_seconds()` 扩展为带斜率的在线时钟映射，或定期重锚。

本轮 30 s 和 300 s 实测中 `pc104_dvl_bi_time_valid=0`，原因是
`DVL_BI_Uptime_Ms=0`，说明 PC104 本轮未解析到有效 DVL BI 数据。因此目前可以
确认“协议、bridge 和 ES-EKF 消费路径成立”，但不能声称已经实测证明该时间戳
改善了 ES-EKF 精度。

相关纯函数和协议回归已通过：

- PC104 uptime 到 ROS 时间域映射及 DVL 早于上行打包时刻的映射；
- `$AUV` PC104 uptime、DVL uptime 和 firmware echo 字段解码；
- ES-EKF 对延迟 DVL 观测执行噪声膨胀。

当前环境没有 `pytest` 可执行文件，上述测试通过直接加载对应无 fixture
测试函数完成。

## 8. 与必须实验 5 的关系

`毕业设计写作文档/潜在待完成事项/28_后续实物计划.md` 的必须实验 5 要求同时
覆盖正常通信基线和故障降级。本文件完成其中的正常链路基线：

- 真实 PC104/VxWorks 代替执行脑模拟器；
- 双向 `$CKTH/$AUV` UDP 通信；
- 正常工况通信到达间隔、first-echo RTT、解析错误和丢帧统计；
- 固件接收时间与上行打包时间的双端可观测字段。

后续正式矩阵已在真实 PC104 上完成 5 次自然心跳中断、3 次 telnetd 强制
watchdog 超时、固定种子精确 30% 应用层丢包、200 ms 排队延迟和 Bit5 错误状态
回传；生产 `CommandArbiter` 与行为树又分别完成控制器/PC 超时和任务级降级回放。
因此必须实验 5 已达到“分层半实物验收完成”，详细数据与边界见
[15_pc104_fault_injection_and_layered_safety.md](15_pc104_fault_injection_and_layered_safety.md)。

这里的“分层”不可省略：PC104 Bit14、ROS2 仲裁器超时和行为树授权丢失并非同一次
ROS2--PC104 同步闭环，当前结果也不包含执行机构动态响应或严格单向物理时延。
