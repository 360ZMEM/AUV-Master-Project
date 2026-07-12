# PC104 实物部署: 上位机/Brain/Foxglove 拓扑合理性分析

状态: `DRAFT`
适用场景: PC104、运行本仓库的嵌入式/工控平台、上位机 PC、Foxglove 可视化终端接入同一交换机。

## 1. 目标网络假设

本阶段推荐固定以下网络锚点:

```text
PC104/VxWorks:            192.168.0.101
运行本代码仓库的平台:       192.168.0.11
上位机 PC:                192.168.0.x，例如 192.168.0.12
Foxglove 可视化终端:       192.168.0.y，例如 192.168.0.13
交换机网段:                192.168.0.0/24
```

仍保留“上位机 PC 与运行本代码仓库的平台为同一台机器”的可能性。

核心原则:

1. `192.168.0.11` 继续作为 PC104 实物链路的默认锚点。
2. PC104 的 `$AUV`/`$CKTH` 当前实测使用 `21/udp`，不是历史 mock profile 的 `52364/52365`。
3. 只允许一个进程绑定 `192.168.0.11:21/udp`。需要 ROS2 和 PySide6 同时接入时，应使用 fan-out。
4. Foxglove 推荐只把“浏览器/客户端”放远端，`foxglove_bridge` 仍运行在本代码仓库平台。

## 2. 当前软件链路分层

### 2.1 PC104 UDP 主链路

```text
PC104 192.168.0.101:21
  <-> 运行本仓库平台 192.168.0.11:21
```

该链路承载:

- `$AUV` 上行遥测。
- `$CKTH` 下行控制。
- VxWorks HIL 期间的安全零执行器短测。

它是实物控制的主链路。无论上位机是否启用 Zenoh，PC104 最终只认识 UDP 协议帧。

### 2.2 PySide6 上位机链路

PySide6 当前不再只是 C# 版本的纯 UDP 克隆，它包含两层:

| 层级 | 作用 | 是否控制必需 |
|---|---|---|
| UDP WiFi 通信 | 构造并发送 `$CKTH`，接收 `$AUV` | 手动遥控/安全包必需 |
| Zenoh side channel | 发布 `rt/pc/cmd_raw`，订阅 `rt/auv/telemetry` 等仲裁/状态 | 自主请求、任务语义命令、仲裁状态显示需要 |

代码层面的关键事实:

- `CommunicationManager.send_packet()` 在 WiFi 模式下会先发送 UDP，再尝试通过 Zenoh side channel 发布 raw packet。
- Zenoh side channel 未激活时，UDP 发送不会因此失败。
- `请求自主`、`任务下发`、`自主心跳 JSON` 等功能依赖 Zenoh。
- `手动接管`按钮当前也会检查 Zenoh side channel 是否激活；但底层 PC104 遥控/急停/零执行器包可以通过普通 UDP 下发。

因此结论是:

```text
仅做手动遥控/安全零执行器/PC104 UDP 烟测:
  PySide6 可以不依赖 brain_linux/Zenoh，只要 UDP 端点正确。

需要自主模式、仲裁状态、任务语义下发、与 brain_linux 共享状态:
  PySide6 必须能连到运行仓库平台上的 Zenoh router 或等价 side channel。
```

## 3. 推荐拓扑

### 拓扑 A: 单机集成，最推荐用于阶段性实物调试

```text
运行本仓库平台 192.168.0.11
  ├─ fan-out 绑定 192.168.0.11:21
  ├─ ROS2 brain / protocol_udp bridge
  ├─ PySide6 上位机
  ├─ Zenoh router / side channel
  └─ foxglove_bridge ws://0.0.0.0:8765

PC104 192.168.0.101
```

优点:

- `127.0.0.1` fan-out profile 可直接使用。
- ROS2 DDS、Zenoh、PySide6、fan-out 都在同一网络命名空间，变量最少。
- 已完成实物 passive、non-passive 零执行器和 180 秒 soak 证据。

推荐命令:

```bash
scripts/start_pc104_fanout_concurrent.sh --passive
scripts/status_pc104_fanout_concurrent.sh
scripts/run_pc104_fanout_zero_soak.sh --duration 180 --command-hz 2.0
```

PySide6:

```bash
cd console_soft/auv_console_pyside6
python3 main.py --config console_config.pc104_fanout.yaml
```

### 拓扑 B: 上位机 PC 分离，但只做手动/安全 UDP

```text
上位机 PC 192.168.0.12
  └─ PySide6 直接 UDP

PC104 192.168.0.101

运行本仓库平台 192.168.0.11
  └─ 可不启动 brain_linux
```

该拓扑最接近 C# 老上位机:

- PySide6 只依赖 UDP。
- 不要求 brain_linux、ROS2、Zenoh 同时运行。
- 适合手动遥控、零执行器烟测、配置/参数下发。

风险和限制:

1. 当前 `console_config.pc104.yaml` 固定 `local_ip: 192.168.0.11`，不能直接拿到 `192.168.0.12` 上运行。
2. 如果 PC104 固件将上行目标固定为 `192.168.0.11:21`，则上位机 PC 直接绑定 `192.168.0.12:21` 可能收不到 `$AUV`。
3. 此拓扑不能验证 ROS2 仲裁、自主状态、`AMD_UPLINK_STALE` 消除、任务语义下发。

若要采用，需要新增或复制一份 PC 专用配置:

```yaml
udp:
  local_ip: "192.168.0.12"
  local_port: 21
  amd_ip: "192.168.0.101"
  amd_port: 21
```

并实测:

```text
PySide6 能绑定 192.168.0.12:21
PC104 能收到 $CKTH
PySide6 能收到 $AUV
Telnet 读回 UI_WIFI_Instruction 与上位机下发一致
```

若 `$AUV` 仍只回到 `192.168.0.11`，说明 PC104 回包目标仍固定在仓库平台 IP，此时不建议让分离上位机直连 PC104，而应采用拓扑 C。

### 拓扑 C: 上位机 PC 分离，并保持 brain_linux/fan-out 联动

```text
PC104 192.168.0.101:21
  <->
运行本仓库平台 192.168.0.11
  ├─ fan-out 绑定 192.168.0.11:21
  ├─ ROS2 brain / protocol_udp bridge
  ├─ Zenoh router: 192.168.0.11:7447
  └─ foxglove_bridge: 192.168.0.11:8765

上位机 PC 192.168.0.12
  └─ PySide6
```

这是“分离上位机但不破坏 brain_linux 链路”的合理拓扑。

需要调整 fan-out:

当前 fan-out 默认:

```text
cmd ingress: 127.0.0.1:52364
PySide6 uplink subscriber: 127.0.0.1:52366
PySide6 expected source port: 52366
```

如果 PySide6 在另一台 PC，`127.0.0.1` 不再成立。需要让 fan-out 监听局域网入口，并把上行复制到上位机 PC:

```bash
sudo -n python3 scripts/pc104_udp_fanout.py \
  --listen-host 192.168.0.11 \
  --listen-port 21 \
  --pc104-host 192.168.0.101 \
  --pc104-port 21 \
  --cmd-host 192.168.0.11 \
  --cmd-port 52364 \
  --subscriber ros2=127.0.0.1:52365 \
  --subscriber pyside6=192.168.0.12:52366 \
  --console-source-port 52366
```

上位机 PC 的 PySide6 配置应类似:

```yaml
zenoh:
  router_ip: "192.168.0.11"
  router_port: 7447
  mode: "client"

udp:
  local_ip: "192.168.0.12"
  local_port: 52366
  amd_ip: "192.168.0.11"
  amd_port: 52364
```

注意:

- 此时 PySide6 的 `amd_ip` 指向 fan-out，不直接指向 PC104。
- fan-out 会审计 `$CKTH`，默认拒绝非零执行器。
- 需要确保运行仓库平台防火墙允许 `52364/udp`，上位机 PC 防火墙允许 `52366/udp`。
- 如果需要上位机显示仲裁/遥测 side channel，应在上位机 PC 点击连接到 `192.168.0.11:7447`，或在配置中把 router IP 改为 `192.168.0.11`。

该拓扑成功标准:

```text
fan-out 日志 uplink 持续增长
fan-out 日志 pyside6 subscriber 有上行复制
PySide6 顶部报文编号递增
PySide6 下发零执行器包后 fan-out 显示 forward pyside6 -> PC104
Telnet 读回 UI_WIFI_Instruction 与 PySide6 下发一致
ROS2 /auv/arbiter/status 仍可读取 freshness
```

## 4. 上位机 Zenoh 依赖是否会导致控制失效

分情况结论如下:

| 使用方式 | 上位机不连 Zenoh 的结果 | 是否导致 PC104 控制失效 |
|---|---|---|
| 手动 UDP 遥控/零执行器包 | UDP 仍可发送；side channel 状态显示不可用 | 不必然失效 |
| 急停/任务取消这类直接 `$CKTH` 包 | UDP 仍可发送 | 不必然失效 |
| 请求自主按钮 | 当前 UI 要求 side channel active，否则按钮不可用或请求不发送 | 会影响 |
| 任务语义下发 | 依赖 Zenoh JSON publish | 会影响 |
| 仲裁状态/拒绝原因显示 | 依赖 `rt/auv/telemetry` side channel 或 ROS2 topic | 会缺失 |
| 与 brain_linux 共享 PC raw command | 依赖 `rt/pc/cmd_raw` | 会影响自主联动 |

因此，PySide6 相比 C# 版本的合理定位应是:

```text
UDP 是 PC104 兼容控制主链路；
Zenoh 是和 brain_linux/ROS2 协同的增强链路。
```

如果现场希望“上位机像 C# 一样独立运行”，必须在操作 SOP 中声明:

- 只使用手动/UDP 控制功能。
- 不使用请求自主、任务语义下发、仲裁状态依赖项。
- 不把 Zenoh 未连接视为 UDP 控制失败。

如果现场希望“上位机参与自主/仲裁/任务”，则必须部署 Zenoh router，并让上位机 PC 能访问运行仓库平台的 `7447/tcp`。

### 4.1 最终部署的 Zenoh 跨机转发方案

可以通过 Zenoh 跨机转发来实现“上位机 PC 分离但完整功能可用”。更准确地说，不建议为每个 topic 手写转发脚本，而应把 Zenoh 部署成显式 router/client 拓扑:

```text
运行本仓库平台 192.168.0.11
  ├─ Zenoh router: listen tcp/0.0.0.0:7447
  ├─ brain_linux / protocol_udp bridge: Zenoh client -> 192.168.0.11:7447
  └─ PC104 fan-out / ROS2 bridge

上位机 PC 192.168.0.12
  └─ PySide6 Zenoh side channel: client -> 192.168.0.11:7447
```

这样 `rt/pc/cmd_raw`、`rt/auv/telemetry`、`rt/auv/viz/internal` 等 key expression 会由 Zenoh router 统一路由，不需要逐个 topic 写 UDP/TCP 转发。

最终部署应至少覆盖这些 Zenoh key:

| Key | 方向 | 用途 |
|---|---|---|
| `rt/pc/cmd_raw` | 上位机 PC -> brain_linux | PC raw `$CKTH`、自主请求、任务语义命令入口 |
| `rt/auv/telemetry` | brain_linux -> 上位机 PC | 遥测、仲裁状态、freshness、拒绝原因 |
| `rt/auv/viz/internal` | brain_linux -> 上位机 PC，可选 | 内部可视化/诊断状态 |

当前代码支持情况:

| 组件 | 当前状态 | 最终部署建议 |
|---|---|---|
| PySide6 `ZenohSideChannel` | 已有 `connect_to_router(ip, 7447)`，并已支持从 YAML 合并 `zenoh.enabled/router_ip/router_port/key` | 同机使用 `console_config.pc104_fanout.yaml`，异机使用 `console_config.pc104_remote_fanout.yaml` |
| `brain_linux` bridge backend | 已支持 `zenoh_session_json`、`zenoh_session_config`、`zenoh_router_ip/port`，并在 PC104 fan-out profile 中显式 client 到 router | 同机默认连接 `tcp/127.0.0.1:7447`；异机上位机仍连 `192.168.0.11:7447` |
| 同网段 Zenoh peer discovery | 可能在简单 LAN 中工作 | 不建议作为最终部署依据，受 multicast、防火墙、网卡选择影响 |
| 手写 topic forwarder | 可作为临时调试工具 | 不建议作为长期方案，容易遗漏 key 和 QoS/重连行为 |

推荐最终部署流程:

1. 在 `192.168.0.11` 上启动 Zenoh router，监听 `7447/tcp`。
2. `brain_linux` bridge 以 client 方式连接 `tcp/192.168.0.11:7447`。
3. 上位机 PC 的 PySide6 以 client 方式连接 `tcp/192.168.0.11:7447`。
4. 通过一次 loopback smoke 确认上位机发布的 `rt/pc/cmd_raw` 能被 bridge 收到。
5. 确认 bridge 发布的 `rt/auv/telemetry` 能被上位机订阅并更新 UI 状态。

示例配置形态:

```json
{
  "mode": "client",
  "connect/endpoints": ["tcp/192.168.0.11:7447"]
}
```

当前 PySide6 可以通过 `connect_to_router("192.168.0.11", 7447)` 实现上述 client 配置；`brain_linux` 侧也已支持把同样的 session JSON 传给 bridge backend。

当前实现已经提供配置入口:

```yaml
# brain_linux/config/params.protocol_udp_pc104_fanout.yaml
protocol_udp:
  zenoh_side_channel_enabled: true
  zenoh_session_json:
    mode: client
    connect/endpoints:
      - tcp/127.0.0.1:7447
```

```yaml
# console_soft/auv_console_pyside6/console_config.pc104_remote_fanout.yaml
zenoh:
  enabled: true
  router_ip: "192.168.0.11"
  router_port: 7447
```

验收标准:

```text
上位机 PC 发布 rt/pc/cmd_raw 后，brain_linux CommandArbiter 进入 PC_RAW 或对应请求状态。
brain_linux 发布 rt/auv/telemetry 后，上位机 PC 能更新遥测/仲裁状态。
断开上位机 PC 后，PC104 UDP/fan-out/ROS2 bridge 不崩溃。
重新连接上位机 PC 后，Zenoh side channel 能自动或手动恢复。
```

这一路径可以满足最终部署“上位机 PC 完整功能”的需求，但它是一个明确的网络架构项，应纳入部署 SOP，而不是依赖同机默认 peer 行为。

### 4.2 上位机和 brain_linux 在同一台机器

适用:

```text
运行本仓库平台 = 上位机 PC = 192.168.0.11
PC104 = 192.168.0.101
```

操作步骤:

1. 在 `192.168.0.11` 启动 Zenoh router:

```bash
zenohd --listen tcp/0.0.0.0:7447
```

2. 启动 PC104 fan-out 和 ROS2 bridge:

```bash
scripts/start_pc104_fanout_concurrent.sh --passive
```

3. 启动 PySide6 上位机:

```bash
cd console_soft/auv_console_pyside6
python3 main.py --config console_config.pc104_fanout.yaml
```

4. 在上位机中确认:

```text
UDP: 127.0.0.1:52366 -> 127.0.0.1:52364
Zenoh: 127.0.0.1:7447
遥测报文编号递增
仲裁状态/自主状态可更新
```

该拓扑的优势是变量最少，适合调试期和首次完整链路验收。

### 4.3 上位机和 brain_linux 在不同机器

适用:

```text
运行本仓库平台/brain_linux/fan-out = 192.168.0.11
上位机 PC/PySide6 = 192.168.0.12
PC104 = 192.168.0.101
```

运行本仓库平台操作:

1. 启动 Zenoh router:

```bash
zenohd --listen tcp/0.0.0.0:7447
```

2. 启动 fan-out，允许来自上位机 PC 的 `52364/udp` 下行入口，并把上行复制到 `192.168.0.12:52366`。如果使用手工命令:

```bash
sudo -n python3 scripts/pc104_udp_fanout.py \
  --listen-host 192.168.0.11 \
  --listen-port 21 \
  --pc104-host 192.168.0.101 \
  --pc104-port 21 \
  --cmd-host 192.168.0.11 \
  --cmd-port 52364 \
  --subscriber ros2=127.0.0.1:52365 \
  --subscriber pyside6=192.168.0.12:52366 \
  --console-source-port 52366
```

3. 启动 `brain_linux` bridge，继续使用:

```bash
brain_linux/config/params.protocol_udp_pc104_fanout.yaml
```

该配置会让 `brain_linux` 侧 Zenoh side channel 连接 `tcp/127.0.0.1:7447`。

上位机 PC 操作:

1. 确保本机 IP 为 `192.168.0.12`，能访问:

```text
192.168.0.11:52364/udp
192.168.0.11:7447/tcp
192.168.0.12:52366/udp 本机可绑定
```

2. 启动 PySide6:

```bash
cd console_soft/auv_console_pyside6
python3 main.py --config console_config.pc104_remote_fanout.yaml
```

3. 在上位机中确认:

```text
UDP: 192.168.0.12:52366 -> 192.168.0.11:52364
Zenoh: 192.168.0.11:7447
报文编号递增
rt/pc/cmd_raw 发布后 brain_linux 能进入 PC_RAW 或对应请求状态
rt/auv/telemetry 能更新上位机仲裁/遥测状态
```

如果上位机 PC 不是 `192.168.0.12`，只需要复制并修改 `console_config.pc104_remote_fanout.yaml` 中:

```yaml
udp:
  local_ip: "<上位机PC实际IP>"
  local_port: 52366
  amd_ip: "192.168.0.11"
  amd_port: 52364

zenoh:
  router_ip: "192.168.0.11"
```

注意:

```text
不要在上位机 PC 上直接使用 console_config.pc104_fanout.yaml。
该文件使用 127.0.0.1，只适合同机 fan-out。
```

## 5. Foxglove 远端运行策略

### 5.1 推荐方式: 远端只运行浏览器或 Foxglove 客户端

推荐:

```text
运行仓库平台 192.168.0.11
  └─ foxglove_bridge 监听 ws://0.0.0.0:8765

Foxglove 终端 192.168.0.13
  └─ 浏览器/桌面端连接 ws://192.168.0.11:8765
```

目标 PC 不需要安装本仓库、ROS2、Zenoh 或 Python 依赖。它只需要:

- 浏览器，或 Foxglove Desktop。
- 能访问 `192.168.0.11:8765/tcp`。
- 与运行仓库平台在同一网段，或有路由可达。

运行仓库平台需要:

- ROS2 Humble 环境。
- 本仓库 `brain_linux` 已 build/source。
- `foxglove_bridge` 已安装并能 launch。
- 防火墙允许 `8765/tcp`。

连接方式:

```text
Foxglove -> Open connection -> ws://192.168.0.11:8765
```

不建议让远端 Foxglove 终端直接加入 ROS2 DDS 域。这样会引入 multicast、DDS discovery、用户上下文、RMW 配置等额外变量。

### 5.2 需要转发哪些话题

如果使用 `foxglove_bridge`，不需要手工逐个 UDP 转发话题。Foxglove 通过 WebSocket 看到运行仓库平台 ROS2 graph 中的 topic。

关键 ROS2 topic 包括:

```text
/auv/sensors/depth
/auv/sensors/dvl
/auv/sensors/imu
/auv/sensors/altitude
/auv/bridge/shadow_telemetry
/auv/arbiter/status
/auv/sensors/status
/auv/state/raw_dr
/auv/state/filtered
/tf
/tf_static
```

可视化 bridge 或业务节点可能还会发布:

```text
/auv/visual/seabed_cloud
/auv/visual/cable_marker
/auv/visual/truth_pose
/auv/visual/history_trail
/auv/visual/view_range
```

这些应由运行仓库平台内部 ROS2/Zenoh bridge 转成 ROS2 topic，再由 `foxglove_bridge` 统一 WebSocket 输出。

### 5.3 如果必须让 Foxglove 相关进程也在另一台 PC

不推荐作为实物首选方案。若必须这么做，有两条路:

1. 在 Foxglove PC 上安装 ROS2、`foxglove_bridge`、匹配的消息包，并让它加入同一 ROS2 DDS 域。
2. 在运行仓库平台和 Foxglove PC 之间部署 `zenoh-bridge-ros2dds` 或等价 DDS/Zenoh 桥。

这会引入额外要求:

```text
ROS_DOMAIN_ID 一致
RMW 实现一致或兼容
DDS multicast/UDP 发现可达
防火墙放通 DDS 动态端口或使用静态 peers
两侧消息包版本一致
```

除非有明确需求，不建议在当前 PC104 HIL 阶段采用。

## 6. 防火墙与端口清单

| 端口 | 协议 | 方向 | 用途 |
|---|---|---|---|
| `21` | UDP | `192.168.0.11 <-> 192.168.0.101` | PC104 `$AUV`/`$CKTH` |
| `52367` | UDP | PC104 -> 调试机 | UdpLogger |
| `52364` | UDP | 上位机/ROS2 -> fan-out | fan-out 下行入口 |
| `52365` | UDP | fan-out -> ROS2 | ROS2 上行订阅端 |
| `52366` | UDP | fan-out -> PySide6 | PySide6 上行订阅端 |
| `7447` | TCP | 上位机 PC -> 运行仓库平台 | Zenoh router client 连接 |
| `8765` | TCP | Foxglove 终端 -> 运行仓库平台 | foxglove_bridge WebSocket |
| `23` | TCP | 调试机 -> PC104 | VxWorks Telnet |

## 7. 现场操作建议

### 最小安全验证

1. 只接 PC104 与运行仓库平台。
2. 运行 `sniffer.py` 或 fan-out，确认 `$AUV`。
3. 发送零执行器 `$CKTH`。
4. Telnet 读回 `UI_WIFI_Instruction`。

### 上位机同机

1. 启动 fan-out。
2. 启动 ROS2 bridge。
3. 启动 PySide6 `console_config.pc104_fanout.yaml`。
4. 如需 Foxglove，在远端浏览器连接 `ws://192.168.0.11:8765`。

### 上位机分离

1. 不要直接使用 `console_config.pc104_fanout.yaml`，因为其中都是 `127.0.0.1`。
2. 使用拓扑 B 做 UDP-only 手动验证，或使用拓扑 C 经 fan-out。
3. 若要自主/仲裁/任务语义，确认 Zenoh router 可达:

```text
上位机 PC -> 192.168.0.11:7447/tcp
```

4. 若只做手动 UDP，不要把 Zenoh 未连接视为控制失败。

## 8. 需要后续补强的工程项

1. 根据现场上位机 IP 维护 `console_config.pc104_remote_fanout.yaml` 模板，避免临场手改同机 profile。
2. 在 PySide6 UI 中更清晰地区分“UDP 主链路状态”和“Zenoh side channel 状态”。
3. 允许手动接管按钮在 Zenoh 不可用时仍发送 UDP remote override，避免 UI 语义和底层安全包耦合过紧。
4. 为 `pc104_udp_fanout.py` 增加多 PC profile 或 systemd 参数模板。
5. 为 Foxglove 远端连接补一份检查脚本，至少检查 `8765/tcp`、topic 列表和 `/auv/arbiter/status`。

## 9. 当前结论

1. 上位机独立运行不会天然导致 PC104 UDP 控制失效；但只适用于 UDP 手动/安全包，不适用于完整自主/仲裁/任务语义闭环。
2. 如果上位机 PC 与运行仓库平台分离，当前 `127.0.0.1` fan-out profile 不能直接使用，必须改成局域网 IP 或新增 remote fan-out profile。
3. 若要保留 brain_linux 与上位机协同，推荐让运行仓库平台继续做 PC104 网络锚点和 fan-out/Zenoh/Foxglove bridge 主机。
4. Foxglove 最合理的跨 PC 方式是远端只连 `ws://192.168.0.11:8765`，不要让远端 PC 直接加入 ROS2 DDS，除非后续专门配置 DDS/Zenoh 桥。
