# Manual Protocol Injector 开发计划

## 1. 目标与范围 (Summary)
开发一个基于 PySide6 的手动协议注入工具（Manual Protocol Injector），用于 AUV (Jetson -> AMD) 的远程联调。该工具作为独立的单点脚本放置在 `tools/` 目录下，不依赖复杂的 ROS 节点或算法，仅负责构造和发送 72 字节的大端序 `$CKTH` 协议报文。为了适应容器环境，将支持 `--headless` 命令行模式以供无 GUI 测试。

## 2. 现状分析 (Current State Analysis)
- 项目中 `common/protocol.py` 已经实现了完善的 `$CKTH` 报文构造函数 `build_downlink_packet` 和 `build_downlink_packet_from_payload`，包含了协议头部、校验和、限幅等逻辑。
- AMD 的通信协议文档（如《VxWorks最新协议.md》）定义了控制模式、工作指令和调参字段的明确含义。
- 容器内默认没有显示服务器（X11/Wayland），直接启动 GUI 会抛出错误，因此需要提供无头模式（headless）来进行初步的功能验证。

## 3. 具体修改方案 (Proposed Changes)

**新建文件**：`tools/manual_protocol_injector.py`

### 3.1 核心逻辑与模块设计
- **参数解析**：使用 `argparse` 提供 `--headless`, `--ip`, `--port` 等参数。
- **协议复用**：直接引用 `sys.path` 导入 `common.protocol.build_downlink_packet` 和常用常量（`KEY_THRUST`, `KEY_LEFT` 等）。
- **UDP 通信**：使用标准的 Python `socket` 库（`SOCK_DGRAM`）进行报文发送。

### 3.2 无头模式 (Headless Mode)
- 命令行提供选项如 `--headless`, `--continuous` 等。
- 在 Headless 模式下，不导入任何 PySide6 组件，直接构造一个安全默认报文（或根据传入参数），并发送到目标 IP/端口。如果在连续模式下，使用 `time.sleep(0.5)` 进行 2Hz 循环发送。

### 3.3 GUI 界面设计 (PySide6)
- **网络设置区**：
  - 目标 IP（默认 192.168.0.101，对应 mock AMD 默认接收）
  - 目标端口（默认 52364）
- **核心控制区**：
  - Ctrl_Mode (Byte 7)：下拉框（00:默认, 01:遥控, 02:自主定点, 03:自主定向, 04:回航），默认 00。
  - Work_Cmd (Byte 22)：下拉框（00: 默认, 01:任务开启, 02:任务取消, 11:主推上电, 12:主推断电, 13:侧推上电, 14:侧推断电, 15:水平舵上电, 16:水平舵断电, 17:垂直舵上电, 18:垂直舵断电, 91:初始化开启），默认 00。
- **电机动力**：
  - Motor_Speed1 (主推)：`QSpinBox`，范围 -1500 ~ 1500，默认 0。由于底层需要 `thrust` 百分比，将换算为 `Motor_Speed1 / 15.0`。
  - Motor_Speed2 (侧推)：`QSpinBox`，范围 -4000 ~ 4000，默认 0。直接作为 `side_motor_rpm` 参数传入。
- **舵机角度**：
  - 左、右、上、下 四个 `QDoubleSpinBox`，范围 -30 ~ 30，步长 0.1，默认 0。
- **保护参数**：
  - 深度保护：`QSpinBox`（最小值 0，最大值 50m 等），传给 `depth_protect_params`。
  - 离底保护：`QSpinBox`（最小值 0，最大值 5m 等），传给 `bottom_protect_params`。
- **调参区**：
  - 12 个长整型参数输入框（Para1-12）。Para1-4 范围为 int32，Para5-12 为 int16。默认全部为 0。
- **动作执行区**：
  - 发送单次包按钮。
  - 连续发送 (2Hz) 复选框，关联 `QTimer`。附带状态指示灯（使用 `QLabel` 变色）。
  - 🔴 紧急停止：巨大红色按钮。点击时将主侧推设为0、舵角设为0、Work_Cmd 设为 02 (任务取消)，并立刻发送一次报文。
- **原始监测区**：
  - `QTextEdit`（只读）显示最近一次发送的 Hex 字节流。
  - `QLabel` 显示计算得到的校验和（即报文倒数第 3 字节）。

## 4. 安全性与约束 (Safety & Constraints)
- UI 输入组件本身具备限幅功能，无法输入越界数值。
- `build_downlink_packet` 内部自带 clamping 和精度转换功能。
- “紧急停止”按钮强制复位关键参数并立即发送，忽略当前的连续发送节拍。

## 5. 验证步骤 (Verification Steps)
1. 在环境中执行 `pip install PySide6`。
2. 启动终端 A：拉起 Mock AMD 服务器（`python3 sim_holoocean/interfaces/mock_amd_server.py`），监听 UDP 52364 端口。
3. 启动终端 B：执行 `python3 tools/manual_protocol_injector.py --headless`。
4. 验证终端 A 的 Mock AMD 服务器正确接收到并解析了 `$CKTH` 报文。
