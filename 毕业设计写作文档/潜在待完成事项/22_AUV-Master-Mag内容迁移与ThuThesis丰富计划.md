# AUV-Master-Mag 内容迁移与 ThuThesis 丰富计划

> 状态：迁移计划，不是已完成证据报告。  
> 审计对象：`AUV-Master-Mag/results`、`AUV-Master-Mag/thesis`、`AUV-Master-Mag/docs/figure`，以及主仓 `thuthesis/data/auv-chap02.tex` 至 `auv-chap05.tex`。  
> 子仓库审计提交：`12e1884b59737dbe14e83c825b6cea9bb3c7a4bb`。  
> 核心原则：迁移的是电缆巡检算法的原理、机制和边界证据，不把算法级单次仿真改写成主仓端到端、多种子或实物结论。

---

## 1. 审计结论

### 1.1 资产规模

| 位置 | 规模 | 主要内容 |
|---|---:|---|
| `AUV-Master-Mag/results` | 约 567 MB、1436 个文件 | 123 个 NPZ、20 个 CSV、761 张 PNG；覆盖声呐工况、先验畸变、曲率边界、留一法消融、跨车道压力、之字形埋深等 |
| `AUV-Master-Mag/thesis` | 约 24 MB | 通用 AUV 章节稿、架构图、控制/地形图及工程证据说明 |
| `AUV-Master-Mag/docs/figure` | 5 组概念图及多组论文结果图 | 磁感知流水线、主动感知、任务 FSM、纯磁失效时序、机制消融、埋深权衡、先验配准解耦 |

### 1.2 主论文已经吸收的内容

主 ThuThesis 并非完全缺少子仓库内容。第 5.5.11 节已经：

1. 说明主仓端到端消费的是子仓库同源部署接口；
2. 用“专用仓库算法级电缆探测边界摘要”表吸收了六类结论；
3. 区分算法级单次仿真、主仓开环回放、六自由度闭环和实物验收四个证据层级；
4. 写入纯磁失效、30 m 曲率、留一法、跨车道压力、先验配准和之字形埋深等关键数值。

目前的主要缺口不是“没有结论”，而是：

- 第 2--4 章缺少说明算法内部机理的专用图；
- 第 5 章只有摘要表，缺少能展示因果链的关键结果图；
- 部分正文数值仍沿用早期写法，与子仓库当前结果不一致；
- 迁移证据尚未作为独立 artifact 固化，仍依赖子仓库工作树和被忽略的 `results/`。

### 1.3 `thesis/figures` 的去重结论

子仓库 `thesis/figures` 中的控制、地形和通用系统图，大部分已在主仓 `docs/thesis/figures` 中存在同名副本，但文件内容已经分叉。因此不得用子仓库目录整体覆盖主仓。

子仓库 `thesis/figures/architecture` 中只有以下三类图是主仓没有同名文件的：

- `auv_code_layer_architecture`
- `auv_ros2_node_topology`
- `auv_safety_arbiter_deployment`

它们属于通用软件/部署架构，不是本轮电缆算法丰富的优先项。主仓已有更新的五层架构、双脑架构、任务生命周期和安全仲裁图，直接迁移会造成重复和版本冲突。

真正值得迁移的专用材料主要位于：

- `AUV-Master-Mag/docs/28_声磁协同方法论合龙.md`
- `AUV-Master-Mag/docs/29_声磁协同实验设计与结果.md`
- `AUV-Master-Mag/docs/30_声磁协同意义与展望.md`
- `AUV-Master-Mag/docs/31_声磁协同算法部署输入输出规范.md`
- `AUV-Master-Mag/docs/figure/`
- `AUV-Master-Mag/results/20260628_*` 至 `20260705_*`

---

## 2. 可迁移内容分级

### 2.1 A 级：优先进入正文

| 内容 | 现有源 | 主论文落点 | 迁移动作 |
|---|---|---|---|
| 磁感知融合流水线 | `docs/figure/fig_perception_pipeline.*` | 第 3.3.3/3.3.4 节 | 按主仓真实 DLIA、ES-EKF 与部署接口重绘，不原样复制 |
| 主动感知之字形原理 | `docs/figure/fig_zigzag_probe.*` | 第 4.3.1 节，或第 2.3.5 节交叉引用 | 保留几何示意，明确区分“大范围覆盖扫描”与“局部主动探查” |
| 纯磁失效时序 | `docs/figure/fig_b1_failure_timeseries.{pdf,png}` | 第 5.5.11 节“失效边界” | 可迁移，图注必须标注专用仓库、纯仿真、`n=1` |
| D4 投影安全与在线先验配准解耦 | `docs/figure/fig_d4_prior_alignment_decoupling.{pdf,png}` | 第 5.5.11 节“恢复机制” | 可迁移，作为“投影连续不等于物理对齐”的核心机制图 |
| 调优后之字形埋深结果 | `results/20260705_zigzag_burial/*.csv` | 第 5.5.11 节或新增第 5.5.12 节 | 必须重新出图，不能直接采用当前第一轮 tradeoff 图 |
| 两级估计方法 | `docs/28` 第 2 节 | 第 3.1/3.3 节 | 压缩为“载体状态估计→电缆几何级在线修正”两级框架，避免另起算法体系 |

### 2.2 B 级：正文或附录择一

| 内容 | 现有源 | 建议用途 | 边界 |
|---|---|---|---|
| 留一法机制分解 | `fig_b3_ablation_health`、`ablation_sweep.csv` | 第 5.5.11 节机制归因，或附录 A.9 | 综合健康分可解释性有限；最好改为完成度、横偏、跳变和通过状态组合图 |
| 30 m 曲率半径扫描 | `fig_b2_radius_boundary`、`radius_sweep.csv`、`radius_causality.csv` | 附录 A.9；正文一句结论 | 30 m 是环境硬下限，不是已找到的真实失效阈值；`n=1` |
| 声磁贡献占比 | `showcase_contribution` | 第 3.3.4 节或附录 | 算法模拟器内部贡献口径，不等同于 ES-EKF 的动态 R 权重 |
| 任务 FSM 与状态机层级 | `fig_mission_fsm`、`fig_statemachine_hierarchy` | 第 4.2 节补充或附录 | 子仓库五态 FSM 与主仓行为树/生命周期状态机职责不同，需画成层级关系而非替换主图 |
| 部署 I/O 契约 | `docs/31` | 附录 A.9 或实物 handoff 文档 | 适合支撑算法同源性和 Sim-to-Real 接口，不宜在正文列代码字段 |

### 2.3 C 级：不迁移或只作核对

| 内容 | 原因 |
|---|---|
| 子仓库 `thesis/figures` 中 PID、MPC、Terrain、BT vs FSM 图 | 主仓已有更新版本和更强实验，整体覆盖会导致回退 |
| `auv_code_layer_architecture`、`auv_ros2_node_topology`、`auv_safety_arbiter_deployment` | 与主仓现有架构图重叠，且子仓库版本不是当前系统事实源 |
| `fig_arch_onion` 原图 | 强绑定子仓库模块名和 200/20 Hz 双速率，不应替代主仓全系统架构；可作为重绘参考 |
| `progress_*` 早期前后对照 | baseline 使用冻结常量，适合作为开发演进，不适合作为当前算法公平消融 |
| 当前 `fig_zigzag_burial_tradeoff` | 图中是 0--20° 第一轮未达标结果，与后续 25--36° 调优达标结论不完整对应 |
| `case_maze_no_sonar` 的“通过”表述 | 当前结果明确显示无声呐初始捕获失败，应保留为可观测性边界 |

---

## 3. 必须先修正的正文冲突

迁移前先修正文事实，否则新增图会与旧文字冲突。

### 3.1 第 3.3.4 节的过强数值

当前第 3 章写有：

- 稀疏声呐有效率约 20% 时，弯道跟踪误差可维持在 `≤0.2 m`；
- 声呐 100% 失效后可依靠行为树主动之字形完成全盲重捕；
- 磁侧弯道边界以 `R<200 m` 描述。

子仓库当前可复核结果并不支持这三个强表述：

1. 稳定稀疏声呐场景的算法级 TRACK 横偏约为 0.9 m，不是 0.2 m；
2. `case_maze_no_sonar` 仍未完成初始捕获，健康分约 12，应写成可观测性负边界；
3. 声呐锁定后中断的纯磁场景在 30--120 m 专项弯道扫描中均通过，TRACK 横偏约 1.7--2.6 m；30 m 是扫描下限，不是证明 `R<200 m` 必然失效。

建议改写为：

> 稀疏声呐可提供低频绝对锚点并与磁路径/先验修正共同维持长程跟踪；声呐在完成初始锁定后中断时，受控之字形与在线先验修正可在所测工况中维持任务推进。无声呐初始捕获仍失败，表明磁模量与局部过线证据不足以单独解决全局切向与方向初始化。上述结论均为专用算法仓库的单次纯仿真边界，不等同于主仓 ES-EKF 或实物结果。

### 3.2 “实测”与“仿真”的术语

子仓库文档多处把离线确定性仿真称为“实测结果”。迁入主论文时统一改为：

- “算法级仿真结果”
- “单次确定性复现”
- “专用仓库离线扫描”

只有 TMR/SK2301、ArUco、PC104 等真实采集才使用“实测”。

### 3.3 两类之字形必须拆开

主论文当前第 4.3.1 节描述的是大范围覆盖扫描：

\[
d=\lambda W_{\mathrm{eff}}
\]

子仓库的 `fig_zigzag_probe` 描述的是跟踪阶段局部主动横切，用于制造磁过线峰值、中心线拟合和 cycle-local 埋深后验。二者目的不同：

| 类型 | 任务阶段 | 主要目标 | 关键参数 |
|---|---|---|---|
| 覆盖之字形 | SEARCH | 区域无遗漏覆盖 | 航线间距、重叠率、覆盖时间 |
| 主动探查之字形 | TRACK/REACQUIRE | 增强磁几何可观测性 | 横切角、探查周期、进入门、恢复段、冷却段 |

计划在第 4.3.1 节增加“局部主动探查并非覆盖扫描”的过渡段，并引入主动感知图。

---

## 4. 章节丰富方案

### 4.1 第 2 章：补足“物理模型如何转化为可观测动作”

现状：第 2.3.5 节已有 FWHM 推导，但只有公式，没有直观几何图。

新增内容：

1. 在 FWHM 推导后插入一张简化主动横切示意；
2. 图中只保留真值电缆、AUV 横切轨迹、峰值点、横切角、估计中心线；
3. 正文说明横切同时服务两类几何信息：
   - 峰值时刻给横向中心线；
   - 半高全宽给垂直距离；
4. 不在第 2 章引入 FSM、prior alignment 等实现细节。

建议图名：

```text
docs/thesis/figures/architecture/cable_active_crossing_observability.png
```

建议图题：

> 单三轴磁力计主动横切形成的中心线与垂直距离可观测性

### 4.2 第 3 章：补足“原始磁场如何进入统一感知状态”

现状：第 3 章已经写出 DLIA、FWHM、ES-EKF 和动态 R，但缺少从采样到输出的端到端方法图。

新增一张按主仓事实重绘的流水线：

```text
TMR8637 / SK2301 三轴采样
  -> 标定、去趋势、窗函数
  -> 45/50 Hz DLIA：I/Q、模量、SNR
  -> 峰值/FWHM/过线周期
  -> 横偏、垂直距离、埋深及质量
  -> 声呐中心线与方向消歧
  -> 电缆几何级在线修正
  -> CableTrackingOutput
  -> ES-EKF / 行为树 / UA-MPC
```

该图需吸收 `fig_perception_pipeline` 的结构，但必须作以下修订：

- 内层采样从子仓库示意的 200 Hz 改为“按采集配置”，正文示例引用当前 2000 Hz 实测链；
- “滤波/RMS”改为 DLIA I/Q 和旋转不变模量；
- 明确 `CableTrackingOutput` 与 ES-EKF 的上下游边界；
- 真值只进入离线评价，不进入在线管线；
- 声呐观测提供几何锚点和方向消歧，不写成无条件可信。

建议图名：

```text
docs/thesis/figures/architecture/cable_acoustic_magnetic_perception_pipeline.png
```

建议增加一个两级估计框：

```text
载体级 ES-EKF：AUV 位姿 + 协方差
                |
                v
电缆几何级修正：先验地图 + 声磁观测 -> 横偏/走向/埋深
```

这能把第 3 章目前“ES-EKF 既估 AUV 又似乎直接估整条电缆”的歧义拆开。

### 4.3 第 4 章：补足主动感知的任务逻辑

现状：已有覆盖扫描与动态航速，但“为什么跟踪阶段还要主动横切”没有展开。

建议在第 4.3.1 节增加一段局部主动感知策略：

1. 正常跟踪时维持小幅或零附加摆动；
2. 当磁几何可观测性下降、埋深后验未收敛或声呐退化时，触发有限时长探查 burst；
3. burst 后先恢复至路线，再进入冷却；
4. 将“状态许可”和“本帧执行许可”分开，避免探查动作越过安全门；
5. 说明之字形幅值越大，埋深可观测性可能提升，但横偏和完成时间会恶化。

正文优先使用 `fig_zigzag_probe` 的重绘版。子仓库 `fig_mission_fsm` 与 `fig_statemachine_hierarchy` 只在确有篇幅时放附录，否则主仓已有行为树、任务生命周期状态机和应急仲裁图，继续增加状态机图会稀释主线。

### 4.4 第 5 章：从摘要表升级为“机理证据链”

建议把第 5.5.11 节的算法级部分从一张摘要表扩展为三组图，每组只回答一个问题。

#### 图组 A：为什么失败

源：

- `fig_b1_failure_timeseries.pdf`
- `results/20260630_ablation/ablation_sweep.csv`

叙事：

```text
关闭在线先验修正
  -> 重档错位先验不能被吸收
  -> 横偏进入 30--40 m
  -> U 弯触发 +57.5 m 跨车道投影跳变
  -> 完成度与健康度下降
```

边界：单次确定性算法仿真，不能称主仓 ROS 闭环或实物。

#### 图组 B：什么机制真正起作用

源：

- `fig_b3_ablation_health.pdf`
- `ablation_sweep.csv`
- `fig_d4_prior_alignment_decoupling.pdf`
- `lane_shortcut_prior_alignment_{50,70}.csv`

推荐不是原样放两张，而是：

1. 正文放 D4/prior alignment 解耦图；
2. 留一法消融用一张紧凑表或重新绘制主指标图；
3. 强调：
   - map-frame tracker 保证“投影在哪一段”连续；
   - prior alignment 负责“把错位地图拉向真实电缆”；
   - 投影连续本身不保证任务健康；
   - 当前正则下在线先验修正和自适应之字形是关闭即失败的机制。

#### 图组 C：主动探查带来什么运维价值

源：

- `zigzag_burial_sweep.csv`
- `zigzag_burial_tuning_depth2.csv`
- `zigzag_burial_tuning_focused.csv`
- `zigzag_burial_tuning_shallow_mid.csv`

必须生成一张新图，而不是使用当前第一轮图：

1. 左图：1.0/1.5/2.0 m 三档的“摆幅--cycle MAE”曲线，完整覆盖 20--36°；
2. 右图：最优点的埋深误差与 TRACK 横偏/完成度权衡；
3. 标出 0.15 m 参考线；
4. 标出三个当前最优点：
   - 1.0 m：36°，cycle MAE 0.124 m；
   - 1.5 m：32°，cycle MAE 0.079 m；
   - 2.0 m：25°，cycle MAE 0.123 m；
5. 图注写明 `n=1`、算法仿真、幅值需按埋深/信号状态自适应。

建议新图名：

```text
docs/thesis/figures/experiments/cable_algorithm/zigzag_burial_tuned_envelope.pdf
```

### 4.5 附录 A：把正文放不下的证据契约下沉

附录 A.9 建议补充：

- 子仓库 commit 与结果目录；
- 场景参数：lane 长度、间距、U 弯半径、先验轻/中/重档；
- `passed` 判据和 `route_progress_large_jump_count` 定义；
- 部署 I/O 中 `map_frame_*` 与 `prior_alignment_*` 的语义；
- 随机种子未透传、当前 `n=1` 的限制；
- 真值字段只允许离线评价；
- 30 m 曲率扫描的“下限未击穿”语义。

---

## 5. 图表迁移清单

### 5.1 正文最小集

| 优先级 | 新图/表 | 来源 | 章节 | 状态 |
|---:|---|---|---|---|
| P0 | 主仓口径声磁感知流水线 | 重绘 `fig_perception_pipeline` | 3.3.3/3.3.4 | 待重绘 |
| P0 | 主动横切可观测性示意 | 精简 `fig_zigzag_probe` | 2.3.5 或 4.3.1 | 待重绘 |
| P0 | 关闭先验修正的纯磁失效时序 | `fig_b1_failure_timeseries.pdf` | 5.5.11 | 可迁移 |
| P0 | 投影连续与物理配准解耦 | `fig_d4_prior_alignment_decoupling.pdf` | 5.5.11 | 可迁移 |
| P0 | 调优后埋深--摆幅--跟踪权衡 | 四份 zigzag CSV | 5.5.11/5.5.12 | 待新绘 |
| P1 | 留一法机制分解 | `ablation_sweep.csv` | 5.5.11 | 建议重绘 |

正文新增图控制在 5--6 张。其余进入附录或 Artifact Manifest，避免第 5 章继续膨胀。

### 5.2 附录/答辩备选集

| 图 | 用途 |
|---|---|
| `fig_b2_radius_boundary` | 回答“纯磁在多急弯道失效” |
| `showcase_contribution` | 回答声呐、稀疏声呐和声呐中断时各观测贡献变化 |
| `fig_mission_fsm` | 回答搜索、锁定、跟踪、重捕、应急如何切换 |
| `fig_statemachine_hierarchy` | 回答行为树、任务 FSM、探查 burst 子状态机是否冲突 |
| `case_maze_sonar_detail_probe_cycle` | 回答主动探查在时序上是否真实执行 |

---

## 6. 证据固化方案

### 6.1 为什么不能直接引用子仓库现状

当前子仓库存在两个可追溯风险：

1. `results/` 大量文件不受 Git 跟踪；
2. `docs/figure` 多个 PNG/PDF 相对提交处于 modified 状态。

这意味着“子仓库 commit”不能单独唯一确定当前图像与结果。迁移前必须冻结最小证据包。

### 6.2 建议新增 artifact

建议在 Artifact Manifest 新增：

```text
MAG-CABLE-ALGORITHM-BOUNDARY
```

建议属性：

| 字段 | 建议值 |
|---|---|
| `data_layer` | `algorithm_simulation` |
| `evidence_grade` | `C` |
| `declared_status` | `complete_with_boundaries` |
| `sample_scope` | 专用电缆跟踪算法；确定性单次复现；先验/声呐/曲率/之字形多场景 |

最小文件集：

- `AUV-Master-Mag/docs/28_声磁协同方法论合龙.md`
- `AUV-Master-Mag/docs/29_声磁协同实验设计与结果.md`
- `AUV-Master-Mag/docs/31_声磁协同算法部署输入输出规范.md`
- `AUV-Master-Mag/results/20260628_dr_ins_boundary/critical_sweep_after_estimator_guard.csv`
- `AUV-Master-Mag/results/20260630_ablation/ablation_sweep.csv`
- `AUV-Master-Mag/results/20260630_radius_boundary/radius_sweep.csv`
- `AUV-Master-Mag/results/20260705_radius_causality/radius_causality.csv`
- `AUV-Master-Mag/results/20260705_lane_shortcut/lane_shortcut_prior_alignment_50.csv`
- `AUV-Master-Mag/results/20260705_lane_shortcut/lane_shortcut_prior_alignment_70.csv`
- `AUV-Master-Mag/results/20260705_zigzag_burial/zigzag_burial_*.csv`
- 对应绘图脚本：
  - `tools/render_stress_test_figures.py`
  - `tools/render_prior_alignment_figures.py`
  - `tools/render_zigzag_burial_figures.py`
- 迁移后的主论文图和 `_SOURCE.md`

`claims_supported` 只写：

1. 在线先验修正关闭会在重档错位先验下引发横偏累积和跨车道跳变；
2. map-frame 投影连续与先验物理配准是两个不同机制；
3. 当前场景中在线先验修正与自适应之字形是关闭即失败的载荷机制；
4. 之字形主动激励在调优后显示进入 0.15 m 参考线的算法级潜力；
5. 30--120 m 扫描未击穿曲率边界。

`claim_boundaries` 必须写：

- 全部是专用算法仓库的单次确定性纯仿真；
- 不等于主仓 ROS/PVS 端到端、多种子或实物；
- 30 m 是扫描下限，不是实际失效阈值；
- 埋深达标点是参数扫描最优点，不代表固定幅值全场景达标；
- 无声呐初始捕获仍失败；
- 综合健康分是任务级复合指标，机制判断需同时引用原始横偏、完成度、跳变和通过状态。

---

## 7. 实施顺序

### M0：冻结来源与修正文事实

1. 记录子仓库 commit、dirty 文件和选定文件 SHA256；
2. 为每张迁移图建立 `_SOURCE.md`；
3. 修正第 3.3.4 节的 `≤0.2 m`、`R<200 m` 和全盲重捕等过强表述；
4. 把算法级“实测”统一为“仿真复现”。

退出条件：正文与子仓库最新数据不再矛盾。

#### M0 执行记录（2026-08-12）

**子仓库审计基线**：`AUV-Master-Mag` HEAD `12e1884b59737dbe14e83c825b6cea9bb3c7a4bb`（2026-08-08 23:40:36 +0800）。

`docs/figure/*` 多个 PNG/PDF 相对提交处于 `M`（modified）状态，`results/` 未纳入 Git 跟踪，故 commit 不能单独唯一确定当前图像/结果。因此在迁移前用 SHA256 冻结最小证据包（相对子仓库根目录）：

| 文件 | SHA256（前 16 位） |
|---|---|
| `docs/28_声磁协同方法论合龙.md` | `d7ccb1a1c898c08d` |
| `docs/29_声磁协同实验设计与结果.md` | `fb26f2688288ae44` |
| `docs/31_声磁协同算法部署输入输出规范.md` | `e8931afd64006903` |
| `docs/figure/fig_b1_failure_timeseries.pdf` | `dafdb0f8c514bd83` |
| `docs/figure/fig_d4_prior_alignment_decoupling.pdf` | `5d40d2a75c292dd2` |
| `docs/figure/fig_perception_pipeline.png` | `c6e061e0adb219ab` |
| `docs/figure/fig_zigzag_probe.png` | `4e0661beda984017` |
| `results/20260630_ablation/ablation_sweep.csv` | `3e1b20cac3996666` |
| `results/20260630_radius_boundary/radius_sweep.csv` | `a8ff5ff633f696c2` |
| `results/20260705_zigzag_burial/zigzag_burial_sweep.csv` | `adf67247b91af314` |
| `results/20260705_zigzag_burial/zigzag_burial_tuning_focused.csv` | `017168376c6ed34c` |
| `results/20260705_zigzag_burial/zigzag_burial_tuning_depth2.csv` | `9c447ca7a81869b7` |
| `results/20260705_zigzag_burial/zigzag_burial_tuning_shallow_mid.csv` | `5c84e8644bcfff81` |
| `tools/render_stress_test_figures.py` | `6119bf0b035f2118` |
| `tools/render_prior_alignment_figures.py` | `07d4ee6f5bc175e4` |
| `tools/render_zigzag_burial_figures.py` | `8575028350726e0c` |

完整 64 位哈希由 `sha256sum` 生成，M3 固化 Artifact 时逐项写入 catalog。

**正文事实修正（`thuthesis/data/auv-chap03.tex` 第 3.3.4 节）**：

1. 删除磁场侧 `R<200 m` 失效阈值表述，改为“急弯段方向可辨识性”定性机理，并补注“30 m 环境硬下限前未观测弯道触发失效，瓶颈接近电缆几何物理下限而非固定曲率半径”（见第 5.5.11 节）；
2. 工况 A 由“厘米级跟踪”改为“米级贴线跟踪”，工况 C 由“弯道 `R<200 m`”改为“急弯段方向模糊”；
3. 重写“两条可靠性底线”：稀疏声呐（20\%）跟踪段横偏改为“米级量级而非厘米级”；纯磁续航（声呐初始锁定后中断）横偏改为约 1.7--2.6 m；删除“全盲自救/全盲重捕”，改为“无声呐初始捕获失败”的可观测性负边界；全段显式标注“专用算法仓库单次纯仿真，非主仓端到端或实测”。

**术语核对**：`auv-chap03.tex`/`auv-chap05.tex` 中现存“实测”均指 TMR8637/SK2301/ArUco/PC104 真实采集或“实测噪声回放”，属合规用法，无需改为“仿真复现”；子仓库算法级扫描结果在 §5.5.11 已统一标注“算法级、单次复现、纯仿真”。

**退出条件核对**：正文不再出现 `R<200 m`、`≤0.2 m` 跟踪误差、全盲重捕三处与子仓库当前数据矛盾的强表述。M0 完成。


### M1：补方法图

1. 重绘声磁感知流水线；
2. 精简主动横切可观测性图；
3. 在第 3 章引入两级估计，在第 4 章拆分覆盖扫描与局部主动探查。

退出条件：读者仅看第 2--4 章即可回答“磁信号如何变成横偏/埋深、为什么要横切、结果交给谁”。

### M2：补第 5 章因果图

1. 迁移 B1 失效时序；
2. 迁移 D4/prior alignment 解耦；
3. 从 CSV 重新生成调优后埋深权衡；
4. 必要时重绘留一法主指标图。

退出条件：第 5.5.11 节形成“失效现象→原因消融→机制解耦→运维价值”的连续证据链。

#### M2 执行记录（2026-08-12）

**绘图脚本**：`tools/render_cable_mag_causal_figures.py`（主仓中文排版约定，WenQuanYi CJK），输出至 `docs/thesis/figures/experiments/cable_mag_integration/`。三图溯源见同目录 `CAUSAL_FIGURES_SOURCE.md`。

1. `pure_magnetic_failure_timeseries.{png,pdf}`：重跑子仓库确定性仿真（`case_maze_sonar_dropout_prior_heavy` 基线 vs 关闭在线先验修正的消融），成功复现 +57.5 m 跨车道跳变 @ 约 2119 s、横偏漂移至 30--40 m。接入 §5.5.11“失效现象”，图 `fig:ch05-mag-failure-timeseries`。
2. `prior_alignment_decoupling.{png,pdf}`：读 `lane_shortcut_prior_alignment_{70,50}.csv`；左图全局路由跳变 686.4/724.1 m vs 地图系投影跳变约 0.2 m，右图基线累计约 7.53 m 平移与约 −3.18° 旋转。接入 §5.5.11“机制解耦”，图 `fig:ch05-mag-prior-decoupling`。
3. `zigzag_burial_tradeoff.{png,pdf}`：**按计划 §4.4 图组 C 重绘**，合并三份调优 CSV（`tuning_focused`/`tuning_shallow_mid`/`tuning_depth2`，取 `lat_2p0` 基础覆盖变体）得到 20--36° 完整包络，圈标三个最优点（1.0 m@36°=0.124 m、1.5 m@32°=0.079 m、2.0 m@25°=0.123 m），并增补右面板“埋深精度增益 vs TRACK 横偏/完成度代价”权衡与 0.15 m 参考线。接入 §5.5.11“运维价值”，图 `fig:ch05-mag-zigzag-tradeoff`。

**正文接入**：在 §5.5.11 算法级摘要表（表 `tab:ch05-cable-algorithm-boundaries`）之后、主仓端到端实测段之前插入过渡段与三图，把“摘要口径”还原为可核查因果链。三图 caption 与 alt 均显式标注“专用算法仓库单次纯仿真，`n=1`”，不构成主仓端到端或实测结论。

**边界核对**：三图数值与摘要表逐行对应（纯磁失效时序 / 跨车道压力与地图系解耦 / 之字形埋深估计达标潜力）；留一法机制分解一行暂保留为摘要文本，M3 视排版余量决定是否补 P1 重绘图。

**退出条件核对**：§5.5.11 现已形成“失效现象（图1）→机制解耦（图2）→运维价值（图3）→主仓端到端实测→分层判定”的连续证据链。M2 完成。


### M3：固化 Artifact Manifest

1. 新增 `MAG-CABLE-ALGORITHM-BOUNDARY`；
2. 将选定 CSV、脚本、报告和迁移图纳入；
3. 更新附录 A.7/A.9；
4. 运行 Manifest rebuild 与 `--check`。

退出条件：论文中的每个算法级数字都能回溯到 CSV 和绘图脚本。

#### M3 执行记录（2026-08-12）

1. **新增 artifact**：在 `06_现有证据Artifact_Manifest.catalog.json` 的 `BUILD-R00` 之后插入 `MAG-CABLE-ALGORITHM-BOUNDARY`（`data_layer=algorithm_simulation`、`evidence_grade=C`、`declared_status=complete_with_boundaries`），artifacts 总数 33→34。
2. **文件集**：纳入 §6.2 计划的最小证据包——子仓库方法论/实验/部署契约 3 份 md、8 份结果 CSV（含 dr_ins_boundary、ablation、radius、radius_causality、lane_shortcut×2、zigzag_burial base+3 份调优）、子仓库 3 份参考绘图脚本、主仓 3 份重绘脚本、迁移到主论文的 4 张图（M1 方法图×2、M2 因果图×3 中 png）与 2 份 `_SOURCE.md`、迁移计划本身，共 27 个文件全部 `present`，`required_complete=true`，`artifact_digest_sha256=8b42548b9e66feed…`。`claims_supported`/`claim_boundaries` 严格按 §6.2 措辞写入（关闭即失败机制、投影/配准解耦、之字形达标潜力、30 m 下限语义、n=1 纯仿真等）。
3. **附录更新**：A.9 补足场景族参数（车道长度/50/70 m 间距/U 弯半径/轻中重档）、`passed` 与 `route_progress_large_jump_count` 判据、`map_frame_*` vs `prior_alignment_*` 语义、30 m 扫描下限语义、真值仅离线评价、种子未透传 n=1，并显式指向 artifact `MAG-CABLE-ALGORITHM-BOUNDARY`；A.7 证据矩阵新增“专用仓库算法级电缆边界”行。
4. **Manifest rebuild 与 check**：`python3 tools/build_thesis_artifact_manifest.py` 写出 JSON+MD，`--check` 两项均 `OK`。

退出条件核对：正文 §5.5.11 与附录 A.9 引用的算法级数字均可经 catalog 中带 SHA256 的 CSV/脚本回溯。M3 完成。

### M4：排版与一致性验证

1. 编译 ThuThesis；
2. 检查图中文字是否可读、是否跨页、是否出现 overfull box；
3. 检查所有 caption 均含“专用算法仓库、纯仿真、`n=1`”中的必要限定；
4. 核对摘要、第 3--6 章和附录中的样本量与证据等级；
5. 不因引入子仓库结果而提升实物 handoff 或海试结论。

#### M4 执行记录（2026-08-12）

1. **编译**：`make auv-thesis` 通过（latexmk 报 up-to-date，全部 M0--M3 编辑已进最终 PDF）。log 中 `Undefined control sequence|Citation/Reference undefined|Rerun to get cross-references|Please (re)run Biber` 全部为空，无未定义引用/交叉引用。`sec:ch05-5-5-11`、`sec:app-a-9` 标签均解析。
2. **overfull/图跨页**：全书仅 1 处 overfull hbox（§5 表格内 `depthHeadingAutopilot` 术语，47.7 pt，属既有 PVS 执行链表格）与 1 处 overfull vbox（p101 terrain-following 图页），二者均为迁移前既有项，与本轮新增电缆图无关。5 张新增图（`cable_acoustic_magnetic_perception_pipeline`、`cable_active_crossing_observability`、`pure_magnetic_failure_timeseries`、`prior_alignment_decoupling`、`zigzag_burial_tradeoff`）均正常载入并成图，无新增 overfull、无异常跨页。
3. **caption/alt 限定核对**：三张算法级因果图（§5.5.11）的 caption 与 alt 均显式含“专用算法仓库单次纯仿真，`n=1`”。两张方法图（第 2/3 章）为机理示意图，按其性质标注几何/流水线含义而不冠 `n=1`（非单次实验结果），符合“方法图述机理、结果图述边界”的口径。
4. **样本量与证据等级核对**：摘要（`auv-abstract.tex`）与结论（`auv-chap06.tex`）经关键词扫描仅含主仓端到端结论（六自由度闭环恢复、DL/T1278 验收、R13-v2 36/36、CBF 18/18、R22 96/96），子仓库算法级新结论（纯磁失效时序、之字形埋深调优、跨车道跳变）未上浮至摘要/结论，仍局限于 §5.5.11 与附录 A.9。附录 A.7 新增“专用仓库算法级电缆边界”行，A.9 已补足场景族参数、判据、语义与 `n=1` 限制并指向 artifact。
5. **不提升实物/海试结论**：`MAG-CABLE-ALGORITHM-BOUNDARY` 保持 `evidence_grade=C`、`data_layer=algorithm_simulation`；实物 handoff（`MAG-R08-HANDOFF` 等）与海试边界未被本轮迁移改判。
6. **强表述回归扫描**：`R<200`、`≤0.2 m` 跟踪、`全盲重捕/全盲自救`、`厘米级` 正向断言在正文/摘要/附录中均已消除，仅存否定形（“不能宣称厘米级”“米级量级而非厘米级”“‘全盲重捕’并不成立”），M0 修正保持有效。
7. **Manifest 收口**：发现提交态 `06_...Manifest.json/.md` 早于 M3 catalog 编辑（缺 MAG-CABLE 条目、BUILD-R00 数值陈旧），且三张因果图在边界修复后重生、PDF 重编译致 artifact digest 漂移；已 `rebuild` 同步。另将 BUILD-R00 `sample_scope` 由“175 页 42 图”订正为“180 页 47 图（+5 电缆迁移图）”，`--check` 两项均 `OK`。

**退出条件核对**：编译零未定义引用、无新增 overfull/跨页、所有算法级图 caption 带 `n=1` 纯仿真限定、摘要/结论未上浮子仓库算法级结论、Manifest 一致且真实。M4 完成，本迁移计划（M0--M4）全部收口。

---

## 8. 推荐最终叙事

迁移后的主论文不应把子仓库写成第二套并列系统，而应形成以下单线叙事：

```text
三相海缆弱磁物理
  -> DLIA 与旋转不变模量提取
  -> AUV 主动横切形成峰值/FWHM/局部中心线可观测性
  -> 声呐提供稀疏几何锚点与方向消歧
  -> 载体级 ES-EKF 给出 AUV 位姿及不确定性
  -> 电缆几何级在线修正吸收先验平移/旋转误差
  -> map-frame 约束投影连续性
  -> 行为树/FSM 按观测质量安排搜索、锁定、跟踪和重捕
  -> UA-MPC/内层执行链消费可信参考
  -> 数字孪生和算法级消融分别验证链路与机制边界
```

其中子仓库最有价值的贡献是补齐四个问题：

1. 磁观测为什么需要由运动主动激励；
2. AUV 位姿估计与电缆几何估计为什么应分层；
3. 错位先验为什么会在 U 弯转化为跨车道跳变；
4. 投影连续、物理配准和任务完成为什么不是同一个概念。

这四点比继续增加通用架构图或更多场景截图更能丰富主 ThuThesis 的算法深度。

---

## 9. 本轮建议

建议先实施 M0--M2，不直接整体复制 `AUV-Master-Mag/thesis/figures`。最小高收益组合为：

1. 修正第 3.3.4 节三处过强结论；
2. 新增声磁感知流水线图；
3. 新增主动横切可观测性图；
4. 在第 5.5.11 节加入 B1 失效时序和 D4/prior alignment 解耦图；
5. 基于四份 CSV 重绘调优后埋深结果；
6. 完成后再建立 `MAG-CABLE-ALGORITHM-BOUNDARY` Artifact。

该组合能在不改变主论文系统架构和已完成实验结论的前提下，把当前“摘要表式引用”提升为“原理图+因果图+边界图”的完整电缆巡检算法论证。
