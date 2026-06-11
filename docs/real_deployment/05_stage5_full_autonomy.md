# S5 — 全自主巡检（行为树 + ros2 bag）

> 释放完整 py_trees 行为树，全程录 bag。这是"实物部署"在本仓库范围内的终点，也是与 DLT+1278—2025 工程规程对接的入口。

---

## 1. 目的

- 释放 [auv_decision](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_control/auv_decision_ros) 行为树的 Patrol/CableTracking 任务；
- 全程 `ros2 bag record -a -s mcap`，作为黑匣子；
- 把 `$AUV` 上行帧序号写进 bag，供事后丢包诊断。

---

## 2. 前置条件

| 项 | 要求 |
|----|------|
| S4 通过 | `log/real_deployment/*_S4_closed_loop_single_*/passed.flag` 存在 |
| 调参 | S4 的超调与稳态误差已收敛至阈值内 |
| 任务参数 | 巡检剖面（深度/速度/路径）已在 [scenarios/](file:///home/auv_user/auv_ws/AUV-Master-Project/scenarios/) 下选定 |
| 工程合规 | 与 DLT+1278—2025（在 `标准文档/` PDF）核对作业窗口、上浮策略 |

---

## 3. 命令清单

```bash
cd /home/auv_user/auv_ws/AUV-Master-Project

# mock：直接复用 start_experiment.sh，最大限度复用既有经过验证的栈
bash scripts/real_deployment/05_full_autonomy.sh --target mock --duration 120

# real：栈 + auto_activate + 单独 ros2 bag
bash scripts/real_deployment/05_full_autonomy.sh \
     --target real --duration 300 --i-have-physical-auv

# 干跑
bash scripts/real_deployment/05_full_autonomy.sh --target mock --duration 5 --dry-run
```

mock 路径直接调用 [start_experiment.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment.sh) `--sim-backend pvs --bridge-backend protocol_udp --arbiter-profile --auto-activate --duration N`，等价于 [docs/user-guide/02_experiment_runner.md](../user-guide/02_experiment_runner.md) 描述的最小复现。

vxsim/real 路径走 stack + auto_activate + 单开一个 `ros2 bag record -a -s mcap -o $RUN_DIR/rosbag`，避开 mock 路径里的 `--sim-backend` 假数据源。

---

## 4. 通过判据

- shell 退出码 0；
- `$RUN_DIR/rosbag/*.mcap` 大小 > 0；
- 完成后 `$RUN_DIR/report.md` 列出 bag 路径；
- 行为树无 `StandbyCheck` 卡死（看 `stack.log`）；
- 序号无大间隔跳变（看 [actuator_polarity_recorder.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/actuator_polarity_recorder.py) 写出的 CSV，或离线 grep bag）。

---

## 5. 失败回退

| Symptom | Likely Cause | Fix Step |
|---------|--------------|----------|
| 行为树停在 StandbyCheck | auto_activate 没在跑 | 看 `auto_activate.log`；确认 0xEE 心跳进 bridge |
| MCAP 末尾损坏 | recorder 被 SIGKILL | 已修复在 [start_experiment.sh:176](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment.sh) 改 SIGINT；如自定义请同等处理 |
| AUV 不上浮终止 | 行为树 Abort 条件未触发 | 立刻 kill_switch；查 [docs/internals/INDEX.md](../internals/INDEX.md) 决策章节的 abort guard |
| 序号跳变 | WiFi 弱信号 / AMD CPU 抖 | 把作业区间往天线方向移；或在 PC104 端降低非关键任务优先级 |
| 闭环跑歪 0.5 m+ | EKF 在长航段漂 | S3 重跑取新协方差；或把任务时长拆成多段 |

---

## 6. 实施修复（巡检剖面对接）

1. **最小映射** DLT+1278—2025 → 本仓库：

| 工程规程章节 | 本仓库对应位置 |
|----|----|
| 作业前自检 | S0/S1/S2 |
| 巡检窗口（潮汐/能见度） | 在 `scenarios/<task>.yaml` 的 `mission.window` |
| 应急上浮 | [auv_decision](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_control/auv_decision_ros) 行为树的 `EmergencySurface` 节点 |
| 录像/数据归档 | bag 自动落 `$RUN_DIR/rosbag/`；离线分析见 [04_rosbag_analysis.md](../user-guide/04_rosbag_analysis.md) |
| 事故复盘 | bag + `report.md` + 标准文档 PDF 章节号交叉引 |

2. 序号对齐丢包诊断：把 bag 转 CSV，检查 `$AUV.frame_counter` 差分；超过 `1` 的位置打 ✗。

---

## 7. 关键引用

- [scripts/real_deployment/05_full_autonomy.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/real_deployment/05_full_autonomy.sh)
- [scripts/start_experiment.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment.sh) — mock 路径复用
- [scripts/start_lin_brain.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_lin_brain.sh) — vxsim/real 路径
- [scripts/auto_activate_emu.py](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/auto_activate_emu.py)
- [auv_decision](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_control/auv_decision_ros) — 行为树
- DLT+1278—2025 海底电力电缆运行规程（PDF 在 `标准文档/`）
