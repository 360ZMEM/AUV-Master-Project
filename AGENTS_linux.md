# AGENTS_linux.md — 毕设写作项目上下文索引（Linux/主体职责）

> 本文件是 `AGENTS.md` 分流后的 Linux 侧主索引。**每次上下文清理/重置后，即使不是第一次进入，也必须完整读完本文件**，以在不重复探索的前提下恢复目标与约束。
> 维护约定：本文件既要「概括」又要「行号对应」（`文件#Lxx-Lyy`），以便精准跳读；发现新关键位置随时补行号。目标体量 ~50KB，高度专业化的子内容分流到子文档并在此登记路径。
> 最后更新：2026-08-06（初次建立，预备操作阶段）

---

## 0. 一句话目标（Prime Directive）

把一台四年前「上位机纯遥控」的老 AUV，升级为满足 **海上风电海底电缆自主巡检** 的战略平台，并据此完成一篇**高度工程化但具备扎实创新点**的清华专硕毕业论文。**本对话（Linux 侧）的核心职责 = 完成论文主体写作与实验佐证**，把毕设推进到 pass 2（见 §5 进度语义）。

关键判据（写作 baseline）：**实验结果服务于写作，不能让指标凌驾于逻辑之上**。既不滥用「首创/第一次」，也不回避真正的创新点。面向清华教授要能拿高分。

---

## 1. 指令 Prompt 与作者背景

### 1.1 主 Prompt 位置
- **主计划书**：[毕业写作完善计划.md](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/毕业写作完善计划.md)
  - 项目定位与分工：`#L1`
  - 老架构代码位置（C# 上位机 / VxWorks）：`#L3`
  - Jetson 主线 + protocol_udp/zenoh + pvs/holoocean 说明：`#L13`
  - 更新版 VxWorks（`csd_vx6.8_lastest`，新增安全机制/可被 Jetson 控制/水池分级部署）：`#L14`
  - 两个 submodule（电缆声磁跟踪算法库 + 硬件 wrapper）说明：`#L15`
  - `docs/thesis/paper` 素材现状与已知问题（只报指标/堆补丁/风格不统一）：`#L17-L29`
  - 附件目录清单：`#L33-L36`
  - **预备操作清单（本阶段任务源）**：`#L40-L56`
  - **协作/写作操作清单**：`#L58-L67`
  - 落盘规范（`01new_` 前缀、未完成/核心中间进度同步分流、图片相对路径）：`#L71-L85`
  - 建议起点：从第五章 + 上下文全面审核与衔接开始：`#L87`
- **无 ROS 辅助侧计划**：[毕业写作无ROS辅助完善计划.md](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/毕业写作无ROS辅助完善计划.md)（macwin 侧职责：检索/文献/浏览器/电脑操纵）
- **顶层分流**：[AGENTS.md](file:///home/auv_user/auv_ws/AUV-Master-Project/AGENTS.md) → `uname` 返回 Linux 读本文件；Darwin 读 `AGENTS_macwin.md`。

### 1.2 作者背景
- 作者：谢冠文 <xgw24@mails.tsinghua.edu.cn>，清华专硕，2026 年 8 月。
- 分工：本人负责 **控制、软件基础、电路、传感器选型、电磁屏蔽**；**声呐及声呐相关加工由丁同学负责**；整个大项目是中航天佑张师兄（工程博士）的课题，本毕设是其中「控制/软件/感知」这条主线。
- 详细心路历程与 Q&A 背景：[AI对话记录——了解背景信息.md](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/AI对话记录——了解背景信息.md)（~773KB，可用 `Q&A` 序号精准定界；线级索引见 §6.4）。

---

## 2. 已形成的原则（Principles）

1. **目标导向 + 上下文回归**：每次上下文重置后必读本文件与 `dashboard.md`；不做无意义的重复扫描。
2. **写作优先于指标**：结果服务论文逻辑；补实验是为了佐证/填逻辑断点，不是堆数字。
3. **创新点表述克制而不回避**：少用「首创」，但清晰立住真正创新（降维反演、UA-MPC、双脑异构、磁卫生布局等）。
4. **改动的奥卡姆剃刀 + 正交性**：欢迎创新性更改，但**严禁未经授权、会使已有实验失效的更改**；改动须最小、与既有实验正交（详见 [rating.md](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/rating.md)）。
5. **写作 / 实验严格隔离**（用对话分支）：
   - 新增实验且**未获批准** → 落盘 [毕业设计写作文档/未完成内容/](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/未完成内容)（或落到代码仓库 `results/` 后软链接至此）。
   - 实验**符合预期、无 WIP** → 落盘 [毕业设计写作文档/核心中间进度同步/](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/核心中间进度同步)。
   - 写作支线读取「特定 scope」实验结果前，先反馈：结果是什么、达成什么目的。
6. **图片一律用 markdown 相对路径引用**；占位符必须对 Ctrl/Cmd+F 友好（唯一、可检索）。
7. **架构图 → drawio（宿主机执行）**：容器内不生成 drawio，改为写「严格自包含的图描述文本」（元素/相对位置/上下文/约束具象化）+ markdown 明确占位符，转交宿主机或另一 AI 复现。
8. **落盘前缀规范**：旧 AI 初稿用 `01_`、`02_`…；新写作用 `01new_`、`02new_`… 前缀，纳入更高 level 推演 + 实物 spec + 「做了什么/为什么/仿真&实物结合」。
9. **不在根目录新建散文件**；专业化内容分流到子目录并在本文件登记路径。
10. **环境噪声**：Shell 命令常伴随 `crashpad/prctl` WARNING，属无害噪声，可忽略/过滤（`| grep -v prctl | grep -v crashpad`）。

---

## 3. 文件阅读方法与契约（多格式）

已确认的稳定读取方式（**本容器内无 pdftotext/poppler/pymupdf/pdfplumber/pypdf/python-docx**；已安装：pandoc、ghostscript、pandas、matplotlib、PIL）：

| 格式 | 方法 | 备注 |
|------|------|------|
| `.md` / `.txt` / 代码 | Read 工具；结构用 `grep -nE "^#{1,3} "` | 首选 |
| `.pdf`（文本层） | `timeout 60 gs -sDEVICE=txtwrite -dFirstPage=A -dLastPage=B -o /tmp/x.txt "<pdf>"` 再 Read `/tmp/x.txt` | **必须加 `timeout` 且限页**，大 PDF 全量会卡住；中文可正常抽取（已验证 DL/T1278、TMR8637 spec） |
| `.pdf`（扫描/图纸） | 无 OCR；按计划 §L85「CAD/PCB 等专有格式选读」处理，必要时截图/交宿主机 | 图纸类多为矢量，txtwrite 可能仅出图框文字 |
| `.docx` | `pandoc -t plain "<file>.docx"` | 已验证（采购清单读取正常） |
| `.png/.svg/.jpg` | Read 工具（多模态直接看图） | 架构图/结果图 |
| `.drawio` | 视为 XML 文本 Read；或看同名 `.png/.svg` | |
| CAD (`.dwg` 等)/PCB/`.docx` 图纸 | 选读，优先看 `图纸PDF版` 里的 PDF | |

> `tools/convert_to_pdf.py`（计划 `#L21` 提及、须在 `docs/` 下运行）**当前路径下未找到该脚本**（`tools/` 下现存的是 `plot_*.py`、`dlt1278_cable_report.py` 等出图/报告脚本）。→ 记入待澄清项（见 §7）。

---

## 4. 目录地图与关键文件（含行号锚点）

### 4.1 论文写作根目录 `毕业设计写作文档/`
- [研究生毕业设计初稿.md](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/研究生毕业设计初稿.md)（2284 行，含大量 AI 口水话；结构见 §6.1）
- [AI对话记录——了解背景信息.md](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/AI对话记录——了解背景信息.md)（背景 Q&A，§6.4）
- 子目录（预备阶段**均为空**，待按 §2.5 规范填充）：
  - `未完成内容/`、`核心中间进度同步/`、`潜在待完成事项/`、`相关插图（架构图）/`、`参考文献/{文献PDF,文献引用信息}/`

### 4.2 论文素材 `docs/thesis/`（旧 AI 初稿 + 图）
- 过程日志 `00_overview.md` … `16_cable_dlt1278_scoring_and_operator_products.md` + `INDEX.md`
- **正文章节 `docs/thesis/paper/`**（写作主战场）：
  - [01_background_and_significance.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/01_background_and_significance.md)
  - [02_system_design.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/02_system_design.md)
  - [03_state_estimation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/03_state_estimation.md)
  - [04new_decision_and_control.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/04new_decision_and_control.md)（canonical；旧 04 仅作历史对照）
  - [05new_experiments_and_discussion.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/05new_experiments_and_discussion.md)（canonical；约 93KB；结构见 §6.2）
  - [06_conclusion_and_outlook.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/06_conclusion_and_outlook.md)
  - [A_appendix_implementation_and_data_index.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/A_appendix_implementation_and_data_index.md)
  - 附属：`INDEX.md`、`e2e_distorted_prior_next_plan.md`、`experiment_gap_and_next_plan.md`、`pvs_extreme_cable_scenarios.md`
- 图目录 `docs/thesis/figures/`：`architecture/`（drawio+png+svg 多份系统图）、`cable_acceptance/`、`console_operator_video/`、`experiments/`、`terrain_following/`
- 其他 docs 入口：[docs/INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/INDEX.md)、[docs/JETSON_DEPLOYMENT_CONTEXT.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/JETSON_DEPLOYMENT_CONTEXT.md)、`docs/prompt.md`、`docs/real_deployment/`、`docs/user-guide/`、`docs/internals/`

### 4.3 附件与参照 `相关附件和参照/`
- `原始AUV类核心文档/`：VxWorks最新协议.md、软件通信协议.md、程序实现.md、设计方案2021.5.28.md、湖上试验大纲.md、`MCU 程序（STM32）/`、`图纸等更细节硬件spec/图纸PDF版/{第一..四册}`
- `原始AUV部分潜在技术细节/`：VxWorks最新协议.pdf、`csd_vx6.8_lastest/`、BMS电池监控、主推电机、北斗gps资料、SMCL舵机、3DM-GX3-25(电子罗盘)协议 pdf、能源变换/MCU 模块等（**高度专业化，选读**）
- `本人新增传感器类/`：**TMR8637技术规格.pdf**（磁传感器，实测 TMR8607 芯片系）、`ADC以太网转换器FK2301/`
- `相关国家标准和行业论文/`：**DL/T 1278—2025 海底电力电缆运行规程.pdf**、T/CSGPC、GB/T 17502-2009、海缆探测技术选型、国际巡检规范、《海底电缆巡检运维管理规范》、`重要国家标准/`
- `考核和阶段性同步文件/`：采购清单 docx（第一批 9562.3 元 / 第二批 5368 元）

### 4.4 代码大本营（软件基地，仅供写作抽象，勿改坏）
- Jetson 主线：`brain_linux/`、`algorithm/`、`common/`、`config/`、`scenarios/`、`scripts/`、`sim_holoocean/`、`tests/`、`tools/`
- 仿真结果 `results/`（写作数据源，规模见 §6.3）
- 老架构：`console_soft/csharp`（C# 上位机）、`csd_vx6.8_lastest_bak`（旧 VxWorks）、`csd_vx6.8_lastest`（新 VxWorks，安全机制/分级部署）
- Submodules（`.gitmodules`）：
  - `AUV-Master-Mag` → 电缆声磁跟踪算法库（github 360ZMEM/AUV-Master-Mag）
  - `hardware_wrappers/fangkong_adc` → FK2301 ADC + 江苏多维 TMR8637 wrapper（github 360ZMEM/fangkong_adc）

### 4.5 本索引维护的产出文件（预备操作交付物）
- 本文件 `AGENTS_linux.md`
- [dashboard.md](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/dashboard.md)（进度看板，§5）— 待建
- [plan.md](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/plan.md)（实物部署功能缺口）— 待建
- [rating.md](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/rating.md)（负结果/风险/第一性更改登记）— 待建

---

## 5. dashboard.md 进度语义（速查）

以 **三级标题（无三级则退化到二级标题）** 为行目标，列：`章节 | pass | 缺失项 | 依赖前序任务 | 备注`。
- **pass 1** — 实验/写作信息仍需显著完善。
- **pass 2** — 大体完善，仅需润色/口径/参考文献。**← 本对话主目标止于 pass 2。**
- **pass 3** — 主体完成，主查前后一致性。
- 缺失项分类：1 图片 / 2 文字 / 3 实验 / 4 其他信息 / 5 参考文献。

---

## 6. 结构索引（行号锚点）

### 6.1 研究生毕业设计初稿.md（2284 行）
- 目录（暂定）`#L5`；参考文献 `#L239`；References `#L342`
- 第一章 绪论与文献综述 `#L109`（1.1 背景 `#L111` / 1.2 探测现状 `#L149` / 1.3 控制决策现状 `#L181` / 1.4 创新点 `#L203` / 1.5 组织 `#L215`）
- 夹杂大量 Q&A 段（Q109/A111 …）与「第二导师」写作点评，属背景对话残留
- 第二章 系统架构与多源感知建模（多份重复标题）`#L764 / #L1086 / #L1341 / #L1588`；全景回顾 `#L1734`
  - 2.1 需求/标准对齐 `#L766`；2.2 双脑硬件架构 `#L1088`；2.3 海缆磁场建模与降维反演 `#L1343`（核心解套 2.3.4 `#L1394`）；2.4 载荷标定/杆臂 `#L1590`；2.5 小结 `#L1661`
- 第三章 声磁协同融合状态估计 `#L1808`（3.1 引言 `#L1810`）
- **注意**：初稿中「第四章/第五章」目前多以「〔示例〕〔待回填〕」提纲形式出现（`#L227` 四章、`#L229` 五章），正文实体主要在 `docs/thesis/paper/04、05`。

### 6.2 docs/thesis/paper/05new_experiments_and_discussion.md（canonical，约 93KB）
- 5.1 平台与指标 `#L3`（5.1.1 虚实架构 `#L5` / 5.1.2 指标定义 `#L18`）
- 5.2 数字孪生场景 `#L26`（复杂海缆场景 `#L28` / 综合压力 `#L46` / 噪声注入 `#L50`）
- 5.3 硬件集成与标定 `#L54`（链路压力 `#L58` / 磁杆臂标定 `#L62` / 故障自救 `#L85`）
- 5.4 近底巡检与反演精度 `#L89`（大电流台 `#L93` / 实测磁场反演 `#L97`）
- 5.5 结果讨论与仿真到实物边界 `#L99`：已完成总表 `#L103` / Terrain 主结果 `#L130` / PID 地形消融 `#L170` / MPC 极端路径 `#L186` / ES-EKF 鲁棒性 `#L221` / UA-MPC 定位消融 `#L253` / 控制指标 `#L270` / UA-MPC 归因 `#L293` / 迁移性 `#L299` / DL/T 1278 验收 `#L307` / 端到端证据分层 `#L397`
- 5.6 缺失实验与讨论 `#L494`
- 5.7 极端场景 `#L506`（S-curve `#L510` / Hairpin `#L521` / Slope `#L532` / Buried Gap `#L543` / Cross Current `#L554` / Combined `#L565` / 代理环境 smoke `#L579`）
- 5.8 本章小结 `#L613`

### 6.3 results/（写作数据源，文件数）
`cable_ops_report/`(531) `control/`(526) `control_aggregates/`(342) `uncertainty_aggregates/`(99) `visual_feedback/`(55) `localization/`(35) `thesis_sweep_aggregates/`(27) `es_ekf_extrinsics/`(29) `mag_extrinsics/`(16) `tuning/`(14) `decision/`(7) `cable_tracking/`(1) `archive/`(155)

### 6.4 AI对话记录——了解背景信息.md（11792 行；Q1–Q129 / A1–A131）
> 文件过大，**禁止全量 Read/grep（会卡死）**。已用切分脚本 [split_ai_conv.py](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/工具/split_ai_conv.py) 按 Q/A 标记切成 17 个 ~45KB 块（输出到 `/tmp/ai_conv_chunks/`，含 `_INDEX_markers.txt` 全量行号索引 + `_MANIFEST.txt`）。需精读时按下表行号只读目标区间，或 `python3 毕业设计写作文档/工具/split_ai_conv.py` 重新生成分块。
> 定位法：所有 Q/A 都是 `## Qn` / `## Am`（注意 Q 与 A 编号有 +2 错位，如 Q129↔A131）。

Q/A 行号锚点（部分）：Q1`#L3` Q10`#L908` Q20`#L1829` Q30`#L2826` Q40`#L4019` Q50`#L4983` Q60`#L5720` Q70`#L6840` Q80`#L7589` Q90`#L8483` Q100`#L9331` Q110`#L10278` Q120`#L11047` Q129`#L11707`。

**主题图谱（写作最相关，按主题给行锚）：**
- **分工边界**（张师兄工程博士出资/陈老师总师人设/丁同学声呐）：A1 `#L20-L90`、A40 `#L4082`、A51 `#L5244`。
- **三层架构（上位机/Jetson/AMD）为何优于两层**：A4 `#L369-L397`、A73(双脑异步) `#L7157`、创新点一 `#L10193`。
- **三相电缆螺旋绞合磁场为何可测 + 声磁接力**：A14 `#L1251-L1298`、A124(1.87nT 含金量/三级演进) `#L11186-L11251`、A127(砂石掩埋不影响磁导率/埋深反演) `#L11427-L11468`。
- **磁标定（硬/软铁、椭球拟合、非正交性、杆臂）**：A66 `#L6588`、A93(杆臂改正 SOP) `#L8651-L8705`、A102(非正交) `#L9416`、A103(硬软铁椭球拟合) `#L9515-L9565`。
- **缩比模型合理性 / 坡莫合金·钢丝铠装屏蔽 / 剥洋葱实验**：A117(4mm vs 10cm 极限缩比恶劣工况) `#L10654`、A118(SWA 钢丝铠装采购) `#L10730`、A126(海缆解剖规程) `#L11349-L11389`。
- **宿舍/低成本磁实验台（双通道声卡生偶极子/三相、10A 电流台）**：A65(几何布局+真值标定) `#L6496`、A115(避开 50Hz) `#L10487`、A121/A122/A123(声卡三相) `#L10966 / #L11057 / #L11113`、A52(电缆选型 3 芯) `#L5325`。
- **Jetson 双脑（NVPModel 25W/散热/JTOP、UDP 桥接、接口）**：A28 `#L2637-L2721`、A27(AMD↔Jetson 连接) `#L2523-L2615`、A34(UDP 收发代码) `#L3236`、A105(六层软件全景) `#L9701-L9747`。
- **行为树 + 之字形搜索 + 不确定性触发**：A62(行为树草案/T-CSGPC 3.4 之字形) `#L6211-L6254`、A96(决策vs控制边界/模式切换门槛) `#L8938-L8975`。
- **安全自救（漏水/失联心跳/低电/失控 + VxWorks 兜底）**：A64 `#L6391-L6456`。
- **行业标准解构（DL/T1278、T/CSGPC、GB/T 17502/12327、IEEE 1120）**：A55 `#L5596`、A56(磁力仪硬指标/埋深精度) `#L5668-L5699`、A57(作业规程/评价) `#L5732-L5782`、A58(GB 国标) `#L5805`。
- **磁探测选型/隔离电源/ADC（Fluxgate、HSF-500、±15V 隔离、ADS1256、ENOB）**：A59 `#L5879`、A82(0.05nT 噪声矛盾) `#L7810`、A83(隔离电源三级) `#L7891-L7933`、A84(BOM) `#L7962`、A104(ENOB/空间走样/铠装涡流相移) `#L9596-L9668`。
- **论文骨架与写作方法论（6 章黄金结构 / 创新点包装 / 防流水账铁律）**：A90(6 章结构) `#L8431-L8472`、A91–A100(逐章目录+检索词) `#L8497 起`、A110(创新点三条+架构图工具链) `#L10124-L10205`、A128(四大升维突破口:主动感知/物理信息融合/模态拒止容错/Sim-to-Real 随机映射) `#L11503-L11533`、A131(2.2 节写作骨架+翻译矩阵) `#L11723-L11786`。

**durable 约束/第一性决策（写作/实验红线，与 rating.md 呼应）：**
- 三大边界（初稿 `研究生毕业设计初稿.md` `#L461/#L478/#L503`，源于此对话）：①声呐"拿来主义"剥离给丁同学；②软件安家于 Jetson+Mock AMD；③三相电缆+磁屏蔽"偷天换日"（核心突破）。
- 严禁"跨层污染"三层洋葱架构：A61 `#L6059-L6096`。
- 创新点须克制表述、指标合规优先于"能测到"：A73 `#L7147-L7157`、A106(平台化思维 vs 产品) `#L9792`。

---

## 7. 已完成 / 待改进实验 与 待澄清项

### 7.1 已有实验（来自 05 章）
Terrain Following（PID/MPC 地形跟随）、ES-EKF 多场景多种子鲁棒性、UA-MPC 定位/控制消融、DL/T1278 数字孪生验收、端到端 distorted-prior 边界、PVS 六自由度闭环恢复、磁杆臂/安装角标定、双脑链路实时性压测、故障注入自救。

### 7.2 计划书点名的薄弱点（→ 写作重点）
- 只报指标、缺原理与因果诊断；堆补丁导致前后矛盾/信息冗余；图风格不统一（第四、五章 matplotlib 图需全面审核 + 风格统一 + 关键消融补充，覆盖潜在未覆盖点/负结果/逻辑断点）。计划 `#L60-L67`。

### 7.3 待澄清项（TODO_CLARIFY，Ctrl+F 友好）
1. `tools/convert_to_pdf.py` 计划提及但当前仓库未见 → 是否已移动/重命名？（现用 gs+timeout 方案替代，见 §3）
2. HoloOcean 后端「不完全可用」，当前以 PVS 为准（计划 `#L13`）；写作中涉及 HoloOcean 的实验需标注可复现边界。
3. 初稿第四/五章为提纲，实体在 `docs/thesis/paper/04、05` → `01new_`…`05new_` 迁移策略需在 roadmap 落定。

---

## 8. 下一步（roadmap 摘要）

详见 `plan.md` / `rating.md` / `dashboard.md`。总路径：**从第五章 + 上下文的全面审核与衔接切入** → 建 dashboard 全量行级进度 → 逐章 `0Xnew_` 重写（High-level 推演 + 实物 spec + 仿真/实物结合）→ 图统一 + 关键消融补充 → 架构图文本化交宿主机。

### 8.1 完整 Roadmap（分阶段）
- **P0 预备（已完成）**：文件/目录存在性核对；PDF/docx 阅读契约（§3）；`AGENTS_linux.md` / `dashboard.md` / `plan.md` / `rating.md` 建立；AI 背景对话行级索引（§6.4）。
- **P1 第五章审核与衔接（当前起点，计划书 `#L87`）**：
  1. 精读 canonical `05new_experiments_and_discussion.md`，逐 5.x 小节比对 `dashboard.md` pass 值与缺失项，落实到行。
  2. 梳理「指标→原理→因果」链，识别逻辑断点/前后矛盾/信息冗余（计划书 `#L26-L27`）。
  3. 清点第 4/5 章所有 matplotlib 图 → 建立「图清单 + 风格差异表」（尺寸/字号/配色/坐标），为统一做准备。
  4. 把 §5.6 缺口 + §7 责任边界回填进 `rating.md` A/B 表（已初步完成，精读后补细）。
- **P2 逐章 `0Xnew_` 重写**：01→05 顺序，每章融入 High-level 推演 + 实物 spec（附件 §4.3）+「做了什么/为什么/仿真&实物结合」；创新点表述走 §2.3 baseline。
- **P3 图统一 + 关键消融补充**：matplotlib 风格契约落地；补 dashboard 标 pass1 且缺「实验(3)」的行（新增实验走写作/实验隔离，落 `未完成内容/`→批准后 `核心中间进度同步/`）。
- **P4 架构图文本化**：按 §2.7 写自包含图描述 + Ctrl+F 友好占位符，交宿主机 drawio。
- **P5 参考文献 + 一致性（pass3 收尾，超出本对话主目标）**。

### 8.2 立即下一步（本对话续作建议）
正文读取与后续迁移统一从 `docs/thesis/paper/04new_decision_and_control.md`、`05new_experiments_and_discussion.md` 开始；无 `new` 后缀的 04/05 只用于历史差异追溯，不再作为事实源。

### 8.3 预备操作交付物核对（P0 DoD）
| 交付物 | 计划书条目 | 状态 |
|---|---|---|
| 文件夹/文件存在性确认 | `#L42` | ✅ |
| 多格式阅读契约 | `#L43` | ✅（§3；`convert_to_pdf.py` 缺失已记 §7.3） |
| `AGENTS_linux.md`（行号对应，~50KB） | `#L44-L47` | ✅ |
| `dashboard.md`（三级标题行/pass/缺失/依赖/备注） | `#L49-L54` | ✅ |
| `plan.md`（部署功能缺口） | `#L55` | ✅ |
| `rating.md`（负结果/第一性更改） | `#L56` | ✅ |
| 计划与 roadmap | `#L87` | ✅（本节 §8.1） |
