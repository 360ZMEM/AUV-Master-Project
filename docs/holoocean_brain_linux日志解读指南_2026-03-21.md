# holoocean <-> brain_linux 联调日志解读指南（2026-03-21）

## 一、日志来源与结构
- 文件样例：`scripts/log/log_example.log`
- 运行节点：
  - `zenoh_json_bridge_node`（仿真数据转 ROS2）
  - `auv_localization_node`（状态融合/滤波）
  - `auv_controller_node`（控制器开环/闭环输出）
  - `auv_decision_node`（行为树决策/状态总结）

每条日志格式为：`[节点] [级别] [时间戳] [节点名]: 消息`

---

## 二、核心指标解释
### 1. 数据通路延迟
- `zenoh_json_bridge_node`: `[bridge] mean sensor ingress latency` 与仿真数据时戳差
  - 理想值：0.3~0.6 ms
  - 判断：0.5 ms 以下为健康，若持续 >5 ms 需排查网络+zenoh订阅速率。

- `auv_localization_node`: `[localization] mean sensor->filter latency`
  - 观察值：9.2~9.6 ms
  - 判断：10~25 ms 属可接受，若 >50 ms 关注滤波计算/CPU瓶颈或被其他节点抢占。

- `auv_controller_node`: `[controller] mean state/setpoint->cmd latency`
  - 观察值：22.8~22.9 ms
  - 判断：<=30 ms 目前正常；若出现突增（>100 ms），可能是 setpoint 频率不稳或 control loop 阻塞。

### 2. 复盘频率
- `decision_node`周期约 1.0 s 输出一次 `状态摘要` 及 `行为树快照`。
  - 关键字段：`mode=ZIGZAG_SEARCH`、`depth=0.00m`、`speed=0.00m/s`、`goal_depth=4.00m`、`goal_speed=0.40m/s`
  - 判断：若状态摘要停滞（同一值长时间不变），检查传感器输入（/auv/sensors/*）是否异常。

---

## 三、日志工程（查点步骤）
1. 首先定位时间轴 
   - `zenoh_json_bridge_node` 先出现采样延迟记录，表示数据流可进；
   - `auv_localization_node` 之后出现定位延迟，表示滤波器开始工作；
   - `auv_controller_node` 再出现控制延迟，表示闭环控制在输出。

2. 交叉核对是否有断点
   - `bridge` 有输出且 `latency > 0` -> sim 侧有效
   - `localization` 有输出 -> 传感器数据已进入脑端
   - `controller` 有输出 -> setpoint->cmd 闭环正常
   - `decision` 输出行为树快照 -> 决策链未停止

3. 关键字段检查
   - `decision_node` 中 `confidence` 与 `battery_low`/`anomaly` 等为稳态值
   - `goal_speed`/`goal_depth` 与 `mode` 一致

4. 终端退出信号
   - log 末尾出现 `SIGINT` / `process has finished cleanly` -> 常规中断退出，非崩溃

---

## 四、异常案例与快速定位
1. `bridge` 间断：若 `mean sensor ingress latency` 一直不变或缺失
   - 先看 是否有 `traceback`（zenoh 网络问题）
   - 再看 `run_zenoh_bridge.py` 是否从 sim 拆包成功

2. `localization` 丢数据/延迟变大
   - 检查 `auv_localization_node` 可能输入丢失，探查 `/auv/sensors/imu` `/auv/sensors/dvl` `/auv/sensors/depth`
   - 运行 `ros2 topic hz` 确认频率

3. `controller` 频繁跳闹
   - 说明状态噪声或 setpoint 过快；检查 `/auv/control/setpoint` 和 `/cmd_vel` 频率、值域

4. `decision` `ConfidenceAbove(0.70) [✕]` 不上
   - 若一直在 ZigZagSearch 且 `confidence=0.50`，表示未进入巡检深度逻辑；可对比 `auv_state` 和 `目标点`是否到位。

---

## 五、推荐的可视化监控点（长期）
- 采集 `epoch` 与 `latency` 成为时序曲线
- 用 `ros2 bag` 录一段典型 60s 数据，后续离线分析频率/漂移
- 结合 Foxglove 显示：`/auv/sensors/*` 和 `/cmd_vel`轨迹，查看 ZIGZAG 行为是否符合预期

---

## 六、知识点补充
- 如果后续改动 `scripts/start_lin_sim.sh` 里的 `python` 到 `/usr/bin/python3`，建议在这里也记录版本号（`python3 --version`）与依赖版本。 
- 日志统一可用 `grep -E "bridge|localization|controller|decision" scripts/log/log_example.log` 快速筛选。

