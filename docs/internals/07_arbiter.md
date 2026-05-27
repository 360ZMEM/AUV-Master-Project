# 仲裁器与安全机制

## 核心设计

仲裁器（Arbiter）回答一个关键问题：**谁拥有控制权？**

在 AUV 系统中，存在两个潜在的控制源：
- **PC 遥控**：操作员通过上位机手动发送控制指令
- **Jetson 自主**：板载 MPC/PID 控制器自动生成控制指令

仲裁器确保在任何时刻只有一个控制源生效，并提供安全的切换机制。

---

## 两种模式

| 模式 | 枚举 | 数据源 | 行为 |
|------|------|--------|------|
| REMOTE | `ArbiterMode.REMOTE` | PC 上位机原始指令 | 透明路由转发，Jetson 不修改任何控制量 |
| AUTONOMOUS | `ArbiterMode.AUTONOMOUS` | Jetson MPC 输出 | 自主控制，MPC/PID 生成的指令直接下发执行器 |

---

## 模式切换逻辑（状态机）

```
                ┌─────────────────────────┐
                │                         │
                ▼                         │
           ┌────────┐   0xEE        ┌────────────┐
    ──────►│ REMOTE │──────────────►│ AUTONOMOUS │
           └────────┘               └────────────┘
                ▲                         │
                │   TASK_CANCEL /         │
                │   CLEAR_FAULT           │
                └─────────────────────────┘
```

切换规则：

| 条件 | 动作 |
|------|------|
| `control_mode_byte == 0xEE` | 切换至 AUTONOMOUS（需通过守卫器检查） |
| `work_instruction == TASK_CANCEL` | 立即切换至 REMOTE（ESTOP） |
| `work_instruction == CLEAR_FAULT` | 立即切换至 REMOTE（ESTOP） |
| 其他 | 保持 REMOTE |

---

## AutonomyGuard（自治守卫器）

在切入 AUTONOMOUS 之前，守卫器对系统状态进行安全检查：

| 检查项 | 阈值 | 拒绝原因 |
|--------|------|----------|
| 漏水 | `leak_level > 0` | `LEAK_DETECTED` |
| 电压 | `voltage <= 47V` | `LOW_VOLTAGE` |
| 置信度 | `confidence <= 0.5` | `LOW_CONFIDENCE` |
| 遥测新鲜度 | `uplink_age >= 200ms` | `AMD_UPLINK_STALE` |
| 存储占用 | `disk_usage > 90%` | `LOW_CONFIDENCE` |

只有所有检查项通过，才允许切入自主模式。

### 守卫器状态机

```
    ┌────────┐  请求自主   ┌────────────┐
    │ LOCKED │────────────►│ REQUESTING │
    └────────┘             └────────────┘
         ▲                   │         │
         │                   │检查通过  │检查失败
         │                   ▼         ▼
         │              ┌────────┐  ┌────────┐
         │              │ ACTIVE │  │ DENIED │
         │              └────────┘  └────────┘
         │                   │         │
         └───────────────────┴─────────┘
                  超时/ESTOP
```

- **LOCKED**：默认状态，不允许自主
- **REQUESTING**：收到自主请求，正在执行安全检查
- **ACTIVE**：检查通过，自主模式激活
- **DENIED**：检查失败，拒绝切入自主，记录原因

---

## 分层超时看门狗

仲裁器维护一个分层超时机制，监控上位机通信链路健康：

### Soft Warning（1.0s ~ 1.5s）

- 触发条件：上位机帧间隔 > 1.0s
- 行为：发出链路弱告警，通知决策层
- 不改变控制权

### Hard ESTOP（> 1.5s）

- 触发条件：上位机帧间隔 > 1.5s
- 行为：
  - 强制锁回 REMOTE 模式
  - 下发零推力指令（所有舵角归零、推力为零）
  - 等待通信恢复

---

## AUTONOMOUS 模式下命令选择

当处于 AUTONOMOUS 模式时，仲裁器按以下优先级选择命令源：

```
MPC 命令新鲜 (age < 0.5s)?
    ├── 是 → 使用 MPC 输出
    └── 否 → Safety Fallback: 零推力保持
```

- **MPC 新鲜**：最近一次 MPC 求解结果不超过 500ms，直接使用
- **Safety Fallback**：MPC 超时（求解失败或通信中断），下发零推力指令，保护 AUV

---

## Bumpless Transfer（无扰切换）

模式切换时采用无扰切换策略，避免控制量阶跃：

### PID 积分项重置

切换瞬间，将所有 PID 控制器的积分器清零，避免积分饱和导致的控制突变。

### Setpoint Shadowing（设定值跟踪）

在非 AUTONOMOUS 模式下，自主控制器持续跟踪（shadow）当前实际状态作为设定值：

- `target_depth = current_depth`
- `target_heading = current_heading`
- `target_speed = current_speed`

切换至 AUTONOMOUS 时，设定值从当前状态平滑过渡到任务目标，消除阶跃。

---

## passive_mode（被动模式）

当 `passive_mode = True` 时：

- 仲裁器**不发送**任何实际控制命令至执行器
- 仍然执行完整的决策和控制计算
- 所有输出仅用于 shadow 观察和日志记录
- 适用于：系统集成测试、算法验证、回放分析

```python
arbiter.set_passive_mode(True)  # 仅观察，不执行
```
