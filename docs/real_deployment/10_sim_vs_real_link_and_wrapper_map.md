# 10 — 仿真 / 真机链路、配置分层与 Wrapper 接入图

> 这页回答三个交接时最容易混在一起的问题：
> 1. `PVS/HoloOcean` 仿真链路和 `PC104/VxWorks` 真机链路到底差在哪；
> 2. 各类 YAML 分别管哪一层，切换目标时应该改谁；
> 3. 后续像磁传感器这类新增输入，应该放在哪一层做 wrapper，输出什么契约。

---

## 1. 一句话结论

- **仿真链路**的目标是验证高层任务、行为树、控制与传感器替身，主通道通常是 `PVS/HoloOcean <-> protocol_udp <-> ROS2`，额外传感器走 Zenoh side-channel。
- **真机链路**的目标是验证真实 PC104/VxWorks 与执行层通信，主通道是 `Jetson/Host <-> UDP <-> PC104:21`。
- **fan-out** 不是所有场景都必须上；它是“**一个低端口、多消费者并发调试**”的工程工具，尤其适合 GUI 和 ROS2 同时观察/发包、以及 macOS Docker Desktop 的 UDP 转发场景。
- **wrapper 的原则**是：在靠近数据源的一层把“厂商/仿真专有格式”收敛成仓库内标准契约，不要把专有字段一路泄漏到控制层。

---

## 2. 两条链路分别是什么

### 2.1 仿真链路

典型拓扑：

```text
PVS/HoloOcean
  -> config/bridge_params.protocol_udp.pvs.yaml
  -> protocol_udp bind 52364 / send 52365
  -> brain_linux/config/params.protocol_udp_arbiter*.yaml
  -> ROS2 brain stack
  -> cable_tracking / controller / behavior tree

额外传感器（magnetic / ground truth / sonar）
  -> Zenoh key
  -> bridge_backends.py / bridge_node.py
  -> ROS topic
```

当前主线里，仿真侧 `config/bridge_params.protocol_udp.pvs.yaml` 绑定 `52364`，brain 侧默认 `52365 -> 52364` 配对；磁场等非 `$AUV/$CKTH` 二进制字段通过 `rt/auv/sensors/magnetic` 等 Zenoh key 旁路进入 ROS2。

这条链路已经覆盖了：

- `auto_activate_emu.py -> rt/pc/cmd_raw` 自主授权；
- `protocol_udp` 下行进入仿真端；
- 行为树进入 `ZigZagSearch` 等任务态；
- `ESTOP / MANUAL_OVERRIDE / CLEAR_FAULT` 锁存与解锁语义；
- 磁传感器 side-channel 到 `/auv/sensors/magnetic` 再到 cable tracking 的高层链。

也就是说，**高层任务闭环、状态机、安全锁存、磁巡检逻辑，优先在仿真链验证**。

### 2.2 真机链路

典型拓扑：

```text
GUI / Jetson ROS2
  -> UDP
  -> PC104 / VxWorks (21/udp)
  -> $AUV uplink / $CKTH downlink
```

真实部署时，`brain_linux/config/params.protocol_udp_arbiter.real.yaml` 会把 brain 下行目标改到：

```yaml
bridge:
  protocol_udp:
    local_port: 52365
    remote_host: 192.168.0.101
    remote_port: 21
```

这条链路已经实证到的边界是：

- `$AUV` 上行能稳定进入容器；
- `$CKTH` 零执行器能到 PC104；
- GUI 的 `work_cmd=0x11`、`ESTOP=0x02` 能到 PC104；
- UdpLogger、Telnet probe、空板异常位可读；
- fan-out 可以在 Docker Desktop/macOS 拓扑下工作。

但当前空板不能证明：

- 真实 DVL / IMU / 深度闭环；
- 非零执行器真实动作；
- 依赖真实传感器反馈的高层任务闭环。

所以 **真机链路当前更适合做通信、安全、执行层边界验证，不适合替代仿真去做高层全覆盖**。

---

## 3. 最大区别：谁在扮演“世界”

| 维度 | 仿真 | 真机 |
|---|---|---|
| 下行对象 | `PVS/HoloOcean bridge` | `PC104/VxWorks` |
| 上行来源 | 仿真器生成的 `$AUV` / side-channel | 真实 PC104 生成的 `$AUV` / UdpLogger / Telnet 状态 |
| 额外传感器 | 仿真 wrapper 直接生成 | 真实硬件 wrapper 或外部适配进来 |
| 主要验证目标 | 高层逻辑与闭环 | 底层通信与安全边界 |
| 典型端口 | `52364 <-> 52365` | `PC104:21`, log `52367` |
| 是否需要 fan-out | 通常不需要 | 并发调试时常需要 |

更直白一点：

- **仿真**里，系统是在和“我们自己写的桥”打交道；
- **真机**里，系统是在和“真实 PC104 的协议实现和状态机”打交道。

---

## 4. 配置文件到底谁管谁

这部分最容易误改。建议按“**仿真侧 / brain 侧 / GUI 侧 / 算法侧**”四层来记。

### 4.1 仿真侧配置：`config/bridge_params*.yaml`

代表文件：

- `config/bridge_params.protocol_udp.pvs.yaml`
- `config/bridge_params.protocol_udp.yaml`

它们描述的是：

- 仿真器绑定哪个端口；
- 仿真器把二进制协议发到哪里；
- 仿真侧 Zenoh key 是什么；
- 是否镜像到 sniffer / GUI；
- digital twin、磁场、海缆、PVS 运动学 setpoint 等仿真专属内容。

**这类文件只改仿真世界，不改真实 PC104 目标。**

### 4.2 brain 侧配置：`brain_linux/config/params.protocol_udp_arbiter*.yaml`

代表文件：

- `params.protocol_udp_arbiter.yaml`：mock / 本机仿真默认
- `params.protocol_udp_arbiter.vxsim.yaml`：VxWorks 仿真器
- `params.protocol_udp_arbiter.real.yaml`：真实 PC104

它们描述的是：

- ROS2 bridge 本地监听端口；
- 下行远端地址；
- `passive_mode`；
- `rt/pc/cmd_raw`、`rt/auv/telemetry` 等 key；
- 安全守卫、仲裁器、电压阈值；
- 真机控制器限幅、PID、EKF 噪声；
- `sensor_extrinsics_estimated.mag` 等部署参数。

**切换 mock / vxsim / real，优先改这一层，而不是去改仿真 bridge yaml。**

### 4.3 GUI 侧配置：`console_soft/.../console_config*.yaml`

代表文件：

- `console_config.yaml`
- `console_config.pc104_fanout.yaml`
- `console_config.pc104_remote_fanout.yaml`

它们描述的是：

- GUI 的 UDP 本地端口；
- GUI 要往哪发包；
- GUI 是否走 Zenoh side-channel；
- GUI 订阅哪些 telemetry/viz key。

例如 `console_config.pc104_fanout.yaml` 的含义是：

- GUI 自己只绑定 `127.0.0.1:52366`；
- GUI 下行发给 `127.0.0.1:52364`；
- 低端口 `21/udp` 由 fan-out 占用，不由 GUI 直接占用。

### 4.4 算法 / 任务配置：`brain_linux/config/cable_tracking.yaml` 等

这类文件描述的是：

- 电缆先验路径；
- 跟踪质量门限；
- 在线先验修正开关；
- 磁导出横偏、埋深估计等算法参数。

**它们决定算法行为，不决定 PC104 发到哪里。**

---

## 5. fan-out 什么时候用，怎么用

### 5.1 fan-out 解决的是什么问题

在真实 PC104 场景里，`21/udp` 是低端口，而且同一时刻不能让多个进程都直接绑定它。可现场又常常需要：

- ROS2 bridge 收上行、发下行；
- GUI 同时观察/手动发包；
- sniffer 或 soak controller 做旁路记录；
- macOS + Docker Desktop 场景里，容器看到的上行源地址不一定就是 `192.168.0.101`。

这时 fan-out 作为唯一低端口绑定者，把真实链路“拆”成多个高端口消费者。

### 5.2 fan-out 并发拓扑

```text
PC104:21
  <->
scripts/pc104_udp_fanout.py   (唯一绑定 21/udp)
  |- ROS2 bridge   : 127.0.0.1:52365 <-> 127.0.0.1:52364
  |- PySide6 GUI   : 127.0.0.1:52366 <-> 127.0.0.1:52364
  |- sniffer/log   : 按脚本需要旁路观察
```

当前仓库约定里：

- fan-out 是唯一绑定 `192.168.0.11:21` 的进程；
- ROS2 收上行 `52365`，向 `52364` 发下行；
- GUI 收上行 `52366`，也向 `52364` 发下行；
- fan-out 默认只允许零执行器 `$CKTH`，非零执行器需显式放开。

### 5.3 推荐使用场景

适合上 fan-out 的场景：

- PC104 联调期，需要 GUI 和 ROS2 同时在线；
- 要做只读观察、被动监听、零执行器 soak；
- 需要兼容 macOS Docker Desktop 的 UDP publish；
- 需要统一做下行门控，防止误发非零执行器。

不必强行上 fan-out 的场景：

- Jetson 已经成为唯一控制端，现场只需要单写者；
- 只做纯仿真，不接真实 `21/udp`；
- 只做离线 bag 分析。

### 5.4 macOS / Docker Desktop 的特殊点

在该拓扑下，容器内看到的上行源可能是 Docker 网关而不是 PC104 本机，因此脚本层要保留：

```text
--pc104-remote-host 192.168.0.101
--accept-uplink-source 172.18.0.1
```

前者保证下行仍然发给真实 PC104，后者允许 fan-out 接受从 Docker 网关转发进来的上行。

### 5.5 使用 fan-out 时的边界

- 真实接 PC104 时，要避免同时运行 `socat`、旧 relay、另一个 `pc104_udp_fanout.py`，否则容易端口污染。
- fan-out 是**通信复用层**，不是行为逻辑层；业务状态机和安全语义仍由 bridge / arbiter / autonomy guard 负责。
- 若现场目标已经切到 `real` 并且 brain 直接对 PC104 发包，就不要再让另一套 GUI 直连 `21/udp` 抢占链路。

---

## 6. 后续传感器怎么替代：推荐的 wrapper 分层

以磁传感器为例，建议把“替代”和“接入”分成三层看。

### 6.1 仿真 wrapper

代表位置：

- `sim_holoocean/interfaces/pvs_sim_wrapper.py`
- `config/bridge_params.protocol_udp.pvs.yaml`

职责：

- 从仿真真值或数字孪生场生成传感器读数；
- 按仓库约定发布 Zenoh key；
- 保持单位、坐标系、时间戳一致。

这层的核心是“**生成模拟观测**”。

### 6.2 协议桥 / 设备接入 wrapper

代表位置：

- `brain_linux/src/auv_bridge/auv_bridge/bridge_backends.py`
- `brain_linux/src/auv_bridge/auv_bridge/bridge_node.py`

职责：

- 订阅外部 key 或设备数据；
- 做 JSON/二进制到 ROS 消息的转换；
- 统一 frame、单位和时间基；
- 发布 `/auv/sensors/magnetic`、`/auv/sensors/magnetic_extrinsics_status` 等标准输出。

这层的核心是“**把外部世界收敛成仓库内部标准消息**”。

### 6.3 算法门面 wrapper

代表位置：

- `brain_linux/src/auv_control/auv_decision_ros/cable_tracking_node.py`
- `brain_linux/src/auv_control/auv_decision_ros/cable_prior_adapter.py`

职责：

- 把 ROS 标准消息转成 `AUV-Master-Mag` 需要的 `NavigationInput` / `MagneticInput`；
- 调用专用仓算法；
- 把 tracking / guidance 再发布回标准 topic。

这层的核心是“**把算法仓接成主仓可消费的门面**”。

---

## 7. 磁传感器接入时，推荐遵守的契约

### 7.1 最终应该长成什么样

无论磁传感器来自仿真、真实串口/以太网设备，还是另一个进程，最终都应当收敛到：

- 输入：`/auv/sensors/magnetic` (`sensor_msgs/MagneticField`)
- 附加证明：`/auv/sensors/magnetic_extrinsics_status`
- 算法消费：`cable_tracking_node.py`

如果必须走 side-channel，也应复用现有 `bridge.magnetic_key`，而不是临时再发一个“只给某个算法看得懂”的专用 key。

### 7.2 wrapper 最少要做什么

一个合格的真实磁传感器 wrapper，至少要完成：

1. 读取厂商原始报文；
2. 转成标准单位和坐标系；
3. 写清楚 frame id 和时间戳；
4. 处理掉线、超时、无效值；
5. 输出标准 ROS topic 或标准 Zenoh key；
6. 把外参来源写入 `sensor_extrinsics_estimated.mag` 和 `metadata.mag_extrinsics_source`；
7. 保持 `bridge.magnetic_extrinsics_status.enabled=true`，让 bag 能证明当时采用了哪套外参。

### 7.3 不推荐的写法

不要这样做：

- 让算法节点直接解析厂商私有二进制/JSON；
- 在控制层里塞“仿真真值字段”；
- 把 `sensor_extrinsics_truth` 当成真机运行时配置；
- 为了接新设备临时加一套只在某个脚本里可见的 topic/key 命名。

推荐的思路是：

```text
厂商设备/仿真器
  -> wrapper
  -> 仓库标准契约
  -> bridge / ROS
  -> algorithm adapter
```

这样后面替换传感器、换通信方式、做录包取证，代价都最小。

---

## 8. 真机替代磁传感器时，优先放在哪一层

按接入位置选：

- **设备直接挂 Jetson，且驱动能在 ROS2 内跑**：
  优先直接发布 `/auv/sensors/magnetic`，这是最干净的方式。

- **设备在外部进程、外部工控机或 side-channel 网络上**：
  优先发布到 `rt/auv/sensors/magnetic`，由 `bridge_node.py` 统一转成 ROS topic。

- **只是仿真替身或录包回放**：
  放在仿真 wrapper / replay wrapper 层，不要改算法节点。

判断准则只有一个：**离数据源越近，越应该处理厂商差异；离算法越近，越应该只剩标准契约。**

---

## 9. 真实磁传感器 wrapper 最小模板

这一节不是要求现在就按某个厂商协议实现，而是给出一个**最小可维护骨架**。后续无论接串口磁强计、网口磁探头，还是另一个进程转发的数据，都建议先收敛成这个形状。

### 9.1 推荐输出契约

优先目标：

- 发布 `/auv/sensors/magnetic` (`sensor_msgs/MagneticField`)
- 由现有 bridge/部署配置发布 `/auv/sensors/magnetic_extrinsics_status`

若必须先走 side-channel：

- 发布 `rt/auv/sensors/magnetic`
- 载荷字段至少保持 `timestamp`、`frame_id`、`magnetic_field` 三类信息齐全

### 9.2 ROS 直发型 wrapper 骨架

适用场景：设备直接挂 Jetson，本机进程可直接读串口、网口或 SDK。

```python
from rclpy.node import Node
from sensor_msgs.msg import MagneticField


class MagneticSensorWrapper(Node):
    def __init__(self):
        super().__init__("magnetic_sensor_wrapper")
        self.publisher = self.create_publisher(
            MagneticField, "/auv/sensors/magnetic", 10
        )
        self.timer = self.create_timer(0.02, self.poll_device)
        self.frame_id = "mag_link"

    def poll_device(self):
        raw = self.read_vendor_packet()
        if raw is None:
            return

        sample = self.decode_vendor_packet(raw)
        if sample is None:
            return

        msg = MagneticField()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id

        # 统一在 wrapper 层完成单位和坐标轴转换。
        msg.magnetic_field.x = sample["bx_tesla"]
        msg.magnetic_field.y = sample["by_tesla"]
        msg.magnetic_field.z = sample["bz_tesla"]

        self.publisher.publish(msg)

    def read_vendor_packet(self):
        raise NotImplementedError

    def decode_vendor_packet(self, raw):
        raise NotImplementedError
```

这个骨架里，真正和厂商耦合的部分只有两处：

- `read_vendor_packet()`
- `decode_vendor_packet()`

其余部分都应该尽量保持成仓库内公共约定。

### 9.3 Side-channel 型 wrapper 骨架

适用场景：设备不直接挂 ROS2，或者已有外部进程统一采集，再送进 `bridge_node.py`。

```python
payload = {
    "timestamp": 1721212345.123,
    "frame_id": "mag_link",
    "magnetic_field": {
        "x": bx_tesla,
        "y": by_tesla,
        "z": bz_tesla,
    },
    "status": {
        "healthy": True,
        "source": "vendor_mag_sensor",
    },
}

# publish to rt/auv/sensors/magnetic
```

这里最重要的不是字段名字本身，而是三件事：

1. 单位已经在 wrapper 层统一好；
2. 时间戳是可追溯的；
3. bridge 收到后可以稳定映射成 `/auv/sensors/magnetic`。

### 9.4 wrapper 里必须当场处理的事

这些事情不要留给 `cable_tracking_node.py` 或更下游的控制节点：

- 厂商单位转 Tesla；
- 厂商坐标轴转车体系约定；
- 坏包/短包/校验失败丢弃；
- 掉线和超时告警；
- 无效值、饱和值、NaN 过滤；
- 必要的低通或节流。

换句话说，**下游看到的应该是“能直接拿来做融合/感知”的标准磁场消息，而不是半成品。**

### 9.5 外参与配置怎么落

真实磁传感器接入后，至少要同步这几处：

1. 把安装位姿写入 `sensor_extrinsics_estimated.mag`
2. 把标定结果来源写入 `metadata.mag_extrinsics_source`
3. 保持 `bridge.magnetic_extrinsics_status.enabled=true`
4. 若新设备 frame 改了，统一更新 `frame_id` 和相关 TF/文档说明

建议做法仍然是：**生成新的部署配置，不要就地覆盖基础配置。**

### 9.6 交付前自检清单

- 能稳定发布 `/auv/sensors/magnetic`
- bag 中能看到 `/auv/sensors/magnetic_extrinsics_status`
- 断开设备后 wrapper 会报健康状态下降，而不是静默卡死
- 更换厂商协议时，只需改 `read_vendor_packet()/decode_vendor_packet()` 一层
- `cable_tracking_node.py` 无需知道厂商私有字段

---

## 10. 实际迁移时建议怎么走

建议按这个顺序：

1. 先在 `PVS + protocol_udp` 验证高层逻辑和安全语义；
2. 真机阶段先只验证 `$AUV/$CKTH`、ESTOP、零执行器和日志链；
3. 需要 GUI + ROS2 并发时，引入 fan-out；
4. 新传感器先写 wrapper，把数据收敛到标准接口；
5. 再把真机外参、噪声、限幅写进 `params.protocol_udp_arbiter.real.yaml` 和相关部署配置；
6. 最后才做带真实传感器的闭环任务。

这和当前仓库已验证出来的边界是一致的：**高层全覆盖靠仿真，真机逐步接管靠阶段化部署。**

---

## 11. 相关文档

- 仿真验证记录：[`../experiment/protocol_udp_sim_validation.md`](../experiment/protocol_udp_sim_validation.md)
- PC104 空板边界：[`../experiment/pc104_sensorless_limit.md`](../experiment/pc104_sensorless_limit.md)
- 参数差异速查：[`07_param_diff_sim_vs_real.md`](07_param_diff_sim_vs_real.md)
- 电缆巡检 I/O 契约：[`08_cable_inspection_io_contract.md`](08_cable_inspection_io_contract.md)
- 磁探测集成原理：[`../internals/12_cable_tracking_mag_integration.md`](../internals/12_cable_tracking_mag_integration.md)
- fan-out 与脚本契约：[`../../scripts/README.md`](../../scripts/README.md)
