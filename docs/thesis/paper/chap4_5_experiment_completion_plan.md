# 第 4/5 章实验完善方案（未完成实验专线）

- 生成时间：`2026-08-06`
- 定位：本文件是"对话分叉后专注未完成实验继续"的产物，是 [experiment_gap_and_next_plan.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/experiment_gap_and_next_plan.md) 的**执行细化版**，不覆盖后者的 P0–P3 矩阵。差异在于：后者按章节列缺口，本文按用户三维度（缺少的 / hack 的 / 深入 probe）逐项给**可执行命令 + 优先级 + 验收标准 + 数据保真边界**。
- 探查范围：第 4 章（决策与控制）、第 5 章（实验与讨论）。
- 数据保真红线（贯穿全文）：仿真 / 台架 / emulated 数据不得表述为实物海试或真机结论；所有新增结论须落在 [rating.md](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/rating.md) A/B/C 三表与 [INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/INDEX.md)"当前不能声称"清单边界内；不为达标调阈值，优先补诊断字段 / bag 证据 / 失败项（遵 [AGENTS.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/AGENTS.md)）。

## 0. 探查结论速览（截至 2026-08-06 的实测状态）

以下为对 `log/thesis_sweep/`（23 个 run）、`log/proxy_cable_sweep/`（3 个 run）、`results/control/`、`results/control_aggregates/`、`tools/` 的实测盘点，是本方案的事实基座：

| # | 事实 | 证据 |
|---|---|---|
| F1 | UA-MPC 敏感度消融（A2/A3/A4）**从未执行**：全部 23 个 thesis_sweep run 的 `manifest.json` 中 `param_grid` 均为 `null`，`sensitivity_summary.md` 从未产出 | `log/thesis_sweep/*/manifest.json` |
| F2 | 代理电缆 6 场景**仅 seed0（n=1）**，无多种子 | `log/proxy_cable_sweep/20260613_182825_cable_proxy_full6_smoke/` |
| F3 | terrain PID 有两套完整 3seed 目录，但 low/mid 各有独立 `*_retry` 补跑目录，**结果分散未合并** | `results/control/terrain_pid_seed_sweep_*_{low,mid}_retry/` |
| F4 | solve time 两版都无效：旧 H1 run 为 `nan`，solvetime 专门 run 为 `0`；**UA 模式 fallback rate ≈0.63，约为 baseline（≈0.30）的两倍** | `results/control_aggregates/20260613_173559_..._solvetime/control_aggregate_report.md` |
| F5 | **无** 针对 thesis_sweep `results.csv` 的 RMSE/CEP 曲线或箱线图脚本；`aggregate_thesis_sweep.py` 只出 Markdown 表 | `tools/`（全目录无 boxplot / savefig） |
| F6 | `--param-grid` 代码路径就绪：`;` 分隔轴、`:` 分 key 与取值、`,` 分取值 → `AUV_MPC_PARAM_OVERRIDES`(JSON) → 非空时写 `sensitivity_summary.md` | [run_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py#L449-L505) |

**一句话结论**：主消融的"存在性"已跑（baseline vs ua，3×2×3），但**归因链断裂**——UA-MPC 相对 baseline 的差异无法归因到具体机制（缺 A2/A3/A4），且伴随两个未解释的异常（UA fallback≈0.63、solve time≡0）。真实性侧（电缆几何、声磁耦合）与硬件侧仍是最大空缺。

---

## 一、目前实验缺少的（Missing / Gap）

这一维度指"论文正文已经预留位置或已有论述框架，但对应实验数据/表格尚未产出"的项。按能否在本环境软件跑通分为 M-软件（可跑）与 M-硬件（未来工作）。

### M1（P0）UA-MPC 控制侧机制消融 A2/A3/A4 —— 归因链的核心缺口

- **缺口**：§4.4.3(4) 与 §5.5.8 已定义 A0 baseline / A1 ua / A2 w/o sigmoid / A3 alpha=1.0 / A4 scale=0 五个变体，但探查证实（F1）**A2/A3/A4 从未执行**，`param_grid` 全 null。当前只能说"UA-MPC 整体优于 baseline"，无法说"优势来自 sigmoid 控制代价 / 来自非线性 α / 来自权重放大的哪一个"。这是第 4 章创新点归因的最大软肋。
- **执行方式**（代码路径已就绪，F6）：用 `--param-grid` 注入变体参数，在 baseline + dvl_dropout_60 + combined_stress 三场景各跑 3 seed。变体到参数的映射依据 [auv_mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py) L175-183 默认值：

```bash
# A3 (alpha=1.0，去掉不确定性映射的非线性) + A4 (scale=0，关闭低置信权重放大) 单轴扫描
python3 tools/run_thesis_sweep.py \
  --scenarios baseline,dvl_dropout_60,combined_stress \
  --seeds 0,1,2 --mpc-modes ua --duration 120 --sim-backend pvs \
  --param-grid 'confidence_alpha:1.0,1.5;low_confidence_scale:1.0,3.0' \
  --label a3a4_ablation_3seed
```

  - A2（w/o sigmoid）不在同一 param-grid 内表达（sigmoid 由 `confidence_smoothness_k` 或 mpc_mode 决定），单独跑：`--param-grid 'confidence_smoothness_k:0.001,8.0'`（k→0 使 sigmoid 退化为常数 1，等效关闭控制代价缩放）。
  - `--param-grid` 非空会自动产出 `sensitivity_summary.md`（xy_rmse 组间方差占比），这正是"哪个机制主导"的定量证据。
- **优先级**：**P0**（无此实验，第 4 章 UA-MPC 创新点只能写"整体更好"，达不到硕士论文的机制阐述深度）。
- **验收标准**：`sensitivity_summary.md` 产出；三变体各 3×3=9 run 全部 generated；能给出"A4（scale=0）使 combined_stress 的 xy_rmse 退化 X%"这类单机制归因结论；控制侧 lateral RMSE / fallback / control rate 由 `aggregate_control_metrics.py` 二次提取。
- **数据保真边界**：n=3 只能写"趋势一致"，不写"统计显著"（需 n≥5 才提显著性）；结论限 PVS 仿真。

### M2（P1）5 seed / 120 s 全量传感器 sweep —— 把 3seed 抬到统计可信

- **缺口**：现有 DVL/mag/sonar/combined 多档均为 **ua 模式、3 seed、且部分为 30 s 片段**（§5.5.1 边界列注"仅限 30 s 片段"）。缺 (a) baseline 模式对照，(b) 5 seed，(c) 统一 120 s。`scripts/run_dvl_sweep.sh` / `run_mag_sweep.sh` / `run_combined_sweep.sh`（5seed×2mode×120s 包装）**存在但从未真跑**。
- **执行方式**：

```bash
bash scripts/run_dvl_sweep.sh        # 5seed × {baseline,ua} × 120s，DVL 四档
bash scripts/run_mag_sweep.sh        # 磁畸变 light/heavy
bash scripts/run_combined_sweep.sh   # combined_stress
python3 tools/aggregate_thesis_sweep.py <sweep_root>   # 出 XY/Z RMSE + CEP50 表
```

- **优先级**：**P1**。
- **验收标准**：每档 5/5 ok；产出 mean±std；能画出"RMSE 随 DVL 丢包率单调/非单调"曲线（依赖 M8 绘图脚本）。
- **数据保真边界**：§5.5.1 已记录"XY RMSE 非单调"，5seed 后须如实保留非单调事实，不得挑种子。

### M3（P1）terrain PID low/mid/high 干净 3seed —— 合并 retry 碎片

- **缺口**（F3）：low/mid 结果分散在主 3seed 目录 + 独立 `*_retry` 目录，§5.5.1 边界列已诚实标注"low/mid 含 retry 合并 seed"。这是"数据卫生"缺口——应重跑一套干净、同 label、同 seed 集的 low/mid/high 各 3seed。
- **执行方式**：

```bash
python3 tools/run_terrain_pid_seed_sweep.py \
  --terrains low,mid,high --seeds 0,1,2 --label terrain_pid_clean_3seed
```

- **优先级**：**P1**（近底安全是已声明的主结果之一，数据碎片会被答辩质疑）。
- **验收标准**：单一目录内 9/9 ok，无 retry 后缀；clearance RMSE / min / violation 三指标 mean±std 落在现有 0.59–0.71 m 区间即自洽。
- **数据保真边界**：若干净重跑数值与 retry 合并版偏离，以干净版为准并在 rating.md 记录差异。

### M4（P1）代理电缆 6 场景多种子 —— 从 smoke 抬到 n=3

- **缺口**（F2）：§5.7.1–5.7.7 六场景结果表仍是占位/仅 seed0 smoke（n=1），无法写统计优劣。
- **执行方式**：

```bash
python3 tools/run_proxy_cable_sweep.py \
  --scenarios s_curve,hairpin,slope_crossing,buried_gap,cross_current,combined_extreme \
  --seeds 0,1,2 --mpc-modes baseline,ua --duration 120 --label cable_proxy_3seed
```

- **优先级**：**P1**（但见二、H1：这些场景本身是 hack 的，多种子只提升统计强度、不改变"几何代理≠声磁耦合"的定性边界）。
- **验收标准**：6 场景 ×2 模式 ×3 seed = 36 run，报告 completed 数与失败项；cross_current/combined 的 lateral RMSE mean±std。
- **数据保真边界**：结论必须写成"极端几何代理场景下的控制压力测试"，**不得**写成"海缆巡检真实性验证"（见二、H1 与 pvs_extreme_cable_scenarios.md 定性边界）。

### M5（P2）§5.2.3 传感器噪声模型对照表 —— 对齐 HSF-500

- **缺口**：§5.2.3 表格占位符，磁饱和阈值（1e-6/1e-8 T）与真实 HSF-500 手册噪声模型未对齐；§2.1.1 已锚定 DL/T 1278—2025 附录 D 的 0.05 nT，但噪声"分布假设 + 手册来源"表未填。
- **执行方式**：不跑代码，查 HSF-500 数据手册 + DL/T 1278—2025，填参数来源/分布/对照表。属文档类。
- **优先级**：**P2**。
- **验收标准**：表格三列（参数值 / 分布假设 / 手册来源）齐全，无 TODO:cite。

### M6（P3，未来工作）硬件实物实验 —— 保持"设计方案+未来工作"书写

- **缺口**：§5.3.1 Jetson-AMD UDP 时延表（p50/p95/p99、丢包、序列跳变）、§5.4.1 10A 大电流电缆台、§5.4.2 HSF-500 埋深反演、转台九参数硬铁/软铁标定——全部依赖现场硬件。
- **执行方式**：本环境不可跑，写清方案 + 指标 + 验收标准（UDP p50<5ms/p99<50ms、标定残差<0.05nT、埋深误差<0.2m），列入未来工作。
- **优先级**：**P3**。
- **数据保真边界**：§5.3/5.4 已按"设计方案和未来工作"书写，**维持现状，严禁**把 emulated/仿真标定写成真机结论（§5.3.2 仿真标定 scaffold 边界须保留）。

### M7（P2）§4.2.3 BT vs FSM 多场景对照 —— 从 n=1 到可比

- **缺口**：行为树 vs FSM 仅 `benchmark_test_log.md` 单次（n=1），缺多场景节点覆盖率对比。
- **执行方式**：设计 3–4 个含应急抢占的场景（低压/漏水/失联触发），统计 BT 抢占正确率与 FSM 状态膨胀对比。可复用现有 chaos 场景触发条件。
- **优先级**：**P2**。
- **验收标准**：≥3 场景，给出抢占响应时间与覆盖率表。

### M8（P1）thesis_sweep 绘图脚本 —— 新代码（唯一"需新工作"项）

- **缺口**（F5）：`aggregate_thesis_sweep.py` 只出 Markdown 表，**无** RMSE/CEP 曲线或箱线图脚本。M2/M4 跑完后无法直接出论文图。
- **执行方式**：新写 `tools/plot_thesis_sweep_figures.py`，读 `results.csv`，出 (1) 各场景 XY/Z RMSE 箱线图（按 seed 分布）、(2) DVL 丢包率 vs RMSE 折线、(3) baseline vs ua 分组柱状 + 误差棒。风格对齐现有 `plot_terrain_following_figures.py`。
- **优先级**：**P1**（是 M2/M4 成果落图的前置）。
- **验收标准**：脚本吃任意 thesis_sweep `results.csv` 出 PNG 到 `docs/figures/experiments/`，与 §5 图风格一致（B 表 B7 图风格约束）。

---

## 二、目前实验比较 hack 的（Hacky / 权宜代理）

这一维度指"已有数据能跑通、也已写入论文，但实现方式是权宜代理、口径不一致或数值可疑"的项。这些不是"没做"，而是"做的方式站不住脚"，须么修正、么显式降级表述。

### H1（P1）代理电缆场景用几何 config 冒充声磁耦合

- **hack 点**：§5.7 六个极端电缆场景（s_curve/hairpin/slope_crossing/buried_gap/cross_current/combined）是用 PVS bridge config 的几何字段（`terrain_slope_deg`/`noise`/`current`/`cable_path.points_ned`）表达的，**不是真实声磁耦合数字孪生**——电缆几何、地形耦合、声磁接力、掩埋三相漏磁在 [pvs_extreme_cable_scenarios.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/pvs_extreme_cable_scenarios.md) 差距表里均标为"缺"。buried_gap 靠"磁饱和阈值收紧"近似掩埋，而非真实声呐丢失+磁接力。
- **为何是 hack**：把"路径变难"当成了"电缆巡检任务变难"，观测对象没变。多种子（M4）只增加统计强度，不改变这个定性代理属性。
- **处理方式（二选一，建议先做 A 再评估 B）**：
  - **A（诚实降级，P1，低成本）**：正文把这组场景**明确定名为"复杂几何/近底扰动控制压力测试"**，与"海缆巡检真实性"解耦；在场景表、§5.7 引言、图注三处统一措辞。这与 pvs_extreme_cable_scenarios.md 结尾"写成面向海缆巡检的高保真仿真增强，而非真实海试等价验证"一致。
  - **B（真实性升级，P2，需新工作）**：按 pvs_extreme_cable_scenarios.md"最小落地三步"，把 terrain height map 与电缆中心线绑定、加入声呐短时不可见+磁接力的联合 chaos 注入，形成真正的 slope_crossing / buried_gap 声磁耦合场景。改动面大、须先登记经批准。
- **验收标准**：A 完成后，全文无"极端场景=海缆巡检验证"的越界表述；B 完成后，buried_gap 能给出"声→磁→声 handover 无漂移>3m"这类真实接力指标。
- **数据保真边界**：这是 rating.md B 表 B2（声磁耦合场景）与 A 表真实海缆缺失的直接对应项，红线不可越。

### H2（P0）solve time 恒为 0/nan —— 计时语义 bug 未定位

- **hack 点**（F4）：§5.5.1 已诚实标注"solve time 恒 0 ms（计时语义待确认）"，但这是**把一个未定位的 bug 挂在正文里当已知边界**。旧 H1 run 为 nan、solvetime 专门 run 为 0，说明 `t_proc_total×1000` 的取数路径有问题（IPOPT 计时字段名/单位错，或 `/auv/controller/debug` 未透出该字段）。
- **为何是 hack**：§4.4/§5.5 用"IPOPT 求解时间维持在控制周期可接受范围"支撑 MPC 实时性论述，但**实测求解时间不可用**——这个论述目前没有数据支撑，只靠 emulated 定性。
- **处理方式**：查 [auv_mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py) IPOPT stats 取数（`solver.stats()['t_proc_total']` vs `t_wall_total`，CasADi 版本差异会导致字段缺失返 0），确认 `/auv/controller/debug` 是否 publish 该字段，修正后重跑一个小 sweep 验证非零。
- **优先级**：**P0**（直接支撑 MPC 实时可行性这一核心论点，且是明确 bug 而非固有局限）。
- **验收标准**：单场景 3seed 重跑后 solve time 有物理合理非零值（预期 ms 量级）；若确认本环境无法取真值，则**降级论述**——把实时性明确改写为"emulated 算力接口验证，真机时延待测"，不再暗示已实测求解耗时。
- **数据保真边界**：修不好就降级表述，**不允许**填一个看起来合理的假值。

### H3（P0）fallback rate 两版口径冲突 + UA 模式异常偏高

- **hack 点**（F4）：(a) 旧 bag fallback rate 全 0，重跑非零（baseline≈0.30/UA≈0.63），两版口径冲突；(b) 更严重的是 **UA 模式 fallback≈0.63 约为 baseline 的两倍**，这与"UA-MPC 更鲁棒"的论点**表面矛盾**——若 UA-MPC 一半以上周期在回退，其"优势"到底来自优化解还是来自回退兜底？
- **为何是 hack**：目前正文（§5.5.7）把 UA-MPC 写成定位/控制双改善，却回避了"UA 模式 fallback 更高"这一反直觉事实，等于选择性引用。
- **处理方式**：
  1. 统一 fallback 判定口径（§5.1.2(2) 定义"solver_status 含 FALLBACK 或 fallback_reason 非空"），确认新旧两版差异来自判定逻辑改动还是数据源改动，以新版为准并废弃旧全 0 版。
  2. **拆解 UA 的 0.63 由什么触发**——`fallback_reason` 分类统计（IPOPT 失败 / 超时 / 状态不可靠）。若 UA 因权重放大导致问题病态而更常 IPOPT 失败，这本身是**重要负结果**，应写入 rating.md 并在 §5.5.8 讨论（正是 M1 A2/A3/A4 消融要回答的机制问题）。
- **优先级**：**P0**（涉及核心创新点的可信度，且可能是负结果）。
- **验收标准**：给出 baseline/UA 各自 fallback_reason 分布表；正文对"UA fallback 更高"给出机制解释或诚实标注为待解释负结果。
- **数据保真边界**：不得为掩盖矛盾而只报 baseline fallback；反直觉结果如实写。

### H4（P1）lateral RMSE 数值异常小（0.003–0.008 m）

- **hack 点**：§5.5.7 combined 场景 lateral RMSE UA 0.0029 m vs baseline 0.0035 m——**毫米级横向误差**对于欠驱动 AUV + combined_stress 是物理上不可信的（真实/代理电缆场景 cross_current lateral 都在 5 m 量级）。极可能是"参考路径 = 直线、AUV 本就在线上"导致 d_lat≈0，即指标没有真正加载横向跟踪压力。
- **为何是 hack**：用一个几乎恒为 0 的指标去论证"UA-MPC 横向跟踪更好"，改善 15.8% 是在噪声级别上的比较，不具说服力。
- **处理方式**：核对 combined_stress 的参考路径几何——若是直线，lateral RMSE 无区分度，应改用**有横向机动的参考**（S 弯/hairpin，即 M4 的代理场景）来评 lateral RMSE；把 combined_stress 的 lateral 结论降级或移除，改在 s_curve/hairpin 场景比较。
- **优先级**：**P1**。
- **验收标准**：lateral RMSE 在有横向机动场景下落到物理合理量级（分米~米级），baseline/UA 差异有区分度。
- **数据保真边界**：毫米级 lateral 不写成"精确跟踪"结论。

### H5（P2）terrain low/mid retry 合并 seed

- **hack 点**（F3）：见 M3——low/mid 靠独立 retry 目录补齐 3seed，是"跑失败了再补一个种子凑数"。虽已诚实标注，但属数据卫生 hack。
- **处理方式**：由 M3 干净重跑替代。
- **优先级**：**P2**（M3 完成即消解）。
- **验收标准**：同 M3。

---

## 三、目前实验还不能说明的深入 probe（Unprovable / 需深挖佐证的断点）

这一维度指"结论已写或想写，但现有证据链在关键一步断开，需要设计专门的探针实验去打通因果"的项。与"缺少"（没做）和"hack"（做法权宜）不同，这里是**做了但说不清为什么**。

### P-1（P0）UA-MPC 优势的机制归因未隔离

- **不能说明什么**：现在能说"UA-MPC 整体优于 baseline"（§5.5.6/5.5.7），但**不能说清优势来自哪个机制**——是权重放大 `low_confidence_scale`、非线性映射 `confidence_alpha`、还是 sigmoid 控制代价？三者在 A1(ua) 里同时开启，无法解耦。
- **为何断开**：缺 A2/A3/A4（F1，见 M1）。这是整篇论文"创新点=不确定性感知"的因果核心，目前是黑箱。
- **深入 probe 方案**：M1 的 `--param-grid` 消融 + `sensitivity_summary.md` 的方差占比分解，逐一关闭每个机制看 xy_rmse/lateral/fallback 的退化幅度。理想再叠加 `low_conf_scale:1.5,3.0,5.0` 的单调性扫描，回答"权重放大是否越大越好、拐点在哪"。
- **优先级**：**P0**。
- **验收标准**：能画出"关闭机制 X → 指标退化 Y%"的归因条形图；能回答"UA-MPC 的鲁棒性主要由哪个机制贡献"。

### P-2（P0）fallback 路径从未被有效压力测试

- **不能说明什么**：§5.5.1 记录 P1 全 8 场景 fallback/safety **全 0**（PVS chaos 未压到兜底激活），却又在 solvetime run 里出现 UA fallback≈0.63（H3）——两个数据源对"MPC 何时回退"给出矛盾图景，**说明当前无法刻画 UA-MPC 的失效边界**。安全仲裁层（CommandGuard + failsafe，§4.1.2）作为核心安全设计，其触发逻辑从未被真正激活验证过。
- **为何断开**：PVS chaos 场景的扰动强度不足以逼出兜底；而 fallback≈0.63 又疑似来自求解器数值问题而非安全触发（口径混淆）。
- **深入 probe 方案**：
  1. 先解决 H3 的口径统一，区分"求解器 fallback"与"安全仲裁 fallback"两类计数。
  2. 设计**递增压力扫描**：把 combined_stress 的扰动强度分档拉高（DVL 60→90%、磁饱和收紧、注入极端海流），观察 safety violation 与 fallback 从 0 变非 0 的**激活阈值**，画失效边界曲线。
  3. 用代理电缆 hairpin（大曲率）场景逼 MPC 到可行域边界，验证是否触发降速/回退（§4.5.2 极端安全边界，正是 §4.5.2 占位表所需）。
- **优先级**：**P0**（安全设计不被激活 = 安全论述无实证）。
- **验收标准**：给出"扰动强度 → fallback rate / safety violation"激活曲线；至少一个场景观测到 safety 仲裁被正确触发并恢复。
- **数据保真边界**：**不为让兜底激活而调低阈值**（AGENTS.md 红线）——是拉高扰动去撞阈值，不是降阈值去迎合。

### P-3（P1）distorted-prior 恢复能力的边界

- **不能说明什么**：§5.5.11(3f) 已首次在 PVS 六自由度闭环复现 distorted-prior 在线恢复（mid/heavy 各 3/3 pass），但边界是**确定性先验偏差 + 缆恰好埋于车下满足磁观测前提 + n=3**。不能说明：(a) 真实检测噪声下是否仍恢复；(b) 偏差连续增大时的**恢复失效拐点**在哪（现在只测了 mid/heavy 两个离散档）；(c) 观测前提不成立时（如 (3d) 缆与车共面）恢复必然缺席——这个负结果边界虽已诚实记录，但没有量化"前提偏离多少度/多少米后恢复开始退化"。
- **为何断开**：见 [e2e_distorted_prior_next_plan.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/e2e_distorted_prior_next_plan.md) §4.3 剩余项 b/c/d——缺真实检测噪声、多种子统计、硬件实物。
- **深入 probe 方案**：
  1. 偏差档位细化扫描（light→mid→heavy→beyond-heavy 连续），定位恢复失效拐点。
  2. 垂直分离 `d` 扰动扫描：让缆逐步偏离车正下方，量化磁横偏观测退化到被残差门拒绝的临界几何（打通 (3d) 负结果与 (3f) 正结果之间的连续边界）。
  3. 注入合成检测噪声于 `B_ned`，测恢复对噪声的敏感度。
- **优先级**：**P1**。
- **验收标准**：给出"先验偏差 vs 恢复后 route offset"曲线与失效拐点；量化 `d` 偏离 vs 磁横偏反演误差的关系。
- **数据保真边界**：仍是数字孪生，n 值如实标注；不写"真机可恢复"。

### P-4（P1）ES-EKF 协方差一致性：real NIS 依赖 ground truth

- **不能说明什么**：§5.5.5 用 NIS/自适应 R（r_scale_max=5.0、trigger 0.24–0.36）作协方差一致性证据，但 §5.5.1 边界列注"real NIS 依赖 ground truth，属离线量"——**在线运行时 AUV 拿不到 ground truth，无法实时判定协方差是否一致**。当前 NIS 是事后用真值算的，不能证明"在线自适应 R 的触发决策是基于可观测量的正确决策"。
- **为何断开**：真值只在仿真里有；真机没有。
- **深入 probe 方案**：区分两个 NIS——(a) 基于真值的离线 NIS（现有，评估协方差质量），(b) 基于**新息与其理论协方差**的在线 NIS（不需真值，是自适应 R 实际消费的量）。核对自适应 R 触发用的是 (b) 而非 (a)；给出两者对照，证明在线决策不依赖真值。
- **优先级**：**P1**（涉及第 3 章 ES-EKF 可实机部署性）。
- **验收标准**：明确 §5.5.5 的 NIS 曲线哪条是在线可算的；自适应 R 触发链路证明不消费 ground truth（呼应 rating.md C 类红线：在线 tracking 禁消费真值）。

### P-5（P2）Jetson emulated 与真机时延的等价性未验证

- **不能说明什么**：§5.1.1 L3 "Jetson emulated 已验证"，但 emulated 只跑了算力接口，不能说明真机 IPOPT 求解时延、真实 UDP 双脑时延。§5.5.1 已诚实标注"不能写真机绝对时延"。
- **深入 probe 方案**：属 M6 硬件未来工作；软件侧可先做的是**在 emulated 下用 cgroup 限 CPU 频率/核数**模拟 Jetson Orin NX 算力档，给出 IPOPT 求解时延随算力档的敏感度曲线（依赖 H2 先修好计时），作为真机时延的**下界估计**而非实测。
- **优先级**：**P2**。
- **验收标准**：给出 CPU 档位 vs 求解时延曲线，明确标注为"emulated 算力敏感度，非真机实测"。

---

## 四、执行路线图与优先级汇总

### 4.1 优先级总表

| ID | 维度 | 项 | 优先级 | 能否本环境软件跑 | 前置 |
|---|---|---|---|---|---|
| M1 | 缺少 | UA-MPC A2/A3/A4 机制消融 | P0 | ✓ | — |
| H2 | hack | solve time 计时 bug 定位 | P0 | ✓ | — |
| H3 | hack | fallback 口径统一 + UA 0.63 拆解 | P0 | ✓ | — |
| P-1 | probe | UA-MPC 机制归因 | P0 | ✓ | M1 |
| P-2 | probe | fallback/安全边界压力测试 | P0 | ✓ | H3 |
| M2 | 缺少 | 5seed/120s 全量传感器 sweep | P1 | ✓ | M8 |
| M3 | 缺少 | terrain 干净 3seed（消 H5） | P1 | ✓ | — |
| M4 | 缺少 | 代理电缆 6 场景 n=3 | P1 | ✓ | — |
| M8 | 缺少 | thesis_sweep 绘图脚本（新代码） | P1 | ✓ | — |
| H1 | hack | 电缆场景降级/升级表述 | P1 | ✓(A) | — |
| H4 | hack | lateral RMSE 场景重选 | P1 | ✓ | M4 |
| P-3 | probe | distorted-prior 恢复边界 | P1 | ✓ | — |
| P-4 | probe | 在线 NIS vs 离线 NIS | P1 | ✓ | — |
| M5 | 缺少 | 噪声模型对照表 | P2 | 文档 | — |
| M7 | 缺少 | BT vs FSM 多场景 | P2 | ✓ | — |
| H5 | hack | terrain retry 合并 | P2 | ✓ | =M3 |
| P-5 | probe | emulated 算力敏感度 | P2 | ✓ | H2 |
| M6 | 缺少 | 硬件实物（UDP/电缆台/标定） | P3 | ✗ 未来工作 | — |

### 4.2 建议执行顺序（分批）

- **第 1 批（P0，先修 bug 再补消融）**：H2（修 solve time 取数）→ H3（统一 fallback 口径 + reason 拆解）→ M1（A2/A3/A4 消融）→ P-1/P-2（在 M1/H3 产物上做归因与失效边界分析）。这一批打通"UA-MPC 为什么好 + 何时失效"的因果核心，是第 4/5 章最高价值增量。
- **第 2 批（P1，补统计与出图）**：M8（绘图脚本）→ M2（5seed sweep）→ M3（terrain 干净 3seed）→ M4（代理电缆 n=3）→ H1-A（表述降级）→ H4（lateral 场景重选）→ P-3/P-4（边界与 NIS 探针）。
- **第 3 批（P2，模型与迁移）**：M5、M7、P-5。
- **第 4 批（P3，未来工作书写）**：M6、H1-B、P-3(c)、P-4 真机部分——写方案不跑数据。

### 4.3 全局数据保真守则（每批执行时复核）

1. 仿真/台架/emulated 结论一律标注层级（L1–L4），**不越级**表述为真机/海试。
2. n<5 不提"统计显著"；retry 合并、seed0 smoke 如实标注。
3. 反直觉/负结果（UA fallback 偏高、distorted-prior 前提不成立、solve time 取不到）**必须写入正文与 rating.md**，不选择性引用。
4. **不为达标调阈值**：撞失效边界靠加压，不靠降门限（AGENTS.md）。
5. 新增结论先过 [INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/INDEX.md)"当前不能声称"清单与 rating.md A/B/C 表边界。

### 4.4 交付说明

本文件仅为**方案文档（read-only 探查产物）**，尚未执行任何 sweep、未修改 04/05 正文、未改任何代码。执行需用户确认后按 4.2 分批推进；每批完成后回填结果到 04/05 正文对应占位符并更新 rating.md。

---

## 五、第 1 批 P0 零成本诊断结果（2026-08-06 更新）

按 4.2 第 1 批"先修 bug 再补消融"的思路，先做零成本诊断（读代码 + 复算已有 bag + 台架微基准，不起新 PVS 闭环）。以下为 H2/H3 的根因定论，直接改变后续 M1 的必要性判断。

### 5.1 H2（solve time=0）诊断结论：**陈旧数据 artifact，代码已修，非开放 bug**

- **取数链路完好**：`algorithm/auv_mpc_controller.py` solve() → ROS `mpc_controller.py`（动态加载同一 optimizer）→ `auv_controller_node.py` publish `/auv/controller/debug` → `analyze_bag.py` / `aggregate_control_metrics.py` 解析——四段代码均正确读写 `solve_time_ms`，无 bug。
- **台架微基准实测非零**（`tools/mpc_solve_microbench.py --iters 30`，直接调 optimizer，无仿真）：
  - cold-start：wall mean **11.51 ms**（p95 12.36 / max 14.49）、IPOPT 内部 `t_proc_total` mean **11.25 ms**（非零，已填充）；
  - warm-start：wall mean **6.77 ms**、IPOPT 内部 mean **5.76 ms**；全部 `Solve_Succeeded`。
  - 结论：当前 optimizer 求解时间物理合理（ms 量级），`t_proc_total` 现已被正确填充。
- **根因（git 定位）**：
  - 原始 optimizer（`e6c9e9a` 2026-05-03）只读 `t_proc_total` 无 wall fallback；当时该 CasADi/IPOPT 环境 `t_proc_total` 返 0 → `solve_time_ms` 恒 0。
  - H1 solvetime sweep 运行于 **2026-06-13**，用的正是上述旧代码 → 18 个 bag 全部记 0（复算 `/auv/controller/debug` 证实 `solve_time_ms` 113/113 帧均为 0，但**同帧 `total_compute_ms`≈11.9 ms 非零**，佐证"计时字段坏、计算真实发生"）。
  - wall-clock fallback 修复落于 **`cedd80b` 2026-06-30**，晚于 sweep 17 天。
- **处置**：**无需改代码**。只需在 2026-06-30 后重跑一次小 sweep（可与 M1 合并），solve time 即为非零。§5.5.1/§5.5.7"solve time 恒 0 ms（计时语义待确认）"应改写为"旧 sweep 用修复前代码，现已具备台架 11.5/6.8 ms（cold/warm）与 IPOPT 内部计时，闭环重跑后回填"。**不得**继续把它当"未解之谜"挂在正文。

### 5.2 H3（fallback UA≈0.63）诊断结论：**求解器收敛回退，非安全触发；graceful 降级；是应写入正文的机制性负结果**

复算三个 bag 的 `/auv/controller/debug`（baseline_seed0：baseline vs ua；combined_seed0 ua）：

| bag | fallback_rate | 全部 fallback 的 solver_status | 全部 fallback 的 reason |
|---|---:|---|---|
| baseline seed0 **baseline** | 0.301（34/113） | `FALLBACK_LAST_OUTPUT` | `Maximum_Iterations_Exceeded` |
| baseline seed0 **ua** | 0.628（71/113） | `FALLBACK_LAST_OUTPUT` | `Maximum_Iterations_Exceeded` |
| combined seed0 **ua** | 0.667（76/114） | `FALLBACK_LAST_OUTPUT` | `Maximum_Iterations_Exceeded` |

- **fallback 性质**：100% 是 **IPOPT `Maximum_Iterations_Exceeded`**（`max_iter=100`、`tol=1e-4`，见 [auv_mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py#L350-L355)），**不是**安全仲裁（safety violation 全 0）、**不是**数值崩溃（NaN/Inf）。回退动作是 `FALLBACK_LAST_OUTPUT`——沿用上一帧成功的制导指令，属**优雅降级**，这解释了为何 lateral RMSE 仍很小（H4）：车辆没有失控，只是本帧复用了上帧解。
- **UA 为何翻倍**：不确定性感知的权重放大（`low_confidence_scale` 在低置信帧把跟踪权重乘到 3×）使 NLP 病态化、更难在 100 次迭代内收敛到 `tol=1e-4` → 更高比例撞 max-iter → 更常回退。即 **UA 的"鲁棒"部分依赖"退化到上帧解"的兜底**，不是每帧都拿到更优的在线优化解。这是一个**真实且反直觉的机制性负结果**，正是 P-1（A2/A3/A4 归因）要隔离的核心问题。
- **口径澄清（消解 F4 表面矛盾）**：§5.5.1"P1 全 8 场景 fallback 全 0"来自**旧 bag**（时间更早、判定口径为旧版）；H1 solvetime run（新口径）fallback 非零。二者不是同一批数据的冲突，而是**新旧口径 + 不同 sweep**。当前 `is_fallback_payload`（[aggregate_control_metrics.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/aggregate_control_metrics.py#L378-L384)）判定为"solver_status 含 FALLBACK 或 reason 非空或 state_source_fallback"——口径统一、可用。以新口径为准，废弃旧全 0 版表述。
- **处置**：
  1. 正文（§5.5.7/§5.5.8）**如实写入**"UA 模式 fallback≈0.63，成因为权重放大致 NLP 更难在 max_iter=100 内收敛，回退为沿用上帧制导（graceful），非安全失效"。写入 rating.md B/负结果。
  2. **不为降 fallback 而调 max_iter/tol**（AGENTS.md 红线）——若要探究"放宽 max_iter 能否降 fallback 且不升 solve time"，属 P-2 的机制探针，需作为独立对照实验、诚实标注，而非直接改默认值美化结果。
  3. H4（lateral 0.003–0.008 m）与本条同源：直线参考 + graceful 兜底使横向误差天然极小、无区分度。lateral 优劣结论应移到有横向机动的场景（M4 s_curve/hairpin）。

### 5.3 对 M1 执行必要性的影响

诊断**不削弱**反而**强化** M1（A2/A3/A4 消融）的必要性——现在有了明确假设待验证：**"UA 的表观优势有多少来自更优优化解、多少来自更频繁回退到上帧"**。A4（scale=0，关闭权重放大）预期会显著降低 fallback rate；若同时 xy/lateral 指标不劣化，则说明"权重放大"这一机制**得不偿失**，是重要论文发现。M1 值得执行，且 solve time 会在重跑中自动变非零（一并解决 H2 的正文回填）。

### 5.4 M1 执行中发现的运行时门控 bug（H6，新增，2026-08-06）

首次执行 M1（scale=1.0/3.0/5.0 × baseline/dvl_dropout_60/combined_stress × seed0-2 × 60s，27 run，全 `status=ok`）后，解码全部 27 bag 的 `/auv/controller/debug`（3095 帧）发现**MPC 从未真正运行**：

- 100% 帧为 `controller_type: CAPABILITY_GATE` / `mode: CAPABILITY_DEGRADED_HOLD`，无 `solver_status`/`solve_time_ms`；对比 June-13 H1 bag 为 `controller_type: MPC`（每帧带 solver_status）。
- **根因**：提交 `18ac3e3`（**2026-07-17**"磁传感器API合并，支持传感器无效降级"）引入能力门控（[auv_controller_node.py:461-473](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py#L461-L473)）：处于 altitude/terrain-follow 且 `terrain_following` 能力不可用时，发布 zero-effort hold 并 `return`，MPC 不执行。`terrain_following` 依赖 `forward_sonar`（topic `/auv/sensors/forward_sonar_slope`），而 [auv_stack.launch.py:342-345](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/launch/auv_stack.launch.py#L342-L346) 的 `enable_mock_forward_sonar_wrapper` **默认 false** → PVS 栈里该 topic message_count=0 → 能力不可用 → 门控拦截 MPC。
- **修复**：`start_experiment.sh --enable-mock-forward-sonar-wrapper`，经 `run_thesis_sweep.py --start-arg=--enable-mock-forward-sonar-wrapper` 透传。单 run 冒烟（40s）验证：`controller_type: MPC`（76/76）、`terrain_following available: True`、**solve_time nonzero 76/76 mean=43.06 ms**（再次坐实 H2）、solver_status 24 Solve_Succeeded/41 FALLBACK_LAST_OUTPUT/11 FALLBACK_SETPOINT（scale=3.0 fallback≈0.68，印证 H3）。
- **v1（27 run）作废**；**v2 重跑**（同设计 + forward-sonar 使能）已完成（见 §5.5）。

#### 5.4.1 H6 污染面复核结论（2026-08-06，v2 完成后执行）

用户决策"先只修 M1，v2 跑完再议"落实：v2 完成后系统扫描门控窗口 **[2026-07-17 19:07（`18ac3e3` 落地）, 2026-08-05]** 内的全部实验产物，判定既有结论是否建立在 MPC 未运行的 `CAPABILITY_GATE` 帧之上。扫描方法：`log/thesis_sweep`/`results/control`/`log/proxy_cable_sweep`/`results/cable_ops_report` 全目录按名/按 mtime 过滤；对窗口内每个 `/auv_data/bags` 目录读 `metadata.txt`。结论：

| 污染面候选 | 门控窗口内是否有产物 | 是否 MPC 未运行污染 | 判定 |
|---|---|---|---|
| `thesis_sweep` 受管 sweep（含 UA-MPC 主消融、P1 传感器、solvetime、terrain PID、代理电缆） | **无**——窗口内全目录仅为今日 M1 系列（v1 作废 / smoke / v2 / P1） | — | 未污染：所有论文引用的 sweep 目录 mtime ∈ [06-12, 07-06]，**早于**门控落地 |
| `results/control`、`results/cable_ops_report`（含 3e/3f distorted-prior、direction-A、terrain PID、mpc_xy_yaw_extreme、mag 标定） | **无**——最新为 `20260707_132022`（恢复聚合），其余 ∈ [06-12, 07-07] | — | 未污染：全部早于门控；其中 3f/direction-A 虽用 altitude/terrain-follow，但录制于 07-06/07-07 门控前，MPC 正常运行 |
| `/auv_data/bags` 窗口内目录（07-17 共 ~24 个、07-30 共 6 个） | 有目录，但**全部 `record_bag=false`**（交互/调试运行，无 MCAP） | 无 bag 可污染结论 | 未污染：无落盘证据被任何正文结论引用；且 `20260717_173658` 等运行本就带 `enable_mock_forward_sonar_wrapper:=true` |

- **净结论**：门控窗口内**无任何被论文引用的 bag-backed 实验**。H6 的实际污染仅限**今日 M1 v1 的 27 run**——发现即作废、已 v2 重跑替代，未流入正文。所有既有 terrain/altitude-follow 结论（terrain PID 3seed、3f PVS 闭环恢复、direction-A、mpc_xy_yaw_extreme）录制于门控落地前（≤07-07），`controller_type: MPC` 正常，**不受影响**。
- **残留风险边界**：本复核只覆盖**已落盘产物**。门控仍是**当前代码的活跃行为**——今后任何 PVS terrain/altitude-follow 实验若不带 `--enable-mock-forward-sonar-wrapper`，MPC 会被静默跳过。因此复核结论是"历史无污染"，而非"门控已消除"；后者需要修复默认值或在 CI 加断言（见 rating.md B8 收尾建议）。

### 5.5 M1 v2 有效归因结果（27 run 全 ok，MPC 100% 运行，2026-08-06）

`low_confidence_scale` = 1.0/3.0/5.0（scale=1.0 即关闭 xy/ψ 跟踪权重放大，对应 A4 语义）× 3 场景 × 3 seed × 60s。全部 bag `controller_type: MPC`（mpc%=100%），solve_time 100% 非零。

| scale | mpc% | fallback_rate | Solve_Succeeded | solve_mean_ms | xy_rmse(m) | cep50(m) |
|---:|---:|---:|---:|---:|---:|---:|
| 1.0（放大关） | 100% | **0.816** | 18% | 30.08 | 1.713 | 1.750 |
| 3.0（默认） | 100% | **0.690** | 31% | 26.30 | 1.731 | 1.776 |
| 5.0（放大强） | 100% | **0.621** | 38% | 21.63 | 1.633 | 1.678 |

**核心发现（推翻 §5.2 基于旧 bag 的 H3 推断，方向相反）：**

1. **权重放大越强，fallback 越低、Solve_Succeeded 越高**：scale 1.0→5.0，fallback 0.816→0.621（单调下降），成功率 18%→38%。此前基于旧 baseline(0.30) vs ua(0.63) 对比推断"UA 权重放大→问题病态→fallback 高"是**错误归因**——那是 baseline vs ua 两种模式差异（baseline 权重恒定 + 无 sigmoid 控制代价），并非权重放大本身的效应。在 ua 模式内单独调 scale，放大反而**改善**收敛。
2. **机理（待 P-1 进一步隔离）**：更大的跟踪权重使代价面在参考轨迹附近更"陡峭聚焦"，IPOPT 更快落入极小并在 max_iter=100/tol=1e-4 内收敛；scale=1.0 时 xy/ψ 权重不随低置信放大，代价面更平、更易在容差前撞满迭代 → 更常 FALLBACK_LAST_OUTPUT。solve_mean 随 scale 下降（30→21ms，均 <50ms 预算），排除"超时截断致假性 fallback"。
3. **跟踪精度对 scale 基本不敏感**：xy_rmse 1.63–1.73m、cep50 1.68–1.78m，三档无显著差异（且 n=3/档，不足以声称统计显著）。即"权重放大"在当前直线/温和场景**既不明显改善也不损害跟踪精度，但确实降低 fallback**——与"得不偿失"的预判相反，倾向"无害偏有利"。
4. **fallback 仍以 FALLBACK_LAST_OUTPUT 为主**（全体 61%），FALLBACK_SETPOINT≈10%（各 scale 稳定），reason 全为 IPOPT `Maximum_Iterations_Exceeded`——graceful 降级性质不变（印证 H3 关于"非安全失效"的部分）。

**对论文的影响：**
- §5.2/H3 中"UA 权重放大致 fallback 偏高"的表述**必须撤回/改写**：真实结论是"跨模式（baseline↔ua）fallback 差异显著，但 ua 模式内权重放大反而降 fallback"。这是必须如实写入正文 + rating.md 的**归因修正**。
- **待深化（P-1）**：需补 A0 baseline / A2（关 sigmoid）/ A3（alpha=1.0）三个变体，才能完整拆分"模式切换 / sigmoid 控制代价 / alpha / scale"各自对 fallback 与精度的独立贡献。当前 v2 只隔离了 scale 轴。
- **fallback 绝对水平偏高（0.62–0.82）本身仍是问题**：即便最优 scale=5.0 仍有 62% 帧走 fallback，说明 max_iter=100 对该 NLP 偏紧。属 P-2（放宽 max_iter 的独立对照，诚实标注，不为美化默认值而改）。

### 5.6 P-1 机制拆分归因结果（A0/A2/A3 补全，2026-08-06）

在 v2 只隔离 `low_confidence_scale` 轴之上，补跑三变体拆分 UA-MPC 各机制的独立贡献。全部 forward-sonar 使能、`controller_type: MPC` **100%**（无 H6 门控污染）、safety violation 全 0、每档 3 场景 × 3 seed。变体到 override 的映射：A0=`AUV_MPC_MODE=baseline`（权重恒定 + 控制代价不缩放）、A2=ua 但 `low_confidence_control_scale=1.0`（关 sigmoid 控制降权）、A3=ua 但 `confidence_alpha=1.0`（(1−conf) 线性映射，取代默认 1.5 次幂）。A1 为 v2 的 scale=3.0 档（ua 默认 scale3/alpha1.5/cs0.3），作公共参照。

`/auv/controller/debug` 为 2 Hz 定时采样（`create_timer(0.5,...)`），fallback_rate 为采样帧占比；fallback_reason 全串经解码确认。

| 变体 | 关键差异 | mpc% | fallback_rate | Solve_Succeeded | solve_mean_ms | xy_rmse(m) | lateral RMSE(m) |
|---|---|---:|---:|---:|---:|---:|---:|
| **A0** | mode=baseline（权重恒定 + 无 sigmoid） | 100% | **1.000** | 0% | 83.5 | 1.201 | ~1e-5–5e-3 |
| **A2** | ua，ctrl_scale=1.0（关 sigmoid 控制降权） | 100% | **1.000** | 0% | 87.0 | 1.163 | ~1e-6–5e-3 |
| **A1** | ua 默认（scale3/alpha1.5/cs0.3）=v2@3.0 | 100% | 0.690 | 31% | 26.3 | 1.731 | — |
| **A3** | ua，alpha=1.0（线性映射，低 conf 段放大更早更强） | 100% | **0.335** | 66% | 19.9 | 1.601 | ~4e-6–8e-3 |

**核心机制归因：**

1. **sigmoid 控制代价缩放（A2 消融）是维持可解性的关键机制**：关掉它（`low_confidence_control_scale=1.0`，控制代价不再随低置信降权）→ fallback 从 A1 的 0.690 **跳到 1.000**、Solve_Succeeded 从 31% 归零、solve_mean 从 26ms 翻到 87ms（撞满 max_iter=100 的典型征兆）。这坐实"控制代价降权让 IPOPT 在低置信下有更宽松的控制自由度、更易在容差内收敛"是 UA-MPC 相对 baseline **可解性**优势的主要来源。
2. **baseline 模式（A0）与 A2 几乎同样病态**：A0 fallback 也 1.000、solve_mean 83ms。说明 A0↔A1 的 0.30→0.69（旧 bag）差异**并非**"ua 更差"，恰相反——ua 的 sigmoid + 权重放大合起来把 baseline/A2 的"全回退"改善到 31%–66% 成功。旧 H3"UA 权重放大致 fallback 偏高"结论**方向完全错误**，本轮以隔离变体二次坐实撤回。
3. **alpha 从 1.5 降到 1.0（A3）显著降 fallback（0.690→0.335）、solve_mean 最低（19.9ms）**：线性映射 `(1−conf)^1.0` 在中低置信段比 1.5 次幂放大更早、更强 → 代价面更早陡峭聚焦 → IPOPT 更快收敛。这与 v2"scale 越大 fallback 越低"同源——**凡是让跟踪权重在低置信段更强的机制（大 scale 或小 alpha）都降 fallback**。
4. **xy_rmse / lateral RMSE 不能作精度优劣判据（诚实边界，呼应 H4）**：A0/A2 fallback=1.000 却 xy_rmse 最低（1.16–1.20），A3 fallback 最低却 xy_rmse 偏高（1.60）——**反相关**。根因是这三场景参考路径近直线、AUV 本在线上，全回退时 hold setpoint 反而漂移更小；lateral RMSE 全部落在 1e-6–8e-3 m（毫米级、无区分度）。故本批**只支撑"可解性/收敛"机制归因，不支撑"跟踪精度"结论**——精度侧须在有横向机动场景（S 弯/hairpin，M4）另做（H4 待办）。

**净结论（机制排序）**：UA-MPC 相对 baseline 的**可解性**改善，主要由 **sigmoid 控制代价降权（A2）** 贡献（关掉即回到全回退），其次由**低置信段跟踪权重放大**（scale↑ 或 alpha↓）进一步降 fallback；两者叠加把 baseline/A2 的 100% 回退改善到 A3 的 33.5%。但**绝对 fallback 水平仍高**（最优 A3 仍 33.5%，A1 默认 69%），且**精度优势在本批直线场景无法证明**（H4）。

**对论文的影响：**
- §5.5.8 消融表可从"仅 scale 轴"扩为"scale + 模式 + sigmoid + alpha 四机制拆分"，机制归因链闭合到硕士论文要求的深度。
- 默认参数 A1（alpha=1.5）在本批**并非** fallback 最优（A3 alpha=1.0 更低）——但 alpha 更小会否损害高置信段的控制平顺/精度需在有机动场景验证，**不能仅凭 fallback 低就改默认值**（AGENTS.md 不为单指标调参红线）。登记为 rating.md 待议项，不擅改 `params.yaml`。
- 数据保真边界：n=3/档、直线/温和场景、PVS 仿真、2 Hz 采样口径；不作统计显著性声称，不外推真机。

### 5.7 P-2 max_iter 独立对照结果（2026-08-07）

为检验 A11 中“`ipopt.max_iter=100` 偏紧是否是高 fallback 的主因”，仅放宽迭代上限，保持 A1 默认 UA 参数、三场景、三 seed、60 s、forward-sonar 使能不变。新增的 `max_iter` 实验 override 默认仍为 100，不改变生产配置。正式 sweep 为 `100/200/400 × 3 场景 × 3 seed`，27/27 ok，全部 `controller_type: MPC`。

| max_iter | debug frames | fallback_rate | Solve_Succeeded | 成功帧 solve mean(ms) | 初始 fallback-setpoint 当前失败 wall(ms) | xy_rmse(m) | safety violation |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 1027 | 0.699 | 0.301 | 13.49 | 88.41 | 1.538 | 0 |
| 200 | 1024 | 0.685 | 0.315 | 15.00 | 192.21 | 1.532 | 0 |
| 400 | 761 | 0.594 | 0.406 | 17.04 | 372.20 | 1.552 | 0 |

各档 fallback reason 均为 IPOPT `Maximum_Iterations_Exceeded`。按场景看，200 档并不单调改善（combined_stress：0.657→0.736），400 档才在三场景均下降到约 0.57–0.61，但代价是失败求解 wall time 增至约 372 ms，远超 50 ms 预算；同时 2 Hz debug/control 有效帧由 1027 降至 761（约少 26%），说明单线程 executor 已被长求解明显阻塞。定位指标与毫米级 lateral 指标均无可解释收益。

**归因结论：**

1. **max_iter=100 偏紧是次要因素，不是高 fallback 的主因。** 翻倍至 200 仅带来 1.4 个百分点的 fallback 降幅，却使失败耗时翻倍；400 虽下降约 10.5 个百分点，仍有 59.4% fallback，且破坏控制更新频率。
2. **不修改默认 `max_iter=100`。** 放宽迭代上限不是有效工程修复；后续应优先改善初值/热启动连续性、约束可行性或求解器容差结构，并用独立实验验证，而不是用更长阻塞换取表面成功率。
3. **新增观测性边界**：`FALLBACK_LAST_OUTPUT` 当前实现复用上一成功输出，其 `solve_time_ms` 是陈旧值；因此普通聚合报告中的“全帧 solve mean”会低估失败帧耗时。本表只用成功帧真实 IPOPT 时间与 `FALLBACK_SETPOINT` 当前失败 wall time。fallback rate/status 仍可靠。若后续要给失败耗时分布，须先修复该 debug 字段并重跑。
4. 数据边界：PVS、n=3/档、2 Hz debug 采样；400 档样本数下降本身就是阻塞效应的一部分，但也使其 fallback 比例与 100/200 档并非完全等采样率比较，不作统计显著性声称。

证据：`log/thesis_sweep/20260807_101744_p2_maxiter_ablation_3seed/` 与 `results/control_aggregates/20260807_101744_p2_maxiter_ablation_3seed/`。

### 5.8 H4 横向机动场景 lateral RMSE 归因结果（2026-08-07）

P-1/P-2 的参考路径近直线，lateral RMSE 为毫米级，不能回答“UA-MPC 的精度收益来自哪一项机制”。本轮新增 `tools/mpc_uampc_maneuver_ablation.py`，复用 `mpc_xy_yaw_extreme_benchmark.py` 的路径生成、运动学 plant 与 LOS fallback 契约，在可跟踪长波 S 弯和 180° hairpin 上做确定性解耦闭环。固定 `confidence=0.3`、`max_iter=100`，比较 A0 baseline、A1 UA 默认、A2 w/o sigmoid、A3 alpha=1.0。该实验只回答横向激励下的精度机制归因，不替代 PVS 六自由度闭环，更不能外推真机。

| 场景 / 指标 | A0 baseline | A1 UA default | A2 w/o sigmoid | A3 alpha=1.0 |
|---|---:|---:|---:|---:|
| S 长波 lateral RMSE (m) | 0.0852 | **0.0754** | 0.0852 | **0.0740** |
| S 长波固定时长进度 | 76.5% | 85.8% | 76.5% | 86.6% |
| Hairpin 有效路径段 RMSE (m) | 0.102 | 0.100 | 0.102 | **0.097** |
| Hairpin 末端越界 RMSE (m) | 7.480 | 7.484 | 7.480 | 7.563 |
| solve success（两场景） | 100% | 100% | 100% | 100% |

**归因结论：**

1. **sigmoid 控制代价降权是精度侧主贡献。** S 长波中，A1 相比 A0 lateral RMSE 改善约 11.6%，固定时长进度增加 9.3 个百分点；A2 关闭 sigmoid 后几乎逐位退化回 A0。这与 P-1 “A2 全回退、A1 恢复 31% 成功”的可解性结论一致，说明同一机制同时贡献收敛与横向跟踪。
2. **alpha=1.0 只有边际收益，不改默认值。** A3 相比 A1 在 S 长波再改善约 1.9%，hairpin 有效段改善约 3%，但 terminal overshoot 略恶化。当前证据不足以支持把默认 `confidence_alpha=1.5` 改为 1.0。
3. **hairpin 全时段 RMSE 不可直接当作转弯失败。** 轨迹检查显示约 52 s 已完成路径，之后车辆继续航行造成 terminal overshoot。正文引用时应使用首次到达 99% 路径前的 active-path RMSE，并把末端停止/保持策略作为任务设计边界记录。
4. **H4 不解释 PVS 中的 `Maximum_Iterations_Exceeded`。** H4 两场景四变体均 100% solve success，只能说明有横向激励时的精度贡献；PVS 闭环的高 fallback 仍以 P-1/P-2 结论为准。

证据：`results/control/uampc_maneuver_ablation/20260807_110001/metrics.csv`、`report.md`、`s_turn_long_wave_trajectories.png`、`hairpin_180deg_trajectories.png`。事实源汇总见 `docs/experiment/uampc_p2_h4_attribution_20260807.md`。
