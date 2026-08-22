# PC104/AMD 物理 UDP 时序: 端口转发与 fan-out 判断

日期: 2026-08-10

本文记录当前容器端口映射下，PC104/VxWorks 物理 UDP timing probe 是否需要宿主机端口转发，以及是否需要启用 `scripts/pc104_udp_fanout.py`。

## 1. 当前结论

1. 当前映射 `10021:21/udp` 不能直接接住 PC104 固定发往宿主机 `21/udp` 的 `$AUV` 上行，除非 PC104 上行目标端口可改为 `10021`。在既有实物记录中，PC104 主链路按 `192.168.0.101:21 <-> 192.168.0.11:21` 工作，因此需要宿主机侧转发。
2. 当前映射 `62367:52367/udp` 同理不能直接接住固定发往宿主机 `52367/udp` 的 UdpLogger，除非固件日志目标端口可改为 `62367`。若需要日志证据，需要宿主机侧 `52367/udp -> 62367/udp` 转发。
3. 单向 `socat -u UDP4-RECVFROM:21 -> 127.0.0.1:10021` 只能验证 PC104 上行进入容器，不能验证容器下行以宿主机 `192.168.0.11:21` 身份进入 PC104。若 timing probe 要发送零推力 `$CKTH`，下行也必须经过宿主机 relay。
4. 物理 timing 证据优先使用宿主机 full-duplex relay 加容器 probe，不默认引入 ROS2/PySide6 fan-out。理由是 fan-out 会增加一层业务复用，适合并发联调，不适合作为最小干扰的时序基线。
5. 当需要 ROS2 bridge、PySide6 GUI、旁路 timing/sniffer 同时在线，或需要统一阻断非零执行器下行时，启用 fan-out。现有 `scripts/pc104_udp_fanout.py` 已覆盖该需求，不需要重新实现 fan-out 架构。
6. 当前 PC104 firmware echo 已能报告 host-relay 应用路径 RTT 和 PC104 receive-to-pack；但没有共享时钟时仍不能把 RTT 拆分为上下行单向物理时延。

## 2. 端口映射解释

当前容器端口映射为:

| 宿主机端口 | 容器端口 | 协议 | 与 PC104 时序的关系 | 判定 |
|---:|---:|---|---|---|
| 10021 | 21 | UDP | PC104 主上行 `$AUV` 历史目标是宿主机 `21/udp` | 需要宿主机 `21 -> 10021` 转发，或改 PC104 目标端口 |
| 2222 | 22 | TCP | SSH/容器入口 | 与 timing 无关 |
| 52364 | 52364 | UDP | fan-out 下行入口或 mock/bridge 端口 | 可直接用于容器内 fan-out/bridge |
| 52365 | 52365 | UDP | ROS2/timing probe 上行订阅端 | 可直接用于容器内高端口消费者 |
| 52366 | 52366 | UDP | PySide6 GUI 上行订阅端 | 可直接用于容器内高端口消费者 |
| 62367 | 52367 | UDP | PC104 UdpLogger 历史目标是宿主机 `52367/udp` | 需要宿主机 `52367 -> 62367` 转发，或改 UdpLogger 目标端口 |
| 7447 | 7447 | TCP/UDP | Zenoh router | 与 PC104 UDP timing 主链路解耦 |
| 8765 | 8765 | TCP | Foxglove/WebSocket | 与 PC104 UDP timing 主链路解耦 |

## 3. 拓扑 A0: 单向上行检查

用途:

- 只确认 PC104 `$AUV` 上行是否能从宿主机 `21/udp` 转入容器；
- 不发送 `$CKTH` 下行；
- 用于区分“PC104 无上行”和“容器端口映射/转发未打通”。

宿主机执行:

```bash
# PC104 $AUV: 192.168.0.101 -> 宿主机 21/udp -> 容器 21/udp。
# 该命令是单向上行检查，不是 full-duplex timing relay。
sudo socat -u \
  UDP4-RECVFROM:21,bind=192.168.0.11,reuseaddr,fork \
  UDP4-SENDTO:127.0.0.1:10021
```

容器内执行:

```bash
python3 tools/probe_pc104_udp_timing.py \
  --receive-only \
  --remote-host 192.168.0.101 \
  --remote-port 21 \
  --local-host 0.0.0.0 \
  --local-port 21 \
  --duration 30 \
  --output-dir results/control/pc104_udp_timing_real_uplink_only_$(date +%Y%m%d_%H%M%S)
```

若宿主机 `socat -v` 显示收到 PC104 上行，但容器仍 `uplink_count=0`，优先检查宿主机到 Docker publish 的方向。Linux 宿主机可尝试把目标从 `127.0.0.1:10021` 改为容器 IP，例如当前容器为 `172.18.0.2:21`:

```bash
sudo socat -u -v \
  UDP4-RECVFROM:21,bind=192.168.0.11,reuseaddr,fork \
  UDP4-SENDTO:172.18.0.2:21
```

## 4. 推荐拓扑 A: full-duplex host relay + timing probe

用途:

- 需要发送 10 Hz 安全零推力 `$CKTH`；
- 希望 PC104 看到的下行源端点仍是宿主机 `192.168.0.11:21`；
- 不同时运行 ROS2 bridge 和 PySide6。

宿主机执行:

```bash
# 必须先停止占用 21/udp 的 socat、fan-out 或旧 relay。
sudo python3 scripts/pc104_udp_host_relay.py \
  --host-ip 192.168.0.11 \
  --pc104-host 192.168.0.101 \
  --pc104-port 21 \
  --pc104-local-port 21 \
  --container-uplink-target 127.0.0.1:10021 \
  --downlink-bind-host 0.0.0.0 \
  --downlink-bind-port 10022 \
  --container-log-target 127.0.0.1:62367

# 可选: PC104 UdpLogger -> 宿主机 52367/udp -> 容器 52367/udp
# 上述 relay 默认也会绑定 192.168.0.11:52367 并转发到 127.0.0.1:62367。
```

说明: `--container-uplink-target` 是静态回退目标。默认情况下，relay 会从第一帧通过安全检查的 `$CKTH` 下行学习容器在宿主机侧呈现的实际 UDP 源地址，并通过 `10022/udp` 同一 socket 把 PC104 主上行回送到该地址。该机制用于规避 Docker Desktop/宿主机网络中 `127.0.0.1:10021` 不一定可靠投递到容器的问题。

容器内执行:

```bash
python3 tools/probe_pc104_udp_timing.py \
  --remote-host 192.168.65.254 \
  --remote-port 10022 \
  --local-host 0.0.0.0 \
  --local-port 21 \
  --duration 300 \
  --send-rate-hz 10 \
  --output-dir results/control/pc104_udp_timing_real_forwarded_$(date +%Y%m%d_%H%M%S)
```

判据:

- `status=ok`，且 `uplink_count > 0`；
- `observed_uplink_rate_hz` 接近 PC104 实际上行频率；
- `uplink_sequence_gap_count` 和 `uplink_estimated_lost_frames` 用于判断丢帧；
- `uplink_interarrival_p95_ms/p99_ms` 用于报告到达间隔抖动；
- 若 `pc104_time_valid_rate > 0`，再报告 PC104 uptime 单调性和 delta 分布。

边界:

- 该拓扑的到达时间包含宿主机 relay 和 Docker UDP publish 的转发开销；
- firmware echo 可构成应用路径 RTT，但仍不构成一程物理时延；后者需要共享时钟或双向时间同步；
- 若需要更接近物理网卡时间，应在宿主机同时运行 `tcpdump -ni <iface> udp port 21 or udp port 52367` 作为旁路证据。

## 5. 推荐拓扑 B: 容器内 fan-out 并发

用途:

- ROS2 bridge 与 PySide6 GUI 需要同时在线；
- 需要旁路 timing/sniffer 记录；
- 需要 fan-out 对下行 `$CKTH` 做零执行器安全门控；
- Docker Desktop 或容器 publish 后，上行源地址可能显示为 Docker 网关。

宿主机仍需先执行第 4 节的 full-duplex host relay，或确认 PC104 接受容器源地址下行。容器内启动 fan-out:

```bash
python3 scripts/pc104_udp_fanout.py \
  --listen-host 0.0.0.0 \
  --listen-port 21 \
  --pc104-host 192.168.0.101 \
  --pc104-port 21 \
  --accept-uplink-source 172.18.0.1 \
  --cmd-host 127.0.0.1 \
  --cmd-port 52364 \
  --subscriber ros2=127.0.0.1:52365 \
  --subscriber pyside6=127.0.0.1:52366 \
  --subscriber timing=127.0.0.1:52368
```

若只用 timing probe 占用 ROS2 角色，不启动 ROS2 bridge:

```bash
python3 tools/probe_pc104_udp_timing.py \
  --remote-host 127.0.0.1 \
  --remote-port 52364 \
  --local-host 127.0.0.1 \
  --local-port 52365 \
  --duration 300 \
  --send-rate-hz 10
```

若 ROS2 bridge 已占用 `52365`，timing probe 改为只读旁路:

```bash
python3 tools/probe_pc104_udp_timing.py \
  --receive-only \
  --remote-host 127.0.0.1 \
  --remote-port 52364 \
  --local-host 127.0.0.1 \
  --local-port 52368 \
  --duration 300
```

边界:

- fan-out 适合做实物联调的通信复用层，不应把 fan-out 后的到达间隔写成最小物理链路时延；
- `--accept-uplink-source` 应按现场容器看到的源地址调整，可用 `scripts/sniffer.py` 或 fan-out 日志确认；
- 默认不加 `--allow-nonzero-actuator`，除非已经进入明确批准的 bench 非零执行器短测。

## 6. 不推荐拓扑: 宿主机原生 fan-out 叠加当前 publish

当前 Docker publish 已占用宿主机 `52364/52365/52366/udp`。如果再在宿主机原生运行 fan-out 并绑定这些高端口，容易产生端口冲突和双重转发。因此当前基础设施下不推荐宿主机原生 fan-out。

若必须宿主机原生 fan-out，应二选一:

1. 停止 Docker 对 `52364/52365/52366/udp` 的 publish，改由宿主机 fan-out 独占这些端口；
2. 给宿主机 fan-out 使用另一组高端口，并同步修改容器内 ROS2/GUI/probe 的目标端口。

## 7. 论文与 Artifact 口径

可写:

- 当前已确认物理 PC104 timing 需要宿主机端口转发或固件目标端口调整；
- 直连 probe 是物理时序审计的推荐低干扰路径；
- fan-out 是并发调试和安全门控架构，不是 timing 基线的必要条件。

不可写:

- 不能把 `10021:21/udp` 映射本身写成已接通 PC104 `21/udp`；
- 不能把无上行的容器负结果写成 PC104 无响应；
- 不能把 fan-out 后的到达时间写成裸链路单向延迟；
- 不能在没有 echo 或共享时钟时报告 Jetson 到 PC104 的一程物理延迟。
