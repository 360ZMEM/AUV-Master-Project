# AUV 枚举定义速查

## BehaviorMode（行为模式）

| 值 | 说明 | 使用场景 |
|----|------|----------|
| `IDLE` | 空闲状态 | 系统启动时默认 |
| `DIVING` | 下潜模式 | 下潜到目标深度 |
| `ZIGZAG_SEARCH` | 之字形搜索 | 低置信度巡检 |
| `PARALLEL_TRACK` | 并行跟踪 | 高置信度巡检 |
| `EMERGENCY_SURFACE` | 紧急上浮 | 安全触发时 |
| `STABILIZE_HOLD` | 定深定航 | L1 Hold 模式 |
| `ANALYTICAL_PATH` | 解析式轨迹 | L2 Path 模式 |

## BridgeBackend（桥接后端）

| 值 | 说明 | 用途 |
|----|------|------|
| `ZENOH_JSON` | Zenoh JSON 协议 | 仿真侧通信 |
| `PROTOCOL_UDP` | 二进制 UDP 协议 | 实物 AUV 通信 |

## ControlModeByte（控制模式字节）

| 值 | 十六进制 | 说明 |
|----|----------|------|
| `SEND_ONLY` | 0x00 | 仅发送 |
| `REMOTE_CONTROL` | 0x01 | 遥控模式 |
| `AUTO_FIXED_POINT` | 0x02 | 自动定点 |
| `AUTO_DIRECTION` | 0x03 | 自动定向 |
| `RETURN_HOME` | 0x04 | 返航模式 |
| `JETSON_PROTOCOL` | 0xEE | 自主模式（新增） |

## WorkInstruction（工作指令）

| 值 | 十六进制 | 说明 |
|----|----------|------|
| `NONE` | 0x00 | 无指令 |
| `TASK_START` | 0x01 | 任务开始 |
| `TASK_CANCEL` | 0x02 | 任务取消 |
| `MAIN_THRUSTER_ON` | 0x11 | 主推进器开启 |
| `MAIN_THRUSTER_OFF` | 0x12 | 主推进器关闭 |
| `DVL_ON` | 0x21 | DVL 开启 |
| `DVL_OFF` | 0x22 | DVL 关闭 |
| `CLEAR_FAULT` | 0x91 | 清除故障 |
| `INITIALIZE` | 0x92 | 初始化 |
| `AUTONOMOUS_CONTROL` | 0xEE | 自主控制 |

## AutoState（自主状态）

| 值 | 说明 |
|----|------|
| `LOCKED` | 锁定状态 |
| `REQUESTING` | 请求自主控制权 |
| `ACTIVE` | 自主控制激活 |
| `DENIED` | 自主控制被拒绝 |

## ArbiterMode（仲裁模式）

| 值 | 说明 |
|----|------|
| `REMOTE` | 遥控模式 |
| `AUTONOMOUS` | 自主模式 |

## ArbiterSource（仲裁来源）

| 值 | 说明 |
|----|------|
| `NONE` | 无来源 |
| `PC_RAW` | PC 原始命令 |
| `JETSON_MPC` | Jetson MPC 输出 |
| `SAFETY_FALLBACK` | 安全回退 |

## DenyReason（拒绝原因）

| 值 | 说明 |
|----|------|
| `NONE` | 无 |
| `MANUAL_OVERRIDE` | 手动覆盖 |
| `LEAK_DETECTED` | 检测到漏水 |
| `LOW_VOLTAGE` | 低电压 |
| `LOW_CONFIDENCE` | 低置信度 |
| `AMD_UPLINK_STALE` | AMD 上行数据过期 |
| `MPC_HEARTBEAT_TIMEOUT` | MPC 心跳超时 |

## DebugLevel（调试级别）

| 值 | 说明 | 激活行为 |
|----|------|----------|
| `AUTO` | 自动模式 | 主任务流 |
| `HOLD` | L1 保持 | 定深定航 |
| `PATH` | L2 轨迹 | 解析式轨迹跟踪 |
| `FULL` | L3 全功能 | 主任务流 |

## FaultCode（故障码）

| 值 | 说明 |
|----|------|
| `LEAK_DETECTED` | 漏水检测 |
| `LOW_VOLTAGE` | 低电压 |

## LeakLevel（漏水等级）

| 值 | 说明 |
|----|------|
| `NONE` | 0 - 无漏水 |
| `INTERNAL` | 1 - 内部漏水 |
| `EXTERNAL` | 2 - 外部漏水 |
| `BOTH` | 3 - 内外同时漏水 |

---

**相关文件**: `common/enums.py`
