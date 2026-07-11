# PySide6 上位机 PC104 并发调试计划与 SOP

日期：2026-07-11  
目标：在 PC104 实物板、ROS2 `protocol_udp` bridge、PySide6 上位机同时参与调试时，明确哪些动作可以由脚本自动模拟，哪些必须由用户手动点按；同时定义每一步用户侧应看到什么。

## 一、当前结论

PySide6 上位机已经可用于 PC104 直连安全烟测：

- 可加载 `console_config.pc104.yaml`。
- 可绑定 `192.168.0.11:21` 并向 `192.168.0.101:21` 发 `$CKTH`。
- 已用 PySide6 自身 `PacketBuilder + UDPCommunicator` 证明 PC104 能解析安全字段：
  - `Depth_Para1=501` 可写入 `UI_WIFI_Instruction`。
  - 再写回 `Depth_Para1=500` 可恢复。
  - 电机保持 `0`。

但在并发模式下，PySide6 不应再直接绑定本机 `21/udp`。后续应使用 fan-out profile：

- fan-out 唯一绑定本机 `192.168.0.11:21`。
- PySide6 绑定高端口，例如 `127.0.0.1:52366`。
- PySide6 下行发给 fan-out，例如 `127.0.0.1:52364`。
- fan-out 再按仲裁规则转发到 PC104 `192.168.0.101:21`。

## 二、可以自动模拟并绕过 GUI 读取的内容

这些内容可以由脚本完成，不要求用户点 GUI：

1. 配置加载验证
   - 自动操作：运行 Python 片段加载 `console_config.pc104_fanout.yaml`。
   - 验证点：UDP 端点应变为 `127.0.0.1:52366 -> 127.0.0.1:52364`。
   - 期望结果：不启动 GUI 也能确认 profile 生效。

2. 安全构包验证
   - 自动操作：调用 PySide6 的 `PacketBuilder` 构造 `$CKTH`。
   - 默认字段：
     - `obj_address=1`
     - `work_mode=1`
     - `Depth_Para1=500`
     - `Depth_Para2=29`
     - `Height_Para1=300`
     - `Height_Para2=200`
     - `Remain_Time=10`
     - 电机/舵角为 `0`
   - 期望结果：包可被 `common.protocol.parse_downlink_packet()` 正确解析。

3. fan-out 下行安全规则验证
   - 自动操作：PySide6 sender 向 fan-out 下行端口发包。
   - 期望结果：
     - fan-out 日志显示来源为 `console`。
     - 安全包被允许转发。
     - 非零电机包默认被拒绝，除非显式开启高风险开关。

4. PC104 读回验证
   - 自动操作：Telnet 读取 `UI_WIFI_Instruction` 和 `Instruction_To_FMCU`。
   - 期望结果：
     - `UI depth_para1=500`
     - `UI motor1=0`
     - `INS motor1=0`

5. ROS2 topic 读数验证
   - 自动操作：使用 sudo ROS 环境 echo。
   - 期望结果：
     - `/auv/sensors/depth` 有样本。
     - `/auv/arbiter/status` 有样本。
     - `/auv/bridge/shadow_telemetry` 有样本。

## 三、必须由用户手动操作的内容

这些内容涉及真实 GUI 状态、人员确认或潜在执行器动作，不应完全由脚本替用户点击：

1. GUI 可视状态确认
   - 用户操作：
     - 启动 PySide6。
     - 确认窗口正常显示。
     - 确认状态栏显示在线/连接类提示。
   - 期望看到：
     - 主界面无崩溃。
     - 状态栏出现“在线模式”或“已连接到 AUV”类似提示。

2. 通信模式切换
   - 用户操作：点击 `WiFi`。
   - 期望看到：
     - 通信模式切换到 WiFi。
     - 没有端口占用报错。
     - fan-out 日志继续显示上行转发。

3. 在线/离线模式切换
   - 用户操作：点击 `在线模式`。
   - 期望看到：
     - 状态栏显示在线模式。
     - UDP 接收线程保持运行。

4. 首选项确认
   - 用户操作：
     - 检查目标地址为 `1`。
     - 检查工作模式为安全 remote/send 模式。
     - 检查深度/离底保护参数为 `500/29/300/200/10`。
     - 点击 `确认首选项`。
   - 期望看到：
     - 控制台/状态栏提示参数已保存或已应用。
     - 后续包仍保持电机为 `0`。

5. Zenoh side channel
   - 用户操作：点击 `连接 Zenoh`。
   - 期望看到：
     - 若已安装 `zenoh` 并启动 router：按钮变为 `断开 Zenoh`，状态显示已连接。
     - 若缺依赖或 router 未启动：界面应提示连接失败，不影响 UDP 主链路。

6. 自主仲裁按钮
   - 用户操作：
     - 点击 `请求自主`。
     - 再点击 `手动接管`。
   - 前置条件：
     - 必须确认 fan-out 下行仲裁规则允许该类安全包。
     - 必须确认电机输出仍为 `0`。
   - 期望看到：
     - 请求自主后，界面提示已发送自主请求或显示拒绝原因。
     - 手动接管后，界面提示已发送手动接管。
     - ROS2 `/auv/arbiter/status` 中状态随之变化或给出拒绝原因。

7. 紧急切断
   - 用户操作：
     - 点击 `紧急切断 ESTOP`。
     - 确认状态进入急停。
     - 点击 `解除急停`。
   - 期望看到：
     - 急停后 GUI 状态明显变化。
     - fan-out/ROS2/Telnet 读回电机为 `0`。
     - 解除后仍保持安全参数。

8. 非零控制
   - 用户操作：暂不建议直接在 GUI 上做。
   - 前置条件：
     - 明确允许执行机构动作。
     - 明确推进器/舵机电源和急停状态。
     - 先完成 ROS2 小幅非零 `/cmd_vel` 受控短测。

## 四、用户侧并发调试 SOP

### SOP-A：只看状态，不允许 PySide6 下行

适合首次并发观察。

1. 启动 fan-out。
2. 启动 ROS2 passive 或 non-passive 零执行器 bridge。
3. 启动 PySide6 fan-out profile。
4. 用户点击：
   - `在线模式`
   - `WiFi`
5. 期望看到：
   - PySide6 不报端口占用。
   - ROS2 topic 正常有数据。
   - fan-out 日志显示 PC104 上行被同时转发给 ROS2 和 PySide6。

### SOP-B：允许 PySide6 发送安全参数包

适合验证 GUI 下行能力。

1. fan-out 开启 console 安全下行。
2. PySide6 profile 使用 `obj_address=1` 和安全参数。
3. 用户点击：
   - `在线模式`
   - `WiFi`
   - `确认首选项`
4. 期望看到：
   - fan-out 日志显示 `console` 来源 `$CKTH` 被允许。
   - Telnet 读回：
     - `UI depth_para1=500`
     - `UI depth_para2=29`
     - `UI height_para1=300`
     - `UI height_para2=200`
     - `UI remain_time=10`
     - `UI motor1=0`

### SOP-C：Zenoh side channel 验证

适合验证 PySide6 与 ROS2 仲裁 side channel。

1. 确认已安装 Python `zenoh`。
2. 确认 Zenoh router 已启动。
3. 用户点击 `连接 Zenoh`。
4. 期望看到：
   - 成功：按钮变 `断开 Zenoh`，状态显示已连接。
   - 失败：显示失败原因，UDP 主链路不应中断。

### SOP-D：请求自主/手动接管

适合验证仲裁 UI，不适合带执行器动作。

1. 确保 ROS2 bridge 已运行。
2. 确保 fan-out 只允许零执行器包。
3. 用户点击 `请求自主`。
4. 观察 `/auv/arbiter/status`。
5. 用户点击 `手动接管`。
6. 期望看到：
   - 自主请求被接受或给出明确拒绝原因。
   - 手动接管后状态回到 remote/locked。
   - Telnet 读回电机仍为 `0`。

## 五、暂停条件

出现以下情况应立即暂停：

- `UI motor1` 或 `INS motor1` 非预期非零。
- `Depth_Para1` 被写成 `0`。
- `21/udp` 被非 fan-out 进程占用。
- fan-out 日志显示未知来源持续下行。
- PySide6 与 ROS2 同时出现端口绑定失败。
- 用户未确认执行机构安全状态时出现非零控制请求。
