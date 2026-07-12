# AUV-Master-Project 接手提示词

你正在接手 `/home/auv_dev/AUV-Master-Project`。请先读取：

1. `AGENTS.md`
2. `docs/JETSON_DEPLOYMENT_CONTEXT.md`
3. `README.md`
4. 当前任务直接涉及的源码、脚本和测试

## 当前主线

仓库主线是 AUV 数字孪生、ROS2 决策控制、上位机和真机部署的完整工程链路。近期最重要的上下文是“仿真电缆巡检”和“全链路仿真测试”：

```text
PVS/protocol_udp
  -> magnetic side-channel
  -> ROS2 /auv/sensors/magnetic
  -> cable_tracking_node
  -> AUV-Master-Mag
  -> /auv/cable/tracking + /auv/cable/diagnostics + /auv/control/setpoint
  -> rosbag
  -> DL/T 1278 风格报告
  -> 多 run 聚合验收
```

当前可复用的主线入口：

- 普通仿真：`bash scripts/start_experiment.sh --sim-backend pvs --duration 120`
- 电缆验收 run：见 `docs/JETSON_DEPLOYMENT_CONTEXT.md` 的常用运行命令章节
- distorted-prior 闭环恢复：`bash scripts/run_cable_closedloop_distorted.sh`，随后 `bash scripts/score_cable_closedloop_recovery_runs.sh`
- 报告链：`tools/extract_cable_tracking_jsonl.py`、`tools/dlt1278_cable_report.py`、`tools/plot_cable_tracking_fullflow.py`、`tools/aggregate_cable_acceptance_runs.py`

## 协作要求

- 用中文输出主要结论和计划。
- 先做仓库探索，再修改；不要凭历史记忆直接写。
- 保护现有 working tree，不回滚他人改动。
- 对复杂问题给出 blame 分析，区分根因、证据和未闭合边界。
- 不把数字孪生 ready/pass 写成真实海缆验收通过。
- 如果需要改主线命令、验收口径或关键结论，同时更新 `docs/JETSON_DEPLOYMENT_CONTEXT.md` 和相关索引。

## 诚实边界

在线电缆 tracking 不得消费仿真真值字段。distorted-prior 正结果限定在满足磁观测前提的数字孪生配置、人工静态位姿扭曲、有效巡检窗口和 n=3/档统计下。真机仍需要磁传感器外参、背景场去除、真实噪声、多种子统计和硬件实物证据。
