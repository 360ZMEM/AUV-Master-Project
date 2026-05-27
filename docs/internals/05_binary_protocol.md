# 二进制协议

## 协议背景

PC/Jetson 与 AMD（VxWorks PC104 嵌入式板）之间的通信采用二进制 UDP 协议。该协议分为两个方向：

- **下行帧 `$CKTH`**：PC → AUV，72 字节，携带控制指令
- **上行帧 `$AUV`**：AUV → PC，145 字节，携带传感器遥测数据

所有多字节字段均采用小端序（Little-Endian），与 VxWorks 端保持一致。

---

## 下行帧 $CKTH（72字节，PC → AUV）

### 帧结构

| 偏移 | 长度 | 字段 | 说明 |
|------|------|------|------|
| 0 | 2B | 帧头 | 固定标识 `$CKTH` 前两字节 |
| 2 | 1B | 帧序号 | 循环递增 0~255 |
| 3 | 1B | 工作模式 | control_mode_byte |
| 4 | 数B | 控制参数 | work_instruction、fin_deg、thrust_percent 等 |
| ... | 12×4B | 可调参数 | 12 个浮点型可调参数（PID增益等） |
| 69 | 1B | 校验和 | 字节和低 8 位 |
| 70 | 2B | 帧尾 | 固定结束标识 |

### 关键字段

| 字段 | 类型 | 取值 | 含义 |
|------|------|------|------|
| `control_mode_byte` | uint8 | `0x01` | 手动遥控模式 |
| | | `0xEE` | 自主控制模式 |
| `work_instruction` | uint8 | 见任务枚举 | 当前任务指令 |
| `fin_deg` | int8/uint8 | -30~+30 | 舵角（度） |
| `thrust_percent` | int16/uint16 | -100~+100 | 推力百分比 |

---

## 上行帧 $AUV（145字节，AUV → PC）

### 帧结构

| 偏移 | 字段 | 说明 |
|------|------|------|
| 0~1 | 帧头 | 固定标识 |
| 2~... | 姿态 | roll / pitch / yaw（浮点） |
| ... | GPS | latitude / longitude |
| ... | DVL | 三轴速度 |
| ... | 深度 | 压力传感器转换深度 |
| ... | 电压 | 电池电压 |
| ... | 温度 | 舱内温度 |
| ... | 漏水 | 漏水传感器状态 |
| ... | 异常位图 | 各子系统异常标志 |
| 143~144 | 帧尾 | 固定结束标识 |

### 关键字段

- **姿态数据**：roll、pitch、yaw（弧度或度，视版本）
- **GPS 坐标**：latitude、longitude（double 型）
- **DVL 速度**：u、v、w 三轴体坐标系速度
- **深度**：由压力传感器换算，单位米
- **电池状态**：电压 (V)、电流 (A)
- **温度**：舱内温度 (°C)
- **漏水**：leak_level（0=正常，>0=告警）
- **异常位图**：每 bit 对应一个子系统的异常状态

---

## 编解码函数

编解码实现位于 `common/protocol.py`：

### 下行编解码

```python
def build_downlink_packet(frame_seq, control_mode_byte, work_instruction,
                          fin_deg, thrust_percent, tunable_params) -> bytes:
    """构建72字节下行帧"""

def parse_downlink_packet(data: bytes) -> dict:
    """解析72字节下行帧，返回字段字典"""
```

### 上行编解码

```python
def build_uplink_packet(attitude, gps, dvl, depth, voltage,
                        temperature, leak, fault_bitmap) -> bytes:
    """构建145字节上行帧"""

def parse_uplink_packet(data: bytes) -> dict:
    """解析145字节上行帧，返回传感器数据字典"""
```

---

## 校验算法

采用**字节和低 8 位**校验：

```python
checksum = sum(frame[start:end]) & 0xFF
```

校验范围为帧头之后、校验和字段之前的所有字节。接收端重新计算并比对，不匹配则丢弃该帧。

---

## Python ↔ VxWorks 7 已知偏差

由于 Python 端与 VxWorks 嵌入式端独立开发，存在以下 7 处已知偏差：

| # | 偏差描述 | 影响 |
|---|----------|------|
| 1 | **帧头长度差异** | VxWorks 端帧头可能多/少 1 字节，导致后续字段整体偏移 |
| 2 | **压力 vs 航向字段错位** | 某版本中压力和航向字段位置互换 |
| 3 | **深度缩放因子** | Python 端使用 depth_m = raw / 100.0，VxWorks 端使用 raw / 10.0 |
| 4 | **舵角类型 (int8 vs uint8)** | Python 端使用有符号 int8（-128~127），VxWorks 端使用无符号 uint8（0~255，128为中位） |
| 5 | **电机类型 (int16 vs uint16)** | 推力字段符号约定不同 |
| 6 | **异常位图编码** | bit 定义顺序和含义存在差异 |
| 7 | **电压温度位置** | 上行帧中电压和温度字段的偏移量不同 |

> ⚠️ 在对接新固件版本时，务必逐字段校对协议文档。

---

## 调试工具

### `scripts/sniffer.py` — UDP 协议嗅探器

监听指定端口的 UDP 流量，实时解析并显示上/下行帧内容：

```bash
python scripts/sniffer.py --port 5000 --direction both
```

### `tools/manual_protocol_injector.py` — 手动注入协议帧

构造并发送自定义协议帧，用于测试 AUV 响应：

```bash
python tools/manual_protocol_injector.py --mode manual --thrust 50 --fin 10
```

### `common/protocol_debug.py` — 格式化输出

提供 `dump_frame(data)` 函数，以人类可读格式输出帧的每个字段及其原始十六进制值，便于排查协议解析问题。
