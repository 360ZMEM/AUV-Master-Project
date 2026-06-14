# S4 — 单回路闭环（恒定 setpoint，0xEE/0xEF 模式）

> Jetson 第一次真正夺权。激活仲裁器，不走行为树，给一个**恒定**的深度+航向+速度，看真机跟踪表现。

---

## 1. 目的

- 关闭 `passive_mode`，让 bridge 真的下发 `$CKTH`；
- 用 [tools/single_setpoint_driver.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/single_setpoint_driver.py) 注入一条 `/auv/manual/setpoint`（高优先级），由 [decision_node._on_manual_setpoint](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_control/auv_decision_ros/decision_node.py) 接管为 ControlGoal；
- 量化 **超调 / 稳态误差 / 响应时间**。

---

## 2. 前置条件

| 项 | 要求 |
|----|------|
| S3 通过 | `log/real_deployment/*_S3_shadow_navigation_*/passed.flag` 存在 |
| EKF 已校 | S3 的 RMSE 满足阈值；如果未满足，本阶段超调会被放大 |
| 安全 | 水面有人；并行终端常驻 [kill_switch.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/real_deployment/kill_switch.sh) 待按 |
| 围隔 | 至少 5 m × 5 m × 2 m（深度可达 1.5 m） |

---

## 3. 命令清单

```bash
cd /home/auv_user/auv_ws/AUV-Master-Project

# mock：本地回环
bash scripts/real_deployment/04_closed_loop_single.sh --target mock --duration 60

# real：必须显式确认；可指定 setpoint
bash scripts/real_deployment/04_closed_loop_single.sh \
     --target real --duration 120 --i-have-physical-auv \
     -- depth=2.0 heading=90 speed=0.5

# 干跑
bash scripts/real_deployment/04_closed_loop_single.sh --target mock --duration 5 --dry-run
```

`--` 之后的位置参数透传给 [single_setpoint_driver.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/single_setpoint_driver.py)，支持 key=value：

| key | 含义 | 默认 |
|-----|------|------|
| `depth` | 目标深度（m） | 1.0 |
| `heading` | 目标航向（度，正北 0） | 0.0 |
| `speed` | 目标对地速度（m/s） | 0.3 |

shell 在内部做：
1. 启动 stack（不带 `passive_mode`，即默认 false）；
2. 启动 [auto_activate_emu.py](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/auto_activate_emu.py) 提供 0xEE 心跳，绕过 AutonomyGuard 的"上位机失联"判据；
3. 启动 single_setpoint_driver 周期发 Setpoint；
4. 退出时**主动跑一次** [kill_switch.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/real_deployment/kill_switch.sh) 防止执行器残留。

---

## 4. 通过判据

- shell 退出码 0；
- `single_setpoint.csv` 行数 ≈ duration × rate_hz；
- 通过人工查看 rosbag（或现场目视）：超调 < 30%，稳态误差 < setpoint × 10%；
- 退出时 ESTOP 帧已发出（看 `kill_switch.log` 不为空）。

---

## 5. 失败回退

| Symptom | Likely Cause | Fix Step |
|---------|--------------|----------|
| AUV 不动 | AutonomyGuard 没解锁 | 看 `auto_activate.log`；确认 0xEE 心跳进入 [auv_bridge](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_bridge) |
| 上下振荡 ±0.5 m | AMD 端本地 PID 太硬 | 在 Jetson 端降低 `Set_Course` 变化率；按 [07_param_diff_sim_vs_real.md](07_param_diff_sim_vs_real.md) §7 找到当前 target 的 brain params yaml 后修改 |
| 响应慢半拍（>1s） | bridge 缓存太长 | 看 [bridge_node.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_bridge/auv_bridge/bridge_node.py) 的 `qos history depth` |
| 直接漂走 | 极性错（S2 没做） | 立刻 Ctrl+C / kill_switch；回到 S2 |
| stack 起来后立刻 ESTOP | guard_min_total_voltage_v 不匹配电池 | 看 `08_real_hardware_sop.md` Step 5 电压阈值 |

---

## 6. 实施修复（PID 调参顺序）

1. **kp 减半优先**：振荡 → kp 减半，复跑 30s；
2. **再加 ki**：稳态误差 → ki 加 25%；
3. **kd 不动**：除非有明显高频抖；
4. 只动当前 target 的 brain params yaml（映射见 [07_param_diff_sim_vs_real.md](07_param_diff_sim_vs_real.md) §7）的 `controller.{depth,yaw,speed}.{kp,ki,kd}`；不要动算法层。
5. 完成后**回到 S3 重跑一次**，确认新参数没让 shadow RMSE 退化。

参考既有调参表：[user-guide/08_real_hardware_sop.md](../user-guide/08_real_hardware_sop.md) Step 2 "控制器参数切换"。

---

## 7. 关键引用

- [scripts/real_deployment/04_closed_loop_single.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/real_deployment/04_closed_loop_single.sh)
- [tools/single_setpoint_driver.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/single_setpoint_driver.py)
- [scripts/auto_activate_emu.py](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/auto_activate_emu.py)
- [brain_linux/src/auv_interfaces/msg/Setpoint.msg](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_interfaces/msg/Setpoint.msg)
- [decision_node.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_control/auv_decision_ros/decision_node.py) — `_on_manual_setpoint`
