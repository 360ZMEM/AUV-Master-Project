# PC104 空板实物全链路调试定界报告

日期：2026-07-11  
对象：纯 PC104/VxWorks 实物板，无外接 DVL、IMU、深度计、磁传感器、BMS、推进器负载传感器等完整实物传感链  
拓扑：调试电脑 `192.168.0.11/24` 直连 PC104 `192.168.0.101`  
结论状态：Telnet、UDP、上位机直连、ROS2 被动上行链路已形成可复现实物证据；ROS2 非 passive 下行仍需先补安全默认参数后再短测。

## 一、总体结论

本轮调试已经把“电脑直连 PC104 空板”的核心通信链路打通，并完成了多项安全状态机的 Telnet HIL 证据采集。当前可以确认：

- PC104 与电脑之间的 Telnet、UdpLogger、`$AUV` 上行、`$CKTH` 下行均已通。
- 上位机 PySide6 的 PC104 直连 profile 已可绑定 `192.168.0.11:21` 并向 `192.168.0.101:21` 发送协议包。
- 用上位机自身 `PacketBuilder + UDPCommunicator` 发送的零电机 `$CKTH` 包，已被 PC104 的 WIFI 接收、校验和解包路径写入 `UI_WIFI_Instruction`。
- ROS2 `protocol_udp` passive 模式已经可以从真实 PC104 `$AUV` 上行生成 ROS2 topic。
- 纯 Telnet 注入足够验证“内存变量、状态机分支、部分协议字段和告警位”，但不足以替代真实传感器验证声学锁底、惯导噪声、BMS/漏水、电机负载和长期闭环稳定性。

当前不建议直接运行 ROS2 `protocol_udp` 非 passive idle 烟测。原因是默认 remote payload 虽然电机/舵角为零，但深度/离底保护参数也是 `(0, 0)`，会把 PC104 影子保护参数临时清零。下一步应先给 ROS2 PC104 profile 或 arbiter 默认 remote payload 补安全保护参数，再做非 passive 短时实物烟测。

## 二、最终已经调通的内容

### 2.1 基础网络与 Telnet

- 调试电脑网卡：`enp3s0 = 192.168.0.11/24`。
- PC104 地址：`192.168.0.101`。
- `ping 192.168.0.101` 成功，3/3 回复，RTT 约 `0.15 ms`。
- Telnet `192.168.0.101:23` 成功，账号链路可进入 VxWorks shell。
- 运行期符号必须用 `lkup "Symbol"` 获取，不应复用旧绝对地址。

已经确认的关键运行期符号包括：

- `Current_State = 0x536b20`
- `UI_WIFI_Instruction = 0x536ac0`
- `Instruction_To_FMCU = 0x536d20`
- `DVL_Prase_Data = 0x536da0`
- `Sys_Abnorm_Inf_Judgement = 0x5171ac`
- `Seafloor_Grounding_Arbitration = 0x33d301`
- `Vehicle_No = 1`

### 2.2 UdpLogger 回传链路

- 电脑监听 `52367/udp` 可收到 PC104 UdpLogger 日志。
- 已观测到 `Main_Ctrl_Task_Count_No`、`NetSendTask start::::`、`EmergencyTask start::::`、`WD_Depth`、`WD_Check` 等日志。
- 结论：PC104 到电脑的辅助 UDP 日志回传链路可用。

### 2.3 `$AUV` 上行链路

- 在 sudo 授权后，电脑可绑定 `21/udp` 接收 PC104 `$AUV` 上行。
- 源地址为 `192.168.0.101:21`。
- 已收到合法 `$AUV` 帧：帧头、帧尾、checksum、地址、控制模式、电机字段均可解析。
- 结论：真实 PC104 上行使用 `21/udp`，不是 mock profile 的 `52364/52365`。

### 2.4 `$CKTH` 零推力下行链路

- 从电脑向 `192.168.0.101:21` 发送零推力 `$CKTH` 包成功。
- PC104 上行随后反映控制模式变化，Telnet 也能在 `UI_WIFI_Instruction` 中看到零电机影子状态。
- 结论：电脑到 PC104 的 `$CKTH` 下行通路可用，且 PC104 可以解析并更新内部 UI shadow。

### 2.5 上位机 PySide6 直连链路

已经新增独立 PC104 profile：

- `console_soft/auv_console_pyside6/console_config.pc104.yaml`
- 本地绑定：`192.168.0.11:21`
- 远端 PC104：`192.168.0.101:21`
- 目标板号：`packet.obj_address: 1`
- 安全工作模式：`packet.work_mode: 1`
- 安全保护参数：`depth_proprotect_param1: 500`、`depth_proprotect_param2: 29`、`bottom_proprotect_param1: 300`、`bottom_proprotect_param2: 200`

同时已经修改上位机加载逻辑：

- `main.py` 支持 `--config console_config.pc104.yaml`。
- `main_window.py` 支持从 YAML 覆盖 legacy `port_set.txt` 的 UDP 端点。
- `main_window.py` 支持从 YAML 覆盖 legacy `param.txt` 的目标板号、工作模式和保护参数。
- 默认不带 `--config` 时仍走原始 `console_config.yaml` 路径，尽量不影响 mock/default 流程。

关键实物证据：

- 先用 `obj_address=2` 发送 `Depth_Para1=501`，PC104 不更新。
- Telnet 读回 `Vehicle_No=1`，确认原因是 VxWorks `Unpack_Data_From_UI12_WIFI()` 只接受 `temp_buf[6] == Vehicle_No` 的包。
- 改用 `obj_address=1` 后，发送五帧零电机 `Depth_Para1=501` 包。
- Telnet 读回：
  - `UI ctrl=1`
  - `UI depth_para1=501`
  - `UI motor1=0`
  - `INS motor1=0`
- 随后发送五帧零电机 `Depth_Para1=500` 恢复包。
- Telnet 读回：
  - `UI depth_para1=500`
  - `UI motor1=0`
  - `INS motor1=0`

结论：上位机协议构包、UDP 发送、PC104 WIFI 接收、checksum 校验、解包写入 `UI_WIFI_Instruction` 这条链路已经闭合。

### 2.6 ROS2 `protocol_udp` passive 上行桥接

已经新增 PC104 ROS2 profile：

- `brain_linux/config/params.protocol_udp_pc104.yaml`
- `backend: protocol_udp`
- `passive_mode: true`
- 本地绑定：`0.0.0.0:21`
- 远端：`192.168.0.101:21`
- `protocol_udp.obj_address: 1`

实测结果：

- ROS2 bridge 可持续收到真实 PC104 `$AUV` 上行。
- bridge 日志显示 `[bridge] received N sensor payloads via protocol_udp` 连续增长。
- ROS graph 中可见：
  - `/auv/sensors/depth`
  - `/auv/sensors/dvl`
  - `/auv/sensors/imu`
  - `/auv/sensors/altitude`
  - `/auv/bridge/shadow_telemetry`
  - `/auv/arbiter/status`
  - `/cmd_vel`
- 使用 sudo ROS CLI 可 echo 到样本：
  - `/auv/sensors/depth`: `data: 0.0`
  - `/auv/sensors/dvl`: 速度/角速度均为 `0.0`
  - `/auv/bridge/shadow_telemetry`: `active_arbiter=REMOTE`、`auto_state=LOCKED`
  - `/auv/arbiter/status`: `effective_control_mode_byte=1`、`telemetry_freshness_ms` 为新鲜值

结论：真实 PC104 `$AUV` 到 ROS2 topic 的 passive 上行桥接已经调通。

### 2.7 Telnet HIL 状态机验证

BUG-3：超深滑动窗口计数

- 注入超深状态后，`Depth_Exceed_FromUI12_Depth_Para1` 可上升到 `9`。
- 恢复安全深度后，计数可衰减回 `0`。
- 结论：BUG-3 计数递增/递减逻辑有效。

BUG-4：超深应急上浮命令路径

- 触发后 `DepthExceed=19`。
- UI shadow：`ctrl=1`、`depth_para1=5`、`motor1=300`、`lh_angle=-20`、`rh_angle=-20`。
- `Instruction_To_FMCU` 中看到 `motor1=300`、左右水平舵位置约 `2275/1821`。
- 结论：当前烧录固件中，BUG-4 应急上浮执行命令路径闭合。
- 注意：`Sys_Abnorm` 的 Bit9 可观测性未闭合。

BUG-5：DVL 离底软/硬限

- 软限：注入 `BD_Check=2.0`、`BD_Height=2.5m` 后，`SYS=0x00000800`，Bit11 有效。
- 硬限：注入 `BD_Check=2.0`、`BD_Height=1.2m` 后，`SYS=0x00001800`，Bit12 有效。
- 注意：硬限自救主推输出没有保留到 `Instruction_To_FMCU`，读回 `motor=0`。

BUG-6：DVL 丢底

- 注入 `Current_Mode=0xEE`、`BD_Check=0.0` 后，多次调用仲裁。
- 读回 `SYS=0x00002000`，Bit13 有效。
- UI 控制模式降级到 `0x01` 有效。
- 注意：丢底自救主推输出没有保留到 `Instruction_To_FMCU`，读回 `motor=0`。

## 三、没有完全调通或仍未闭合的内容

### 3.1 BUG-4 Bit9 告警位

- 已验证 `Sys_Abnorm_Inf_Judgement` 手动置 `0x00000200` 后，`$AUV` 上行能正确带出该字段。
- 但 BUG-4 运行触发期间，`Sys_Abnorm` 仍为 `0x00000000`。
- 结论：上行打包和解析没有问题，缺口在运行期设置/保持 Bit9 的逻辑。

### 3.2 DVL 硬限/丢底自救主推输出

- BUG-5 硬限和 BUG-6 丢底的告警位、模式降级均已验证。
- 但自救主推输出未保留到 `Instruction_To_FMCU`。
- 当前怀疑原因：分支内先写 `Instruction_To_FMCU.McuFD_Motor1_Set_Speed`，随后又调用 `Remote_Assignment(&Instruction_To_FMCU)`，该函数可能从 `UI_WIFI_Instruction` 覆盖了主推字段；硬限/丢底分支没有同步写 `UI_WIFI_Instruction.FromUI12_Motor_Speed1`。
- 结论：需要源码修复、重新编译烧录后再验。

### 3.3 DVL 自动化脚本仍不够可靠

- `scripts/vxworks_dvl_runtime_probe.py` 可以解析符号、执行 dry-run。
- 但自动 execute 全流程未稳定复现手工 raw Telnet 写浮点字段的证据。
- 手工 Telnet raw 写 `IEEE754` 仍是当前权威证据。
- 结论：脚本需要继续加固，不能把它作为最终无人值守验收工具。

### 3.4 ROS2 非 passive 下行尚未运行

- 没有直接运行 ROS2 `protocol_udp` 非 passive idle 烟测。
- 原因：静态检查发现默认 remote payload 的执行器字段为零，但保护参数也是 `(0, 0)`，会临时清空 PC104 影子保护参数。
- 结论：理论可行，但必须先补安全默认保护参数，再做短时实物烟测。

### 3.5 ROS2 bridge 与 PySide6 上位机不能同时占用 `21/udp`

- ROS2 PC104 passive profile 和 PySide6 PC104 profile 都需要绑定本地 `21/udp`。
- 当前 socket 设置下二者不能同时运行。
- 结论：必须分阶段测试，或者后续设计专门的端口复用/转发策略。

## 四、必须补充真实传感器后才能验证的内容

纯 PC104 空板加 Telnet 注入可以验证内存分支和协议路径，但不能替代以下实物传感链：

### 4.1 DVL 实际锁底/丢底行为

Telnet 能写 `BD_Check` 和 `BD_Height`，但不能验证：

- 真实 DVL 声学锁底质量。
- 水池/海试中的高度跳变、丢底恢复、异常噪声。
- DVL 串口接收任务对真实帧的解析稳定性。
- DVL 速度、底跟踪质量与控制器之间的动态耦合。

### 4.2 IMU/深度计/磁传感器真实数据质量

Telnet 能伪造某些状态变量，但不能验证：

- IMU 加速度/角速度噪声、偏置、坐标轴方向。
- 深度计随水压变化的真实响应。
- 磁传感器安装误差、硬软铁干扰、外参一致性。
- EKF/DR 在真实传感器噪声下的漂移和收敛。

### 4.3 BMS、漏水、电压、急停硬件链路

空板不能完整验证：

- 真实电池电压、欠压边界。
- 漏水传感器输入。
- 硬件急停/继电器/电源切断链路。
- AutonomyGuard 对真实故障输入的响应。

### 4.4 推进器、舵机和负载闭环

Telnet 只能看到 `Instruction_To_FMCU` 或 `$MCUFD` 字段，不能验证：

- 推进器实际转速。
- 舵机实际角度与堵转。
- 负载、电流、温升。
- 控制命令到执行机构的物理闭环。

### 4.5 电缆巡检传感链

空板不能验证：

- 电缆探测传感器实际信号。
- SNR、埋深、横向偏移、置信度。
- 与 DL/T 巡检规范相关的真实巡检指标。
- Foxglove/ROS2 中电缆巡检语义字段的实测闭环。

## 五、由于缺少依赖或环境限制形成的 TODO 与临时方案

### 5.1 `21/udp` 低端口权限

- 当前 Linux 默认 `net.ipv4.ip_unprivileged_port_start = 1024`。
- 普通用户不能绑定 `21/udp`，因此实测使用 sudo。
- TODO：
  - 给指定 Python/ROS2 可执行文件设置 capability，或
  - 临时调整低端口策略，或
  - 通过受控端口转发把高端口映射到 `21/udp`。

### 5.2 sudo 运行导致 ROS2 DDS 用户上下文不一致

- sudo 启动 bridge 后，普通用户 `ros2 topic echo` 可看到 publisher，但不一定能收到样本。
- 使用同一 sudo ROS 环境 echo 可以收到样本。
- TODO：
  - 统一 ROS2 运行用户。
  - 固化 DDS/RMW 环境变量。
  - 尽量避免同一图里混用 sudo 和普通用户。

### 5.3 `timeout` 对 sudo Qt/ROS 子进程清理不彻底

- `timeout 6s sudo ... main.py` 没有完全回收 Qt 子进程。
- 实测用 `sudo -n pkill -f 'main.py --config console_config.pc104.yaml'` 手动清理。
- TODO：
  - 写专用启动/停止脚本。
  - 启动前后自动检查 `ss -lunp 'sport = :21'`。

### 5.4 DVL 自动化探针脚本仍需加固

- VxWorks shell 对浮点参数不友好：`printf("%f", ...)` 不可用，`*(float*)addr=2.5` 会表现异常。
- 当前可靠方法是写 `IEEE754` raw `unsigned int`。
- TODO：
  - 自动脚本中统一 raw 写浮点。
  - 每次写入后立刻 raw 读回确认。
  - 对任务暂停/恢复做更严谨的 finally 清理。

### 5.5 上位机/ROS2 环境依赖

- PySide6 上位机需要 `PySide6`、`pyyaml` 等依赖。
- ROS2 决策端需要 `/opt/ros/humble/setup.bash` 和系统 Python `/usr/bin/python3`。
- 项目规则要求避免 conda 环境干扰 ROS2 消息生成。
- TODO：
  - 给 PC104 实物联调补一份依赖检查脚本。
  - 在启动脚本里明确拒绝 conda Python。

## 六、给用户侧的建议

1. 每次实物联调前，先确认三件事：
   - `ping 192.168.0.101` 通。
   - `ss -lunp 'sport = :21'` 显示本地 `21/udp` 未被占用。
   - Telnet 读回 `Vehicle_No=1` 或与 profile 中 `obj_address` 一致。

2. ROS2 bridge 和 PySide6 上位机不要同时直连 `21/udp`。
   - 先跑 ROS2 passive 接收。
   - 停掉 ROS2 后再跑 PySide6 上位机。
   - 后续若要同跑，需要专门设计 UDP fan-out/代理。

3. 所有实物下行测试优先使用“可观测但不驱动执行机构”的字段。
   - 推荐 `Depth_Para1=501 -> 500` 这种短时可恢复字段。
   - 不建议直接用主推/舵角作为第一验证字段。

4. VxWorks Telnet 写浮点必须用 raw IEEE754。
   - 推荐 `*(unsigned int*)addr=0x40200000`。
   - 不要信任 `*(float*)addr=2.5` 的表面成功。

5. 对 DVL 硬限/丢底自救主推问题，建议走源码修复后重新烧录。
   - 重点检查 `Remote_Assignment(&Instruction_To_FMCU)` 对自救输出的覆盖。
   - 修复后应同时验证告警位、模式降级、`Instruction_To_FMCU` 和 `$MCUFD` 输出。

6. 补传感器时建议按优先级推进：
   - 第一优先级：深度计、DVL。
   - 第二优先级：IMU、BMS/漏水。
   - 第三优先级：磁传感器、电缆巡检传感链。
   - 最后再做推进器/舵机带负载闭环。

## 七、下一步门禁

在继续“给 ROS2 PC104 profile/arbiter 默认 remote payload 补安全保护参数，再做非 passive 实物短测”前，应先完成：

- 在 ROS2 PC104 profile 或 `CommandArbiter._default_remote_payload()` 中加入安全 bench 默认值：
  - `KEY_DEPTH_PROTECT_PARAMS: (500, 29)`
  - `KEY_BOTTOM_PROTECT_PARAMS: (300, 200)`
  - `KEY_PRESET_TIME_TENTHS_MIN: 10`
  - `KEY_OBJ_ADDRESS: 1`
  - `KEY_CONTROL_MODE_BYTE: 1`
  - 所有执行器输出保持 0。
- 编译/语法检查通过。
- 先 dry-run 或单元测试确认构包字段。
- 再做短时非 passive 实物烟测。
- 烟测后用 Telnet 读回确认：
  - `UI depth_para1=500`
  - `UI motor1=0`
  - `INS motor1=0`
  - `21/udp` 已释放。

## 八、相关文件

- 运行记录：`debug-pc104-telnet-udp.md`
- ROS2 PC104 profile：`brain_linux/config/params.protocol_udp_pc104.yaml`
- 上位机 PC104 profile：`console_soft/auv_console_pyside6/console_config.pc104.yaml`
- 上位机入口：`console_soft/auv_console_pyside6/main.py`
- 上位机主窗口配置加载：`console_soft/auv_console_pyside6/src/ui/main_window.py`
- DVL Telnet 探针：`scripts/vxworks_dvl_runtime_probe.py`
- BUG-4 Telnet 探针：`scripts/vxworks_bug4_runtime_probe.py`
