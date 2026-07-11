# 实物部署 — 文档体系 + 静态验证收尾计划

> 范围：完成"实物部署多级实施路径固化"任务的剩余 4 件事——Task #4（`docs/real_deployment/` 9 个文档）、Task #5（`docs/experiment/real_deployment/` 过程记录）、Task #6（已有 INDEX/README 交叉链接）、Task #7（静态 dry-run 验证）。
>
> 上一总结中 Task #1（`_lib.sh` + `00_static_preflight.sh` + `kill_switch.sh` 骨架）、Task #2（5 个阶段 shell `01..05`）、Task #3（3 个 Python 胶水）已完成且经 Phase 1 校验真实在位。本文档仅规划尚未完成的部分。

---

## 1. 摘要

| 维度 | 内容 |
|---|---|
| 本次目标 | 让"代码库可被信任地部署到真实 Jetson"这一目标的**文档面 + 验证面**闭环 |
| 输出文件数 | 9（`docs/real_deployment/`）+ 2~3（`docs/experiment/real_deployment/`）+ 4 处 Append 链接 + 1 个 chmod |
| 是否可逆 | **完全可逆**：除 chmod 外仅新增/Append 文档，不改源码、不改 launch、不改 yaml |
| 三大原则 | ① 完全向后兼容（不动主线 launch/yaml 默认值） ② 静态验证（dry-run + 文档自洽） ③ mock AMD 验证（默认 `--target mock`） |

---

## 2. 当前状态分析（Phase 1 校验结果）

### 2.1 已存在并验证

```
scripts/real_deployment/
├── _lib.sh                 ✅  (rd_require_target / rd_init_run_dir / rd_*)
├── 00_static_preflight.sh  ✅  (colcon + pytest + 协议自检)
├── 01_link_audit.sh        ✅  (vxworks_safety_hil --mode auto-udp)
├── 02_static_actuator.sh   ✅  (5 路通道顺序注入 + ESTOP 收尾)
├── 03_shadow_navigation.sh ✅  (passive_mode:=true via launch arg)
├── 04_closed_loop_single.sh✅  (stack + auto_activate + setpoint driver + ESTOP)
├── 05_full_autonomy.sh     ✅  (mock→start_experiment.sh; vxsim/real→stack+bag)
└── kill_switch.sh          ✅  (持续 $CKTH ESTOP 帧 @ 20Hz)

tools/
├── actuator_polarity_recorder.py  ✅  (UDP 145B uplink → CSV，无 ROS 依赖)
├── shadow_diff_recorder.py        ✅  (rclpy 订阅 shadow_*，无 rclpy 时 SKIP)
└── single_setpoint_driver.py      ✅  (rclpy 发 Setpoint，无 rclpy 时 SKIP)
```

参数风格统一为 `--target {mock,vxsim,real}` + `--duration` + `--dry-run` + `--i-have-physical-auv`。日志统一落 `log/real_deployment/{ts}_{stage}_{target}/`。

### 2.2 已存在但与本任务相关需要被链接进来的文件

| 路径 | 用途 | 本计划的动作 |
|---|---|---|
| [docs/INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/INDEX.md) | 文档总入口（明/暗双线） | Append "实物部署"段 |
| [docs/user-guide/INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/user-guide/INDEX.md) | 明线索引 | Append 跳转到 `real_deployment/INDEX.md` |
| [docs/user-guide/08_real_hardware_sop.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/user-guide/08_real_hardware_sop.md) | 既有真机迁移 SOP | 顶部 Append "更详细的五阶段路线图" 一段 |
| [README.md](file:///home/auv_user/auv_ws/AUV-Master-Project/README.md) | 仓库首页 | 末尾 Append "Real Deployment" 一行 |
| [docs/experiment/benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md) | 过程日志样板（用户指定参考格式） | 仅作为格式参考，不修改 |

### 2.3 重要依据资产（标准文档/）

中文目录名 Glob 不识别，但 `ls` 验证存在 `标准文档/`：包含 `自主式水下航行器设计方案2021.5.28.md`、`软件通信协议.md`、`VxWorks最新协议.md`、`DLT+1278—2025+海底电力电缆运行规程.pdf`。文档 `00_principles.md` / `05_stage5_full_autonomy.md` 会以 markdown link 引用其相对路径 `../../标准文档/...`。

---

## 3. 提议变更（What / Why / How）

### 3.1 chmod +x（一次性收尾，与 Task #3 配套）

| 文件 | 命令 | 原因 |
|---|---|---|
| `tools/actuator_polarity_recorder.py` | `chmod +x` | shebang 是 `#!/usr/bin/env python3`，方便直接 `./tools/...` 调用 |
| `tools/shadow_diff_recorder.py` | `chmod +x` | 同上 |
| `tools/single_setpoint_driver.py` | `chmod +x` | 同上 |

> 不改文件内容，仅改文件权限。**完全向后兼容**：Python 脚本以 `python3 tools/x.py` 调用方式继续可用，shell 脚本里也都是这种调用方式。

### 3.2 `docs/real_deployment/` 文档体系（9 个新文件）

| # | 文件 | 角色 / 内容要点 |
|---|---|---|
| 1 | `INDEX.md` | 总入口：阅读顺序图、五阶段串图、与 `08_real_hardware_sop.md` 的关系（"详尽路线图" vs "简表"）、与 `docs/experiment/real_deployment/` 的关系（"SOP" vs "过程日志"）、最小启动命令、急停说明 |
| 2 | `00_principles.md` | 三大战术（Shadowing / 协议单元化 / 数据黑匣子）+ 三大架构智慧（Hardware Interface 隔离层 / Kill-Switch / Sequence Number）+ 本次会话三原则（向后兼容 / 静态验证 / mock 验证）+ 引用 `标准文档/` 三份原始件 |
| 3 | `01_stage1_link_audit.md` | S1 SOP：网络拓扑表（PC=192.168.0.11 / VxWorks=192.168.0.101 / 端口 21/52364/52365/52367）+ 命令清单 + 通过判据 + 故障树（uplink 0 帧、p95>500ms、scale 不匹配）+ 失败修复建议 |
| 4 | `02_stage2_static_actuator.md` | S2 SOP：5 路顺序、每路推荐采样时长、ENTER 确认机制（real）、报告解读（极性符号 + 死区 RPM）+ 把结果填回 `sim_holoocean/configs/physics_config.yaml` 与 `params.protocol_udp_arbiter.yaml` 的明确字段映射 + 故障树 |
| 5 | `03_stage3_shadow_navigation.md` | S3 SOP：`passive_mode:=true` 含义 + bridge 节点 shadow 话题 + RMSE 阈值（航向 10°、深度 0.5m）+ EKF Q/R 调参方法 + 修复建议 |
| 6 | `04_stage4_closed_loop_single.md` | S4 SOP：`Setpoint` 字段含义 + AutonomyGuard 心跳 + 超调判定 + Set_Course 变化率限幅 + 单回路 PID 调参 |
| 7 | `05_stage5_full_autonomy.md` | S5 SOP：行为树释放、ros2 bag、DLT+1278 巡检剖面对接（最小映射表）、序号对齐丢包诊断 |
| 8 | `06_kill_switch.md` | 急停 SOP：何时按 + 持续多久 + 与 VxWorks 失联保险的"双保险"分工 + 真机测试方法（先 mock，再 vxsim，最后 real） |
| 9 | `07_param_diff_sim_vs_real.md` | 参数差异速查（仿真 vs 真机；从 `08_real_hardware_sop.md` 现有表格扩展）+ 五阶段每阶段需要核对的参数集合（依阶段递增） |

**Why 9 个文件而不是单文件**：
- 用户明确要求"不止一个文档，而是文档体系"；
- 每阶段一个 SOP 是"指尖即用"的最小单元；
- 文档体系里每篇 < 200 行，新手照单执行；
- 每个 shell 在自己 `--help` 里都引用对应 `docs/real_deployment/0X_*.md` 路径——已写在脚本里（见 `01_link_audit.sh:21` "见 docs/real_deployment/01_stage1_link_audit.md"）。

**How（统一规范）**：
- 每个阶段文档结构一致：① 目的 ② 前置条件（上阶段 passed.flag） ③ 命令清单 ④ 通过判据 ⑤ 失败回退 ⑥ 修复建议表（Symptom → Likely Cause → Fix Step） ⑦ 与 standard 文档/源码 link
- 所有源码引用使用 markdown 文件链接 `[stem](file:///...)` 格式；指令为可粘贴的 fenced bash code blocks
- 所有路径以 `/home/auv_user/auv_ws/AUV-Master-Project/...` 绝对路径开头，避免歧义

### 3.3 `docs/experiment/real_deployment/` 过程记录（2 个新文件）

| # | 文件 | 角色 |
|---|---|---|
| 1 | `INDEX.md` | 过程日志索引：用途说明（"新手照命令复现" + "格式参考 `benchmark_test_log.md`"）、阅读顺序、待补 demo 清单 |
| 2 | `00_dryrun_log.md` | **本次会话** Task #7 的 dry-run 过程实录：`bash 00..05 --target mock --dry-run` 输出、`--help` 输出、关键行确认的 grep 命令、发现的偏差与修正项 |

> 第三个文件 `01_vxsim_handover_log.md` **不在本次范围**：留作未来"接 csd_vx6.8_vxsim 实跑"那一刻的占位（在 INDEX.md 里说明）。理由：本次没有实物，且 vxsim 实跑会改 vxsim 二进制路径——超出本对话三原则。

**格式契约**：严格仿照 [benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md) —— 顶部 `日期` `目的`，每步 `## Step N: <动作>`，每步 `命令`/`结果`/`注意事项` 三段。

### 3.4 既有 INDEX/README 交叉链接（4 处 Append）

| 文件 | Append 内容 | 位置 |
|---|---|---|
| [docs/INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/INDEX.md) | 在"明线 — 使用者指南"段落末尾追加：`- [real_deployment/INDEX.md](real_deployment/INDEX.md) — 实物部署五阶段 SOP 体系（更详尽的真机路线图）` | 第 30 行后 |
| [docs/user-guide/INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/user-guide/INDEX.md) | 在表格末尾追加一行：`\| 11 \| [../real_deployment/INDEX.md](../real_deployment/INDEX.md) \| 实物部署详尽路线图（5 阶段 SOP + dry-run 验证） \|`；并在"建议阅读顺序"末尾加 `6. 准备真机部署进入新阶段时，详尽路线图见 ../real_deployment/INDEX.md` | 表格 `08` 行后 + 阅读顺序末 |
| [docs/user-guide/08_real_hardware_sop.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/user-guide/08_real_hardware_sop.md) | 在文件最顶部"# 真机迁移SOP"标题之后、"---"之前追加：一段 4-5 行的引用，指向 `../real_deployment/INDEX.md`，说明 08 是"6 步速记表"，那边是"5 阶段详尽 SOP" | 第 4 行（"从仿真..."后） |
| [README.md](file:///home/auv_user/auv_ws/AUV-Master-Project/README.md) | 末尾追加一段："## Real Deployment" + 一行链接 `详尽五阶段 SOP 见 [docs/real_deployment/INDEX.md](docs/real_deployment/INDEX.md)；过程日志见 [docs/experiment/real_deployment/](docs/experiment/real_deployment/)` | 文件末 |

> **每处都仅是 Append 或在固定锚点插入小段**，不会改变既有内容含义；老链接不动；老用户不感知。

---

## 4. 假设与决策（决策完整，执行无歧义）

| # | 决策 | 备选 | 选择理由 |
|---|---|---|---|
| D1 | 9 个 SOP 文档全放 `docs/real_deployment/` 平铺，不开子目录 | 按 `stage_1/`、`stage_2/` 分目录 | 平铺更便于 cross-link 与新手扫一眼，9 个还在可控范围内 |
| D2 | `docs/experiment/real_deployment/` 本次只产 2 个文件，第 3 个占位 | 一次性产 3 个 | 没实物 → vxsim/real 实跑日志不能虚构。占位说明引导未来补 |
| D3 | chmod +x 只对 3 个新 tools；shell 已 chmod 不再动 | 一并对所有 shell 重新 chmod | 已经在前几个 task 里 chmod 过；最小动作原则 |
| D4 | INDEX 链接策略：明线 `docs/INDEX.md` + `user-guide/INDEX.md` 都加；暗线 `internals/INDEX.md` 不加 | 也加 internals | 实物部署属于"使用者指南"明线范畴，不是内部原理；保持双线职责 |
| D5 | `08_real_hardware_sop.md` **不重写**，仅顶部加引用段 | 重写让其指向新文档 | 三原则之一：完全向后兼容。已有锚点不变，新增正交 |
| D6 | 文档语言：中文为主，命令/字段名英文 | 全英文 / 全中文 | 与 `benchmark_test_log.md`、`08_real_hardware_sop.md` 一致 |
| D7 | dry-run 验证策略：只跑 `S0..S5 --target mock --dry-run` 与 `--help`，不真启 mock AMD | 顺手跑一次 mock 实跑 | 三原则之二：静态验证。实跑应放在 task #7 之外的"用户照 SOP 做的第一次复现"里 |
| D8 | 文档不内嵌过长代码片段，所有命令以 fenced block 给出 | 把脚本核心代码贴进文档 | 一处真实=脚本本身；文档过期是最大的负债 |
| D9 | 标准文档引用走相对路径 `../../标准文档/x.md` | 绝对路径 / Web URL | 仓库内引用最稳；中文目录名在 markdown link 里需 URL-encode；本计划使用裸 markdown link，渲染端会处理 |
| D10 | `csd_vx6.8_lastest`（用户原文）= `csd_vx6.8_vxsim`（仓库实存） | 等待用户给出真实 lastest 路径 | 用户会话内部已多次确认 vxsim 是当前 VxWorks 替身；`csd_vx6.8_lastest` 在仓库中是 700 权限的另一目录（`drwx------`），通常即同一份代码不同副本 |

---

## 5. 验证步骤（Task #7 内容预演）

执行计划落地时，在 Task #7 阶段会**实际**跑一次以下命令，并把结果记入 `docs/experiment/real_deployment/00_dryrun_log.md`。本计划仅声明命令清单：

```bash
# 5.1 帮助文本完整性
bash scripts/real_deployment/00_static_preflight.sh --help || true   # 没 --help 就 sed 自助
bash scripts/real_deployment/01_link_audit.sh --help
bash scripts/real_deployment/02_static_actuator.sh --help
bash scripts/real_deployment/03_shadow_navigation.sh --help
bash scripts/real_deployment/04_closed_loop_single.sh --help
bash scripts/real_deployment/05_full_autonomy.sh --help

# 5.2 mock + dry-run（不会真启动子进程）
bash scripts/real_deployment/00_static_preflight.sh --dry-run
bash scripts/real_deployment/01_link_audit.sh --target mock --duration 5 --dry-run
bash scripts/real_deployment/02_static_actuator.sh --target mock --duration 10 --dry-run
bash scripts/real_deployment/03_shadow_navigation.sh --target mock --duration 5 --dry-run
bash scripts/real_deployment/04_closed_loop_single.sh --target mock --duration 5 --dry-run
bash scripts/real_deployment/05_full_autonomy.sh --target mock --duration 5 --dry-run

# 5.3 安全闸：real 必须配 --i-have-physical-auv
bash scripts/real_deployment/01_link_audit.sh --target real --dry-run    # 期望非零退出，错误信息明确

# 5.4 Python 工具帮助
python3 tools/actuator_polarity_recorder.py --help
python3 tools/shadow_diff_recorder.py --help
python3 tools/single_setpoint_driver.py --help

# 5.5 向后兼容性
git diff --stat HEAD -- brain_linux/launch/ brain_linux/config/ scripts/start_experiment.sh scripts/start_lin_brain.sh
# 期望：launch/yaml/主线脚本 0 改动
```

通过判据：
- 5.1：每个 shell 输出包含 "用法" 或 "Stage S" 字样
- 5.2：每个 shell 退出码 0；最后一行包含 `[dry-run] skipping pass criteria` 或 `S0 static preflight PASSED`
- 5.3：退出码非 0，stderr 含 "requires explicit --i-have-physical-auv"
- 5.4：3 个工具都在帮助文本里出现 `--csv` `--duration`
- 5.5：diff 输出空白

---

## 6. 实施顺序（决策完整，可一次性 todo 化）

| 步 | 动作 | 产物 | 依赖 |
|---|---|---|---|
| 1 | `chmod +x` 3 个 Python tools | 权限位 | — |
| 2 | 写 `docs/real_deployment/INDEX.md` | 总入口 | — |
| 3 | 写 `docs/real_deployment/00_principles.md` | 原则页 | step 2 |
| 4 | 写 `docs/real_deployment/01_stage1_link_audit.md` | S1 SOP | step 3 |
| 5 | 写 `docs/real_deployment/02_stage2_static_actuator.md` | S2 SOP | step 4 |
| 6 | 写 `docs/real_deployment/03_stage3_shadow_navigation.md` | S3 SOP | step 5 |
| 7 | 写 `docs/real_deployment/04_stage4_closed_loop_single.md` | S4 SOP | step 6 |
| 8 | 写 `docs/real_deployment/05_stage5_full_autonomy.md` | S5 SOP | step 7 |
| 9 | 写 `docs/real_deployment/06_kill_switch.md` | 急停 SOP | step 8 |
| 10 | 写 `docs/real_deployment/07_param_diff_sim_vs_real.md` | 参数差异速查 | step 9 |
| 11 | 写 `docs/experiment/real_deployment/INDEX.md` | 过程索引 | step 10 |
| 12 | 跑 §5 命令清单，落 `docs/experiment/real_deployment/00_dryrun_log.md` | dry-run 记录 | step 11 |
| 13 | Append 4 处交叉链接（INDEX/README/08） | 入口闭环 | step 12 |
| 14 | 最终 git status + 自检（不 commit） | 列出改动文件 | step 13 |

> Step 1-13 均为新增/Append；Step 14 仅 `git status`（只读）。

---

## 7. 范围外（Out of Scope）

明确**不做**：
1. 不修改任何 launch / yaml / 既有 .py 源码；
2. 不重写 `08_real_hardware_sop.md`，只在顶部 Append 引用；
3. 不接 `csd_vx6.8_vxsim` 真启动（无设备无意义；Task #7 只 dry-run）；
4. 不补 `docs/experiment/real_deployment/01_vxsim_handover_log.md`（仅占位说明）；
5. 不 commit、不 push（用户未要求）；
6. 不在 `docs/internals/` 下加任何文件（实物部署是明线职能）；
7. 不动 `console_soft/csharp` 的任何路径（用户已声明被 PySide6 取代，老路径继续保留以历史兼容）。

---

## 8. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| `中文目录名` 在 markdown link 里渲染失败 | 低 | 链接断 | 用相对路径 `[标准文档](../../标准文档/...)`；多数 markdown 渲染器 URL-encode 处理；万一断在仓库内仍可定位 |
| dry-run 跑出来的 shell 退出码非 0 | 中 | Task #7 不通过 | 将偏差写进 `00_dryrun_log.md` 的"修正项"段；不回头改 shell（除非是 critical bug） |
| 既有 INDEX append 写错 markdown 表格分隔符 | 低 | 表格塌 | 严格按现有 INDEX 的列宽与对齐字符插入；新行 cat 后 grep 验证 |
| 文档过长 | 中 | 新手不读 | 每篇硬上限 200 行；超长则拆 |

---

## 9. 验收清单（执行完毕时自查）

- [ ] 9 个 `docs/real_deployment/*.md` 全部存在
- [ ] `docs/experiment/real_deployment/INDEX.md` + `00_dryrun_log.md` 存在
- [ ] 4 处 Append 完成且不破坏既有锚点
- [ ] `chmod +x` 三个 Python tools，`ls -l` 出现 `x` 标记
- [ ] §5 全部命令跑过；每个的输出/退出码记录在 `00_dryrun_log.md`
- [ ] `git status -uno -- brain_linux/launch brain_linux/config scripts/start_*.sh` 输出为空（向后兼容证据）
- [ ] 每个 SOP 文档底部有"修复建议表"
- [ ] 每个 stage shell 的 `--help` 输出在 INDEX 中可被正向找到
- [ ] 主线 README 末尾出现"Real Deployment"段
