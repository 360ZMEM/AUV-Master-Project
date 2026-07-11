# PC104 Telnet/UDP/ROS2/上位机实物调试运行记录

状态：`OPEN`，作为运行时证据记录继续维护。  
最后整理日期：2026-07-11

## 中文整理入口

本文件记录 PC104/VxWorks 直连实物调试过程，覆盖 Telnet、UdpLogger、`$AUV` 上行、`$CKTH` 下行、PySide6 上位机、ROS2 `protocol_udp` passive/non-passive 桥接，以及 BUG-3/4/5/6 的 Telnet HIL 证据。

面向交付和复盘的定界报告见：

- `.trae/documents/PC104空板实物全链路调试定界报告_20260711.md`

当前总结论：

- Telnet、UdpLogger、`$AUV` 上行、`$CKTH` 零推力下行已通。
- PySide6 上位机 PC104 profile 已可用，能完成安全可观测字段的实物下行解析验证。
- ROS2 `protocol_udp` passive 上行桥接已通。
- ROS2 `protocol_udp` non-passive 零执行器下行短测已通。
- PC104 短测后读回：`Depth_Para1=500`、`Depth_Para2=29`、`Height_Para1=300`、`Height_Para2=200`、`Remain_Time=10`、电机为 0。
- 仍未闭合：BUG-4 Bit9、DVL 硬限/丢底自救主推输出、真实传感器链、带负载执行机构闭环、长时间稳定性和多进程同端口架构。

## 一、调试范围与安全原则

会话 ID：`pc104-telnet-udp`

调试范围：

- PC104/VxWorks 与调试电脑直连。
- Telnet 只读和受控写入。
- UdpLogger 日志回传。
- `$AUV` 上行和 `$CKTH` 下行。
- ROS2 `protocol_udp` 实物桥接。
- PySide6 上位机 PC104 直连 profile。
- 空板 HIL 条件下的 BUG-3/4/5/6 验证。

安全原则：

- S0/S1 只读证据通过前，不写 PC104 运行期内存。
- 所有实物下行优先使用零电机、零舵角或可恢复参数字段。
- 非 passive ROS2 下行必须先保证默认保护参数非零，避免把 PC104 shadow 保护参数清空。
- 所有测试后都要确认 `21/udp` 释放，并用 Telnet 读回关键 shadow 字段。

## 二、初始假设

1. 调试电脑直连 PC104 后，PC104 的 UdpLogger 可以回传到 `192.168.0.11:52367`。
2. Telnet 登录和 `lkup` 符号表仍对应当前烧录镜像，但地址不能沿用旧记录。
3. UDP 自动基线可能因本机绑定低端口 `21/udp` 权限不足失败，这不等价于物理链路失败。
4. 实物 HIL 链路实际使用 `21/udp`，不是 mock profile 的 `52364/52365`。
5. BUG-4、BUG-5、BUG-6 中部分问题可能需要源码修复和重新烧录才能完全闭合。

## 三、基础网络与 Telnet 证据

S0 直连网络：

- 调试电脑直连网卡：`enp3s0 = 192.168.0.11/24`。
- PC104：`192.168.0.101`。
- `ping 192.168.0.101` 成功，3/3 回复，RTT 约 `0.15 ms`。
- Telnet TCP `192.168.0.101:23` 可连接。
- 初始检查时本地 UDP 端口 `21/52364/52365/52366/52367` 未被占用。

Telnet 只读基线：

- `python3 scripts/vxworks_bug4_runtime_probe.py --host 192.168.0.101` 在不加 `--execute` 时完成。
- 已确认关键符号：
  - `Current_State = 0x536b20`
  - `UI_WIFI_Instruction = 0x536ac0`
  - `UI_LORA_Instruction = 0x536ee0`
  - `UI_Channel_Selection_Down = 0x517128`
  - `Instruction_To_FMCU = 0x536d20`
  - `Sys_Abnorm_Inf_Judgement = 0x5171ac`
  - `Depth_Exceed_FromUI12_Depth_Para1 = 0x5171bc`
  - `DVL_Prase_Data = 0x536da0`
  - `Seafloor_Grounding_Arbitration = 0x33d301`
  - `Vehicle_No = 1`
- 初始基线：`Sys_Abnorm=0x00000000`，`DepthExceed=0`，UI shadow 字段为安全/空闲状态。

结论：Telnet 只读路径可用。当前符号地址与旧记录不同，后续必须实时 `lkup`，不能复用旧绝对地址。

## 四、UdpLogger 与 UDP 基线

UdpLogger 回传：

- `python3 scripts/log_receiver.py --port 52367 --timestamps` 可收到 PC104 日志。
- 已观测：`Main_Ctrl_Task_Count_No`、`NetSendTask start::::`、`EmergencyTask start::::`、`WI_X/Y/Z/V`、`WD_Depth`、`WD_Check`。

结论：PC104 到电脑的 `52367/udp` 日志回传通。

低端口权限：

- 本机 `net.ipv4.ip_unprivileged_port_start = 1024`。
- 普通用户绑定 `21/udp` 会失败：`PermissionError: [Errno 13] Permission denied`。
- 用户完成 sudo 授权后，`sudo -n true` 可用。

工具修复：

- `scripts/sniffer.py` 原先缺少 `args = parse_args()`，导致 `NameError: args is not defined`。
- 已修复后可用于 `21/udp` 抓包。

## 五、`$AUV` 上行与 `$CKTH` 下行

`$AUV` 上行：

- 命令：`sudo -n timeout 8 python3 scripts/sniffer.py --bind-port 21 --count 1 --ascii-format --no-color`。
- 收到合法上行帧，源地址 `192.168.0.101:21`。
- 示例字段：帧号 `196`，AUV 地址 `1`，控制模式 `0x00`，深度 `0.00 m`，`motor1/motor2=0`，checksum 正确，帧尾正确。

结论：PC104 `$AUV` 上行到电脑 `21/udp` 有效。

安全双向 UDP 烟测：

- 向 `192.168.0.101:21` 发送一帧零推力 `$CKTH`。
- 字段：`CtrlMode=0x01`，`Motor1=0`，`Motor2=0`。
- 发送后收到连续合法上行：
  - 发送前：frame `48`，ctrl `0x00`，sys `0x00000000`，motor `0/0`
  - 发送后：frame `49/50/51`，最终 ctrl 变为 `0x01`，motor 仍为 `0/0`
- Telnet 读回 `UI_WIFI_Instruction`：`ctrl=1`，`motor1=0`。

结论：零推力 `$CKTH` 下行到达 PC104，并同时反映到上行遥测和内部 UI shadow。

## 六、Telnet 工具修复与 VxWorks shell 规则

`lkup` 精确匹配修复：

- `lkup "Current_State"` 会同时返回 `Current_State_printf` 和真正的 `Current_State`。
- 旧解析器误选了 `Current_State_printf`。
- 已修复 `VxShell.lkup()`：优先匹配精确符号名。
- 正确 dry-run 读回：`Current_State = 0x536b20`。

VxWorks shell 浮点规则：

- `printf("%f", ...)` 不支持。
- `*(float*)addr=2.5` 看似成功，但会把 raw word 清成 `0`。
- 可靠写法是 IEEE754 raw：`*(unsigned int*)addr=0x40200000`。

## 七、BUG-3/BUG-4 Telnet HIL 结果

BUG-3：超深滑动窗口计数

- 注入超深状态后，`Depth_Exceed_FromUI12_Depth_Para1` 上升到 `9`。
- 恢复安全深度后，计数衰减回 `0`。
- `Sys_Abnorm` 保持 `0x00000000`。

结论：BUG-3 计数递增/递减行为有效。

BUG-4：超深应急上浮命令路径

- 命令：`python3 scripts/vxworks_bug4_runtime_probe.py --host 192.168.0.101 --execute --probe trigger-bug4`。
- 触发后：`DepthExceed=19`。
- UI shadow：`ctrl=1`，`depth_para1=5`，`motor1=300`，`lh_angle=-20`，`rh_angle=-20`。
- `Instruction_To_FMCU` 扫描：`+0x18=300`，`+0x20=2275`，`+0x22=1821`。
- `$MCUFD` 可见：`00300,00000,2275,1821,2048,2048`。

结论：当前烧录固件中，BUG-4 应急上浮命令路径闭合。

未闭合点：

- 触发期间 `Sys_Abnorm=0x00000000`，Bit9 未观测到。
- 手动设置 `Sys_Abnorm_Inf_Judgement = 0x00000200` 后，`$AUV` 能正确上行 `sys=0x00000200`。
- 因此 Bit9 缺口在运行期设置/保持逻辑，不在上行打包或解析。

## 八、DVL BUG-5/BUG-6 Telnet HIL 结果

已确认 DVL 结构偏移：

- `BD_Height = DVL_Prase_Data + 0x18`
- `BD_Check = DVL_Prase_Data + 0x20`

可靠 DVL HIL 隔离需要暂停：

- `MainCtrlTask`
- `UartRecvFormDVLTask`
- `UnpackDVLDataTask`
- `NetRecvTask`
- `UnpackNetDataTask`

BUG-5 软限：

- 注入 `BD_Check=2.0`、`BD_Height=2.5m`。
- 调用 `Seafloor_Grounding_Arbitration()` 六次。
- 观测到 `SYS=0x00000800`。

结论：Bit11 软限告警有效。

BUG-5 硬限：

- 注入 `BD_Check=2.0`、`BD_Height=1.2m`、pitch `0`、DVL velocity `3.0`。
- 调用仲裁四次。
- 观测到 `HARD sys=0x00001800 motor=0 lh=2275 rh=1821`。

结论：Bit12 硬限告警有效，但 `Motor1` 自救输出没有保留到 `Instruction_To_FMCU`。

疑似原因：硬限分支先设置 `Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 350`，随后调用 `Remote_Assignment(&Instruction_To_FMCU)`，该函数可能又用 `UI_WIFI_Instruction` 覆盖主推；硬限分支没有同步写 `UI_WIFI_Instruction.FromUI12_Motor_Speed1`。

BUG-6 DVL 丢底：

- 注入 `Current_State.Current_Mode=0xEE`、`BD_Check=0.0`。
- 调用仲裁二十一次。
- 观测到 `LOST sys=0x00002000 motor=0 lh=2275 rh=1821 curmode=0xffffffee uictrl=0x00000001`。

结论：Bit13 与 UI 模式降级到 remote `0x01` 有效，但自救主推输出同样没有保留到 `Instruction_To_FMCU`。

工具状态：

- 已新增 `scripts/vxworks_dvl_runtime_probe.py`。
- 脚本可解析符号和 dry-run。
- 自动 execute 尚未稳定复现手工 raw float 写入证据，当前仍以手工 Telnet raw 写入结果为权威。

## 九、ROS2 `protocol_udp` passive 上行桥接

新增 profile：

- `brain_linux/config/params.protocol_udp_pc104.yaml`
- 本地绑定：`0.0.0.0:21`
- 远端：`192.168.0.101:21`
- `backend: protocol_udp`
- `passive_mode: true`
- `protocol_udp.obj_address: 1`

启动方式：

- 由于 `21/udp` 需要权限，使用 sudo 并 source ROS 环境：
  - `source /opt/ros/humble/setup.bash`
  - `source brain_linux/install/setup.bash`
  - `ros2 run auv_bridge zenoh_json_bridge_node --ros-args -p params_file:=.../params.protocol_udp_pc104.yaml -p bridge_backend:=protocol_udp -p passive_mode:=true`

证据：

- bridge 日志：`bridge backend started: protocol_udp, passive_mode=True`。
- 日志持续显示 `[bridge] received N sensor payloads via protocol_udp`，计数从几十增长到上千。
- ROS graph 可见：
  - `/auv/sensors/depth`
  - `/auv/sensors/dvl`
  - `/auv/sensors/imu`
  - `/auv/sensors/altitude`
  - `/auv/bridge/shadow_telemetry`
  - `/auv/arbiter/status`
  - `/cmd_vel`

sudo ROS CLI 样本：

- `/auv/sensors/depth`: `data: 0.0`
- `/auv/sensors/dvl`: `TwistStamped`，线速度/角速度均为 `0.0`
- `/auv/bridge/shadow_telemetry`: `active_arbiter=REMOTE`、`auto_state=LOCKED`、`altitude_m≈1.2`
- `/auv/arbiter/status`: `active_arbiter=REMOTE`、`auto_state=LOCKED`、`effective_control_mode_byte=1`、`telemetry_freshness_ms≈0.49`

注意：普通用户 `ros2 topic echo --once` 可看到 publisher，但不一定收到 sudo-launched bridge 的样本；sudo ROS 环境可以收到。判断为本机 DDS/用户上下文问题，不是 PC104 或 bridge 数据失败。

结论：真实 PC104 `$AUV` 到 ROS2 topic 的 passive 上行桥接已通。

## 十、PySide6 上位机 PC104 直连

新增 profile：

- `console_soft/auv_console_pyside6/console_config.pc104.yaml`
- 本地绑定：`192.168.0.11:21`
- 远端 PC104：`192.168.0.101:21`
- `packet.obj_address: 1`
- `packet.work_mode: 1`
- 默认安全参数：`500/29/300/200/10`

代码改动：

- `main.py` 支持 `--config`。
- `src/ui/main_window.py` 可从 YAML 覆盖 legacy `port_set.txt` 中的 UDP 端点。
- `src/ui/main_window.py` 可从 YAML 覆盖 legacy `param.txt` 中的目标板号、工作模式和保护参数。
- 默认不带 `--config` 时仍保持原行为。

非侵入验证：

- `py_compile` 通过。
- `parse_app_args()` 能消费 `--config console_config.pc104.yaml`，Qt 参数仍保留。
- 不启动 GUI 的 YAML 覆盖 smoke 通过，端点被覆盖为 `192.168.0.11:21 -> 192.168.0.101:21`。

offscreen GUI smoke：

- 命令：`timeout 6s sudo -n -E env QT_QPA_PLATFORM=offscreen /usr/bin/python3 main.py --config console_config.pc104.yaml`
- 观测：
  - 已加载 `console_config.pc104.yaml`
  - legacy mock 端点先被读入：`127.0.0.1:21 -> 127.0.0.1:52364`
  - YAML 覆盖为：`192.168.0.11:21 -> 192.168.0.101:21`
  - `UDP socket 已绑定到 192.168.0.11:21`
  - `UDP接收线程已启动`
- 清理：`timeout` 没有完全回收 sudo Qt 子进程，使用 `sudo -n pkill -f 'main.py --config console_config.pc104.yaml'` 清理。

协议解析实物证明：

- 使用 PySide6 自身模块 `PacketBuilder + UDPCommunicator`，绑定 `192.168.0.11:21`，发送到 `192.168.0.101:21`。
- 全程电机和舵角为 0。
- 第一次用 `obj_address=2` 发送 `Depth_Para1=501`，PC104 不更新。
- Telnet 读回 `Vehicle_No=1`，确认原因是 VxWorks 只接受 `temp_buf[6] == Vehicle_No` 的包。
- 改用 `obj_address=1` 后，发送五帧 `Depth_Para1=501`。
- Telnet 读回：
  - `UI ctrl=1`
  - `UI depth_para1=501`
  - `UI motor1=0`
  - `INS motor1=0`
- 再发送五帧 `Depth_Para1=500` 恢复。
- Telnet 读回：
  - `UI depth_para1=500`
  - `UI motor1=0`
  - `INS motor1=0`

结论：PySide6 上位机的构包、UDP 发送、PC104 WIFI 接收、checksum 校验、解包写入 `UI_WIFI_Instruction` 链路已通。PySide6 可用于 PC104 直连安全烟测。

边界：PySide6 和 ROS2 PC104 profile 都要绑定本地 `21/udp`，当前不能同时运行，需要分阶段测试或后续做 UDP fan-out/代理。

推荐启动：

```bash
cd console_soft/auv_console_pyside6
sudo -E /usr/bin/python3 main.py --config console_config.pc104.yaml
```

## 十一、ROS2 `protocol_udp` non-passive 零执行器下行

风险发现：

- 静态检查发现：启用 arbiter 且没有 PC raw command 缓存时，旧 `CommandArbiter._default_remote_payload()` 会生成：
  - `KEY_DEPTH_PROTECT_PARAMS: (0, 0)`
  - `KEY_BOTTOM_PROTECT_PARAMS: (0, 0)`
  - `KEY_PRESET_TIME_TENTHS_MIN: 0`
- 虽然旧 idle 输出电机/舵角为 0，但会把 PC104 shadow 保护参数清零。

修复：

- `CommandArbiter` 增加可配置默认 remote 安全字段：
  - `default_depth_protect_params`
  - `default_bottom_protect_params`
  - `default_preset_time_tenths_min`
- `AUVBridgeNode` 从 YAML 读取 `bridge.arbiter.default_remote_payload`。
- `brain_linux/config/params.protocol_udp_pc104.yaml` 配置：
  - `depth_protect_params: [500, 29]`
  - `bottom_protect_params: [300, 200]`
  - `preset_time_tenths_min: 10`
- 新增单测：`test_default_remote_payload_can_preserve_pc104_bench_safety_params`。

验证：

- `py_compile` 通过。
- `test_arbiter.py` 定向测试通过：`6 passed`。
- dry-run 构包证明：
  - payload depth: `(500, 29)`
  - payload bottom: `(300, 200)`
  - payload preset: `10`
  - encoded packet: `obj=1`、`ctrl=1`、`work=0`、`motor=0/0`

第一次实物尝试：

- 在未重新构建 `brain_linux/install` 前直接启动 ROS2 bridge。
- bridge 以 `passive_mode=False` 运行并收到上行，但 Telnet 读回 `UI depth_para1=0`。
- 根因：实物运行的是 install 中旧代码。
- 立即用 PySide6 安全帧恢复，读回：`UI depth_para1=500`、`UI motor1=0`、`INS motor1=0`。

重建：

```bash
cd brain_linux
source /opt/ros/humble/setup.bash
colcon build --packages-select auv_bridge --symlink-install
```

结果：`1 package finished`。

第二次实物短测：

- 使用 sudo 内部 timeout，窗口 8 秒。
- `passive_mode:=false`
- `command_publish_hz:=2.0`
- 日志：
  - `bridge backend started: protocol_udp, passive_mode=False`
  - 短测窗口内收到 `30/60/90` 个 sensor payload。
- 停止后 `ss -lunp 'sport = :21'` 显示端口已释放。

Telnet 读回：

- `UI ctrl=1`
- `UI depth_para1=500`
- `UI depth_para2=29`
- `UI height_para1=300`
- `UI height_para2=200`
- `UI remain_time=10`
- `UI motor1=0`
- `INS motor1=0`

结论：ROS2 `protocol_udp` non-passive idle 下行在“零执行器、安全保护参数、短时间窗口”范围内已通。

## 十二、fan-out 并发架构与短测

目标：

- 解决 ROS2 bridge 和 PySide6 上位机同时抢占本机 `21/udp` 的问题。
- 让 fan-out 成为唯一绑定 `192.168.0.11:21` 的进程。
- 将 PC104 `$AUV` 上行复制给 ROS2 和 PySide6 高端口。
- 将 ROS2/PySide6 下行统一送入 fan-out，由 fan-out 做安全审计后再转发到 PC104。

新增脚本：

- `scripts/pc104_udp_fanout.py`
  - 默认绑定真实端：`192.168.0.11:21`。
  - 默认 PC104：`192.168.0.101:21`。
  - 默认本地下行入口：`127.0.0.1:52364`。
  - 默认上行订阅者：
    - ROS2：`127.0.0.1:52365`
    - PySide6：`127.0.0.1:52366`
  - 默认安全策略：
    - 允许 ROS2/PySide6 安全零执行器 `$CKTH`。
    - 拒绝未知来源。
    - 拒绝非零主推、侧推或舵角，除非显式加 `--allow-nonzero-actuator`。

新增 profile：

- ROS2：`brain_linux/config/params.protocol_udp_pc104_fanout.yaml`
  - `local_host: 127.0.0.1`
  - `local_port: 52365`
  - `remote_host: 127.0.0.1`
  - `remote_port: 52364`
- PySide6：`console_soft/auv_console_pyside6/console_config.pc104_fanout.yaml`
  - `local_ip: 127.0.0.1`
  - `local_port: 52366`
  - `amd_ip: 127.0.0.1`
  - `amd_port: 52364`

新增启动/停止脚本：

- `scripts/start_pc104_fanout_concurrent.sh`
  - 先检查 `21/udp` 是否空闲。
  - sudo 启动 fan-out 绑定 `21/udp`。
  - 普通用户启动 ROS2 bridge，避免 sudo-launched bridge 带来的 DDS 用户上下文问题。
  - 默认 `--passive`，可显式 `--non-passive`。
- `scripts/stop_pc104_fanout_concurrent.sh`
  - 停止 ROS2 bridge。
  - 停止 root fan-out。
  - fallback 清理 installed `zenoh_json_bridge_node` 子进程。
  - 最后检查 `21/udp`。

本地 dry-run 结果：

- fan-out 绑定 `127.0.0.1:52121` 模拟实物端口。
- 模拟 145 字节 `$AUV` 上行成功复制到：
  - `127.0.0.1:52365`
  - `127.0.0.1:52366`
- ROS2 来源安全零执行器 `$CKTH` 被转发到模拟 PC104 端口，长度 `72` 字节。
- 非零主推 `$CKTH` 被 fan-out 拒绝，模拟 PC104 未收到。

实物 passive 短测结果：

- 命令：`scripts/start_pc104_fanout_concurrent.sh --passive`。
- fan-out 进程 pid 正确记录。
- ROS2 bridge 使用 fan-out profile，在普通用户上下文运行。
- ROS2 日志显示真实上行持续增长：
  - `received 38 sensor payloads`
  - `received 68 sensor payloads`
  - `received 98 sensor payloads`
  - `received 128 sensor payloads`
  - `received 158 sensor payloads`
  - `received 188 sensor payloads`
  - `received 218 sensor payloads`
  - `received 248 sensor payloads`
- 停止脚本执行后，`21/udp` 已释放，残留 `pc104_udp_fanout.py` 和 `zenoh_json_bridge_node` 进程清理完成。

实物 non-passive 零执行器 soak 结果：

- 命令：`scripts/run_pc104_fanout_zero_soak.sh --duration 180 --command-hz 2.0`。
- ROS2 bridge 以普通用户上下文运行，fan-out 以 sudo 占用低端口 `21/udp`。
- 普通用户 ROS CLI 可直接读取：
  - `/auv/sensors/depth --once`：`data: 0.0`
  - `/auv/arbiter/status --once`：`active_arbiter=REMOTE`、`arbiter_source=NONE`、`auto_state=LOCKED`、`telemetry_freshness_ms≈0.19`
- fan-out 日志显示：
  - 上行计数达到 `uplink=2744`。
  - 下行计数达到 `downlink=360`。
  - 阻断计数保持 `blocked=0`。
  - 每个 ROS2 下行 `$CKTH` 均为 `obj=1`、`depth=(500, 29)`、`bottom=(300, 200)`、`preset=10`、`motor=0/0`、舵角全 `0.0`。
- ROS2 日志显示：
  - `received 2710 sensor payloads via protocol_udp`。
- 停止脚本执行后：
  - `21/udp`、`52364/udp`、`52365/udp`、`52366/udp` 均已释放。
  - ROS2 日志尾部出现 `rclpy.executors.ExternalShutdownException`，这是 stop 脚本终止 ROS2 spin 时的正常退出栈，不是 soak 期间运行异常。

PySide6 并发 SOP：

- 已新增 `.trae/documents/PySide6上位机_PC104并发调试计划与SOP_20260711.md`。
- 已区分：
  - 可由脚本模拟并绕过 GUI 读取的内容。
  - 必须由用户手动点按的内容。
  - 用户侧按钮 SOP 和期望现象。

Zenoh 依赖：

- 普通用户 `/usr/bin/python3` 可以 import `zenoh`，来源为用户目录。
- sudo 环境最初不能 import `zenoh`。
- 尝试 `sudo -n /usr/bin/python3 -m pip install zenoh` 失败，原因是 PyPI 包名不是 `zenoh`。
- 识别正确包名为 `eclipse-zenoh`，普通用户环境已装 `1.8.0`。
- 尝试全局安装 `sudo -n /usr/bin/python3 -m pip install eclipse-zenoh==1.8.0`，但卡在构建 metadata 阶段，已停止。
- 尝试安装到 `/usr/local/lib/python3.10/dist-packages` 仍卡在 `Preparing metadata (pyproject.toml)`，已用 `StopCommand` 终止。
- 当前验证：`sudo -n /usr/bin/python3 -c "import zenoh"` 仍报 `ModuleNotFoundError`。
- 当前结论：fan-out 主链路不依赖 Zenoh；Zenoh side channel 仍作为依赖 TODO 保留。

## 十三、本地工具与代码改动

工具修复：

- `scripts/sniffer.py`：修复 `args = parse_args()` 缺失。
- `scripts/vxworks_bug4_runtime_probe.py`：修复 `lkup()` 精确符号匹配；Motor1 Telnet 写入改为更合适的整数写法。
- `scripts/vxworks_dvl_runtime_probe.py`：新增 DVL 仲裁探针，但 execute 自动化仍需加固。

上位机：

- `console_soft/auv_console_pyside6/main.py`：新增 `--config`。
- `console_soft/auv_console_pyside6/src/ui/main_window.py`：新增 YAML UDP/packet 覆盖。
- `console_soft/auv_console_pyside6/console_config.pc104.yaml`：新增 PC104 直连 profile。
- `console_soft/auv_console_pyside6/console_config.pc104_fanout.yaml`：新增 fan-out 并发 profile。

ROS2：

- `brain_linux/config/params.protocol_udp_pc104.yaml`：新增 PC104 profile 与安全默认 payload。
- `brain_linux/config/params.protocol_udp_pc104_fanout.yaml`：新增 fan-out 并发 profile。
- `brain_linux/src/auv_bridge/auv_bridge/arbiter.py`：默认 remote payload 支持安全参数配置。
- `brain_linux/src/auv_bridge/auv_bridge/bridge_node.py`：读取 YAML 默认 remote payload。
- `brain_linux/src/auv_bridge/test/test_arbiter.py`：增加安全默认参数单测。

fan-out：

- `scripts/pc104_udp_fanout.py`：新增 PC104 UDP fan-out 代理。
- `scripts/start_pc104_fanout_concurrent.sh`：新增并发栈启动脚本，并加固 `21/52364/52365/52366` 启动前端口检查、fan-out 绑定检查和 ROS2 早退检查。
- `scripts/stop_pc104_fanout_concurrent.sh`：新增并发栈停止脚本，并加固 sudo-aware 停止、`--force` 清理和端口释放等待。
- `scripts/status_pc104_fanout_concurrent.sh`：新增并发栈状态脚本，用于显示 pid、端口和日志尾部。
- `scripts/run_pc104_fanout_zero_soak.sh`：新增 bounded non-passive 零执行器 soak 脚本，统一 `timeout`、清理和日志摘要。
- `.trae/documents/PySide6上位机_PC104并发调试计划与SOP_20260711.md`：新增 PySide6 并发调试计划与用户 SOP。

重要备份：

- `debug-pc104-telnet-udp_bak_20260711_before_full_cn.md`
- 其他按阶段创建的 `_bak_20260711_*` 备份文件保留用于 diff 审计。

## 十四、当前完成状态

已完成：

- PC104 直连网络。
- Telnet 登录和只读符号基线。
- UdpLogger `52367/udp` 回传。
- `$AUV` 上行 `21/udp`。
- `$CKTH` 零推力下行。
- BUG-3 计数状态机。
- BUG-4 应急上浮命令路径。
- BUG-5 DVL 软限/硬限告警位。
- BUG-6 DVL 丢底告警位与 UI 降级。
- PySide6 PC104 profile、安全构包、实物解析路径。
- ROS2 `protocol_udp` passive 上行到 ROS topic。
- ROS2 `protocol_udp` non-passive 零执行器、安全保护参数短测。
- ROS2 与 PySide6 并发接入 PC104 的 fan-out 架构。
- fan-out 本地 dry-run。
- fan-out + ROS2 passive 实物短测。
- fan-out + ROS2 non-passive 180 秒零执行器 soak。
- 普通用户 ROS CLI 与 sudo fan-out 的 DDS 上下文验证。
- 一键启动/停止/状态/soak 脚本初版与端口释放检查加固。
- 中文定界报告。
- PySide6 并发调试计划与 SOP。

未完成或未闭合：

- BUG-4 Bit9 运行期设置/保持。
- BUG-5 硬限自救主推输出保留到 `Instruction_To_FMCU`。
- BUG-6 丢底自救主推输出保留到 `Instruction_To_FMCU`。
- DVL 自动化 Telnet 探针 execute 全流程稳定性。
- PySide6 GUI 手动并发 SOP 尚未由用户实际点按验收。
- ROS2 non-passive 更长时间稳定性、断链恢复、重启恢复。
- 非零 `/cmd_vel` 或 MPC 输出到 PC104 的实物链路。
- Zenoh side channel 全局依赖安装和实测。
- 不接入传感器条件下无法完成真实传感器链和带负载执行机构闭环。

## 十五、下一步建议

不涉及传感器接入时，建议下一阶段优先级：

1. 让用户按 PySide6 并发 SOP 手动启动 GUI，完成 fan-out + ROS2 + PySide6 同时观察。
2. 在 180 秒 soak 通过基础上，扩展到 10-30 分钟零执行器 soak，并增加断链/重启恢复观察。
3. 继续加固一键启动/停止脚本，增加更明确的日志轮转和健康检查。
4. 处理 Zenoh side channel 依赖，优先找可直接安装的 wheel 或系统包方案。
5. 加固 `vxworks_dvl_runtime_probe.py`，让 DVL raw float 注入和任务恢复更稳定。
6. 修复并复验 BUG-4 Bit9。
7. 修复并复验 BUG-5/BUG-6 自救主推被 `Remote_Assignment()` 覆盖的问题。
8. 在明确安全许可后，再做小幅非零 `/cmd_vel` 或 MPC 输出链路。

## 十六、仿真回归与 sudo Zenoh 环境验证（2026-07-11 16:30）

目标：

- 确认基于 PC104 实物引入的 fan-out/profile 改动没有显式污染仿真默认链路。
- 确认是否可以通过环境变量让 sudo Python 复用普通用户侧已安装的 `zenoh`。

仿真 smoke 结果：

- 命令：`timeout --foreground 30s bash scripts/start_lin_sim.sh sim`。
- 结果：
  - 仿真使用 `config/sim_params.yaml`。
  - bridge config 解析为 `config/bridge_params.yaml`。
  - 后端为 `holoocean`。
  - 主循环正常输出 LOS + cascaded PID 步进日志。
  - 输出包含 `turn_radius_check: ... pass=True` 与连续 `step=... pos=... cmd=...`。
- 结论：仿真主循环 smoke 通过，未要求 fan-out，未占用 PC104 `21/udp`。

仿真 bridge smoke 结果：

- 命令：`timeout --foreground 30s bash scripts/start_lin_sim.sh bridge`。
- 结果：
  - bridge 持续输出深度和磁场样本，例如 `step=0020xx depth≈12m |B|≈1.6e-07T`。
- 结论：仿真 bridge smoke 通过，普通用户侧 `zenoh` 可支撑仿真 bridge 路径。

ROS2 默认 stack 检查：

- 命令：`ros2 launch brain_linux/launch/auv_stack.launch.py --show-args`。
- 结果：
  - 默认 `params_file` 为 `brain_linux/config/params.yaml`。
  - 默认 `bridge_backend` 为 `zenoh_json`。
  - 默认未指向 `params.protocol_udp_pc104.yaml` 或 `params.protocol_udp_pc104_fanout.yaml`。
- 结论：ROS2 默认 launch 参数未误用 PC104/fan-out profile。
- 保留项：
  - `scripts/start_lin_brain.sh stack` 在当前终端环境下输出异常简短；完整 ROS2 stack 长窗口回归仍需单独执行。

进程与端口清理：

- 仿真/bridge 命令停止后，未发现残留 `sim_holoocean`、`run_zenoh_bridge.py`、`start_lin_sim.sh` 进程。
- `21/udp`、`52364/udp`、`52365/udp`、`52366/udp` 均为空闲。

sudo Zenoh 环境验证：

- 普通用户可用：
  - `/usr/bin/python3 -c "import zenoh"` 成功。
  - 路径为 `/home/gwxie/.local/lib/python3.10/site-packages/zenoh/__init__.py`。
- sudo 默认不可用：
  - `sudo -n /usr/bin/python3 -c "import zenoh"` 报 `ModuleNotFoundError`。
- `PYTHONPATH` 旁路可用：
  - `sudo -n env PYTHONPATH=/home/gwxie/.local/lib/python3.10/site-packages /usr/bin/python3 -c "import zenoh"` 成功。
  - `from zenoh import Config` 成功。
- `PYTHONUSERBASE` 旁路可用：
  - `sudo -n env PYTHONUSERBASE=/home/gwxie/.local /usr/bin/python3 -c "import zenoh"` 成功。

当前结论：

- 不需要继续阻塞在全局 `pip install eclipse-zenoh`。
- 开发期可以用显式环境注入让 sudo Python 复用用户侧 Zenoh：

```bash
sudo -n env \
  PYTHONPATH=/home/gwxie/.local/lib/python3.10/site-packages \
  /usr/bin/python3 -c "import zenoh; print(zenoh.__file__)"
```

- 更推荐用于脚本的是 `PYTHONPATH`，因为它指向明确、行为直观。
- 工业部署仍不建议长期依赖用户目录注入；应优先考虑系统包、wheel、独立运行用户、systemd 环境配置或容器/venv 固化。

## 十七、非零下行、Zenoh 仲裁、DVL/BUG-5/BUG-6 与长 soak 回归（2026-07-11 16:35-16:50）

目标：

- 做一次受控非零 `/cmd_vel -> PC104` 短测。
- 验证 sudo Python 通过 `PYTHONPATH` 透传用户侧 Zenoh 后，能否驱动仲裁 side channel。
- 扩展 ROS2 non-passive 零执行器 soak。
- 复查 BUG-5/BUG-6 自救主推被 `Remote_Assignment()` 覆盖的问题。
- 复查 DVL Telnet 自动化脚本 execute 全流程稳定性。

### 17.1 fan-out 非零放行门控

修改：

- `scripts/start_pc104_fanout_concurrent.sh`
  - 新增 `--allow-nonzero-actuator`。
  - 默认仍不放行非零执行器。
  - 只有显式传参时才把 `--allow-nonzero-actuator` 传给 `scripts/pc104_udp_fanout.py`。
  - 新增 `--params-file PATH`，允许显式选择 ROS2 bridge profile。

新增 profile：

- `brain_linux/config/params.protocol_udp_pc104_fanout_cmdvel_bench.yaml`
  - 基于 fan-out profile 派生。
  - `arbiter.enabled=false`。
  - 仅用于 bench 短测，让 `/cmd_vel` 直接编码成 `$CKTH`。
  - 不作为常规实物运行 profile。

安全边界：

- 常规 fan-out profile 仍启用 arbiter。
- 常规 fan-out profile 下即使 fan-out 允许非零，`/cmd_vel` 也不会直接支配 PC104；remote 默认安全包仍输出零执行器。
- 真正 `/cmd_vel` 直达 PC104 必须显式使用 bench profile。

### 17.2 非零 `/cmd_vel -> PC104` 短测

命令：

```bash
scripts/start_pc104_fanout_concurrent.sh \
  --non-passive \
  --command-hz 2.0 \
  --allow-nonzero-actuator \
  --params-file brain_linux/config/params.protocol_udp_pc104_fanout_cmdvel_bench.yaml
```

随后发布短脉冲：

```bash
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 5.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"

sleep 1

ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
```

fan-out 证据：

```text
[fanout] forward ros2 -> PC104: ... ctrl=238 ... motor=75/0 ...
[fanout] forward ros2 -> PC104: ... ctrl=238 ... motor=75/0 ...
[fanout] forward ros2 -> PC104: ... ctrl=238 ... motor=0/0 ...
```

结论：

- 非零 `/cmd_vel` 到 PC104 的 UDP 编码和 fan-out 转发链路已打通。
- `linear.x=5.0` 在 `main_motor_rpm_scale=15.0` 下编码为 `main_motor_rpm=75`，与预期一致。
- 归零包随后恢复 `motor=0/0`。
- 本测试未接推进器，仍按 bench 高风险路径处理。

注意：

- bench profile 中 `arbiter.enabled=false`，因此默认安全 remote payload 不参与保护。
- bench profile 早期零包曾显示 `depth=(0,0)`，不能用于常规 soak 或实物长期运行。

### 17.3 Zenoh sudo 透传与仲裁 side channel

sudo Zenoh 本机回环：

```bash
sudo -n env \
  PYTHONPATH=/home/gwxie/.local/lib/python3.10/site-packages \
  /usr/bin/python3 - <<'PY'
import time
import zenoh
received = []
conf = zenoh.Config()
conf.insert_json5('mode', '"peer"')
conf.insert_json5('scouting/multicast/enabled', 'false')
session = zenoh.open(conf)
sub = session.declare_subscriber(
    'rt/auv/test/sudo_zenoh_loopback',
    lambda sample: received.append(bytes(sample.payload).decode('utf-8', errors='replace')),
)
pub = session.declare_publisher('rt/auv/test/sudo_zenoh_loopback')
time.sleep(0.3)
pub.put('sudo-zenoh-loopback-ok')
time.sleep(0.5)
print(received)
session.close()
PY
```

结果：

```text
received ['sudo-zenoh-loopback-ok']
```

仲裁 side channel：

- 通过 sudo Python + `PYTHONPATH` 发布 `rt/pc/cmd_raw` 零执行器 PC raw JSON。
- ROS2 bridge 已订阅 `rt/pc/cmd_raw`。
- `/auv/arbiter/status` 从 `arbiter_source: NONE` 变为 `arbiter_source: PC_RAW`。

结论：

- sudo 透传路径不仅能 import Zenoh，还能 open session、declare pub/sub、完成本机回环收发。
- `rt/pc/cmd_raw -> ROS2 bridge -> CommandArbiter` 已实测打通。
- 该路径可作为开发期 side channel 验证方案。

### 17.4 发现并修复 PC raw 超时 degraded payload 清零安全参数

问题现象：

- 发送单包 `rt/pc/cmd_raw` 后，bridge 进入 `arbiter_source=PC_RAW`。
- PC raw 超时后，bridge 进入 degraded/`TASK_CANCEL` 包。
- 修复前 fan-out 观察到：

```text
work=2 depth=(0, 0) bottom=(0, 0) preset=0 motor=0/0
```

风险：

- 这会再次覆盖 PC104 板端 shadow 安全参数。
- 与之前“idle 状态清零保护参数”的风险同类，但触发路径是 PC raw side channel 超时。

修复：

- 修改 `brain_linux/src/auv_bridge/auv_bridge/bridge_node.py`
  - `_build_degraded_payload()` 改为保留：
    - `self.default_remote_depth_protect_params`
    - `self.default_remote_bottom_protect_params`
    - `self.default_remote_preset_time_tenths_min`
  - `_zero_command_payload()` 同样携带上述安全参数。
  - `_zero_command_payload()` 类型标注从 `dict[str, float]` 调整为 `dict[str, Any]`。

验证：

```bash
colcon build --packages-select auv_bridge --symlink-install \
  --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3 -DPYTHON_EXECUTABLE=/usr/bin/python3
```

复测结果：

```text
work=2 depth=(500, 29) bottom=(300, 200) preset=10 motor=0/0
```

结论：

- PC raw 超时 degraded 包不再清零 PC104 安全保护参数。
- 该修复已编译并通过实物 fan-out 日志复验。

### 17.5 ROS2 non-passive 零执行器 300 秒 soak

命令：

```bash
scripts/run_pc104_fanout_zero_soak.sh --duration 300 --command-hz 2.0
```

结果：

- soak 自然结束。
- 停止脚本释放 `21/udp`、`52364/udp`、`52365/udp`、`52366/udp`。
- fan-out 末端状态：

```text
uplink≈4535
downlink≈600
blocked=0
```

fan-out 下行持续保持：

```text
obj=1 ctrl=1 work=0
depth=(500, 29)
bottom=(300, 200)
preset=10
motor=0/0
fins=(0.0,0.0,0.0,0.0)
```

结论：

- 300 秒级 ROS2 non-passive 零执行器 soak 通过。
- 本轮修复后，安全 profile 没有出现安全保护参数清零。

### 17.6 重启恢复验证

命令：

```bash
scripts/start_pc104_fanout_concurrent.sh --non-passive --command-hz 2.0
sleep 8
scripts/status_pc104_fanout_concurrent.sh
scripts/stop_pc104_fanout_concurrent.sh --force
```

结果：

- 重启后 fan-out 与 ROS2 bridge 均正常运行。
- ROS2 bridge 8 秒内收到 PC104 payload，日志出现 `received 128 sensor payloads via protocol_udp`。
- fan-out 上行/下行恢复：

```text
uplink=155
downlink=15
blocked=0
```

- 停止后四个 UDP 端口均释放。

结论：

- 基础重启恢复通过。
- 断链恢复仍需进一步设计“运行中杀 fan-out / 板端断电 / 网线拔插 / bridge 是否自动重连”的专项测试。

### 17.7 DVL Telnet execute 复验

dry-run：

- 符号解析正确：
  - `DVL_Prase_Data=0x536da0`
  - `Current_State=0x536b20`
  - `UI_WIFI_Instruction=0x536ac0`
  - `Instruction_To_FMCU=0x536d20`
  - `Sys_Abnorm_Inf_Judgement=0x5171ac`
  - `Seafloor_Grounding_Arbitration=0x33d301`
- 基线正常：
  - `Sys_Abnorm=0`
  - `UI_WIFI para1=500`
  - `Instruction_To_FMCU motor1=0`

execute：

```bash
/usr/bin/python3 scripts/vxworks_dvl_runtime_probe.py \
  --execute \
  --case soft \
  --suspend-runtime-tasks
```

结果：

- 脚本完成全流程，没有挂死。
- 成功 suspend/resume：
  - `MainCtrlTask`
  - `UartRecvFormDVLTask`
  - `UnpackDVLDataTask`
  - `NetRecvTask`
  - `UnpackNetDataTask`
- cleanup 后 dry-run 基线恢复正常。

但功能判定未通过：

```text
[AFTER SOFT]
Sys_Abnorm=0x00000000
DVL: BD_Check=0.000 BD_Height=0.000
Current_State: mode=238 ...
UI_WIFI: ctrl=238 para1=0
```

结论：

- 自动化 execute 的“连接、执行、恢复任务、cleanup”稳定性比之前前进了一步。
- 但 DVL 注入值没有保持，疑似仍被运行时覆盖或写入路径不对。
- soft case 未触发 Bit11。
- DVL 自动化脚本从“流程不稳定”推进为“流程稳定但注入保持/仲裁触发未闭合”。

### 17.8 BUG-5/BUG-6 `Remote_Assignment()` 覆盖复验

dry-run 基线：

```text
UI_WIFI shadow: ctrl=1 depth_para1=500 motor1=0 lh_angle=0 rh_angle=0
Instruction_To_FMCU ... +0x18=0 ... +0x20=2048 +0x22=2048
TOBUF ... Motor1=00000
```

execute：

```bash
/usr/bin/python3 scripts/vxworks_bug4_runtime_probe.py \
  --execute \
  --probe shadow-override
```

结果：

```text
[AFTER SHADOW-OVERRIDE]
UI_WIFI shadow: ctrl=1 depth_para1=500 motor1=0 lh_angle=-20 rh_angle=-20
Instruction_To_FMCU ... +0x18=0 ... +0x20=2275 +0x22=1821
```

结论：

- `Remote_Assignment(&Instruction_To_FMCU)` 后，舵面值能进入 `Instruction_To_FMCU`。
- `motor1` 仍为 0，没有保留写入的 300。
- BUG-5/BUG-6 自救主推被覆盖/未透传问题仍未闭合。
- cleanup 后基线恢复正常。

### 17.9 当前状态更新

本轮新增完成：

- 非零 `/cmd_vel -> PC104` bench 短测通过。
- fan-out 非零放行开关与 bench profile 已实现。
- sudo Zenoh 本机回环通过。
- sudo Zenoh `rt/pc/cmd_raw -> ROS2 CommandArbiter` 仲裁链路通过。
- PC raw 超时 degraded 包清零保护参数问题已发现并修复。
- 300 秒 ROS2 non-passive 零执行器 soak 通过。
- 基础重启恢复通过。
- DVL Telnet execute 已稳定完成流程，但功能触发未闭合。
- BUG-5/BUG-6 复验确认仍未闭合。

仍保留：

- BUG-4 Bit9 运行期设置/保持。
- BUG-5/BUG-6 自救主推进入 `Instruction_To_FMCU` 与最终 `to_MCU_buf`。
- DVL `BD_Check/BD_Height` 注入保持与 Bit11/12/13 触发。
- 真正断链恢复专项：运行中杀 fan-out、杀 ROS2 bridge、PC104 断电/重连、网线拔插。
- PySide6 GUI 手动并发 SOP。
- `scripts/start_lin_sim.sh both` 与 ROS2 默认 stack 的完整长窗口仿真回归。
