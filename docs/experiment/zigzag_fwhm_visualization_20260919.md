# Zig-zag、FWHM 与答辩可视化验证（2026-09-19）

## 结论

本轮已把 v2 的真实搜索/横扫规划、磁场观测、海缆位置估计、FWHM 区间、埋深结果和不确定度接入 ROS2/Foxglove。旧版内容均保留，新版使用独立的 `defense-perception-1366` profile 和 `stack-v2` 启动模式。

计划 zig-zag 与实际轨迹偏差的主要原因不是艇体转向能力不足，而是两个软件问题叠加：

1. 旧 `limit_guidance` 把瞬时航向误差直接与单位为 deg/s 的角速度限制比较，没有使用控制周期或历史航向状态。历史回放中 412 个样本有 248 个（60.19%）被此逻辑限幅。
2. v2 叠加启动曾同时运行旧 `decision_node` 和 v2 tracking node，两者共同发布 `/auv/control/setpoint`，控制器收到交替航向目标。

请求轨迹本身处于动力学约束内：1.5 m 振幅、24 m 波长、0.8 m/s 对应峰值航向约 21.44°、精确最小转弯半径约 9.73 m、峰值横向速度约 0.292 m/s；均低于 25°、6 m 和 0.45 m/s 的配置限制。量化报告见 `assets/defense_demo/zigzag_diagnosis.json` 和 `zigzag_diagnosis.png`。

## 实施变更

- v2 启动默认关闭旧决策发布者，v2 成为 cable mission 的唯一 setpoint 所有者；基础 v1 启动保持不变。
- v2 配置只在本 profile 中关闭旧 `auto_limit`，由下层控制器处理实际航向动态；稳定 v1 配置未修改。
- 可视化桥优先显示算法发布的 `active_plan_waypoints_xy_m`，不再用夸张的合成锯齿代替真实计划。
- 新增估计海缆点、2σ 位置环、埋深箭头、磁场矢量、FWHM 跨度、感知标签及相应 typed topics。
- Foxglove 2.44 不再响应旧动态 Markdown schema，因此新版布局改用原生 Indicator、Gauge、Plot 和 3D Marker。

## 实机联合验证

运行目录：`.auv_data/bags/20260919_210509`。

- PVS → protocol UDP → ROS2 → Foxglove WebSocket 全链路运行 210 s。
- `/auv/control/setpoint` 实测发布者数为 1，控制命令竞争已消除。
- Foxglove 实测进入 `CONFIRM · FWHM 横扫`，原生面板订阅位置 X/Y、埋深、磁场、FWHM 和置信度 topic。
- FWHM 自动重扫推进至第 3 次，横扫计划扩为约 40 m；过程中检出峰值 8196.47 nT、半高值 4267.16 nT 和左交点 -8.38 m。
- 210 s 结束时得到宽度 23.71 m，但置信度为 0，估计器没有接受该轮形状，因此没有发布埋深。这一空值是质量门控结果，不是界面缺失。

运行快照见 `assets/defense_demo/fwhm_runtime_probe.json`，实际 1366×900 Foxglove 截图见 `foxglove_defense_perception_1366_live_v2.png`。

## 当前边界与下一步

现有 PVS 磁场曲线和艇体横扫仍会造成单侧交点缺失或形状残差不合格。答辩时可以可靠展示 SEARCH→CONFIRM、重扫范围扩张、磁峰、FWHM 宽度候选和质量拒绝；不得把当前空埋深描述为已完成有效反演。

若需要稳定演示 TRACK 与埋深，应先录制一包能覆盖峰值两侧且通过形状门控的磁场数据，再使用同一布局回放。不要通过硬编码埋深或绕过 `fwhm_valid` 来制造结果。

## 复现

```bash
cd /home/zmem063/AUV-Master-Project
export AUV_DATA_ROOT="$PWD/.auv_data"
scripts/run_defense_perception_1366.sh --duration 210 --no-record-bag
```

Foxglove 连接 `ws://localhost:8765`，导入：

```text
foxglove_layout_project/output/auv_defense_perception_1366.json
```

运行中检查唯一控制发布者：

```bash
source /opt/ros/humble/setup.bash
source brain_linux/install/setup.bash
ros2 topic info /auv/control/setpoint -v
```

离线复算历史偏差：

```bash
python3 tools/analyze_zigzag_tracking.py \
  --input .auv_data/aux-smoke/tracking.jsonl \
  --json-output docs/experiment/assets/defense_demo/zigzag_diagnosis.json \
  --plot-output docs/experiment/assets/defense_demo/zigzag_diagnosis.png
```
