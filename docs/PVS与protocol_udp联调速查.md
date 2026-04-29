# PVS 与 protocol_udp 联调速查

这是一份短版速查文档，目标是把当前 PVS 后端、protocol_udp、arbiter profile 和 sniffer 的关键入口收拢到一页，方便快速切换和验收。

如果你需要完整实验产物阅读顺序、rosbag 回放和分析图说明，请继续看 [PVS 全流程 Runbook](PVS全流程runbook.md) 和 [PVS 调试排坑记录](PVS调试排坑记录.md)。

## 1. 当前推荐入口

### 1.1 PVS 纯仿真

```bash
bash scripts/start_pvs_sim.sh sim
```

默认会走 PVS 专属配置：

- [config/sim_params.pvs.yaml](../config/sim_params.pvs.yaml)
- [config/bridge_params.pvs.yaml](../config/bridge_params.pvs.yaml)

### 1.2 PVS + Foxglove + ROS2

```bash
bash scripts/start_foxglove_pvs_ros.sh
```

### 1.3 protocol_udp + arbiter profile

```bash
bash scripts/start_lin_brain.sh stack --arbiter-profile
```

或者一键全链路：

```bash
bash scripts/start_foxglove_holoocean_ros.sh --bridge-backend protocol_udp --protocol-control-mode-byte 238 --arbiter-profile
```

## 2. 模式切换要点

### 2.1 选择后端

- `--sim-backend pvs`：切到 PVS。
- `--backend protocol_udp`：桥接侧切到二进制协议。
- 不指定时，默认仍是 HoloOcean + `zenoh_json`。

### 2.2 arbiter profile 做了什么

`--arbiter-profile` 会默认把脑端切到协议仲裁所需的一组参数：

- `brain_linux/config/params.protocol_udp_arbiter.yaml`
- `bridge_backend:=protocol_udp`
- `protocol_control_mode_byte:=238`

这样可以少记一堆参数，直接跑最小闭环。

### 2.3 protocol_udp 侧的关键端口

- 仿真侧监听：`52364`
- 脑端 / 下行侧：`52365`
- sniffer 镜像：`52366`

如果你怀疑链路断了，先看端口有没有对上，再看消息内容。

## 3. 联调时先看什么

### 3.1 仿真侧

看是否出现这些关键字：

- `simulation_backend=pvs`
- `backend open`
- `depthHeadingAutopilot`
- `cmd=(...)`

### 3.2 ROS2 侧

重点确认：

- `/auv/sensors/depth`
- `/auv/state/filtered`
- `/auv/control/setpoint`
- `/cmd_vel`
- `/auv/arbiter/status`

### 3.3 协议侧

优先看：

- `$CKTH`
- `$AUV`
- `active_arbiter`
- `auto_state`
- `deny_reason`

## 4. 独立 sniffer

如果你只想看协议包，不想带整套界面和桥接，可以直接起 sniffer：

```bash
/usr/bin/python3 scripts/sniffer.py --bind-port 52364 --show-hex
```

如果你想看更详细的 ASCII 块：

```bash
/usr/bin/python3 scripts/sniffer.py --bind-port 52364 --ascii-format
```

## 5. 最小验收条件

这条链路至少满足下面三项，才算真正打通：

1. ROS2 侧能读到传感数据。
2. `/cmd_vel` 或 protocol 下行里能看到非零控制量。
3. `protocol_udp + arbiter` 场景下，`/auv/arbiter/status` 能反映 `ACTIVE` / `DENIED` 切换。

如果是自主接管场景，还要额外确认：

- `active_arbiter=AUTONOMOUS`
- `deny_reason` 在超时或低电压时能正确变化

## 6. 已验证的判据

当前已经验证过的情况包括：

- `protocol_udp` 下行可以正常回到仿真器。
- arbiter profile 可以通过 `--arbiter-profile` 一键启动。
- sniffer 可以看到 `$CKTH` / `$AUV` 的摘要和 ASCII 输出。

## 7. Shadow 模式与决策回放

### 7.1 Shadow（旁路观察）模式

```bash
bash scripts/start_lin_brain.sh stack --arbiter-profile --passive-mode
```

bridge 不会真正下发指令，但在以下 topic 发布影子快照：
- `/auv/bridge/shadow_cmd`
- `/auv/bridge/shadow_telemetry`

### 7.2 Raw Dead-Reckoning 基准

```bash
ros2 launch auv_stack auv_stack.launch.py publish_raw_state:=true bypass_ekf:=true
```

- `/auv/state/raw_dr`：原始推算里程计
- `/auv/state/filtered`：EKF 滤波后状态

### 7.3 决策回放（无仿真端到端测试）

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/brain_linux
source install/setup.bash
ros2 launch auv_decision_ros decision_replay.launch.py
```

或使用自定义日志：
```bash
ros2 launch auv_decision_ros decision_replay.launch.py \
  log_file:=/home/gwxie/master_work-tmp/Console上位机软件/auv_console_python/20020101103632.txt
```

---

## 8. 和长文档的关系

这份速查只保留切换和验收的最短路径。更详细的内容见对应长文档：
- Shadow / raw DR / 动态参数：[PVS全流程runbook.md](PVS全流程runbook.md)
- 模式切换背景与排障：[protocol_udp联调复现与模式切换_2026-04-01.md](protocol_udp联调复现与模式切换_2026-04-01.md)
- 决策回放详细参数：[brain_linux/src/auv_control/README.md](../brain_linux/src/auv_control/README.md)