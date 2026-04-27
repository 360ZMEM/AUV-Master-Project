# protocol_udp 联调复现与模式切换

本文档把这次协议级数字孪生联调固化成可复现流程，目标是两件事：

1. 不手改默认 YAML，也能在 zenoh_json 与 protocol_udp 之间切换。
2. 出现问题时，能按固定检查顺序快速定位到仿真侧、桥接侧还是 ROS2 脑端。

## 1. 当前基线

- 默认模式仍是 zenoh_json。
- protocol_udp 使用临时桥接配置 [config/bridge_params.protocol_udp.yaml](../config/bridge_params.protocol_udp.yaml)。
- 原始配置已备份：
  - [brain_linux/config/params.yaml.bak-20260401](../brain_linux/config/params.yaml.bak-20260401)
  - [config/bridge_params.yaml.bak-20260401](../config/bridge_params.yaml.bak-20260401)

## 2. 新增的切换入口

本次补充后的脚本支持以下切换参数：

- [scripts/start_lin_sim.sh](../scripts/start_lin_sim.sh)
  - `--backend zenoh_json|protocol_udp`
  - `--bridge-cfg /abs/or/relative/path.yaml`
  - `--sim-cfg /abs/or/relative/path.yaml`
- [scripts/start_lin_brain.sh](../scripts/start_lin_brain.sh)
  - `--backend zenoh_json|protocol_udp`
  - `--protocol-control-mode-byte 238`
  - `--arbiter-profile`
- [scripts/start_foxglove_holoocean_ros.sh](../scripts/start_foxglove_holoocean_ros.sh)
  - `--bridge-backend zenoh_json|protocol_udp`
  - `--bridge-cfg ...`
  - `--sim-cfg ...`
  - `--protocol-control-mode-byte 238`

## 3. 最小复现命令

### 3.1 只启动仿真桥接侧

zenoh_json：

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/scripts
bash start_lin_sim.sh bridge --backend zenoh_json
```

protocol_udp：

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/scripts
bash start_lin_sim.sh bridge --backend protocol_udp
```

如果你想显式指定配置文件，而不是依赖默认映射：

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/scripts
bash start_lin_sim.sh bridge --bridge-cfg /home/gwxie/master_work-tmp/AUV_Master_Project/config/bridge_params.protocol_udp.yaml
```

### 3.2 只启动 ROS2 脑端

zenoh_json：

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/scripts
bash start_lin_brain.sh stack --backend zenoh_json
```

protocol_udp：

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/scripts
bash start_lin_brain.sh stack --backend protocol_udp --protocol-control-mode-byte 238
```

protocol_udp + arbiter profile：

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/scripts
bash start_lin_brain.sh stack --arbiter-profile
```

这个入口会默认使用 [brain_linux/config/params.protocol_udp_arbiter.yaml](../brain_linux/config/params.protocol_udp_arbiter.yaml)。

### 3.3 一条命令起全链路

zenoh_json：

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/scripts
bash start_foxglove_holoocean_ros.sh --bridge-backend zenoh_json
```

protocol_udp：

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/scripts
bash start_foxglove_holoocean_ros.sh --bridge-backend protocol_udp --protocol-control-mode-byte 238
```

如果只是联调桥接，不想每次重建布局：

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/scripts
bash start_foxglove_holoocean_ros.sh --skip-layout --bridge-backend protocol_udp --protocol-control-mode-byte 238
```

## 4. 模式切换规则

### 4.1 zenoh_json

- 仿真侧读取 [config/bridge_params.yaml](../config/bridge_params.yaml)。
- ROS2 侧 launch 参数 `bridge_backend:=zenoh_json`。
- 适合保留旧链路、Foxglove 可视化和历史脚本兼容验证。

### 4.2 protocol_udp

- 仿真侧优先读取 [config/bridge_params.protocol_udp.yaml](../config/bridge_params.protocol_udp.yaml)。
- ROS2 侧 launch 参数 `bridge_backend:=protocol_udp`。
- 决策层额外传 `protocol_control_mode_byte:=238`，对应协议接管字节 `0xEE`。
- 适合验证二进制 `$CKTH/$AUV` 闭环链路。

### 4.3 protocol_udp + arbiter side channel

- 推荐使用 [brain_linux/config/params.protocol_udp_arbiter.yaml](../brain_linux/config/params.protocol_udp_arbiter.yaml)。
- `rt/pc/cmd_raw` 输入可以是 72B raw `$CKTH`，也可以是 bridge 当前兼容的 JSON dict。
- bridge 会把解包后的仲裁反馈发布到 `rt/auv/telemetry` 与 `rt/auv/viz/internal`。
- freshness 超过 guard 门限时，bridge telemetry 会回 `DENIED + AMD_UPLINK_STALE`。
- Python 上位机主窗口现已支持“请求自主”“手动接管”和拒绝反馈显示；其中“请求自主”会持续保持控制模式字节为 `0xEE`。

### 4.4 独立 sniffer

如需脱离 bridge 和 GUI 单独看协议报文，可直接启动 sniffer：

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
/usr/bin/python3 scripts/sniffer.py --bind-port 52364 --show-hex
```

说明：

- 监听 52364 时，通常能看到上位机发往 bridge/Mock AMD 的 `$CKTH`。
- 若监听 AUV 回传端口，可看到 `$AUV` 遥测摘要。
- sniffer 与 Mock AMD 彩色日志共用同一套 shared protocol 格式化逻辑，便于三方对照。

## 5. 联调成功判据

至少同时满足下面三类现象，才算 protocol_udp 真正打通：

1. ROS2 侧有桥接输入：

```bash
source /opt/ros/humble/setup.bash
source /home/gwxie/master_work-tmp/AUV_Master_Project/brain_linux/install/setup.bash
ros2 topic echo --once /auv/sensors/depth
ros2 topic echo --once /auv/state/filtered
```

2. 决策与控制在跑：

```bash
source /opt/ros/humble/setup.bash
source /home/gwxie/master_work-tmp/AUV_Master_Project/brain_linux/install/setup.bash
ros2 topic echo --once /auv/control/setpoint
ros2 topic echo --once /cmd_vel
```

3. sim 侧 Mock AMD 收到回传控制，而不是全零：

```text
[mock-amd TX][AUV][127.0.0.1:52365] frame=138 auv=1 mode=0xEE instr=0xEE depth=7.60m heading=87.2deg gps=(0.000000,0.000000) voltage=48.0V cmd=(-28.5,-30.0,28.5,30.0,181) step=051690
```

只要 sim 日志里的 `cmd=(...)` 或彩色摘要里对应舵角/主推值出现稳定非零值，就说明 Linux 控制量已经通过 protocol_udp 回到了仿真器。

如果验证的是 arbiter 最小闭环，还应额外看到：

4. `rt/auv/telemetry` 中出现 `active_arbiter`、`auto_state`、`deny_reason`。
5. freshness 超过 200ms 时可复现 `auto_state=DENIED`、`deny_reason=AMD_UPLINK_STALE`。
6. freshness 门限内重复发送 uplink 后，`auto_state=ACTIVE`，`active_arbiter` 切到 `AUTONOMOUS`。

## 6. 推荐排障顺序

### 6.1 看不到桥接节点，或者 `/auv/sensors/depth` 为空

优先单独运行桥接节点，而不是一开始怀疑控制器：

```bash
source /opt/ros/humble/setup.bash
source /home/gwxie/master_work-tmp/AUV_Master_Project/brain_linux/install/setup.bash
ros2 run auv_bridge zenoh_json_bridge_node --ros-args \
  -p params_file:=/home/gwxie/master_work-tmp/AUV_Master_Project/brain_linux/config/params.yaml \
  -p bridge_backend:=protocol_udp
```

如果 standalone 能收到 telemetry，而整栈不行，优先查 launch 参数是否覆盖成功。

### 6.2 sim 侧有 telemetry，但控制回不到仿真

依次检查：

1. [brain_linux/config/params.yaml](../brain_linux/config/params.yaml) 里的 `bridge.protocol_control_mode_byte`。
2. [config/bridge_params.protocol_udp.yaml](../config/bridge_params.protocol_udp.yaml) 里的 `bridge.protocol_udp.remote_port` / `bind_port`。
3. `/cmd_vel` 是否持续发布。
4. sim 侧日志里的 `cmd=(...)` 是否长期全零。

### 6.3 只想切模式，不想改文件

直接用命令行参数，不需要手改 YAML：

```bash
bash start_lin_sim.sh bridge --backend protocol_udp
bash start_lin_brain.sh stack --backend protocol_udp --protocol-control-mode-byte 238
```

## 7. 当前结论

截至 2026-04-01，这套 protocol_udp 模式已经完成过一次真实闭环验证：

- Linux 侧收到 protocol uplink telemetry。
- `/auv/sensors/depth` 与 `/auv/state/filtered` 有实时值。
- sim 侧持续打印非零控制量。

因此，后续如果再出现“链路不通”，应优先按本文档排查，而不是回到手改配置和临时试错流程。