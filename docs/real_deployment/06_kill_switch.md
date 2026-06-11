# 06 — 急停 Kill-Switch SOP

> 这一页只回答四个问题：**什么时候按、按了之后会发生什么、怎么释放、怎么自测它真的有效**。
> 急停脚本本身只有一份：[`scripts/real_deployment/kill_switch.sh`](../../scripts/real_deployment/kill_switch.sh)，三个 target 共用同一份代码、只换网络端点。

---

## 1. 双保险架构（先理解再使用）

实物部署有 **两道独立的"停机"机制**，互不依赖：

| 保险 | 谁触发 | 走哪条路径 | 触发条件 | 期望延迟 |
|---|---|---|---|---|
| **保险 A — 上位机急停** | 操作员手动按 `kill_switch.sh` | PC → AMD（UDP 21/52364） `Work_Cmd=0x02 / ctrl_mode=0x01 / Motor=0` | 人为判断异常 | ≤1 帧 (50 ms) |
| **保险 B — VxWorks 失联保护** | AMD 自身 | AMD 内部状态机 | 1 s 内未收到 PC 下行 | ≤1 s |

**它们是 OR 关系，不是 AND**：保险 A 的脚本只需要 PC 网络可达；保险 B 在 PC 直接断网/断电时仍会自启。**这正是"架构智慧 #2 急停重置"的目的——任何一道路径瘫痪，另一道仍能保住艇**。

> 决策栈侧的 `AutonomyGuard`（1.5 s 上位机失联自动 ESTOP）是**保险 A 的镜像复刻**，作用域是 ROS2 内部，与本节的 PC→AMD 急停**不重合**。详见 [`docs/internals/04_arbiter_and_guard.md`](../internals/04_arbiter_and_guard.md)。

---

## 2. 什么时候按

凡出现以下任一现象，**先按急停、再排查**：

- 推进器出现非预期方向（向后/向上/向下时刻不对）。
- 深度计读数与目标偏离 > 1.0 m 且持续 > 2 s。
- 航向漂移 > 30° 且趋势不收敛。
- 闭环输出在饱和值附近振荡（推力 ±100% 来回切）。
- PySide6 上位机失联、决策栈日志卡死、ROS2 节点崩溃。
- 任何"哪里不对劲"的直觉信号——**没有"假警报"成本**。

---

## 3. 按下急停的命令

| target | 命令 |
|---|---|
| mock | `bash scripts/real_deployment/kill_switch.sh --target mock` |
| vxsim | `bash scripts/real_deployment/kill_switch.sh --target vxsim` |
| **real** | `bash scripts/real_deployment/kill_switch.sh --target real --i-have-physical-auv` |

按下后：
- 终端立即打印 `kill-switch armed: target=<host>:<port>  rate=20Hz`。
- 脚本以 **20 Hz** 持续向 AMD 发送 ESTOP 帧（`ctrl_mode=0x01 REMOTE / Work_Cmd=0x02 ESTOP / 5 路 Motor=0`）。
- 帧序号每秒落一次盘到 `runs/real_deployment/<run_id>/kill_switch.log`，便于事后核对"第 N 帧才到位"。
- 直到操作员按 **Ctrl+C** 之前，脚本不会自动退出。

---

## 4. 通过判据（按下急停后 1 s 内必须满足）

- AMD 上行帧（145B）首字节 `Ctrl_Mode == 0x01 (REMOTE)`。
- 5 路 `Motor_Speed == 0`（含主桨与四个侧推）。
- 决策栈内部 `ControlGoal.cmd.work_cmd == 0x02`（仲裁器在收到 0x01 模式后会被同步降权）。
- VxWorks 状态字 `link_ok == True`（即保险 B 没有同时被触发——若同时触发，说明 PC↔AMD 链路也已断，此时只看 AMD 上行）。

---

## 5. 怎么释放（顺序很重要）

```
1. 操作员目视确认：5 路推力计读数全部归零、艇体姿态稳定
2. Ctrl+C 释放 kill_switch.sh
3. 在 PySide6 上位机切回 MANUAL 模式，目视确认面板上 ctrl_mode 显示为 0x01
4. 如果之前在跑 ros2 stack：另开终端 ros2 node list 确认决策栈未崩
5. 重新进入下一阶段（通常回到 S3 影子或 S4 单点闭环复测）
```

**不允许的操作**：
- 直接 `kill -9` kill_switch 进程——会让发送在帧序号未对齐时停止，AMD 可能在下个保险 B 触发前出现 50 ms 真空窗。
- 不释放 kill_switch 就启动 `bash scripts/real_deployment/05_full_autonomy.sh`——决策栈下行会被持续覆盖，看似"行为树没起作用"，实际是被急停帧压住。

---

## 6. 自测：怎么确认这把"枪"是好的

**每次实物部署前必跑**（5 分钟）：

```bash
# 终端 1：起 mock AMD（如未在跑）
python3 console_soft/auv_console_pyside6/mock_amd_server.py

# 终端 2：抓上行帧
python3 tools/actuator_polarity_recorder.py --duration 10 \
    --output runs/ks_selftest_$(date +%s).csv

# 终端 3：按急停
bash scripts/real_deployment/kill_switch.sh --target mock
# 等待 3 s 后 Ctrl+C
```

打开 `runs/ks_selftest_*.csv`，**所有行**满足：
- `ctrl_mode_byte == 0x01`
- `motor_thrust == motor_left == motor_right == motor_top == motor_bottom == 0`

任一行不满足 → **不允许进入 vxsim/real**。

---

## 7. 失败回退（自测不过）

| 现象 | 可能根因 | 排查锚点 |
|---|---|---|
| ESTOP 帧从未到达 mock AMD | 端口被占用 / 防火墙拦截 | `ss -ulnp \| grep 52364`；查 [`01_stage1_link_audit.md`](01_stage1_link_audit.md) §5 |
| `ctrl_mode != 0x01` | `common.protocol.build_downlink_packet` 字段错位 | 对照 [`docs/internals/02_protocol_unit.md`](../internals/02_protocol_unit.md) §下行帧布局 |
| Motor 不为 0 | `KILL_PAYLOAD` 被改 / scale 缩放方向错 | 看 kill_switch.sh 第 64–66 行（必须显式写 `0.0`） |
| Ctrl+C 后 mock AMD 仍显示 0x01 | 帧缓冲或 mock 自身不刷新——这是 mock 行为，不是 bug | vxsim/real 不会出现 |

---

## 8. 关键引用

- 急停脚本：[`scripts/real_deployment/kill_switch.sh`](../../scripts/real_deployment/kill_switch.sh)
- 协议字段：[`common/protocol.py`](../../common/protocol.py) `build_downlink_packet`、`KEY_THRUST/LEFT/RIGHT/TOP/BOTTOM`
- AutonomyGuard 决策栈侧镜像：[`docs/internals/04_arbiter_and_guard.md`](../internals/04_arbiter_and_guard.md)
- 上一阶段：[`05_stage5_full_autonomy.md`](05_stage5_full_autonomy.md)
- 下一文档：[`07_param_diff_sim_vs_real.md`](07_param_diff_sim_vs_real.md)
- 标准依据：`../../标准文档/AMD通讯协议.pdf` §下行帧 Work_Cmd / Ctrl_Mode 字段
