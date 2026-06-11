# S3 — 影子导航（入水但 Jetson 不接管）

> 入水后第一次"通电跑算法"的阶段。AUV 由人通过 PySide6 上位机驾驶，Jetson 决策栈以 `passive_mode:=true` 跑完整算法，但**只发布 shadow_cmd，不真发 UDP 下行**。

---

## 1. 目的

- 确认 EKF / 控制器 / 决策器在真实水流下的输出**与人类驾驶**的一致性；
- 量化跟踪误差 RMSE（航向、深度），用以更新 EKF 协方差 Q/R；
- 在不夺权的前提下，验证整套算法链路在水下不崩。

---

## 2. 前置条件

| 项 | 要求 |
|----|------|
| S2 通过 | `log/real_deployment/*_S2_static_actuator_*/passed.flag` 存在 |
| 物理 | AUV 入水；浮性配重已校准；水深 > 1.5 m |
| 上位机 | PySide6 [auv_console_pyside6](file:///home/auv_user/auv_ws/AUV-Master-Project/console_soft/auv_console_pyside6/) 已启动；MANUAL 模式 |
| 网络 | Jetson、上位机、AMD 三方 ping 通 |
| 安全 | 水面有人；急停按钮就位 |

---

## 3. 命令清单

```bash
cd /home/auv_user/auv_ws/AUV-Master-Project

# mock：本地回环（开发联调用）
bash scripts/real_deployment/03_shadow_navigation.sh --target mock --duration 60

# real：必须显式确认
bash scripts/real_deployment/03_shadow_navigation.sh \
     --target real --duration 120 --i-have-physical-auv

# 干跑
bash scripts/real_deployment/03_shadow_navigation.sh --target mock --duration 5 --dry-run
```

shell 在内部做：
1. 后台拉起 `log_receiver.py`（+ mock 时拉起假 AMD）；
2. 通过 launch 参数显式覆盖：`bash scripts/start_lin_brain.sh stack --arbiter-profile passive_mode:=true`，**不修改任何 yaml 默认值**；
3. 启动 [tools/shadow_diff_recorder.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/shadow_diff_recorder.py) 订阅 `/auv/bridge/shadow_cmd` 与 `/auv/bridge/shadow_telemetry`；
4. 等待 duration 完成后停止，写 `report.md`。

> 在这阶段，`/auv/manual/setpoint` **不是**由本 shell 注入；setpoint 来自上位机的人类操作。Jetson 的算法用 EKF 估计真实状态，自己也算了一份"应该的命令"，进 shadow_cmd。

---

## 4. 通过判据

- shell 末尾出现 `marked stage passed`；
- `shadow_diff.csv` 行数 ≥ duration × 1Hz；
- 退出时打印的 RMSE 满足：航向 < 10°，深度 < 0.5 m。

如果 RMSE 超阈值，本阶段也会写 `passed.flag`（因为只是观测期），但 **S4 应该回头先调 EKF，不应贸然开闭环**。

---

## 5. 失败回退

| Symptom | Likely Cause | Fix Step |
|---------|--------------|----------|
| `[shadow_diff] rclpy not available` | source ROS2 之前跑了 | `source /opt/ros/humble/setup.bash` 后再跑 |
| `dheading_deg` 一直 ±180° | 上位机/Jetson 用了不同的 wrap 约定 | 看 [tools/shadow_diff_recorder.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/shadow_diff_recorder.py) wrap 是 `[-180,180)`；上位机端如是 `[0,360)`，调上位机 |
| `ddepth_m` 持续 1+ m | 深度传感器零点未校 | S2 阶段先做静态零点 |
| stack 起 8s 后退出 | colcon build 在某包失败 | `tail -n 50 stack.log` |
| RMSE 大但波形看起来跟手 | EKF Q/R 偏离真实噪声 | 见下面"实施修复" |

---

## 6. 实施修复（EKF 协方差更新）

1. 把 `shadow_diff.csv` 中 `dheading_deg`/`ddepth_m` 的方差作为新的 R 的初值；
2. 在 [params.protocol_udp_arbiter.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/params.protocol_udp_arbiter.yaml) 找到 `auv_localization` 的 `R_*` 段，把对应通道方差调到与实测一致；
3. **不要**为了让 RMSE 漂亮去缩小 Q——会让 EKF 过度信任模型，水中机动响应变慢。

> 参考：[docs/internals/INDEX.md](../internals/INDEX.md) 中的 EKF 章节解释 Q/R 物理含义。

---

## 7. 关键引用

- [scripts/real_deployment/03_shadow_navigation.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/real_deployment/03_shadow_navigation.sh)
- [tools/shadow_diff_recorder.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/shadow_diff_recorder.py)
- [brain_linux/src/auv_bridge/auv_bridge/bridge_node.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_bridge/auv_bridge/bridge_node.py) — `shadow_cmd_topic` / `shadow_telemetry_topic` 默认值
- [params.protocol_udp_arbiter.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/params.protocol_udp_arbiter.yaml) — passive_mode / R_*
