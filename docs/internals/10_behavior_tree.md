# 行为树决策引擎

## 为什么用行为树

| 对比维度 | 有限状态机 (FSM) | 行为树 (BT) |
|----------|-----------------|-------------|
| 可扩展性 | 状态数增长后转移爆炸 | 模块化节点，线性增长 |
| 可组合性 | 难以复用子状态机 | 子树即组件，即插即用 |
| 调试透明度 | 需追踪隐式状态 | 树状结构直观可视化 |
| 反应性 | 需额外全局中断 | 天然支持优先级抢占 |

基于 `py_trees` 库实现，决策核心 **独立于 ROS2**：`auv_decision_core` 可纯 Python 单元测试，无需启动 ROS2 环境。

---

## 行为树结构（完整）

```
RootSelector
├── EmergencySequence [漏水/低电/穿底 → 紧急上浮]
│   ├── EmergencyCondition
│   │   └── 检查: leak_level>0 OR battery_low OR depth>max_depth
│   └── EmergencySurface (depth=0, speed=0.8)
│       └── 输出: Setpoint(EMERGENCY_SURFACE, depth=0, speed=0.8)
│
├── StandbyCheck [auto_state != ACTIVE → IDLE]
│   └── 条件: 仲裁器未处于AUTONOMOUS → 返回IDLE setpoint
│
└── DebugCascadeSelector
    ├── HoldSequence (debug_level==1) [定深定航]
    │   ├── DebugLevelCondition(level=1)
    │   └── StabilizeHold
    │       └── 输出: Setpoint(STABILIZE_HOLD, hold当前深度/航向)
    │
    ├── AnalyticalPathSequence (debug_level==2) [解析轨迹跟踪]
    │   ├── DebugLevelCondition(level=2)
    │   └── AnalyticalPath
    │       └── 输出: Setpoint(ANALYTICAL_PATH, 预设解析轨迹)
    │
    └── MainMissionSequence (debug_level==0/3) [完整任务]
        ├── DiveToDepth(4m)
        │   └── 输出: Setpoint(DIVING, depth=4.0)
        └── SeabedSafetyLimiter
            └── RouteSelector
                ├── PreciseInspection [confidence>0.7]
                │   └── 输出: Setpoint(PARALLEL_TRACKING, track_cable=True)
                └── ZigZagSearch [低置信度搜索]
                    └── 输出: Setpoint(ZIGZAG_SEARCH, sine参数)
```

### 节点语义

- **RootSelector**：从左到右尝试子节点，第一个成功即停止（优先级机制）
- **EmergencySequence**：最高优先级，紧急条件满足时强制上浮
- **StandbyCheck**：非自主状态时输出空闲
- **DebugCascadeSelector**：根据 debug_level 选择运行子集

---

## 行为模式枚举 (BehaviorMode)

| 枚举值 | 名称 | 说明 |
|--------|------|------|
| 0 | `IDLE` | 空闲，不输出控制目标 |
| 1 | `DIVING` | 下潜至目标深度 |
| 2 | `STABILIZE_HOLD` | 定深定航保持 |
| 3 | `ANALYTICAL_PATH` | 解析轨迹跟踪 |
| 4 | `PARALLEL_TRACKING` | 平行线海缆跟踪 |
| 5 | `ZIGZAG_SEARCH` | 之字形搜索 |
| 6 | `EMERGENCY_SURFACE` | 紧急上浮 |

---

## debug_level 控制

通过 Launch 参数 `debug_level` 选择行为树执行的分支：

| debug_level | 行为 | 用途 |
|-------------|------|------|
| 0 | 完整任务（MainMissionSequence） | 正式作业 |
| 1 | L1 Hold（定深定航） | 基础功能验证 |
| 2 | L2 AnalyticalPath（解析轨迹跟踪） | 控制器性能测试 |
| 3 | 完整任务（同0） | 备用 |

---

## 传感器输入模型 (SensorStatus.msg)

行为树从 `/auv/sensors/status` Topic 获取系统状态：

| 字段 | 类型 | 说明 |
|------|------|------|
| `confidence` | float64 | 定位置信度 [0, 1] |
| `leak_level` | uint8 | 漏水等级（0=正常） |
| `battery_low` | bool | 低电压标志 |
| `voltage` | float64 | 当前电池电压 (V) |
| `dvl_valid` | bool | DVL 数据有效 |
| `gps_valid` | bool | GPS 数据有效 |
| `depth` | float64 | 当前深度 (m) |
| `heading` | float64 | 当前航向 (rad) |

---

## 输出：Setpoint

行为树的唯一输出为 `Setpoint` 消息，发布至 `/auv/control/setpoint`：

| 字段 | 类型 | 说明 |
|------|------|------|
| `mode` | uint8 | BehaviorMode 枚举值 |
| `target_depth` | float64 | 目标深度 (m) |
| `target_heading` | float64 | 目标航向 (rad) |
| `target_speed` | float64 | 目标航速 (m/s) |
| `track_cable` | bool | 海缆跟踪模式 |
| `sine_amplitude` | float64 | 之字形搜索振幅 (m) |
| `sine_period` | float64 | 之字形搜索周期 (s) |

---

## Telemetry

行为树运行时通过 `/auv/bt_status` Topic 实时广播树状态：

- 当前活跃节点路径
- 各节点返回状态（SUCCESS / FAILURE / RUNNING）
- 当前 BehaviorMode
- 决策耗时

地面站可订阅该 Topic 进行实时可视化调试。

---

## FSM 基线 (fsm_baseline.py)

作为对照组实现的有限状态机版本：

```
IDLE → DIVING → TRACKING → SEARCHING → SURFACE
                    ↑           │
                    └───────────┘
```

- 状态转移基于固定条件
- 无优先级抢占机制
- 紧急处理需单独全局中断
- 用于与行为树方案进行对比实验，验证行为树的优越性
