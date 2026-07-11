# 实物部署 — 五阶段渐进部署管线 实施计划

> 目标：将 Jetson 上的决策栈从 mock AMD 平稳迁移到真实 PC104+VxWorks AUV，**全程向后兼容、可静态验证、可 mock 验证**。
> 上下文文档：[`docs/user-guide/08_real_hardware_sop.md`](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/user-guide/08_real_hardware_sop.md)、[`docs/architecture/protocol_udp_pipeline.md`](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/architecture/protocol_udp_pipeline.md)（如存在）、`标准文档/软件通信协议.md`、`标准文档/自主式水下航行器设计方案2021.5.28.md`、`标准文档/VxWorks最新协议.md`、`标准文档/DLT+1278—2025+海底电力电缆运行规程.pdf`。

---

## 1. 摘要

把用户给出的【五阶段部署路线图 + 三大架构智慧】固化为一组**显式 shell + Python 胶水 + 文档/SOP**，每个阶段都：

1. 有独立的 `scripts/real_deployment/0X_*.sh` 入口；
2. 接受统一参数 `--target {mock,vxsim,real} [--dry-run] [--i-have-physical-auv] [--duration N]`；
3. 默认 `--target mock`，`--target real` 必须显式 `--i-have-physical-auv`，否则脚本立即拒绝；
4. 透明输出：所有 stdout/stderr 落 `log/real_deployment/<TS>_<stage>_<target>/`，并附 `metadata.txt`、`passed.flag`；
5. 通过判据写入 `passed.flag`；下一阶段会软警告（不阻塞）但提示先跑前一阶段；
6. 文档双轨：`docs/real_deployment/`（SOP 文档体系）+ `docs/experiment/real_deployment/`（执行/探索日志）。

**严格遵循三原则**：(1) 不修改任何现有 launch/节点默认行为；(2) S0 阶段静态验证（colcon build + pytest + 协议自检）；(3) 默认 target=mock，全程可在没有真实 AUV 的环境下完成除 S5-real 外的所有验证。

---

## 2. 现状分析（Phase 1 探索结果）

| 资产 | 路径 | 在新管线中的角色 |
|---|---|---|
| 协议二进制库 | [`brain_linux/src/auv_bridge/auv_bridge/protocol.py`](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_bridge/auv_bridge/protocol.py)（含 `build_downlink_packet` / `parse_uplink_packet`） | 直接 import 生成 $CKTH 帧 |
| Mock AMD 服务端 | [`sim_holoocean/interfaces/mock_amd_server.py`](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/mock_amd_server.py) | S0/S1/S2/S3/S4-mock 的对端 |
| VxWorks 仿真目录 | [`csd_vx6.8_vxsim/`](file:///home/auv_user/auv_ws/AUV-Master-Project/csd_vx6.8_vxsim) | `--target vxsim` 时作为 mock AMD 的替代对端（**用户口中的 csd_vx6.8_lastest 就是它**） |
| Bridge passive_mode | [`brain_linux/src/auv_bridge/auv_bridge/bridge_node.py`](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_bridge/auv_bridge/bridge_node.py)（参数 `passive_mode`、`shadow_cmd_topic`、`shadow_telemetry_topic`） | S3 影子导航直接使用 |
| 真机 arbiter 配置 | [`brain_linux/config/params.protocol_udp_arbiter.yaml`](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/params.protocol_udp_arbiter.yaml) | S3/S4/S5 默认 profile |
| Stack launch | [`brain_linux/launch/auv_arbiter_stack.launch.py`](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/launch/auv_arbiter_stack.launch.py) | 五阶段共用 launch |
| 自动激活 0xEE | [`scripts/auto_activate_emu.py`](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/auto_activate_emu.py) | S4/S5 解锁 AutonomyGuard |
| UDP 日志接收 | [`scripts/log_receiver.py`](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/log_receiver.py) | 全阶段后台抓 PC104 UDP printf |
| VxWorks HIL | [`scripts/vxworks_safety_hil.py`](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/vxworks_safety_hil.py) | **S1 直接征用其 `--mode auto-udp`**，无需重写 |
| 手动 $CKTH 注入 | [`tools/manual_protocol_injector.py`](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/manual_protocol_injector.py) | S2 直接征用 |
| 实验主入口 | [`scripts/start_experiment.sh`](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment.sh) + [`scripts/start_lin_brain.sh`](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_lin_brain.sh) | S5-mock 直接复用 |
| ESTOP 单元测试 | [`brain_linux/src/auv_bridge/test/test_estop_safety_lock.py`](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_bridge/test/test_estop_safety_lock.py) | S0 第二步 pytest 包含 |
| 现有 SOP | [`docs/user-guide/08_real_hardware_sop.md`](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/user-guide/08_real_hardware_sop.md) | 在新文档体系中作为单页"快速版"，新文档体系是其逐阶段展开版 |
| 已落盘骨架 | [`scripts/real_deployment/_lib.sh`](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/real_deployment/_lib.sh)、[`scripts/real_deployment/00_static_preflight.sh`](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/real_deployment/00_static_preflight.sh)、[`scripts/real_deployment/kill_switch.sh`](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/real_deployment/kill_switch.sh) | 上一会话已写入 — 本计划只新增 S1-S5 与文档 |
| 物理参数源 | `标准文档/自主式水下航行器设计方案2021.5.28.md` | S2/S3 文档中的极性/质量/推力极限抄录此处 |
| 通信协议源 | `标准文档/软件通信协议.md`、`标准文档/VxWorks最新协议.md` | S1 字节序/缩放因子表格抄录此处 |
| 任务规程源 | `标准文档/DLT+1278—2025+海底电力电缆运行规程.pdf` | S5 全自主巡检策略锚点 |

**结论**：90 % 工程能力已经存在；本计划主要做"组装与暴露"，几乎不写新算法，只写：
- 5 个 shell（S1-S5）
- 3 个轻量 Python 胶水（极性记录器 / shadow diff / single-setpoint driver）
- 9 篇文档
- 3 篇实验日志

---

## 3. 提议变更（Decision-Complete 清单）

### 3.1 新建 shell 入口（5 个）

| 文件 | 阶段 | 行为 |
|---|---|---|
| [`scripts/real_deployment/01_link_audit.sh`](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/real_deployment/01_link_audit.sh) | S1 通信协议与时钟审计 | 1) 拉起 `log_receiver.py`；2) 若 target=mock 拉起 `mock_amd_server`；3) 调 `vxworks_safety_hil.py --mode auto-udp` 跑 30s；4) 解析输出抽取（字节序、$AUV 帧间隔均值/p95、双向握手 0xEF 反馈）写 `report.md`；5) 通过则 `mark_stage_passed`。 |
| [`scripts/real_deployment/02_static_actuator.sh`](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/real_deployment/02_static_actuator.sh) | S2 全静态硬件自检（上架不入水） | 交互式 prompt 用户启用：`thrust`/`rudder_left`/`rudder_right`/`rudder_top`/`rudder_bottom`，每路用 `tools/manual_protocol_injector.py` 发斜坡（0→±0.3→0），同时启动 `tools/actuator_polarity_recorder.py` 记录 `Real_Pose` 反馈方向 → 输出 polarity 表 + deadzone 推荐值（写 `report.md`）。`--target real` 强制要求 `--i-have-physical-auv` 且必须人工 ENTER 确认每路。 |
| [`scripts/real_deployment/03_shadow_navigation.sh`](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/real_deployment/03_shadow_navigation.sh) | S3 影子导航 | 调 `start_lin_brain.sh stack --arbiter-profile`，**通过环境变量 `AUV_BRIDGE_PASSIVE_MODE=true` 让 launch 把 bridge.passive_mode 设为 true**（不修改 launch 默认值，只在本 shell 内 export）；同时启动 `tools/shadow_diff_recorder.py` 订阅 `shadow_cmd` 与上位机回放的 `Real_Pose`，每秒打印跟踪误差。运行 `--duration` 秒后停。 |
| [`scripts/real_deployment/04_closed_loop_single.sh`](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/real_deployment/04_closed_loop_single.sh) | S4 单回路闭环 | 关闭 passive，启动 stack，调 `auto_activate_emu.py` 解锁 0xEE/0xEF；调 `tools/single_setpoint_driver.py` 以**恒定深度+恒定航向**形式发 `goal`（不走行为树），运行 `--duration`；末尾打印超调/稳态误差/响应时间。 |
| [`scripts/real_deployment/05_full_autonomy.sh`](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/real_deployment/05_full_autonomy.sh) | S5 全自主巡检 | mock 路径直接 `bash start_experiment.sh --sim-backend pvs --bridge-backend protocol_udp --auto-activate --duration $DURATION`；vxsim/real 路径走 `start_lin_brain.sh stack --arbiter-profile` + `auto_activate_emu.py` + `ros2 bag record -a`。 |

所有 5 个 shell 都：
- `source _lib.sh`、`rd_require_target`、`rd_require_real_confirm`、`rd_init_run_dir`、`rd_install_cleanup_trap`、`rd_assert_prev_stage_done <prev>`、（运行）、`rd_mark_stage_passed`；
- 支持 `--dry-run`：只打印将执行的命令，不真正启动；
- 支持 `--help`：列参数 + 通过判据 + 失败回退步骤。

### 3.2 新建 Python 胶水（3 个，每个 < 200 行）

| 文件 | 角色 |
|---|---|
| [`tools/actuator_polarity_recorder.py`](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/actuator_polarity_recorder.py) | 订阅 `rt/protocol_uplink_state`（或 ROS2 话题 `/auv/raw_state`），与 S2 注入命令做相关，输出每路执行器的极性符号（+/-）与最小启动阈值（deadzone）。 |
| [`tools/shadow_diff_recorder.py`](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/shadow_diff_recorder.py) | 订阅 `bridge.shadow_cmd_topic` 与上位机回放的真实 `Real_Pose`/`Set_*`，每秒打印 `(t, jetson_cmd, human_cmd, |diff|)` 并存 CSV。 |
| [`tools/single_setpoint_driver.py`](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/single_setpoint_driver.py) | 以恒定 `set_depth`/`set_heading`/`set_speed` 通过决策栈"goal"接口发布，便于 S4 跑超调/稳态误差测试。 |

### 3.3 新建文档体系 `docs/real_deployment/`（9 篇）

| 文件 | 内容 |
|---|---|
| `docs/real_deployment/INDEX.md` | 总入口：阅读顺序、五阶段串图、与 `docs/user-guide/08_real_hardware_sop.md` 的关系 |
| `docs/real_deployment/00_principles.md` | 三战术原则（影子/单元化/黑匣子）+ 三架构智慧（隔离层 / 急停 / 序号对齐）+ 三本会话原则（向后兼容/静态验证/mock 验证） |
| `docs/real_deployment/01_stage1_link_audit.md` | S1 SOP：连线图、参数表、字节序检查清单（抄 `标准文档/软件通信协议.md`）、通过判据、典型故障树 |
| `docs/real_deployment/02_stage2_static_actuator.md` | S2 SOP：上架安全清单、5 路执行器逐项注入步骤、polarity/deadzone 录入到 `physics_config` 的字段映射、AUV 物理参数（抄 `标准文档/自主式水下航行器设计方案2021.5.28.md`） |
| `docs/real_deployment/03_stage3_shadow_navigation.md` | S3 SOP：passive_mode 启用方式、人控流程、跟踪误差判据、Q/R 协方差再标定建议 |
| `docs/real_deployment/04_stage4_closed_loop_single.md` | S4 SOP：单回路定深/定向闭环、超调/稳态误差判据、Set_Course 变化率限幅参考 |
| `docs/real_deployment/05_stage5_full_autonomy.md` | S5 SOP：行为树激活、ros2 bag 录制、`DLT+1278—2025` 工程规程对接（巡检剖面、应急上浮、避障） |
| `docs/real_deployment/06_kill_switch.md` | 急停脚本三种触发方式（GUI 热键 / SIGUSR1 / 直接 kill_switch.sh）、AMD 失联保护机制说明（1s 内本地 ESTOP） |
| `docs/real_deployment/07_param_diff.md` | 仿真参数 vs. 实机参数差异清单（推力曲线、舵机时延、磁干扰、DVL 分辨率），列出每项需要在哪个阶段被回填到哪个 yaml |

### 3.4 新建实验日志 `docs/experiment/real_deployment/`（3 篇）

格式严格参照 [`docs/experiment/benchmark_test_log.md`](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md)（Step 标题 + 命令块 + 结果 + 注意事项）。

| 文件 | 内容 |
|---|---|
| `docs/experiment/real_deployment/INDEX.md` | 索引 |
| `docs/experiment/real_deployment/00_dryrun_log.md` | 在没有真实 AUV 的开发机上跑 5 阶段 `--dry-run` + S0/S1/S5 `--target mock` 的全过程命令与结果；新手照抄即可。 |
| `docs/experiment/real_deployment/01_vxsim_handover_log.md` | 用 `csd_vx6.8_vxsim` 替换 mock_amd_server 的 handover 试验（命令 + 抓取的字节序/帧间隔/握手反馈，作为后续与真机对比的基线）。 |

### 3.5 关联现有文档（仅追加链接、不破坏既有内容）

- 在 [`docs/INDEX.md`](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/INDEX.md) 明线 § 中追加一行指向 `docs/real_deployment/INDEX.md`；
- 在 [`docs/user-guide/INDEX.md`](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/user-guide/INDEX.md) 把 08 章节的描述行追加 "→ 详细五阶段流程见 docs/real_deployment/"；
- 在 [`docs/user-guide/08_real_hardware_sop.md`](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/user-guide/08_real_hardware_sop.md) 顶部加一句 "本页是单页速查；逐阶段展开版见 docs/real_deployment/"；
- 不动 `README.md` 主体，仅在文档导航段尾加一行指向 `docs/real_deployment/INDEX.md`。

---

## 4. 关键决策（Assumptions & Decisions）

| # | 决策 | 理由 |
|---|---|---|
| D1 | 所有新 shell 放在 `scripts/real_deployment/`（独立目录） | 与 `scripts/` 根下已有的 `start_*` 流程区隔，避免误用；可被一行 grep 找到 |
| D2 | 统一 `--target {mock,vxsim,real}` | 一份 shell 三种部署对端；切对端只改一个 flag，符合"隔离层"思想 |
| D3 | `kill_switch.sh` 直接用 UDP 发 ESTOP 帧（不走 ROS2/Zenoh） | 即使决策栈死循环也能触发；与 AMD 1s 失联保险互补 |
| D4 | 不修改 `bridge_node.py` / launch 的默认参数 | 三原则之一"完全向后兼容"；S3 通过 env var 在 shell 内覆盖 |
| D5 | S2 极性测试用 `tools/manual_protocol_injector.py` 而非新写 | 不重复造轮子 |
| D6 | S1 直接征用 `vxworks_safety_hil.py --mode auto-udp` | 该脚本已有完备的 UDP 收发 + 字节序/帧率/握手位检查，复用即可 |
| D7 | 通过判据用 `passed.flag` 文件（不强制阻塞） | 阻塞反而促使新手 hack 绕过；软警告更安全 |
| D8 | 默认 `--target=mock`、`--target real` 强制 `--i-have-physical-auv` | 防止"输错命令把真船开走" |
| D9 | 文档双轨：`docs/real_deployment/` 是 SOP（HOW），`docs/experiment/real_deployment/` 是日志（DID） | 用户明确要求；与 `docs/experiment/benchmark_test_log.md` 体例一致 |
| D10 | "csd_vx6.8_lastest" 实际目录是 `csd_vx6.8_vxsim` | Phase 1 探索发现；所有文档/脚本统一用 `csd_vx6.8_vxsim`，并在 D10 注释中点明这是用户口中的 lastest |
| D11 | 不动主线 launch / 节点 / yaml 默认值 | 避免引入回归；新管线靠 env var + override flag 注入差异 |
| D12 | 不上传到 GitHub Actions / CI；仅本地执行 | 实物部署本身就需要人在场，CI 化没意义 |

---

## 5. 验证步骤（每个阶段都要跑过的命令）

不依赖真实 AUV：

```bash
# 1) 静态自检（colcon build + pytest + 协议自检）
bash scripts/real_deployment/00_static_preflight.sh --dry-run
bash scripts/real_deployment/00_static_preflight.sh

# 2) 五阶段 --dry-run（只打印将执行命令，不启进程）
for s in 01_link_audit 02_static_actuator 03_shadow_navigation 04_closed_loop_single 05_full_autonomy; do
  bash scripts/real_deployment/${s}.sh --dry-run --target mock
done

# 3) 五阶段 --target mock 真跑（每阶段 ≤ 60s，--duration 30）
bash scripts/real_deployment/01_link_audit.sh --target mock --duration 30
bash scripts/real_deployment/02_static_actuator.sh --target mock --duration 30   # 自动跳过交互
bash scripts/real_deployment/03_shadow_navigation.sh --target mock --duration 30
bash scripts/real_deployment/04_closed_loop_single.sh --target mock --duration 30
bash scripts/real_deployment/05_full_autonomy.sh --target mock --duration 30

# 4) 急停脚本验证（mock）
bash scripts/real_deployment/kill_switch.sh --target mock --duration 3

# 5) 向后兼容回归
bash scripts/start_experiment.sh --sim-backend pvs --duration 30          # 旧入口仍可用
bash scripts/start_lin_brain.sh stack --arbiter-profile --duration 30     # 旧入口仍可用
```

判据：
- (1)/(2) 必须 exit 0；
- (3) 每个 stage 在 `log/real_deployment/<TS>_<stage>_mock/` 下生成 `passed.flag`；
- (4) `tcpdump -n -i lo udp port 52364` 能看到周期 50ms 的 72B 包；
- (5) 旧脚本行为与本次提交前完全一致（差异仅来自 `log/` 下新目录）。

---

## 6. Out of Scope（明确不做）

- 不写新的控制算法 / EKF 调参；只暴露阶段化入口供后续调参。
- 不修改 `csd_vx6.8_vxsim/` 下任何 C 源码；它仅作为可选的对端。
- 不引入新的 ROS2 包；新增 Python 胶水放在 `tools/`，按现有惯例为单文件可执行脚本。
- 不创建 README/INDEX 之外的额外索引；不创建任何"summary.md"。
- 不在 CI 上跑实物部署。

---

## 7. 实施顺序（10 步，原子化）

1. ✅ Task #1（已完成上一会话）：`scripts/real_deployment/_lib.sh` + `00_static_preflight.sh` + `kill_switch.sh`。
2. 写 5 个阶段 shell（S1-S5）。
3. 写 3 个 Python 胶水（actuator_polarity_recorder / shadow_diff_recorder / single_setpoint_driver）。
4. 写 `docs/real_deployment/INDEX.md` + `00_principles.md`。
5. 写 `docs/real_deployment/01..05_stage*.md`（5 篇阶段 SOP）。
6. 写 `docs/real_deployment/06_kill_switch.md` + `07_param_diff.md`。
7. 写 `docs/experiment/real_deployment/INDEX.md` + `00_dryrun_log.md` + `01_vxsim_handover_log.md`。
8. 在现有 4 个文档中追加跨链接（INDEX/INDEX/08_sop/README）。
9. 跑 §5 验证步骤的 (1)(2)(4) 全集 + (3) 中至少 S0/S1/S5 真跑（mock）。
10. 提交报告：列出新增/修改文件清单 + 验证产物路径 + 已知风险与下一步。

---

## 8. 风险

| 风险 | 缓解 |
|---|---|
| 用户误用 `--target real` | 必须 `--i-have-physical-auv`；shell 启动横幅红字提示；Kill-Switch 一键即用 |
| `colcon build` 与 conda 干扰 | 复用 `start_lin_brain.sh` 内已有的 `conda deactivate`；S0 输出明确提示 |
| `mock_amd_server` 端口与运行中的旧实验冲突（52364） | `_lib.sh` 启动前 `lsof -i :52364` 检测，占用则 fail-fast |
| 文档与实际 shell 行为漂移 | SOP 文档每节末尾贴一段"对应脚本 + grep 锚点"，便于审计 |
| 用户手头没有真实 AUV 时 plan 不可用 | 默认 mock；S5-mock 等价于现有 `start_experiment.sh`，无需真船 |
| `csd_vx6.8_vxsim` 与真机协议有差 | S1 的 `01_vxsim_handover_log.md` 显式记录字节序/帧率基线，作为后续 diff 锚 |

---

## 9. 验收清单

- [ ] `scripts/real_deployment/{01..05}_*.sh` + `_lib.sh` + `00_static_preflight.sh` + `kill_switch.sh` 全部存在且 `+x`；
- [ ] `tools/{actuator_polarity_recorder,shadow_diff_recorder,single_setpoint_driver}.py` 全部存在且 `python3 file.py --help` 正常；
- [ ] `docs/real_deployment/` 9 篇 + `docs/experiment/real_deployment/` 3 篇全部存在；
- [ ] §5 验证步骤 (1)(2)(4) 全部 exit 0；(3) 中 S0/S1/S5 至少跑过一次并落 `passed.flag`；
- [ ] `git diff --stat` 中**没有**对 `brain_linux/launch/`、`brain_linux/src/`、`brain_linux/config/`、`scripts/start_*.sh`、`README.md` 主体的修改（只允许追加链接行）；
- [ ] 所有新增文档至少在一处被现有 INDEX/README 反向链接到。
