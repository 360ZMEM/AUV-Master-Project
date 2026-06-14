# 07 — 参数差异速查（仿真 vs 真机）

> 这一页是上电前的"五分钟体检表"。它**不是 yaml 全集**，只列出 **从 mock/HoloOcean 切到 vxsim/real 时容易出问题、且后果严重的参数**，每一行都标注**在哪个文件改、改成什么、谁来核对**。
> 目标读者：从 S3 走到 S4 之前的操作员；以及任何不放心当前 yaml 的人。

---

## 1. 总原则

1. **改 yaml 默认值要谨慎**：仿真默认值和真机默认值不应当**互相覆盖**，应通过 launch 参数（如 `passive_mode:=true`）或独立 yaml 子文件覆盖。
2. **每改一处，记录一条 commit**：commit message 必须包含 "real-deployment param: <参数名>"，便于事后回滚。
3. **每个阶段都有自己的核对清单**（见 §3 五阶段表）。

---

## 2. 关键参数对照表

| 类别 | 参数名 | 仿真默认 | 真机推荐 | 修改位置 | 影响 |
|---|---|---|---|---|---|
| **网络** | AMD_HOST | 127.0.0.1 | 192.168.0.101 | env / launch arg | 全栈下行去向 |
| **网络** | AMD_PORT (下行) | 52364 (mock) | 21 (vxsim/real) | env / launch arg | 下行端口 |
| **网络** | UPLINK_PORT | 52365 | 52365 | 不变 | — |
| **网络** | LOG_RECEIVER_PORT | 52367 | 52367 | 不变 | UDP 日志回流 |
| **协议** | `main_motor_rpm_scale` | 15.0 | 15.0 | `common/protocol.py` | **常量，禁止修改** |
| **协议** | `obj_address` | 1 | 1 | launch arg | 多艇时才改 |
| **桥接** | `passive_mode` | false | **true** (S3) → false (S4+) | launch arg：`passive_mode:=true` | 决定下行是否真实发出 |
| **桥接** | `shadow_cmd_topic` | `/auv/shadow/cmd` | `/auv/shadow/cmd` | yaml | passive_mode 时启用 |
| **桥接** | `shadow_telemetry_topic` | `/auv/shadow/telemetry` | `/auv/shadow/telemetry` | yaml | passive_mode 时启用 |
| **EKF** | 加速度过程噪声 Q | HoloOcean 调好的值 | **真机重新标定** | `localization/config/ekf.yaml` | 状态估计平滑度 |
| **EKF** | 深度计观测噪声 R | 0.05 m² | **0.10–0.20 m²**（真机噪声大） | 同上 | 深度跟踪稳定性 |
| **EKF** | IMU 角速度偏置 | 假设零 | **静置 60s 现场标定** | 同上 | 长时间航向漂移 |
| **控制器** | 深度环 Kp | 仿真整定值 | **首次取仿真的 50%** | `controller/config/cascade_pid.yaml` | 超调与振荡 |
| **控制器** | 航向环 Kp | 仿真整定值 | **首次取仿真的 50%** | 同上 | 航向超调 |
| **控制器** | 推力饱和上限 | ±1.0 (归一化) | **首次 ±0.6** | 同上 | 安全边际 |
| **控制器** | MPC 预测窗 N | 20 | **10**（CPU 受限） | `controller/config/mpc.yaml` | 实时性 |
| **决策** | `AutonomyGuard.timeout_s` | 1.5 | 1.5 | `decision/config/decision.yaml` | 上位机失联硬 ESTOP |
| **决策** | `StandbyCheck.battery_min_v` | 22.0 | **24.0**（真机告警阈值） | 同上 | 进入 AUTO 前置 |
| **仲裁器** | manual injection 优先级 | HIGH | HIGH | 不变 | 决定 PySide6 setpoint 是否被采纳 |
| **bag** | mcap 压缩 | zstd | zstd | launch arg | 录制开销 |
| **bag** | 录制话题 | 全部 | **白名单**（≥10Hz 高频话题除外） | bash 脚本 | 磁盘占用 |

---

## 3. 五阶段每阶段的核对清单

### S1 链路审计（`01_link_audit.sh` 之前）
- [ ] AMD_HOST/PORT 与目标 target 一致（`mock=127.0.0.1:52364` / `vxsim=127.0.0.1:21` / `real=192.168.0.101:21`）
- [ ] PC 网卡 IP=192.168.0.11（real）
- [ ] 标准协议长度常量未被改：`DOWNLINK_LEN==72`、`UPLINK_LEN==145`

### S2 静态执行器极性（`02_static_actuator.sh` 之前）
- [ ] 控制器 `推力饱和上限` 已降为 ±0.6
- [ ] 决策栈未启动（S2 不能跑决策栈，只走 manual_protocol_injector 单路）
- [ ] 急停脚本已自测过本日（见 [`06_kill_switch.md`](06_kill_switch.md) §6）

### S3 影子导航（`03_shadow_navigation.sh` 之前）
- [ ] launch 命令含 `passive_mode:=true`
- [ ] EKF Q/R 参数已根据上次 vxsim 数据更新
- [ ] PySide6 上位机进入 MANUAL 模式
- [ ] `tools/shadow_diff_recorder.py` 输出 csv 路径已分配

### S4 单点闭环（`04_closed_loop_single.sh` 之前）
- [ ] launch 命令**不含** `passive_mode:=true`（即真实发出下行）
- [ ] 控制器 PID Kp 已取仿真值的 50%（首次部署）
- [ ] AutonomyGuard timeout=1.5s 已确认
- [ ] 操作员手指放在急停按钮上

### S5 全自主（`05_full_autonomy.sh` 之前）
- [ ] StandbyCheck.battery_min_v=24.0
- [ ] ros2 bag 输出磁盘 ≥ 10 GB 空闲
- [ ] 行为树/FSM yaml 与上次 vxsim 一致（diff 一遍）
- [ ] DLT+1278 上行帧字段映射已对齐（见 [`05_stage5_full_autonomy.md`](05_stage5_full_autonomy.md) §DLT 表）

---

## 4. "永远不要在真机上改"的参数

以下参数**仅在 mock/vxsim 调试**，**禁止在 real target 现场修改**：

| 参数 | 原因 |
|---|---|
| `main_motor_rpm_scale` | 协议常量，改了所有上行/下行的 motor 字段都会错位 |
| `MAGIC_HEADER` ($CKTH / $AUV) | 协议帧头，改了直接挂 |
| 协议帧 CRC 算法 | 同上 |
| `obj_address` | 多艇协同才用，单艇必须=1 |
| `decision/config/behavior_tree.xml` 的根节点结构 | 真机不是改行为树的地方，先回 vxsim 验证 |

---

## 5. 修改 yaml 的提交流程

```
1. 先在 vxsim target 复现问题（避免凭空改）
2. 在 mock target 跑通新参数
3. git commit -m "real-deployment param: <名称> <旧值> -> <新值>"
4. 在 vxsim target 走完 S0 + S1 + 当前阶段
5. 升 real：对应阶段重新走一遍 SOP
6. 把数据落到 docs/experiment/real_deployment/<run_id>_*.md
```

---

## 6. 关键引用

- 协议常量：[`common/protocol.py`](../../common/protocol.py)
- EKF 配置：[`auv_decision_stack/localization/config/ekf.yaml`](../../auv_decision_stack/localization/config/ekf.yaml)
- 控制器配置：[`auv_decision_stack/controller/config/cascade_pid.yaml`](../../auv_decision_stack/controller/config/cascade_pid.yaml)、`mpc.yaml`
- 决策配置：[`auv_decision_stack/decision/config/decision.yaml`](../../auv_decision_stack/decision/config/decision.yaml)
- 上一文档：[`06_kill_switch.md`](06_kill_switch.md)
- 总入口：[`INDEX.md`](INDEX.md)
- 标准依据：`../../标准文档/AMD通讯协议.pdf` §字段缩放定义

---

## 7. 当前落盘配置区分（2026-06-09 核对）

### 7.1 结论

ROS2 brain stack **不能再只依赖** `brain_linux/config/params.protocol_udp_arbiter.yaml` 这一份文件。实物部署 shell 已按 target 显式选择 `params_file`：

| target | brain params file | 关键差异 |
|---|---|---|
| `mock` | [`brain_linux/config/params.protocol_udp_arbiter.yaml`](../../brain_linux/config/params.protocol_udp_arbiter.yaml) | 仿真/本机默认：`127.0.0.1:52364` |
| `vxsim` | [`brain_linux/config/params.protocol_udp_arbiter.vxsim.yaml`](../../brain_linux/config/params.protocol_udp_arbiter.vxsim.yaml) | VxWorks 仿真：`127.0.0.1:21` |
| `real` | [`brain_linux/config/params.protocol_udp_arbiter.real.yaml`](../../brain_linux/config/params.protocol_udp_arbiter.real.yaml) | 真机：`192.168.0.101:21`，首次部署推力/PID 更保守 |

选择逻辑在 [`scripts/real_deployment/_lib.sh`](../../scripts/real_deployment/_lib.sh) 的 `rd_brain_params_file()`：

1. 若设置 `RD_BRAIN_PARAMS_FILE` 或 `AUV_RD_BRAIN_PARAMS_FILE`，优先使用该显式覆盖；
2. 否则优先使用 `brain_linux/config/params.protocol_udp_arbiter.<target>.yaml`；
3. 如果 target 专属文件不存在，回退到兼容默认 `params.protocol_udp_arbiter.yaml`。

### 7.2 要改哪里

- **只改网络端点**：改对应 target 文件的 `bridge.protocol_udp.remote_host` / `remote_port`。
- **真机首次闭环保守化**：改 `params.protocol_udp_arbiter.real.yaml` 的 `limits.*`、`control.*`、`ekf.*`；不要改 mock 默认文件。
- **vxsim 复现真机端口问题**：改 `params.protocol_udp_arbiter.vxsim.yaml`，不要改 `config/bridge_params*.yaml`。后者是 sim/HoloOcean 侧桥接配置，不是 ROS2 brain stack 的主配置。
- **临时现场覆盖**：用 `RD_BRAIN_PARAMS_FILE=/abs/path/custom.yaml bash scripts/real_deployment/04_closed_loop_single.sh --target real --i-have-physical-auv`，并把该路径写入 run log。

### 7.3 哪些 shell 已显式区分

以下阶段会在启动 brain stack 时传入 `params_file:=...`：

- [`03_shadow_navigation.sh`](../../scripts/real_deployment/03_shadow_navigation.sh) — `passive_mode:=true` + target 专属 params；
- [`04_closed_loop_single.sh`](../../scripts/real_deployment/04_closed_loop_single.sh) — 闭环 stack + target 专属 params；
- [`05_full_autonomy.sh`](../../scripts/real_deployment/05_full_autonomy.sh) — mock 经 `start_experiment.sh --brain-arg params_file:=...`，vxsim/real 直接传 `params_file:=...`。

S1/S2/KS 不启动 ROS2 brain stack；它们只走协议工具或急停帧，因此不需要 brain params file。

### 7.4 S0 dry-run 为什么会落 `passed.flag`

S0 是**静态自检**，不启动网络、推进器或 ROS2 brain stack。它的 dry-run 只把 build/pytest/protocol roundtrip 命令打印出来，随后仍然走到脚本尾部的 `rd_mark_stage_passed`。这和 S1-S5 不同：

- S1-S5 的通过判据依赖真实运行产物（UDP 帧、CSV、bag、RMSE、ESTOP 日志）；
- 因此 S1-S5 在 dry-run 下会执行 `[dry-run] skipping pass criteria`，**不会**写 `passed.flag`；
- 这就是 `00_dryrun_log.md` 里 S2-S5 会看到上一阶段 soft-warning 的原因。

该差异目前是**已知且不阻塞**：S0 dry-run 的 `passed.flag` 只代表静态骨架未崩，不代表任何硬件链路通过。若后续要严格统一语义，可把 S0 dry-run 也改为跳过 `rd_mark_stage_passed`。
