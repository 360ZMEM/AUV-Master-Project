# 24 Draw\.io 全量视觉重构与论文图注同步计划

> 建立时间：2026-08-13\
> 完成时间：2026-08-16\
> 当前状态：**批 0--5 与最终出版验收均已完成；本文同时保留改前审计、逐图计划和改后证据**。\
> 平台职责：Darwin/macOS，属于 `AGENTS_macwin.md` 规定的架构图维护与出版装配任务。\
> 总体目标：逐张消除图内标题/副标题/图注重复、文字过小、层级不清、形状单一、连线重叠和无效留白；同步增强 LaTeX/Markdown 图注，并补齐 `AUV-Master-Mag` 磁相关 Draw\.io 的来源链与论文链接。

***

## 0. 审计范围与事实源

### 0.1 数量

本轮共涉及 **21 张逻辑图、32 个物理** **`.drawio`** **文件**：

| 类别            | 逻辑图数 | 位置                                            | 处置定位                         |
| ------------- | ---: | --------------------------------------------- | ---------------------------- |
| 主仓论文 Draw\.io |   13 | `docs/thesis/figures/architecture/`           | 10 张已进入 ThuThesis，3 张为候选/历史图 |
| 主仓内部实现图       |    3 | `docs/internals/figures/architecture/`        | 只用于内部文档，不回填论文正文              |
| 磁专用方法图        |    5 | `AUV-Master-Mag/docs/figure/`                 | 2 张已有主仓学术化重绘，3 张为内部/附录候选     |
| 磁仓旧架构副本       |   11 | `AUV-Master-Mag/thesis/figures/architecture/` | 与主仓 8 张、内部目录 3 张同名但已分叉，不独立设计 |

### 0.2 两个 `AUV-Master-Mag` 工作树

* 论文内嵌仓：`AUV-Master-Project/AUV-Master-Mag`，提交 `12e1884`，工作树干净，是当前论文审计基线。

* 外部工作树：`/Users/bytedance/coding/AUV-Master-Mag`，提交 `5b3bb95`，另有用户修改 `src/auv_mag_tracking/main_viz.py`。

* 11 张 `thesis/figures/architecture` 架构图在两个工作树中哈希一致；磁专用 `docs/figure` 已分叉。例如外部工作树把 `fig_zigzag_probe` 多数正文从 14 号降至 11 号，**不满足本轮“增强文字醒目程度”目标，不能反向覆盖论文基线**。

### 0.3 单向事实源

1. 主仓 13+3 张通用图，以 `docs/thesis/figures/architecture/generate_architecture_diagrams.py` 的重构版本为可再生事实源，`.drawio` 为可编辑出版源。
2. `auv_thesis_technical_route.drawio` 当前不在生成器中，执行时纳入同一风格规范，但保持独立源文件。
3. 磁专用 5 张图以论文内嵌仓 `AUV-Master-Mag/docs/figure/*.drawio` 为本轮基线。
4. `AUV-Master-Mag/thesis/figures/architecture` 的 11 份旧副本不作为事实源；重构后通过 manifest、哈希和定向同步建立来源关系，禁止整目录覆盖主仓。

***

## 1. 当前全局问题

### 1.1 图内重复文本

* 主仓 13 张图中，12 张含图内主标题；除技术路线外，12 张含说明性副标题；12 张含图内“图注”。

* 行为树、状态机、紧急仲裁还含底部图例或规则说明。

* 磁专用 5 张图全部含大标题和图内图注。

* 图内标题、副标题、图注与 LaTeX `\caption`、Markdown 图题重复，造成上、下边缘大面积空白；用户示例中的任务状态机正是最明显案例。

**统一处置**：

1. 删除图内主标题、说明性副标题、`图注：`、底部规则说明。
2. 必要的语义图例只保留最短符号说明；能够由形状、颜色和箭头直接表达的图例全部删除。
3. 被删信息合并入 LaTeX `\caption` 与 Markdown 图题；`alt` 保持与图注语义一致但更偏可访问性描述。

### 1.2 字号与文字层级

* 当前主仓图节点多为 15--17，边标签多为 14--15；磁仓部分图为 11--14。

* 按 `0.88--0.95\linewidth` 缩入 A4 后，边标签和次级说明明显偏小。

* 节点内中英文、模块名、职责说明常以同一字重出现，读者无法快速区分“模块是什么”和“模块做什么”。

**统一处置**：

* 节点主标签：20--22，粗体。

* 节点次标签：18--20，常规字重。

* 连线标签：不低于 17--18；只保留必要动作/数据语义。

* 泳道/架构区标题：20--22，粗体。

* 不再使用图内 28 号总标题；通过紧裁后放大主体本身。

* 中文优先 Noto Serif CJK SC，英文/公式 Times New Roman；不使用负字距。

### 1.3 形状语义单一

XML 统计显示，除泳道外，大部分图几乎只使用圆角矩形：

* 技术路线：6 个节点全部圆角矩形。

* 功能闭环、能力地图、不确定性流向：全部为圆角矩形。

* 行为树：11 个节点全部圆角矩形。

* 生命周期：20 个过程全部圆角矩形。

**统一形状词汇**：

| 语义                    | 形状                                     |
| --------------------- | -------------------------------------- |
| 输入/输出、外部条件            | 平行四边形                                  |
| 主要过程、算法、模块            | 直角矩形或小圆角矩形（圆角不超过 4--6 px）              |
| 判断、授权、守卫              | 菱形                                     |
| 验证门、准入门               | 倒梯形                                    |
| 日志、证据、数据库、最终成果        | 圆柱体                                    |
| 状态                    | UML 状态框；起止态可用椭圆/终止符                    |
| 系统/角色/硬件边界            | 泳道或容器                                  |
| 行为树 Selector/Sequence | 明确的 BT 控制节点符号；Condition 用菱形，Action 用矩形 |

### 1.4 层级和架构区分

* 多张图只有“散点节点 + 连线”，缺少系统边界、角色边界、在线/离线边界或控制/证据边界。

* `auv_v2_emergency_transition` 把 ROS2 仲裁、AutonomyGuard、PC104 本地覆盖压在同一平面。

* `auv_v2_mission_state_machine` 把正常升级、任务完成、安全回退和复位回路混在同一二维区域。

* `auv_runtime_dataflow`、ROS2 拓扑等实现图虽然有泳道，但边标签和回路仍穿过模块。

**统一处置**：

* 架构图优先使用 2--4 个明确区域，区域标题只说明职责，不写文件路径。

* 主路径沿一个方向展开；反馈、异常、复位走独立轨道。

* 同层模块等宽等高；跨层关系通过专用纵向通道连接，不穿过无关节点。

### 1.5 连线和重叠

视觉审计已确认：

* 任务状态机：`任务完成`、`置信度不足`、`偏差过大`、`复位再预检` 等回路贴近或穿越，标签尺寸过小。

* 紧急仲裁：4 条监听线共用顶部总线，4 条输出共用底部总线，文字贴线且入口拥挤。

* 生命周期：签发、告警、回收指令穿过泳道边界，局部箭头与容器线重合。

* ROS2 拓扑：多个 Topic 标签相互贴近，回环线穿越容器和节点。

* 子系统组织：反馈、仿真替身、扰动和观测证据回路集中在左/下侧。

* 磁状态机层级：长文本、虚线联动和层标题争夺同一空间。

**统一处置**：

* 每个多连接节点分配独立 `entryX/entryY/exitX/exitY`。

* 反馈和异常使用固定外侧轨道；实线主流、虚线反馈、红线安全回退。

* 箭头最后一段至少 20 px；标签置于长度足够的直线段中部。

* 禁止连接线穿过无关形状、文字和泳道标题。

* 导出后逐图放大检查交叉点，不能只依赖 XML 几何不相交。

### 1.6 留白与画布利用率

去除标题/副标题/图注前，主体画布利用率多为 43%--61%：

* 行为树约 43%。

* 任务状态机约 44%。

* 双脑架构约 47%。

* 五层架构约 49%。

* 不确定性流向与安全部署约 50%。

**统一处置**：

* 删除图内出版文本后重排主体，不只机械裁剪。

* 主体包围盒目标占导出图面积 75%--90%。

* 导出边界默认 20--28 px，外侧反馈回路另留 24--40 px。

* 禁止为了填满画布拉伸单个节点；通过缩短层间距、压缩无信息空区、增大文字和主结构实现紧凑。

### 1.7 再生链缺陷

* `generate_architecture_diagrams.py` 仍使用旧的节点 14、边标签 12、标题 24 模板。

* 当前 `.drawio` 中的 28/16 字号和图内图注是后处理结果，生成器未同步，重跑会回退。

* 生成器仍把代码层、ROS2 拓扑、安全部署 3 张内部图写入论文 `architecture/` 目录。

* `auv_system_subsystem_organization.drawio` 重复使用 XML id `s1`。

* `auv_system_verification_deployment_ladder.drawio` 的 `g1`--`g5` 同时用于证据节点和边。

**执行前置条件**：先修生成器、输出路由、id 规则和统一样式 API，再改图；禁止直接批量修改导出 PNG。

***

## 2. 逐图修订计划

### 2.1 已进入 ThuThesis 的 10 张主图

| 图                                           | 当前主要问题                                                 | 计划重构                                                                                                  |
| ------------------------------------------- | ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| `auv_thesis_technical_route`                | 图内标题；节点全为圆角矩形；三级研究主线与验证/目标形状无区分；边标签偏小                  | 顶部“需求”改平行四边形；系统、估计、控制改过程矩形；验证改倒梯形；最终目标改圆柱体；保持自上而下主线，放大边标签；图名和目标说明并入图 1.x 图注                           |
| `auv_system_autonomy_functional_loop`       | 标题/副标题/图注重复；主体约 52%；环境、人工、证据与核心过程形状相同；左侧控制回路与传感回路贴近    | 将环境/人工监督设为外部输入，核心“感知→状态→决策→控制”设为过程链，安全治理设为侧向守卫，运行证据设为圆柱体；反馈走下方独立虚线轨道                                  |
| `auv_v2_dual_brain_async_hardware`          | 标题/副标题/图注；中央协议边界过宽且空；“左大脑/右小脑”内部说明重复；轻量控制意图与反馈线较长      | 保留 Jetson/PC104 两个硬件泳道；中央改为窄协议总线和上下行端口，突出 72 B 下行/145 B 上行；感知、决策、规划与内环、驱动、失联保护纵向对齐；外部说明并入图注           |
| `auv_v2_five_layer_functional_architecture` | 标题/副标题/图注；五层均为同类容器；4 条跨层边靠近边界标题；“运行态势/可行域约束”易压线        | 保留层级架构但将入口输入改平行四边形、治理判断改菱形、算法过程改矩形、协议/物理约束改基座；跨层接口统一放在左/右侧纵向总线；正文层名与图中逐字对齐                            |
| `auv_system_verification_deployment_ladder` | 标题/副标题/图注；上层容器空白过多；“阶梯”实际为水平方框；重复 id `g1`--`g5`        | 重画为六级阶梯/准入门；每级由“阶段模块 + 准入倒梯形 + 证据圆柱体”构成；当前能力与未来阶段只用边框/填充状态区分，不暗示全自主已完成；修复全部 id                        |
| `auv_v2_uncertainty_highway`                | 标题/副标题/图注；中央虚线框过大；输入、估计、量化和执行形状同质；上下空白大                | 上层重画为“扰动输入→观测退化→ES-EKF→协方差/置信度”的流水线；中部改为窄置信度总线；下层分行为决策与控制调度两条支路；执行端统一汇合，公式/阈值留正文                      |
| `auv_v2_mission_state_machine`              | 用户点名问题：标题、副标题、规则、图注；主体约 44%；文本小；主线状态与完成/安全状态相距大；回路重叠   | 完整重排：正常能力释放放上方主轨；`COMPLETE` 放主轨末端下方；`SAFE_HOLD` 放独立安全轨；任务完成、安全触发、偏差/置信度回退分别走不同高度；复位和回空闲走最外侧回路；规则并入图注  |
| `auv_v2_behavior_tree_illustration`         | 标题/副标题/图例/图注；主体约 43%；所有 BT 节点均为圆角矩形；step 标签偏小          | 使用明确 BT 语义：Selector/Sequence 控制节点、Condition 菱形、Action 矩形、Idle 终端；安全与任务子树用浅色分区；删除图内图例，优先级和抢占关系写入图注     |
| `auv_v2_emergency_transition`               | 标题/副标题/规则/图注；顶部监听总线和底部输出总线拥挤；ROS2/Guard/PC104 三层安全语义混杂 | 重画为三层架构：守卫输入层、ROS2/AutonomyGuard 仲裁层、PC104 本地安全覆盖层；输入用平行四边形，权限判断用菱形，安全动作按层分区；零指令、遥控锁定、本地上浮、急停不再平铺为同一级 |
| `auv_v2_mission_lifecycle_flow`             | 标题/副标题/图注；20 个圆角过程同质；签发、告警、回收线穿泳道；`加载 yaml` 偏实现表述      | 保留四泳道，改为左到右时间轴并增加阶段列；操作员输入用平行四边形，授权门用倒梯形/菱形，执行过程用矩形，报告/归档用圆柱体；“加载 yaml”改“装载任务配置”；跨泳道箭头走阶段列之间的专用通道     |

### 2.2 主仓未入正文的 3 张候选图

| 图                                   | 当前主要问题                                    | 计划重构与使用边界                                                                     |
| ----------------------------------- | ----------------------------------------- | ----------------------------------------------------------------------------- |
| `auv_runtime_dataflow`              | 标题/副标题/图注；大量实现名；上下两条路径密度不均；回环跨度大          | 先迁为内部/第五章候选图；若进正文，节点叙述化为“单进程算法闭环/桥接集成闭环”，输入输出用平行四边形，协议/日志用圆柱体，证据等级写入 LaTeX 图注 |
| `auv_system_capability_map`         | 标题/副标题/图注；主体约 50%；中心辐射布局空白大；能力规划易被误读为均已验收 | 压缩为中心平台 + 六个功能区，外部系统与证据输出形状区分；如不进入正文，仅用于内部总览；若采用，图注必须写“能力地图不表示各能力均已完成实物闭环”    |
| `auv_system_subsystem_organization` | 标题/副标题/图注；反馈线集中；重复 XML id `s1`            | 修复 id；保留地面/艇载/环境三泳道，控制、观测、安全各用独立跨层通道；减少边标签；作为第二章可选图，不与功能闭环、双脑架构重复插入           |

### 2.3 主仓内部实现图 3 张

| 图                               | 当前主要问题                                      | 计划重构                                                                                               |
| ------------------------------- | ------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `auv_code_layer_architecture`   | 标题/副标题/图注；文件名多且小；多条跨层线绕行；生成器输出目录错误          | 保留实现名但增大到内部文档可读字号；包/层为容器，入口用平行四边形，模块用矩形，协议产物用圆柱体；输出固定到 `docs/internals/`，不进入 ThuThesis             |
| `auv_ros2_node_topology`        | Topic 标签与边高度重叠；上方回路穿越容器；端口、节点、证据形状相同        | 使用外部系统、ROS2 节点、证据三层；Topic 走独立水平总线，节点以组件框表示，bag/MCAP 用圆柱体；必要时拆成“在线闭环”和“观测记录”两幅内部图                   |
| `auv_safety_arbiter_deployment` | 标题/副标题/图注；控制权、影子、回退连线在 Jetson 区相交；阈值语义未显式分层 | 保留 PC/Jetson/PC104 三列；Guard/Arbiter 用菱形，影子路径单独虚线通道，执行输出与安全回退分离；补 passive/shadow、零执行器验证和分层阈值，但不回填正文 |

### 2.4 磁专用方法图 5 张

| 图                            | 当前主要问题                                            | 计划重构与论文链接                                                                                                                                          |
| ---------------------------- | ------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `fig_arch_onion`             | 大标题/图注；代码实现名多；全部圆角；左侧竖排层名拥挤                       | 保留五层架构和右侧 20 Hz 闭环，但改为清晰泳道；传感输入用平行四边形，过程用矩形，输出状态用圆柱体；作为磁仓方法总图/附录候选，不直接替代主论文全系统架构                                                                   |
| `fig_perception_pipeline`    | 超大标题/图注；上下折返造成中部大量空白；200/20 Hz 已不是主仓当前统一口径；代码变量名多 | 磁仓内部图按其代码事实重构；主论文继续使用 `cable_acoustic_magnetic_perception_pipeline` 学术化重绘，不直接链接原图；`_SOURCE` 记录 Draw\.io 来源与差异                                      |
| `fig_zigzag_probe`           | 超大标题/图注；主体只占中部；标签相互贴近；声呐消歧箭头压在线条上；外部工作树新版字号更小     | 以论文内嵌仓 14 号版本为基线重画，删除标题/图注并放大航迹、观测点、中心线和角度/周期标注；主论文仍使用含 FWHM 下半图的 `cable_active_crossing_observability`，补齐“原始 Draw\.io→主仓重绘→第 2.3.5/4.3.1 节”的显式来源链 |
| `fig_mission_fsm`            | 大标题/图注；状态和回路线分散；任务 FSM 名称易与整艇 Mission FSM 混淆      | 重命名为“电缆跟踪子任务五态 FSM”；正常状态主轨、重捕支轨、应急终态分离；只作为磁仓/附录候选，不替换第 4 章整艇能力释放状态机                                                                                |
| `fig_statemachine_hierarchy` | 大标题/图注；文本过多；长虚线绕图；“任务 FSM 唯一权威”与主论文全局 BT 容易冲突     | 若用于论文，重写为“BT 电缆跟踪子树→跟踪模式 FSM→控制/感知子机制”；使用三层容器和最短接口标签；否则仅保留磁仓内部说明                                                                                   |

***

## 3. LaTeX / Markdown 图注同步计划

### 3.1 统一规则

1. 图注不再出现“draw\.io 架构图”等工程来源说明。
2. 图注负责容纳原图标题、原副标题中必要的抽象边界，以及原图底部规则。
3. 图注只解释“图表达什么”，不重复正文整段论证；证据等级、未完成阶段等必须保留。
4. 同一图片被不同章节复用时允许图注侧重点不同，但不得给出相互冲突的状态边界。

### 3.2 已入正文图的拟定图注

| 图      | 拟定图注要点                                                                       |
| ------ | ---------------------------------------------------------------------------- |
| 技术路线   | “任务约束驱动双脑系统、声磁估计和分层决策控制，并由多层验证界定迁移边界”                                        |
| 自主功能闭环 | “环境/艇体、感知、状态理解、任务决策、运动控制、安全治理、人工监督和运行证据构成闭环”                                 |
| 双脑硬件架构 | “Jetson 承担非实时感知决策优化，PC104/VxWorks 承担硬实时内环、驱动与失联保护；72 B 下行与 145 B 上行解耦”       |
| 五层功能架构 | “入口配置、虚实适配、自治安全、数学算法、协议与物理约束五层及其接口传递”                                        |
| 验证部署阶梯 | “算法仿真至全自主试验的逐级能力释放与对应证据；右端是准入目标，不表示均已完成”                                     |
| 不确定性流向 | “观测退化经 ES-EKF 协方差和置信度映射成为跨层信号，分别驱动行为降级和控制调度”                                 |
| 任务状态机  | “IDLE→PREFLIGHT→SHADOW→SINGLE LOOP→FULL AUTONOMY 的分级释放、任务完成与安全回退；任一阶段保留回退通道” |
| 行为树    | “Selector 以安全监督优先抢占任务序列，Condition 与 Action 的执行关系及回落路径”                       |
| 紧急仲裁   | “通信/遥测/置信度/漏水/人工急停的分层处置：ROS2 回零/锁定与 PC104 本地上浮/防触底不属于同一级动作”                  |
| 生命周期   | “操作员、安全守卫、决策控制脑和执行反馈端协同完成配置、授权、执行、回退、报告与人工回收”                                |

### 3.3 同步对象

* LaTeX：`thuthesis/data/auv-chap01.tex`、`auv-chap02.tex`、`auv-chap03.tex`、`auv-chap04.tex`。

* Canonical Markdown：`docs/thesis/paper/01_background_and_significance.md`、`02_system_design.md`、`03_state_estimation.md`、`04new_decision_and_control.md`。

* Beamer：`thubeamer-1.2/defense/02_system.tex`、`03_perception.tex`、`04_decision_control.tex`、`05_evidence.tex`。

* 磁仓文档：`AUV-Master-Mag/docs/28_*.md`、`29_*.md`、`30_*.md`、`docs/figure/README_figures.md`。

***

## 4. `AUV-Master-Mag` 链接与去重方案

### 4.1 11 张 `thesis/figures/architecture` 旧副本

对应关系：

* 与主仓同名：`auv_runtime_dataflow`、`auv_system_autonomy_functional_loop`、`auv_system_capability_map`、`auv_system_subsystem_organization`、`auv_system_verification_deployment_ladder`、`auv_v2_dual_brain_async_hardware`、`auv_v2_five_layer_functional_architecture`、`auv_v2_uncertainty_highway`。

* 与内部目录同名：`auv_code_layer_architecture`、`auv_ros2_node_topology`、`auv_safety_arbiter_deployment`。

处置：

1. 不建立跨仓绝对路径或越出仓库的符号链接，避免独立 clone 失效。
2. 新建 `_SOURCE.md`/manifest，记录每张图的主仓 canonical 路径、同步提交与 SHA256。
3. 主仓修订完成后仅定向同步这 11 张的 `.drawio/.png/.svg/.drawio.png`；不从磁仓反向覆盖主仓。
4. 若磁仓需要独立发布，保留副本；若不再发布，则在其 README 中改为指向主仓 canonical 图。

### 4.2 Zig-zag 来源链

当前事实：

* 原始可编辑源：`AUV-Master-Mag/docs/figure/fig_zigzag_probe.drawio`。

* 主仓学术化重绘：`docs/thesis/figures/architecture/cable_active_crossing_observability.{png,pdf}`。

* 生成脚本：`tools/render_cable_active_crossing_figure.py`。

* 来源说明：`docs/thesis/figures/architecture/cable_method_figures_SOURCE.md`。

* LaTeX 已落点：第 2.3.5 节图 `fig:ch02-active-crossing`；第 4.3.1 节当前只有正文概念，需核对是否补交叉引用。

计划：

1. 在来源说明中增加原 `.drawio` 相对路径、内嵌仓提交、完整 SHA256 与新版导出哈希。
2. 为主仓重绘补一个可编辑 Draw\.io 版本，或明确脚本是唯一可编辑事实源；二者只选其一，避免双真源。
3. 第 4.3.1 节仅交叉引用第 2.3.5 节的“局部主动探查”图，不重复插图；正文继续区分 SEARCH 覆盖之字形与 TRACK/REACQUIRE 主动横切。
4. 外部工作树的 11 号字版本不进入论文；若后续同步外部仓，先从论文批准版本生成。

***

## 5. 执行分批与顺序

### 批 0：备份与生成器治理

1. 建立改前备份及源/导出哈希清单。
2. 重构 `generate_architecture_diagrams.py`：

   * 移除图内标题、副标题、图注生成。

   * 新增平行四边形、倒梯形、圆柱体、BT 控制节点等 shape helper。

   * 提高字体与边标签基线。

   * 唯一 id 生成和重复 id 门禁。

   * 3 张内部图输出到 `docs/internals/figures/architecture/`。
3. 增加静态检查脚本：XML 可解析、id 唯一、源/目标存在、字体下限、禁止 `caption_auto`/`图注：`。

### 批 1：高优先级正文图

1. `auv_v2_mission_state_machine`。
2. `auv_v2_emergency_transition`。
3. `auv_v2_mission_lifecycle_flow`。
4. `auv_v2_behavior_tree_illustration`。

原因：这 4 张存在最明显的重叠、回路、细字和层级混杂，也是用户示例直接指出的问题。

### 批 2：系统架构正文图

1. `auv_thesis_technical_route`。
2. `auv_system_autonomy_functional_loop`。
3. `auv_v2_dual_brain_async_hardware`。
4. `auv_v2_five_layer_functional_architecture`。
5. `auv_system_verification_deployment_ladder`。
6. `auv_v2_uncertainty_highway`。

### 批 3：主仓候选与内部实现图

1. `auv_runtime_dataflow`。
2. `auv_system_capability_map`。
3. `auv_system_subsystem_organization`。
4. 3 张 `docs/internals` 实现图。

此批只改善图面和维护性，不擅自加入论文正文。

### 批 4：磁专用图与来源链接

1. `fig_zigzag_probe`。
2. `fig_perception_pipeline`。
3. `fig_arch_onion`。
4. `fig_mission_fsm`。
5. `fig_statemachine_hierarchy`。
6. 更新 `cable_method_figures_SOURCE.md` 和磁仓 README/正文引用。
7. 定向同步 11 张 `AUV-Master-Mag/thesis/figures/architecture` 旧副本或登记 canonical 指针。

### 批 5：图注、格式与出版切换

1. 同步 LaTeX、canonical Markdown 和 Beamer 图注。
2. 正文 Draw\.io 主图额外导出 PDF，LaTeX 优先切换到矢量 PDF；Markdown 保留 PNG。
3. 更新图号、交叉引用和 `alt`。
4. 重新构建论文与答辩稿。

***

## 6. 每张图的修订循环

每张图单独完成以下闭环，不能一次批量改完再统一看：

1. 从事实源重构 `.drawio`。
2. 草稿导出：不带 `-e`，PNG 2 倍缩放、20--28 px 边界。
3. 第一轮视觉检查：

   * 标题/副标题/图注是否清零。

   * 节点文字是否可读、是否截断。

   * 形状语义是否一致。

   * 连线是否穿框、穿字、共线或缺箭头。

   * 主体是否紧凑且层级明确。
4. 第二轮 A4 检查：按论文实际 `0.88--0.95\linewidth` 缩放，确保最小文字仍可辨认。
5. 最多两轮自动修正后提交逐图预览；用户确认后再进入下一张或同批下一组。
6. 最终导出：

   * `.drawio`

   * `.png`

   * `.svg`

   * `.drawio.png`（带 `-e`，随后运行 `repair_png.py`）

   * 正文主图另导出 `.pdf`
7. 更新源清单与哈希，不保留 `v1/v2/final_final` 式临时文件。

***

## 7. 验收门禁

### 7.1 XML 与资产

* 所有 `.drawio` 可由 Draw\.io 30.3.14 打开。

* XML id 全局唯一；边 source/target 均存在。

* 图内 `图注：`、`caption_auto`、总标题/说明副标题命中为 0。

* 所有正文图具备 `.drawio/.png/.svg/.drawio.png/.pdf`。

* `.drawio.png` 完成 IEND 修复；PNG/SVG/PDF 均可读取。

### 7.2 视觉

* 无节点重叠、文字截断、箭头断裂、边穿节点、标签压线。

* 同一节点 2 条以上连接时入口/出口分散。

* 主体面积占导出画布 75%--90%。

* A4 实际缩放下正文主标签、边标签可读。

* 颜色、形状、线型具有语义，不依赖颜色单独传达关键信息。

* 图中不出现无必要文件名、变量名和工程路径；内部实现图除外。

### 7.3 论文

* LaTeX 与 canonical Markdown 图注语义一致。

* `draw.io 架构图` 等来源字样从正式图注删除。

* 图号和 `\ref` 无 undefined/multiply-defined。

* ThuThesis 与 Beamer 构建成功，日志无缺图。

* 检查图片在正文页中的最终字号、浮动位置和与图注间距。

***

## 8. 本轮未扩展的事项

* 未把内部代码层、ROS2 Topic 和安全仲裁部署图直接放进论文正文。

* 未从外部 `/Users/bytedance/coding/AUV-Master-Mag` 工作树覆盖论文内嵌仓；外部工作树的
  `src/auv_mag_tracking/main_viz.py` 用户修改保持原样。

* 未把磁子任务 FSM 替代整艇 Mission FSM。

* 未重复插入原始 zig-zag 图与主仓 FWHM 重绘图；采用来源链和跨章交叉引用。

***

## 9. 已完成交付物

1. 21 张逻辑图全部完成逐图修订和视觉验收。
2. 32 个物理 Draw\.io 文件得到明确的 canonical/副本关系。
3. 正文 10 张 Draw\.io 主图完成 PDF 矢量出版切换。
4. LaTeX、canonical Markdown、Beamer 图注同步。
5. `AUV-Master-Mag` 磁相关原图、主仓重绘、论文落点形成可追溯链接。
6. 一份逐图改前/改后截图、哈希、图注和构建结果验收记录。

***

## 10. 执行与最终验收记录

### 10.1 分批完成状态

| 批次 | 状态 | 完成内容 |
| --- | --- | --- |
| 批 0 | 完成 | 建立改前备份与哈希；重构主生成器的形状、字体、边、锚点和输出路由；新增严格静态门禁与磁仓单向同步脚本 |
| 批 1 | 完成 | 重构任务状态机、紧急仲裁、任务生命周期和行为树；分离主轨、反馈轨、安全轨与 BT 控制/条件/动作语义 |
| 批 2 | 完成 | 重构技术路线、自主功能闭环、双脑架构、五层架构、验证阶梯和不确定性流向 |
| 批 3 | 完成 | 重构 3 张论文候选图与 3 张内部实现图；ROS2 Topic 改为中央总线，安全仲裁的执行、影子和回退路径分轨 |
| 批 4 | 完成 | 重构 5 张磁专用图；建立 zig-zag、感知管线、主仓学术化重绘和论文落点的来源链 |
| 批 5 | 完成 | 同步 LaTeX、canonical Markdown、Beamer 和磁仓文档图注；正文与答辩中的 Draw\.io 图切换为 PDF 矢量出版物 |
| 终检 | 完成 | 重导出全部格式，修复嵌入式 PNG，构建 ThuThesis/ThuBeamer，扫描日志并完成论文页和幻灯片页视觉抽检 |

### 10.2 再生链与静态门禁

* 主仓生成器：`docs/thesis/figures/architecture/generate_architecture_diagrams.py`。
* 磁图生成器：`AUV-Master-Mag/docs/figure/generate_drawio_method_figures.py`。
* 严格门禁：`docs/thesis/figures/architecture/validate_drawio_architecture.py --strict-publication`。
* 单向同步：`docs/thesis/figures/architecture/sync_mag_architecture_copies.py`。
* 21/21 张逻辑图通过 XML 解析、id 唯一、端点合法、标题/图注残留、字体下限和字体族门禁。
* 13 张主仓图均具备 `.drawio/.png/.svg/.drawio.png/.pdf`；3 张内部图具备
  `.drawio/.png/.svg/.drawio.png`；5 张磁图具备 `.drawio/.png/.svg/.drawio.png/.pdf`。
* 21 个嵌入式 PNG 末尾均为完整 IEND；18 个 Draw\.io PDF 均嵌入
  `STSongti-SC-Regular/Bold`。

### 10.3 PDF 字体故障与补充修复

首次正文 PDF 切换后，页级抽检发现旧字体串
`Noto Serif CJK SC,Times New Roman` 被 Draw\.io 30.3.14 的 PDF 导出器解释为
Times New Roman，中文在 PDF 中退化为点号。该问题在普通 PNG 中不可见，只有联合构建后的
PDF 页和 `pdffonts/pdftotext` 能揭示。

最终处置：

1. 两个生成器和独立技术路线源统一改为单一 `Songti SC`；
2. 严格门禁拒绝逗号分隔字体串和非 `Songti SC` 出版字体；
3. 全量重导出 13+3+5 张图；
4. 用 `pdffonts` 精确核验 18 个同名 Draw\.io PDF 的宋体嵌入；
5. 重新构建并覆盖论文页/幻灯片页审阅快照。

字体切换后的第二轮视觉检查还发现内部
`auv_safety_arbiter_deployment` 中 `AutonomyGuard` 与“候选命令”边重叠；已增高守卫菱形，
并将候选命令改走守卫与控制权仲裁之间的独立水平通道。

### 10.4 出版构建与日志

* ThuThesis：`thuthesis/auv-thesis.pdf`，181 页 A4，7,251,978 B。
* ThuBeamer：`thubeamer-1.2/auv-defense.pdf`，20 页 16:9，1,037,197 B。
* 两份构建均无 undefined reference、multiply-defined label、缺图或致命错误。
* 论文日志仍有第 5 章旧表格在 `auv-chap05.tex` 632--650 行对应的 4 处
  `Overfull \hbox`；其位置与本轮图形和图注无关。答辩日志无 Overfull/Underfull。
* 本任务定向 `git diff --check` 与内嵌磁仓 `git diff --check` 均通过；全仓未处理用户已有的
  `csd_vx6.8_lastest/DataProcess.c` 合并冲突。

### 10.5 最终视觉抽检

论文逻辑页 11、15、17、19、20、26、36、37、40、50、58、62 已按最终 PDF 重新渲染；
答辩第 5、6、8、10、14 页已按最终 PDF 重新渲染。检查结果：

* 中文完整，无点号替代、缺字或字体回退；
* 图内无标题/副标题/图注重复；
* 图注未挤压正文，图形未越出版芯；
* 节点、箭头、标签和泳道边界无不可解释重叠；
* 第 58 页同页状态机/行为树、第 62 页紧急仲裁及五张答辩图均可读、无裁切。

审阅快照位于：

`毕业设计写作文档/潜在待完成事项/_backup_24_drawio_20260813/final_publication_review/`

### 10.6 哈希与来源追溯

* 改前 21 图源哈希：`_backup_24_drawio_20260813/SHA256_BEFORE.txt`。
* 改后 21 图源哈希：`_backup_24_drawio_20260813/SHA256_AFTER.txt`。
* 改后 102 个源/导出资产哈希：`_backup_24_drawio_20260813/SHA256_AFTER_ASSETS.txt`。
* 主仓与磁仓两张方法图来源链：
  `docs/thesis/figures/architecture/cable_method_figures_SOURCE.md`。
* 11 张磁仓架构快照及 SHA256：
  `AUV-Master-Mag/thesis/figures/architecture/_SOURCE.md`。

至此本轮 Draw\.io 全量视觉重构无遗留项。后续若在 Linux 或其他未安装 `Songti SC` 的平台
重新生成 PDF，应保留当前已嵌入字体的出版物，或先安装等价中文宋体并再次执行字体嵌入门禁。
