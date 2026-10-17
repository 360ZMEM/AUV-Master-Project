# thuthesis 论证与图像治理记录

## 1. 任务边界与基线

- 论文主入口：`thuthesis/auv-thesis.tex`。
- 正文章节：`thuthesis/data/auv-chap01.tex` 至 `auv-chap06.tex`；附录为 `auv-appendix-a.tex`；中英文摘要为 `auv-abstract.tex`；符号表为 `auv-denotation.tex`。
- 参考文献：`thuthesis/ref/auv-references.bib`，由 `biblatex + biber` 处理。
- 构建命令：`make -C thuthesis auv-thesis`；项目现有 `latexmkrc` 使用 XeLaTeX、Biber 和 xdvipdfmx。
- 图片搜索根目录由 `thuthesis/auvsetup.tex` 指向 `docs/thesis/figures/`；架构图以同目录 `.drawio` 为权威可编辑源，论文使用同名 PDF。
- 2026-09-20 基线构建：PASS。构建前 PDF、论文源文件和全部论文图资产已保存到 `.auv_data/thesis-refactor-baseline/`；当前基线 PDF SHA-256 为 `7011bd550e1a99e6fbfdf6f474586ad79fc17dd703820240210f47e7e706357d`。
- 更新版治理后 PDF：`thuthesis/auv-thesis.pdf`，189 页 A4，SHA-256 为 `0815c8bf57461312f71c10805583c6aab35ce17f053d6970b069d329820f9f48`。
- 工作区在本任务开始前已有大量未提交修改；其中 `auv-chap02.tex`、`auv-chap03.tex`、`auv-chap05.tex` 和 `auv-denotation.tex` 已修改。本轮保留这些修改并在其上增量治理，不回滚代码、论文或实验资产。

## 2. 治理目标与执行计划

论文按四个研究问题组织：如何形成有效几何观测，如何评价并传播不确定性，如何据此完成任务决策与安全执行，以及这些设计分别得到什么层级的证据。

| 阶段 | 工作 | 交付与验收 | 状态 |
|---|---|---|---|
| P0 基线与清查 | 冻结 PDF/源文件；清查章节、label、图、参考文献、数据和生成源 | 可回滚基线；迁移表；图源表；证据 backlog | PASS |
| P1 正文职责重排 | 重排第 2、3、5 章；同步摘要、绪论、结论和章节导语 | 方法与结果各有唯一主位置；第 5 章改为分层实验验证；无空节和正文待办 | PASS |
| P2 代表图样板 | 先治理 F03 双脑部署、F09 感知数据流、F11 行为树 | 语义核查完成；统一形状、颜色、字号与连线；drawio CLI 导出并编译 | PASS |
| P3 全图治理 | 按 P0、P1、P2 优先级治理 F01--F13 和其余实际引用图 | 唯一权威源、同名 PDF、正文图题/引用同步、逐图验收 | PASS |
| P4 联合验收 | 全量编译、引用检查、PDF 页面检查、事实一致性审计 | PDF、两份治理文档、逐项 PASS/BLOCKED 结果 | PASS（证据缺口保留于 backlog） |

### 2.1 更新版指引验收表（2026-09-20）

| 更新项 | 状态 | 修改文件 / 行或 label | 证据与检查 | 最小人工确认 |
|---|---|---|---|---|
| 六章结构与第 5 章顺序冻结 | PASS | `auv-chap01.tex`--`auv-chap06.tex`；章节结构未迁移 | 仅做局部叙述与浮动体调整 | 核对目录章/节顺序 |
| 低置信度与紧急上浮语义统一 | PASS | `auv-chap04.tex` 4.3.2；`fig:ch02-emergency-arbitration` | 对照 `bt_engine.py`：低置信回落搜索；漏水/低电/穿底触发紧急分支 | 核对真实部署参数是否改变默认阈值 |
| `>24 dB`、`<15 μVpp`、`1.2 m→三数量级` 纠偏 | PASS | `auv-chap02.tex` 2.2.4、硬件表、2.5.2；backlog E03/E04/E11 | 仓库未定位完整屏蔽/整链纹波/距离基线证据，正文改为设计与定性关系 | 如有外部数据，确认是否补入 backlog 所列元数据 |
| 方法章与结果章去重 | PASS | `auv-chap02.tex` ADC/联合拟合；`auv-chap03.tex` DLIA；`auv-chap04.tex` 求解器 | 详细数值只保留在第 5 章，方法章保留机制与交叉引用 | 抽读第 2--5 章是否仍连贯 |
| 中英文贡献名称统一 | PASS | `auv-abstract.tex`；`auv-chap01.tex` 1.4/1.5；`auv-chap06.tex` 6.1 | 三项贡献采用主动观测与声磁估计、跨层不确定性与控制、退化下分层安全；虚实验证为横向支撑 | 核对答辩口径是否采用同名表述 |
| F01/F05/F06/F08 结构治理 | PASS | `fig:ch01-technical-route`、`fig:ch02-verification-ladder`、`fig:ch02-emergency-arbitration`、`fig:ch03-uncertainty-highway` | Draw.io XML 严格检查、CLI PDF/PNG 导出、独立 PNG 看图检查 | 打开最终 PDF 对应物理页确认字号 |
| F06/F07 分页与 F10/F11 放大 | PASS | `auv-chap02.tex`、`auv-chap04.tex` 对应 figure | F06/F07 位于物理页 62/63；F10/F11 位于物理页 86/88，均已打开页面检查 | 终稿打印前按 100% 比例再抽查一次 |
| Draw.io 查找—生成—导出—校验—预览流程 | PASS | `docs/thesis/figures/architecture/thesis_figure_workflow.py` | `locate/generate/export/check/preview/cycle`；导出与生成分离，允许手工改 `.drawio` 后直接 export | 需要手工改图时，先确认是否应回写统一生成器 |
| 全量构建、引用/字体/图页检查 | PASS | `thuthesis/auv-thesis.pdf` | 189 页 A4；无未定义引用；字体嵌入；修改图页联系表位于 `.auv_data/thesis-final-update/contact-sheet.png` | 终稿提交前抽查目录、图目录及打印字号 |

Ubuntu 无图形会话中直接启动 draw.io 会因缺少 X server 崩溃。现以 `/usr/local/bin/drawio` 包装真实程序 `/opt/drawio/drawio`，无 `DISPLAY` 时自动经 `xvfb-run` 执行；`drawio --version` 返回 24.7.17。所有改动 `.drawio` 均由该 CLI 重新导出为单页矢量 PDF，并由严格出版检查器复核。

## 3. 原组织问题与处理原则

1. 第 5 章当前题为“仿真实验与结果分析”，实际已包含 TMR--SK2301 采集链、45 Hz 电缆--位姿台架、Jetson 求解器、真实 PC104/VxWorks 零执行器安全链和稳态运行证据。章名和分组应改为“分层实验验证与结果分析”，按验证命题组织。
2. 第 3 章的“仿真环境下的状态估计验证”和第 4 章的“鲁棒性分析”含结果性内容，应迁入第 5 章；方法章保留评价设计、指标定义和到实验章的交叉引用。
3. 第 2 章同时承担系统、载荷、观测物理、协议和安全闭环，内容真实但层次拥挤。重排为任务与约束、平台与双脑接口、测量链与磁卫生、观测物理、通信授权与执行接口。
4. 正文多处以“待补、不能证明、剩余验证”组织叙述。影响结论成立的条件保留在实验设置、图题或结果句；项目待办、缺文件和审计过程迁入 `thesis_evidence_backlog.md`。
5. 不把代码存在、原始数据存在、分析完成和有可追溯结果视为同一证据等级；不将数字孪生通过写成真实海缆验收。

## 4. 章节迁移表

| 当前位置 | 目标职责/位置 | 处理 | 关键约束 |
|---|---|---|---|
| 第 1 章研究内容、创新点、组织结构 | 四研究问题与实际证据对应的贡献树 | 改写组织说明，保留已支持贡献 | 不把待分析偶极子、屏蔽或整艇实验写成成果 |
| 第 2 章 2.1 | 任务需求、测量目标和系统约束 | 保留并压缩标准背景 | DL/T 风格评价不等于行业认证 |
| 第 2 章 2.2、2.5 | 平台、双脑部署、通信授权与执行接口 | 重排并去重 | 区分数据流、控制权和安全处置层级 |
| 第 2 章 2.3、2.4 | 测量链、观测物理、主动横切和安装外参 | 重排，保留物理推导唯一主位置 | FWHM 消去幅值尺度，不消去场形模型 |
| 第 3 章 3.2--3.4 | 时空同步、两级估计、ES-EKF、不确定性量化 | 重排并明确载体级/电缆级分工 | 质量分、自适应 R、状态协方差 P、置信度不等价 |
| 第 3 章 3.5 | 第 5 章状态估计与不确定性实验 | 迁移结果，方法章仅保留验证指引 | 保留 DVL 水平不可观等负结果 |
| 第 4 章 4.1--4.4 | 行为树、生命周期、轨迹、UA-MPC、CBF 与恢复授权 | 重排并核对实现语义 | 大范围搜索与局部主动横切分开 |
| 第 4 章 4.5 | 第 5 章决策、控制与近底安全实验 | 迁移结果，保留方法侧评价定义 | UA-MPC 平滑收益不改写为全面精度提升 |
| 第 5 章全部 | 分层实验验证与结果分析 | 按命题重排为共同设置、测量链、估计、决策控制、端到端、计算通信安全、综合讨论 | 仿真、回放、台架、实物子链在标题或设置中明确 |
| 第 6 章 | 与贡献树逐项对应的总结、局限和展望 | 去除重复工程 backlog，保留学术边界 | 不删真实条件和负结果 |

## 5. 方法—实验—证据初始映射

| 研究问题 | 方法主位置 | 验证命题与实验主位置 | 图表/数据 | 当前允许结论 |
|---|---|---|---|---|
| A 有效几何观测 | 第 2 章磁场模型、DLIA、主动横切/FWHM；第 3 章观测接口 | 第 5 章采集链噪声、45 Hz 联合拟合、显式 FWHM 门控审计 | `hardware/mag_chain_noise/`、TMR--ArUco 777 点记录、v2 回归结果 | 可支持信号提取、几何一致性和拒绝路径；不支持真实海缆绝对埋深验收 |
| B 不确定性评价与传播 | 第 3 章 ES-EKF、NIS、自适应 R、分源质量与置信度 | 第 5 章 24 次扰动、NIS 对照、三估计器公平比较 | `experiments/state_estimation/`、`covariance_ab/`、`tri_estimator_fair/` | 可支持一致性调节与退化识别；不把协方差整定写成绝对水平定位恢复 |
| C 决策与安全执行 | 第 4 章行为树、任务状态、UA-MPC、CBF、仲裁与回退 | 第 5 章地形、路径、UA 消融、故障注入和 PC104 同步安全链 | `terrain_following/`、`control_*`、真实 PC104 记录 | 可支持平滑性、条件安全和状态链闭合；不外推为非零执行器整艇水域闭环 |
| D 分层验证 | 第 2 章验证阶梯；第 5 章共同口径 | 数字孪生、回放、台架、计算平台和真实安全子链分别报告 | `results/`、rosbag/MCAP、报告与生成源 | 各结论限定在对应证据层，不合并为“全面通过” |

## 6. 架构与原理图治理清单

| ID | 当前 label / 章节 | 权威源 → 论文导出 | 唯一职责 | 动作 | 状态 |
|---|---|---|---|---|---|
| F01 | `fig:ch01-technical-route` / 第 1 章 | `generate_architecture_diagrams.py` → `architecture/auv_thesis_technical_route.drawio` → `.pdf` | 研究论证路线 | 横向重排四问题主链，工程支撑置底；严格校验并重导出 | PASS |
| F02 | `fig:ch02-autonomy-loop` / 第 2 章 | `architecture/auv_system_autonomy_functional_loop.drawio` → `.pdf` | 系统运行闭环 | 重排主环、监督与证据反馈 | PASS |
| F03 | `fig:ch02-dual-brain-async` / 第 2 章 | `architecture/auv_v2_dual_brain_async_hardware.drawio` → `.pdf` | 部署边界、职责与双向接口 | 增加上位机、传感、执行机构和真实协议方向；正文页检查 | PASS |
| F04 | `fig:ch02-five-layer-architecture` / 第 2 章 | `architecture/auv_v2_five_layer_functional_architecture.drawio` → `.pdf` | 软件组织和约束关系 | 分层重排，保留少量跨层主关系 | PASS |
| F05 | `fig:ch02-verification-ladder` / 第 2 章 | `architecture/auv_system_verification_deployment_ladder.drawio` → `.pdf` | 能力与证据逐级释放 | 改为六个等宽横向阶段；准入门和证据逐列对应 | PASS |
| F06 | `fig:ch02-emergency-arbitration` / 第 2 章 | `architecture/auv_v2_emergency_transition.drawio` → `.pdf` | 触发、处置层级与目标动作 | 改为三栏逐行对应；低置信搜索回落与独立紧急条件分开 | PASS |
| F07 | `fig:ch02-mission-lifecycle` / 第 2 章 | `architecture/auv_v2_mission_lifecycle_flow.drawio` → `.pdf` | 跨角色任务协作 | 以四泳道表达配置、授权、执行、回退和收尾 | PASS |
| F08 | `fig:ch03-uncertainty-highway` / 第 3 章 | `architecture/auv_v2_uncertainty_highway.drawio` → `.pdf` | 不确定性生成与跨层消费 | 精简为质量→\(R_s\)→状态/\(P\)→\(c_s\)→行为/控制 | PASS |
| F09 | `fig:ch03-cable-perception-pipeline` / 第 3 章 | `tools/render_cable_perception_pipeline_figure.py` → `architecture/cable_acoustic_magnetic_perception_pipeline.pdf` | 测量到几何观测及两级估计输出 | 拆为同图 (a) 磁观测链、(b) 两级估计；消除重复模块和真值泄漏暗示 | PASS |
| F10 | `fig:ch04-mission-state-machine` / 第 4 章 | `architecture/auv_v2_mission_state_machine.drawio` → `.pdf` | 任务能力逐级释放与合法回退 | 保留生命周期语义，重导出 | PASS |
| F11 | `fig:ch04-behavior-tree-core` / 第 4 章 | `architecture/auv_v2_behavior_tree_illustration.drawio` → `.pdf` | 安全优先级和任务子树组织 | 按 `bt_engine.py` 重画根优先级、调试级联和主任务子树；正文同步 | PASS |
| F12 | `fig:ch02-fwhm-depth-principle` / 第 2 章 | `tools/independent/plot_fwhm_depth_principle.py` → `magnetics/fwhm_depth_principle.pdf` | FWHM 与垂直距离关系 | 从数值源重生成，不改曲线数据 | PASS |
| F13 | `fig:ch02-active-crossing` / 第 2 章 | `tools/render_cable_active_crossing_figure.py` → `architecture/cable_active_crossing_observability.pdf` | 横切动作与峰值/FWHM 对应 | 从唯一 Python 源重生成，保持两类观测对应 | PASS |

### 6.1 F01--F13 逐图验收记录

下表中的“页面”均指本次最终 PDF 的物理页，只用于证明已打开实际排版页检查，不作为章节归属的固定标识。Draw.io 图的节点/泳道/边标签源字号分别为 24/26/20 px；Python 数值图按生成脚本的实际字号记录。几何检查同时覆盖独立导出和最终页面，不以自动检查代替人工语义检查。

| ID | 定位与章节归属 | 图的职责与语义核查 | 修改方式与可编辑性 | 几何质量与实际字号 | 可追溯性与复现 | 编译、页面与最终状态 |
|---|---|---|---|---|---|---|
| F01 | 旧图 1.2；`fig:ch01-technical-route`；第 1 章研究内容段首次解释；`auv_thesis_technical_route.drawio` → PDF | 只回答论文如何从任务约束走到方法与证据边界；四研究问题、共享置信度和验证出口与正文一致 | 保留权威 Draw.io，重排论证层级；元素和连线均可编辑 | 无碰撞、截字或穿字；24/26/20 px，按 0.95 栏宽可读 | 设计图，语义来自章节贡献树；Draw.io 24.7.17 CLI 重导出 | 引用/字体正确；独立图及最终物理页 31 已检查；**PASS** |
| F02 | 旧图 2.1；`fig:ch02-autonomy-loop`；第 2.1 节；`auv_system_autonomy_functional_loop.drawio` → PDF | 只回答系统运行主环及人工监督、证据记录的关系；实线主环与虚线健康/风险支撑关系一致 | 重排主环与支撑关系；Draw.io 对象可编辑 | 无非预期交叉和遮挡；24/26/20 px，最终宽度可读 | 系统设计图；由统一生成脚本和 CLI 导出 | 编译正确；最终物理页 36 已检查；**PASS** |
| F03 | 旧图 2.2；`fig:ch02-dual-brain-async`；第 2.2.1 节；`auv_v2_dual_brain_async_hardware.drawio` → PDF | 只回答 Jetson、PC104、传感/执行端和上位机的部署职责与双向协议；上/下行和本地保护归属已对照实现 | 重排为双脑边界和中心接口；所有模块/边可编辑 | 无遮挡；24/26/20 px；0.95 栏宽下协议与职责标签可读 | 实施架构图；72 B/145 B 和方向来自协议与代码；统一脚本 + CLI | 编译正确；最终物理页 38 已检查；**PASS** |
| F04 | 旧图 2.3；`fig:ch02-five-layer-architecture`；第 2.2.2 节；`auv_v2_five_layer_functional_architecture.drawio` → PDF | 只回答软件分层、接口传递和底层约束；层级不是时间流程 | 去除伪流程并分层重排；Draw.io 对象可编辑 | 无穿字、遮挡；24/26/20 px，可在正常页宽阅读 | 软件组织图；节点由仓库模块职责核对；生成脚本 + CLI | 编译正确；最终物理页 40 已检查；**PASS** |
| F05 | 旧图 2.4；`fig:ch02-verification-ladder`；第 2.2.3 节；`auv_system_verification_deployment_ladder.drawio` → PDF | 只回答能力、准入门和对应证据如何逐级释放；右端明确为目标，未伪装成全部完成 | 六列等宽横向重画；Draw.io 对象可编辑 | 无碰撞、截字；24/26/20 px；独立浮动页可读 | 验证策略图；完成状态由正文证据边界核对；生成脚本 + CLI | 编译正确；最终物理页 40 已检查；**PASS** |
| F06 | 旧图 2.13；`fig:ch02-emergency-arbitration`；第 2.5.3 节；`auv_v2_emergency_transition.drawio` → PDF | 只回答触发、处置层级和目标动作；低置信度与独立紧急条件分开 | 三栏逐行重画；节点/连线可编辑 | 无非预期交叉、遮挡；24/26/20 px，可读 | 安全架构图；语义对照行为树、仲裁器与 PC104 保护 | 编译正确；最终物理页 62 独立检查；**PASS** |
| F07 | 旧图 2.14；`fig:ch02-mission-lifecycle`；第 2.5.3 节；`auv_v2_mission_lifecycle_flow.drawio` → PDF | 只回答操作员、安全守卫、决策控制和执行反馈之间的任务协作 | 简化为四泳道生命周期；Draw.io 对象可编辑 | 泳道、回退边及标签无碰撞；24/26/20 px，可读 | 系统流程图；角色和授权关系由上位机/仲裁实现核对；生成脚本 + CLI | 编译正确；最终物理页 63 独立检查；**PASS** |
| F08 | 旧图 3.1；`fig:ch03-uncertainty-highway`；第 3.1 节；`auv_v2_uncertainty_highway.drawio` → PDF | 只回答质量分、\(R_s\)、状态/\(P\)、\(c_s\) 与行为/控制消费 | 精简生成—映射—消费链；Draw.io 对象可编辑 | 无遮挡；24/26/20 px，正常页宽可读 | 方法图；变量关系由第 3、4 章公式与接口核对；生成脚本 + CLI | 编译正确；最终物理页 66 已检查；**PASS** |
| F09 | 旧图 3.2；`fig:ch03-cable-perception-pipeline`；第 3.3 节；`render_cable_perception_pipeline_figure.py` → PDF | 只回答磁采集到几何观测，以及载体级/电缆级两级估计的输入输出；真值仅进入离线评价 | 拆成同图 (a)/(b) 两个互补视图；权威源为可维护 Python，不存在位图套壳 | 无重叠、截字；主标签 10–10.5 pt、注释 8–8.2 pt，按 0.95 栏宽可读 | 方法示意，未改写实验数据；脚本直接生成 PDF/PNG | 编译正确；最终物理页 77 已检查；**PASS** |
| F10 | 旧图 4.1；`fig:ch04-mission-state-machine`；第 4.1 节；`auv_v2_mission_state_machine.drawio` → PDF | 只回答能力分级释放、任务完成和合法回退；与行为树 tick 路由明确分工 | 整理前进、恢复和安全回退路径；Draw.io 对象可编辑 | 无标签遮线；24/26/20 px，整栏宽可读 | 生命周期设计图；状态语义与授权流程核对；生成脚本 + CLI | 编译正确；最终物理页 86 已检查；**PASS** |
| F11 | 旧图 4.2；`fig:ch04-behavior-tree-core`；第 4.2 节；`auv_v2_behavior_tree_illustration.drawio` → PDF | 只回答生产行为树根优先级、调试级联和主任务置信度路由；逐节点对照 `bt_engine.py` | 按真实根树和主任务子树重画；Draw.io 对象可编辑 | 容器、节点和边无碰撞/穿字；24/26/20 px，整栏宽可读 | 实现图；紧急、待命、调试、下潜、安全限制、精准巡检/搜索均有代码锚点；生成脚本 + CLI | 编译正确；最终物理页 88 已检查；**PASS** |
| F12 | 旧图 2.8；`fig:ch02-fwhm-depth-principle`；第 2.3.5 节；`plot_fwhm_depth_principle.py` → PDF | 只回答 FWHM 随垂直距离变化、而幅值尺度不改变半峰交点 | 保留数值生成并优化标注；曲线、文字和图例均由 Python 生成 | 两面板无裁切、图例遮挡；脚本字号与坐标刻度在最终 0.96 栏宽可读 | 数值原理图；不改曲线数据；Python 脚本一键复现 | 编译正确；最终物理页 51 已检查；**PASS** |
| F13 | 旧图 2.9；`fig:ch02-active-crossing`；第 2.3.5 节；`render_cable_active_crossing_figure.py` → PDF | 只回答一次主动横切如何同时形成峰值横向中心与 FWHM 垂距观测 | 重绘俯视几何和单次剖面对应；权威源为 Python | 无遮挡、裁切；关键标注 9–9.5 pt、说明 8.6 pt，按 0.88 栏宽可读 | 方法示意；几何关系来自第 2 章推导；Python 脚本一键复现 | 编译正确；最终物理页 52 已检查；**PASS** |

### 6.2 其余正文引用图清查

除 F01--F13 外，正文还引用下列照片、界面截图和数值结果图。它们不属于本轮架构/原理重画范围，均已确认文件存在、引用可解析且性质在图题中可辨；没有将历史资产删除或改写成新的证据。双图/三图组合按一个 figure 记录。

| 章节 | label（组合图合并列出） | 论文资产 | 性质 / 本轮动作 | 状态 |
|---|---|---|---|---|
| 第 1 章 | `fig:ch01-prior-equipment`（含两个子图 label） | `literature/prior_work_equipment/*` | 文献装备照片；保留来源与引用 | PASS |
| 第 2 章 | `fig:ch02-foxglove-cable-console` | `system/foxglove_cable_tracking_console.png` | 部署界面截图；保留 | PASS |
| 第 2 章 | `fig:ch02-single-phase-field`、`fig:ch02-three-phase-helical-field` | `magnetics/single_phase_field_direction.pdf`、`three_phase_helical_field.pdf` | 数值原理图；保留生成结果 | PASS |
| 第 2 章 | `fig:ch02-tmr8637-axis-report`、`fig:ch02-tmr8637-noise-psd` | `hardware/tmr8637_test_report/*` | 随附测试报告扫描；图题明确来源 | PASS |
| 第 2 章 | `fig:ch02-operator-console` | `system/auv_console_operator_interface.png` | 上位机实测界面；保留 | PASS |
| 第 4 章 | `fig:ch04-bt-fsm-complexity`、`fig:ch04-bt-fsm-expansion` | `experiments/decision_bt_vs_fsm/*` | 决策对照结果；保留数据生成图 | PASS |
| 第 4 章 | `fig:ch04-normalized-coverage-tradeoff`、`fig:ch04-mpc-summary` | `experiments/coverage/*`、`experiments/control_mpc/*` | 覆盖率与 PVS 单元结果；图题保留证据口径 | PASS |
| 第 5 章 | `fig:ch05-adc-enob-osr` | `hardware/adc_enob/ch4_enob_vs_osr.pdf`、`ch4_noise_spectral_density.pdf` | ADC 实测双图；保留 | PASS |
| 第 5 章 | `fig:ch05-mag-chain-noise-ros`、`fig:ch05-mag-residual` | `experiments/mag_chain_noise_ros/*`、`experiments/mag_lever_arm_fullflow_*/01_mag_extrinsics_residual.pdf` | 回放对照与仿真标定；图题区分性质 | PASS |
| 第 5 章 | `fig:ch05-joint-trajectory`、`fig:ch05-joint-complex-fit` | `experiments/magnetic_joint/*` | 45 Hz 联合台架结果；保留原数据图 | PASS |
| 第 5 章 | `fig:ch05-eskf-param-sensitivity` | `experiments/state_estimation/eskf_param_sensitivity.pdf` | 单包离线敏感性；图题保留样本边界 | PASS |
| 第 5 章 | `fig:ch05-terrain-tracking`、`fig:ch05-terrain-3d` | `terrain_following/*` | PVS 地形跟随结果；图题区分真值与重建 | PASS |
| 第 5 章 | `fig:ch05-r13-v2-evidence`（三子图） | `experiments/control/r13_v2_*.pdf` | 分源置信控制证据；组合引用有效 | PASS |
| 第 5 章 | `fig:ch05-dlt-scorecard-run1` | `cable_acceptance/cable_dlt1278_scorecard_fresh1.pdf` | 行业标准风格评分，未写成认证 | PASS |
| 第 5 章 | `fig:ch05-pvs-closedloop-recovery`、`fig:ch05-pvs-closedloop-convergence` | `cable_acceptance/pvs_closedloop_*.pdf` | 六自由度数字孪生条件恢复；保留前提 | PASS |
| 第 5 章 | `fig:ch05-pc104-firmware-echo`、`fig:ch05-pc104-layered-fault` | `hardware/pc104_timing/*`、`hardware/pc104_fault_injection/*` | 真实 PC104 零执行器时序/故障结果 | PASS |
| 第 5 章 | `fig:ch05-pc104-cross-layer-fault`、`fig:ch05-pc104-cross-layer-soak` | `hardware/pc104_cross_layer/*` | 真实跨层状态链与 30 min 稳态结果 | PASS |
| 第 5 章 | `fig:ch05-jetson-mpc-realtime` | `real_experiments/jetson_realtime/figures/jetson_mpc_latency_and_success.pdf` | Jetson 求解器微基准；图题保留平台条件 | PASS |

仓库中未被论文引用的历史图不删除，也不因存在而视为已审查。

## 7. 编译与验收记录

| 检查 | 结果 | 证据/备注 |
|---|---|---|
| 真实主入口与构建链 | PASS | `thuthesis/auv-thesis.tex`；`make -C thuthesis auv-thesis` |
| 改动前基线编译 | PASS | 2026-09-20，XeLaTeX/Biber，PDF 已备份 |
| 更新版收口编译 | PASS | 189 页 A4；XeLaTeX + Biber + xdvipdfmx 完整构建；SHA-256 `2ec00332f9d1...` |
| 文字与引用整理后编译 | PASS | 日志无未定义 citation/reference；行为树正文与实现同步 |
| drawio CLI 重导出 | PASS | 10 个 F01--F13 范围内 Draw.io 源均由 24.7.17 CLI 重导出；F09/F12/F13 由 Python 生成；全部单页 PDF |
| 严格图源检查 | PASS | `validate_drawio_architecture.py --strict-publication` 全部通过 |
| 更新图页面检查 | PASS | 本轮修改图物理页为 F01=31、F05=40、F06=62、F07=63、F08=66、F10=86、F11=88；联系表位于 `.auv_data/thesis-final-update/contact-sheet.png` |
