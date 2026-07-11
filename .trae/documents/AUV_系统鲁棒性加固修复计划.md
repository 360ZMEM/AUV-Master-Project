# AUV 系统鲁棒性加固修复计划

## 背景

根据两位审查者的意见，当前 AUV 系统在数值边界、状态机切换、传感器时间对齐、通信链路自愈和诊断文档五个方面存在潜在风险。本计划将这些问题合并为统一的修复方案。

---

## 修复 1：数值鲁棒性加固 — 防止整数溢出和 NaN/Inf 污染

**目标文件**：`common/protocol.py`、`brain_linux/src/auv_control/auv_decision_ros/mappers.py`

### 1.1 在 `build_downlink_packet` 前强制检查所有浮点输入

**位置**：`common/protocol.py` 第 1066 行之前

**修复内容**：
- 新增辅助函数 `_sanitize_float(value, default=0.0)` — 检查 `math.isfinite()`，若为 NaN/Inf 则返回 `default`
- 在 `normalize_control_command()` 返回值被使用前（`build_downlink_packet` 第 1097~1104 行的 `struct.pack_into` 调用处），对所有浮点值（舵角、推力、方向角）执行 `_sanitize_float` 检查
- 若检测到 NaN/Inf，记录 `CRITICAL` 级别日志并替换为安全值（0.0），**禁止抛出异常导致崩溃**

### 1.2 在 `mappers.py` 中增加 Thrust/Rudder 饱和度记录

**位置**：`brain_linux/src/auv_control/auv_decision_ros/mappers.py`

**修复内容**：
- 新增模块级 `saturation_log: list[dict]` 用于记录控制器何时触碰物理极限
- 新增函数 `log_saturation(name, value, limit)` — 当值等于边界时记录（名称、值、边界、时间戳）
- 在现有的 `clamp_thrust_percent` 和 `clamp_rudder_deg`（位于 `common/physics.py`）调用处增加日志钩子

---

## 修复 2：状态机切换原子性 — 消除幽灵推力

**目标文件**：`brain_linux/src/auv_bridge/auv_bridge/arbiter.py`

### 2.1 新增 `reset_all_buffers()` 私有方法

**位置**：`arbiter.py` 的 `CommandArbiter` 类内部

**修复内容**：
```python
def reset_all_buffers(self) -> None:
    """在模式切换时清空所有历史指令缓存，防止旧指令残留。"""
    self._last_mpc = None
    self._last_mpc_ts = 0.0
    # 注意：不清除 _last_pc_raw，因为手动模式需要最近一次 PC 指令
```

### 2.2 在所有模式切换路径调用 `reset_all_buffers()`

**调用点**：
- `update_pc_raw_command()` — 当检测到 `TASK_CANCEL` 或 `CLEAR_FAULT` 指令时（第 119-120 行）
- `force_remote()` — 在进入远程模式时（第 137 行）
- 新增：当从 AUTONOMOUS 切到 REMOTE 时（在 `decide()` 方法中检测模式变化）

### 2.3 确保切换为抢占式

**位置**：`bridge_node.py` 的 `handle_pc_raw_command()`（第 387-390 行）

**修复内容**：
- ESTOP 路径已有 `force_remote()` 调用，但需确保此调用**不等待**当前控制循环
- 在 `handle_pc_raw_command` 的 ESTOP 分支中，增加 `self.get_logger().warn()` 打印切换前后状态

---

## 修复 3：传感器时间对齐补偿 — 处理 DVL 延迟

**目标文件**：`algorithm/es_ekf.py`

### 3.1 新增延迟感知 DVL 修正方法

**位置**：`es_ekf.py` 的 `ES_EKF` 类内部

**修复内容**：
- 新增方法 `correct_dvl_with_timestamp(dvl_vel_body, dvl_timestamp, current_timestamp)`：
  1. 计算 `dt = current_timestamp - dvl_timestamp`
  2. 若 `dt > 0.050`（50ms），执行回溯-修正-前推：
     - 保存当前状态（`p`, `v`, `q`, `b_a`, `b_g`, `P`）
     - 不执行实际回溯（因无法回放 IMU 历史），但记录警告日志
     - 在协方差矩阵 `P` 中增加额外过程噪声，补偿延迟导致的误差膨胀
  3. 执行标准 DVL 修正

### 3.2 编写延迟 DVL 性能测试

**位置**：新建 `algorithm/tests/test_delayed_dvl_performance.py`

**测试内容**：
- 模拟正常 IMU（50Hz） + 延迟 DVL（5Hz + 200ms 随机延迟）
- 比较正常 vs 延迟情况下的位置 RMSE
- 要求：RMSE 增加不超过 10%

---

## 修复 4：通信链路自愈 — WiFi 闪断恢复

**目标文件**：`brain_linux/src/auv_bridge/auv_bridge/bridge_backends.py`、`brain_linux/src/auv_bridge/auv_bridge/bridge_node.py`

### 4.1 UDP 接收循环异常捕获

**位置**：`bridge_backends.py` 的 `_recv_loop()` 方法（第 371-393 行）

**修复内容**：
- 在 `recvfrom()` 调用处增加 `try-except` 捕获 `socket.error`（含 `ConnectionResetError`、`OSError` 等）
- 捕获后：
  1. 调用 `_safe_reconnect()` — 关闭旧 socket → 重新 bind → 重启接收线程
  2. 通过 `node.get_logger()` 记录断开/重连事件
  3. 通知桥接节点触发 `LOCKED` 安全模式

### 4.2 新增 `_safe_reconnect()` 方法

**位置**：`ProtocolBridgeBackend` 类内部

**修复内容**：
```python
def _safe_reconnect(self) -> bool:
    """安全重连 UDP socket，返回是否成功。"""
    self._stop_event.set()
    if self._recv_thread is not None:
        self._recv_thread.join(timeout=1.0)
    if self._socket is not None:
        self._socket.close()
        self._socket = None
    time.sleep(1.0)  # 等待 1s
    try:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind((self.local_host, self.local_port))
        self._socket.settimeout(self.socket_timeout_s)
        self._stop_event.clear()
        self._recv_thread = threading.Thread(target=self._recv_loop, ...)
        self._recv_thread.start()
        return True
    except Exception as exc:
        logger.error(f"Reconnect failed: {exc}")
        return False
```

### 4.3 Zenoh Session 自动重连

**位置**：`bridge_backends.py` 的 `TopicBridgeBackend`

**修复内容**：
- 在 `send_command()` 中捕获 `zenoh` 异常，若 session 失效则调用 `close()` → `open()` 重连
- 增加重试计数器（最多 3 次），失败后记录错误但不阻塞主线程

### 4.4 桥接节点集成链路自愈通知

**位置**：`bridge_node.py`

**修复内容**：
- 在 `ProtocolBridgeBackend` 重连成功后，通知 `AUVBridgeNode` 触发守卫器 `lock()` 调用
- 新增回调接口 `on_link_failure()` / `on_link_recovery()`

---

## 修复 5：诊断文档生成

**目标文件**：新建 `docs/AUV_系统鲁棒性压测记录.md`

### 5.1 文档结构

```markdown
# AUV 系统鲁棒性压测记录

## 1. 溢出实验
### 测试方法
- 向 MPC 输出注入 NaN、Inf、1e9 等极限值
### 结果
- build_downlink_packet 是否拦截非法包：[待填写]
- 日志输出是否正常：[待填写]

## 2. 急停延迟实测
### 测试方法
- 点击 ESTOP → 用 UDP 嗅探捕获 Work_Cmd=0x02
### 结果
- 物理耗时：[待填写，要求 < 20ms]

## 3. 零偏漂移观察
### 测试方法
- 无任何输入，记录 EKF 静止 10 分钟轨迹
### 结果
- 发散范围（m）：[待填写]

## 4. 闪断压力测试
### 测试方法
- 每秒关闭/开启网卡，持续 10 分钟
### 结果
- 句柄数量变化：[待填写]
- 内存泄漏：[待填写]

## 5. 暴力切换实验
### 测试方法
- MPC 满推力输出时，瞬间切换回手动
### 结果
- 下行报文首字节跳变延迟：[待填写]
- 是否有旧指令残留：[待填写]
```

---

## 执行顺序

1. **修复 1**（数值鲁棒性）— 优先级最高，涉及安全边界
2. **修复 2**（状态机原子性）— 优先级高，涉及操作安全
3. **修复 4**（通信链路自愈）— 优先级高，涉及长时间运行稳定性
4. **修复 3**（传感器时间对齐）— 优先级中，涉及定位精度
5. **修复 5**（诊断文档）— 优先级低，可在修复完成后填写测试结果

---

## 涉及文件清单

| 文件路径 | 修改类型 |
|---------|---------|
| `common/protocol.py` | 修改 — 新增 `_sanitize_float`，修改 `build_downlink_packet` |
| `common/physics.py` | 可能修改 — 增加饱和度日志钩子 |
| `brain_linux/src/auv_control/auv_decision_ros/mappers.py` | 修改 — 新增 `saturation_log` |
| `brain_linux/src/auv_bridge/auv_bridge/arbiter.py` | 修改 — 新增 `reset_all_buffers`，修改模式切换逻辑 |
| `algorithm/es_ekf.py` | 修改 — 新增 `correct_dvl_with_timestamp` |
| `algorithm/tests/test_delayed_dvl_performance.py` | 新建 — 延迟 DVL 测试 |
| `brain_linux/src/auv_bridge/auv_bridge/bridge_backends.py` | 修改 — 新增 `_safe_reconnect`，异常捕获 |
| `brain_linux/src/auv_bridge/auv_bridge/bridge_node.py` | 修改 — 集成链路自愈通知 |
| `docs/AUV_系统鲁棒性压测记录.md` | 新建 — 诊断文档 |
