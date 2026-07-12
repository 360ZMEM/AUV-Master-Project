# AGENTS 协作协议

本文件是仓库级 AI/开发者接手协议。任何新会话开始处理本仓库时，先读本文件，再读 `docs/JETSON_DEPLOYMENT_CONTEXT.md`。

## 1. 当前主线

仓库当前主线是 AUV 数字孪生到实物部署的工程链路，其中最重要的阶段性主线是：

```text
PVS/protocol_udp 仿真电缆巡检
  -> ROS2 cable tracking
  -> /auv/control/setpoint
  -> rosbag 取证
  -> DL/T 1278 风格报告
  -> 多 run 聚合验收
  -> distorted-prior 闭环恢复验证
```

Jetson 主线事实入口：`docs/JETSON_DEPLOYMENT_CONTEXT.md`。

## 2. 接手阅读顺序

1. `docs/JETSON_DEPLOYMENT_CONTEXT.md`
2. `README.md`
3. `docs/INDEX.md`
4. `docs/internals/12_cable_tracking_mag_integration.md`
5. `docs/real_deployment/08_cable_inspection_io_contract.md`
6. `docs/thesis/16_cable_dlt1278_scoring_and_operator_products.md`
7. 与当前任务直接相关的脚本或测试

不要先从 `.trae/documents/` 或零散历史日志开始，除非任务明确要求追溯旧计划。

## 3. 工作纪律

- 修改前先读目标文件，确认当前内容和上下文。
- 保持 git working tree 可解释；不要回滚他人改动，不要使用破坏性 git 命令。
- 涉及既有结论时，要区分“证据链打通”“数字孪生 ready/pass”和“真实海缆验收”。
- 文档或代码改动完成后，用 `git diff --stat` 和必要测试给出可审计结果。
- 复杂问题要写清楚 blame：根因属于输入、模型、配置、接口、测试口径还是真实未验证边界。
- 若发现运行证据不足，不要为了结论调整阈值；优先补诊断字段、bag 证据和失败项。

## 4. 主线命令速记

最小 PVS 仿真：

```bash
bash scripts/start_experiment.sh --sim-backend pvs --duration 120
```

电缆巡检验收 run：

```bash
bash scripts/start_experiment.sh \
  --preflight-clean \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --duration 120 \
  --record-bag \
  --bag-profile cable_acceptance \
  --wait-before-record 8 \
  --bag-finalize 15 \
  --brain-arg enable_cable_tracking:=true \
  --brain-arg enable_cable_mission_autostart:=true \
  --brain-arg cable_tracking_config:=/home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/cable_tracking.yaml
```

distorted-prior 闭环恢复：

```bash
bash scripts/run_cable_closedloop_distorted.sh
bash scripts/score_cable_closedloop_recovery_runs.sh
```

单 run 报告链：

```bash
python3 tools/extract_cable_tracking_jsonl.py --bag /auv_data/bags/<TS>/rosbag \
  --output-jsonl results/cable_ops_report/fullflow_<TS>/tracking.jsonl \
  --summary-json results/cable_ops_report/fullflow_<TS>/extract_summary.json

python3 tools/dlt1278_cable_report.py \
  --tracking-jsonl results/cable_ops_report/fullflow_<TS>/tracking.jsonl \
  --output-dir results/cable_ops_report/fullflow_<TS>
```

## 5. 禁止误用的结论

可以说：

- PVS/protocol_udp 数字孪生电缆巡检链路已经能形成 magnetic、tracking、diagnostics、setpoint、bag 和 DL/T 1278 风格产物。
- 在满足磁观测前提的 distorted-prior 数字孪生配置中，在线先验修正已复现 mid/heavy 各 3/3 recovery-gate ready/pass。
- 当前工具链能正确输出 `ready`、`limited`、`invalid`，并通过 failed checks 阻止过度结论。

不能说：

- 已通过真实海缆检测精度验收。
- 在线先验修正可以不经标定和背景场处理直接迁移真机。
- DL/T 风格状态为“正常”就等于工业验收 ready/pass。
- 通过改变窗口或阈值即可把 failed run 解释成 ready。

## 6. 更新规则

当主线命令、验收口径、关键配置或结论边界变化时，同时更新：

1. `docs/JETSON_DEPLOYMENT_CONTEXT.md`
2. 与任务对应的 `docs/internals/`、`docs/thesis/` 或 `docs/real_deployment/` 文件
3. `README.md` 或 `docs/INDEX.md` 的入口索引，如果新增了长期文档

如果只是单次实验记录，优先写入 `docs/experiment/`，不要污染主线入口。
