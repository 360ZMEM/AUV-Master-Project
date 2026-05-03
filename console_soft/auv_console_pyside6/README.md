# AUV Console - Python/PySide6 版本

这是 AUV（自主水下航行器）操控台应用程序的 Python 实现，使用 PySide6 (Qt for Python) 从原始 C# Windows Forms 应用转换而来。

## 功能特性

- **三重通信模式**：
  - WiFi UDP（默认）：通过 192.168.0.11:21 与 AUV 通信
  - 无线电串口：备用通信链路
  - 北斗卫星：长距离卫星通信
- **可选 Zenoh side channel**：
   - 发布 `rt/pc/cmd_raw`，把原始 72B `$CKTH` 同步送入 Linux bridge 仲裁器
   - 订阅 `rt/auv/telemetry`，显示仲裁状态、拒绝原因和链路 freshness
   - 主窗口新增“请求自主”“手动接管”和拒绝反馈区，并把状态变化写入消息页

- **实时遥测显示**：
  - 45+ 数据字段实时更新
  - GPS 坐标、深度、航向等
  - 电池状态、电机转速、舵角

- **GPS 地图可视化**：
  - 实时轨迹跟踪（GPS 和推算航位）
  - 航点规划与显示
  - 缩放（0.001x - 12x）和平移
  - 距离测量工具

- **设备控制**：
  - 30+ 设备电源控制按钮
  - 2 个电机速度控制通道
  - 4 个舵角控制通道
  - 12 个可调参数

- **航点管理**：
  - XML 格式航点导入/导出
  - 表格式航点编辑
  - 地图上点击选点

## 安装依赖

```bash
pip install -r requirements.txt
```

如果只使用传统 UDP/串口链路，可保持 side channel 配置为关闭状态。

## 配置

应用程序需要两个配置文件（位于 `config/` 目录）：

### port_set.txt（6 行）
```
COM3              # 无线电串口
COM4              # 北斗串口
192.168.0.11      # 操控台 IP
21                # 操控台端口
192.168.0.101     # AUV IP
52364             # AUV 端口
```

### param.txt（11 行）
```
2                 # 目标地址 (1-3)
2                 # 工作模式 (0=仅发送, 1=遥控, 2=定点, 3=定向, 4=回航)
500               # 超深保护参数1 (m)
29                # 超深保护参数2 (m)
300               # 离底保护参数1 (m)
200               # 离底保护参数2 (m)
10                # 预设时间 (×0.1 分钟)
0                 # 备用参数1
0                 # 备用参数2
0                 # 回航经度 (×1000000)
0                 # 回航纬度 (×1000000)
```

### zenoh_side_channel.ini（可选）

```ini
[zenoh_side_channel]
enabled = false
pc_cmd_raw_key = rt/pc/cmd_raw
telemetry_key = rt/auv/telemetry
viz_internal_key = rt/auv/viz/internal
publish_cmd_raw = true
subscribe_bridge_telemetry = true
subscribe_viz_internal = false
session_json = {}
```

说明：

- `enabled=false` 时，上位机仍完全按原 UDP/串口主链工作。
- `enabled=true` 时，WiFi 模式发送的 72B `$CKTH` 会额外发布到 `rt/pc/cmd_raw`。
- 主窗口会额外显示 `控制归属`、`自主状态`、`拒绝原因`、`链路时延`、`请求保持`、`拒绝反馈`。

## 运行

```bash
python main.py
```

当前若系统 Python 缺少 `PySide6`，GUI 不能直接启动，但这不影响 Linux bridge 侧的 headless side-channel 联调。

## 使用说明

### 主窗口

1. **通信模式选择**：
   - 点击 "WiFi"、"无线电" 或 "北斗" 按钮切换通信模式
   - 默认使用 WiFi 模式

2. **任务控制**：
   - "任务开启" (0x01)：开始任务
   - "任务取消" (0x02)：取消任务
   - "清除故障" (0x91)：清除系统故障
   - "初始化" (0x92)：初始化系统

3. **仲裁控制**：
   - 仅在“在线模式 + WiFi + Zenoh side channel 激活”时可用
   - "请求自主"：持续把发送包的控制模式字节保持为 `0xEE`，让 Linux bridge 持续收到自主接管请求
   - "手动接管"：立即发送一次 `遥控 + 任务取消` 覆盖包，桥侧会锁回遥控
   - "消息" 标签页会记录 bridge 仲裁状态变化与拒绝原因，便于联调复盘

4. **首选项配置**：
   - 切换到"任务配置"标签页
   - 设置目标地址、工作模式
   - 设置深度和离底保护参数
   - 点击"确认首选项"保存

4. **航点规划**：
   - 切换到"航点规划"标签页
   - 点击"导入航点文件"加载 XML 航点
   - 或在地图上点击添加航点
   - 点击"导出航点文件"保存

5. **地图操作**：
   - 鼠标滚轮：缩放
   - 右键拖动：测量距离
   - 实时显示 AUV 位置和轨迹

### 扩展控制窗口

点击"扩展控制..."按钮打开扩展控制面板：

1. **设备电源控制**：
   - 主推、侧推、水平舵、垂直舵上电/断电
   - DVL、罗经上电/断电
   - 应急压载上电/断电

2. **电机转速控制**：
   - 电机1：-1500 到 1500 RPM
   - 电机2：-4000 到 4000 RPM

3. **舵角控制**：
   - 左/右水平舵：±30°
   - 上/下垂直舵：±30°

### 端口设置

点击"端口设置..."按钮打开配置对话框：

1. 选择串口（无线电、北斗）
2. 配置网络参数（IP 地址和端口）
3. 点击"保存配置"
4. **重启应用程序**使更改生效

## 协议说明

### 发送数据包（72 字节）
```
字节 0-4:   帧头 0x24 0x43 0x4B 0x54 0x48 ($CKTH)
字节 5:     帧序号
字节 6:     目标地址
字节 7:     工作模式
字节 8-21:  保护参数和备用参数
字节 22:    工作指令
字节 23-68: 电机转速、舵角、12 个参数
字节 69:    校验和（字节 0-68 之和）
字节 70-71: 帧尾 0xFF 0xFF
```

### 接收数据包（145 字节）
```
字节 0-4:   帧头 0x24 0x41 0x55 0x56 0x91 ($AUV▒)
字节 5-141: 遥测数据
字节 142:   校验和（字节 0-141 之和）
字节 143-144: 帧尾 0xFF 0xFF
```

### 北斗数据包（34 字节）
- 压缩格式，仅包含关键参数
- 使用 CCTXA 协议编码为 ASCII 十六进制
- XOR 校验和

## 项目结构

```
auv_console_python/
├── main.py                     # 应用程序入口
├── requirements.txt            # Python 依赖
├── README.md                   # 本文件
│
├── packet_viewer.py            # 【核心工具】报文协议可视化查看器
├── text_replay_sender.py       # 【核心工具】文本报文回放发送器
├── pcap_replay_sender.py       # 【核心工具】PCAP 抓包回放发送器
├── config_loader.py            # 【核心工具】统一配置加载器
├── set_data_file.py            # 【核心工具】快速数据文件切换工具
├── migrate_to_unified_config.py # 配置迁移工具
│
├── config/                     # 配置文件目录
│   ├── port_set.txt           # 串口和网络配置
│   ├── param.txt              # 任务参数
│   └── tools_config.ini       # 统一工具配置（数据文件路径、网络配置）
│
├── docs/                       # 📚 文档目录
│   ├── PROTOCOL_MAPPING.md           # ⭐ 协议映射详解（明文↔二进制）
│   ├── text_log_format_analysis.md   # ⭐ 文本日志格式分析
│   ├── CONFIG_GUIDE.md               # 配置系统使用指南
│   ├── REPLAY_MODES_GUIDE.md         # 回放模式说明
│   ├── TEXT_TOOLS_GUIDE.md           # 文本工具使用指南
│   ├── PCAP_REPLAY_SENDER.md         # PCAP 回放工具说明
│   ├── USER_MANUAL.md                # 用户手册
│   ├── QUICKSTART.md                 # 快速开始
│   └── ...                            # 其他技术文档
│
├── tests/                      # 🧪 测试和调试脚本
│   ├── test_complete.py              # 完整功能测试
│   ├── test_text_tools.py            # 文本工具测试
│   ├── test_replay_sender.py         # 回放发送器测试
│   ├── test_protocol.py              # 协议测试
│   └── debug_parse.py                # 解析调试工具
│
└── src/                        # 源代码目录
    ├── data_structures.py      # 数据结构定义
    ├── protocol/               # 通信协议
    │   ├── packet_builder.py   # 数据包构建/解析
    │   ├── checksums.py        # 校验和计算
    │   ├── beidou_protocol.py  # 北斗协议
    │   └── constants.py        # 协议常量
    ├── communication/          # 通信层
    │   ├── udp_comm.py         # UDP 通信
    │   ├── serial_comm.py      # 串口通信
    │   └── comm_manager.py     # 通信管理器
    ├── ui/                     # 用户界面
    │   ├── main_window.py      # 主窗口
    │   ├── extended_control.py # 扩展控制窗口
    │   ├── settings_dialog.py  # 设置对话框
    │   └── map_widget.py       # 地图组件
    ├── threads/                # 后台线程
    │   └── udp_receiver_thread.py  # UDP 接收线程
    └── utils/                  # 工具类
        ├── config_manager.py   # 配置文件管理
        └── xml_handler.py      # XML 航点处理
```

## 快速开始

### 1. 报文协议学习与可视化

```bash
# 查看当前配置的数据文件
python set_data_file.py --list

# 切换到其他数据文件（可选）
python set_data_file.py --file 20020101103632.txt

# 启动报文可视化工具
python packet_viewer.py
```

使用 **packet_viewer.py** 可以：
- 逐帧查看 CKTH（发送）和 AUV（接收）报文
- 逐字节解析协议字段含义
- 通过方向键快速浏览报文
- 查看详细注释（基于 `docs/PROTOCOL_MAPPING.md`）

### 2. 报文回放测试

```bash
# 从文本日志回放 AUV 报文
python text_replay_sender.py

# 或从 PCAP 抓包文件回放
python pcap_replay_sender.py
```

回放工具特点：
- 支持本地模拟模式（127.0.0.1）
- 兼容 C# 和 Python 上位机
- 可配置回放速度和循环模式
- 详细的数据包发送统计

### 3. 运行主应用程序

```bash
python main.py
```

## 测试

```bash
# 从根目录运行测试脚本
python tests/test_complete.py

# 测试文本工具
python tests/test_text_tools.py

# 测试回放发送器
python tests/test_replay_sender.py

# 调试解析问题
python tests/debug_parse.py
```

**重要提示**：所有测试脚本位于 `tests/` 目录，但可以从根目录直接运行。

## 故障排除

### 无法连接到 AUV

1. 检查 IP 地址和端口配置（port_set.txt）
2. 确认 AUV 已开机且网络正常
3. 尝试 ping AUV IP 地址：`ping 192.168.0.101`
4. 检查防火墙设置

### 串口无法打开

1. 确认串口号正确（COM1、COM2 等）
2. 检查串口是否被其他程序占用
3. 在 Windows 设备管理器中查看可用串口

### 地图不显示 GPS 轨迹

1. 等待接收到第一个 GPS 数据
2. 检查 AUV 是否已获取 GPS 定位
3. 查看控制台输出的调试信息

## 技术栈

- **Python 3.10+**
- **PySide6 6.6.0** (Qt for Python 官方版本)
- **pyserial 3.5** (串口通信)
- **pytest 7.4.3** (测试框架)

## 从 C# 转换

本应用程序从 C# Windows Forms 完整转换而来：

- **原始代码**: `Console/Form1.cs` (2,299 行)
- **转换方法**: 逐模块翻译，保持相同功能
- **主要改进**: 模块化设计、更清晰的架构

## 许可证

与原始 C# 应用程序相同。

## 联系方式

如有问题或建议，请联系开发团队。
