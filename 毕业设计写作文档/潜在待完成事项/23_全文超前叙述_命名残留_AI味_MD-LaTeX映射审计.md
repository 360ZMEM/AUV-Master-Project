# 23 全文超前叙述 / 命名残留 / AI 味 / MD-LaTeX 映射协调审计

> 审计时间：2026-08-13
> 审计范围：`thuthesis/data/auv-chap01.tex`–`auv-chap06.tex`（LaTeX 正文事实源），
> `docs/thesis/paper/02_system_design.md`、`03_state_estimation.md`、`04new_decision_and_control.md`、
> `05new_experiments_and_discussion.md`（Markdown canonical 源）。
> 执行约束：Mac 端，**不新增实验**；如需实验仅给建议、不落地。本文档实时更新，作为四类问题的上下文证据留存。
> 处置基线：与 21 号文档一脉相承——先修事实/占位/口径与超前引用，再做命名规范化，最后做 AI 味削弱与篇幅凝练；改前备份、改后静态检索 + 构建 + 编号复核。

---

## 0. 结论速览（问题分级）

| 编号 | 问题类别 | 严重度 | 命中数量（LaTeX） | 处置建议 |
|---|---|---|---|---|
| P1 | 超前叙述 / 前向引用（前章引用后章） | 高 | 见 §1，约 15 处正文 + 1 处错标 label | 逐条改写为"本章方法结论 + 边界"，删除具体后章节号；错标 label 必须修 |
| P2 | chap3/chap4 实验段是 chap5 占位、chap5 杂糅 | 中 | chap3 §3.5、chap4 §4.5 整节转述 chap5 | 保留方法侧结论、剥离结果转述；给"可提前实验"建议（不落地） |
| P3 | 变量名 / 文件名 / verb / 原始 variable 残留 | 高 | `\verb`=0；`\texttt` 数学符号 chap03≈30、代码/文件名 chap02≈15、chap05≈10；`\path` 文件名 chap03=3 | 数学符号一律转数学环境；文件名/变量名/API 名从正文删除或改叙述化 |
| P4 | AI 味（套话、排比、过度总结） | 中 | chap05 filler ≈5，全书连接词偏多 | 按需精简，不逐句改；优先删"至此/综上/一脉相承/这一…意味着"类空转 |
| P5 | MD 与 LaTeX 映射不一致（LaTeX 超前） | 中 | chap02/03/04 均有 LaTeX 独有前向引用与符号；符号跨度 md03=48 / tex03=45 | 明确"LaTeX 为事实源"；将本轮 LaTeX 修订同步回 canonical md，避免二次漂移 |

---

## 1. P1 超前叙述 / 前向引用

判定口径：正文 label 前缀内嵌章号（`sec:chNN-…`、`fig:chNN-…`、`tab:chNN-…`、`eq:chNN-…`），
凡"第 N 章引用第 M 章（M>N）"或 `\ref` 指向更高章号者，均记为前向引用。用户示例"实测 ENOB 曲线见第 5.3.2 节"即属此类。

### 1.1 chap02 → 后章（第 3、5 章）

| 位置 | 原文片段 | 指向 | 处置建议 |
|---|---|---|---|
| [auv-chap02.tex:275](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap02.tex#L275) | "对应的滤波实现与雅可比矩阵推导见第 3.3.3 节" | →3.3.3 | 可保留（承上启下的必要指路），但建议弱化为"在第 3 章状态估计中给出"，不锁定小节号 |
| [auv-chap02.tex:362-368](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap02.tex#L362-L368) | `\ref{fig:ch03-active-crossing}` 且图 **定义在 chap02** 却用 `fig:ch03` 前缀 | label 错标 | **必须修**：该图物理在第 2 章，应改为 `fig:ch02-active-crossing`，并同步 chap03:249 的引用 |
| [auv-chap02.tex:370](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap02.tex#L370) | "…不把它扩展解释为…绝对埋深标定；**对应实测结果见第 5.4 节**。" | →5.4 | 删除"见第 5.4 节"，改为"其系统级验证属实验章内容"或直接删句尾指向 |
| [auv-chap02.tex:496](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap02.tex#L496) | "…与第 3.2.2 节、**第 5.3.2 节**保持口径一致" | →3.2.2 / 5.3.2 | 口径一致声明可保留语义，但删除后章小节号，改"与后续标定/采集章节口径一致" |
| [auv-chap02.tex:569](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap02.tex#L569) | "这一硬件级同步是第 3.2.1 节多源异步时间戳对齐算法的物理基础" | →3.2.1 | 弱化为"…是第 3 章多源时间戳对齐的物理基础" |
| [auv-chap02.tex:631](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap02.tex#L631) | "…完整的不确定度预算。**实测 ENOB 曲线见第 5.3.2 节**。" | →5.3.2 | **用户点名的典型**：删除该句或改"实测 ENOB 表征见实验章"，不写 5.3.2 |
| [auv-chap02.tex:647](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap02.tex#L647) | "以第 3.2.3 节采用的四阶 Butterworth 低通…为例" | →3.2.3 | 此处是"预告未来章参数"，建议改为在本章自述该滤波器设定，或弱化章号 |

> 说明：chap02 内部对 2.3.2/2.3.3/2.3.4/2.3.5 的引用为**同章后节**引用（如 275、307、343、349 行），属正常"先总后分"，不计入前向违规，但需确认"先定义后引用"（见 §2.4）。

### 1.2 chap03 → 后章（第 4、5 章）

| 位置 | 原文片段 | 指向 | 处置建议 |
|---|---|---|---|
| [auv-chap03.tex:175](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L175) | "…第 5.6 节讨论" | →5.6 | 弱化章号或改"见实验章边界总表" |
| [auv-chap03.tex:246-247](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L246-L247) | "第 5.4 节的 45 Hz 电缆--TMR--ArUco 联合实验…验证了…" | →5.4 | 删后章小节号，改"该几何映射的实验验证在第 5 章给出" |
| [auv-chap03.tex:269](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L269) | "专用算法仓库对纯磁段做定半径弧扫描（详见第 5.5.11 节）" | →5.5.11 | 弱化为"（详见实验章端到端探测证据）" |
| [auv-chap03.tex:298-299](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L298-L299) | "第 5.5.5 节进一步用固定 R…作同输入对照" | →5.5.5 | 删小节号，"由实验章多场景对照给出" |
| [auv-chap03.tex:323-325](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L323-L325) | 整段转述"第 5 章 P1 sensor 3 seed sweep…结果在第 5.5.5 节…" | →5.5.5 | 见 §2，属结果转述占位，建议整体收敛 |
| [auv-chap03.tex:333](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L333) | "…统一见第 5.6 节" | →5.6 | 弱化章号 |
| [auv-chap03.tex:339](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L339) | "其集中适用范围与后续验证见第 5.6 节" | →5.6 | 弱化章号 |

### 1.3 chap04 → 第 5 章

| 位置 | 原文片段 | 指向 | 处置建议 |
|---|---|---|---|
| [auv-chap04.tex:386](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap04.tex#L386) | "第 5.5.8 节从可解性和横向精度两个相互独立的指标验证了…" | →5.5.8 | 弱化为"由实验章消融验证"，删小节号 |
| [auv-chap04.tex:502-503](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap04.tex#L502-L503) | `\ref{sec:ch05-5-7-7}` "…给出的 low/mid/high 60 s 三种子复核矩阵…" | →5.7.7 | 结果转述，见 §2；建议保留一句方法侧定位，结果指向弱化 |
| [auv-chap04.tex:522-523](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap04.tex#L522-L523) | "…统一收束于第 5.5.4 节、第 5.7.7 节结果表与第 5.6 节边界总表" | →5.5.4/5.7.7/5.6 | 可保留"结果集中在实验章"语义，删三处小节号堆叠 |
| [auv-chap04.tex:535-536](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap04.tex#L535-L536) | "…统一收纳于第 5.5.4 节，见表~\ref{tab:ch05-mpc-extreme-paths}及图~\ref{fig:ch05-mpc-long-s}" | →5.5.4 + 跨章图表 | **跨章 `\ref` 图/表前向引用**：chap04 直接引 chap05 的表/图。建议本章不引具体结果图表，只留"结果见实验章" |
| [auv-chap04.tex:542](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap04.tex#L542) | "…集中由第 5.6 节边界总表给出" | →5.6 | 弱化章号 |

### 1.4 处置原则（P1 统一）

1. **允许的向前指路**：承上启下、指引"后续章节将展开"可以保留，但**尽量不锁定具体小节号**（`第 5.5.8 节`→`实验章`），减少改章号时的连锁失效。
2. **必须删除的**：把"后章的实测结果/数值/图表"提前搬到前章叙述或直接以 `\ref` 引后章图表（如 chap04:536）。前章只讲"方法与预期边界"，结果留给第 5 章。
3. **错标 label**：`fig:ch03-active-crossing` 定义在 chap02，前缀与物理章不符——必须改为 `fig:ch02-active-crossing`，否则语义误导且违反 label 章号约定。

---

## 2. P2 chap3/chap4 实验占位 & chap5 杂糅

### 2.1 现象：chap3 §3.5、chap4 §4.5 大量转述 chap5 结果

- **chap03 §3.5「仿真环境下的状态估计验证」**（[auv-chap03.tex:313-333](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L313-L333)）：
  §3.5.1、§3.5.2 通篇是"第 5 章 P1 sweep 结果…结果在第 5.5.5 节给出…XY RMSE 2.76–3.55 m…"这类**结果转述**，本章并不承载独立实验，实质是第 5 章占位。
- **chap04 §4.5「决策与控制系统的鲁棒性分析」**（[auv-chap04.tex:505-536](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap04.tex#L505-L536)）：
  §4.5.1/§4.5.2 把 R13-v2、CBF、R22、综合极端 baseline 的 36/36、96/96、2.70–2.90 m 等**第 5 章数值结论**大段前置，末尾再"统一收束于第 5.5.4/5.7.7/5.6 节"。

### 2.2 处置建议（不新增实验）

- **方法/理论侧保留、结果侧剥离**：chap3 §3.5、chap4 §4.5 只保留"该机制要验证什么、成立条件、预期边界"，删除具体运行数（run 数、RMSE、p95、净空数值），把这些统一交回第 5 章。前章一句"其实验证据集中在第 5 章"即可。
- **叙述连贯性**：这样处理后，第 2→3→4 章形成"需求/架构→估计方法→控制方法"的方法主线，第 5 章独占"结果/证据"，避免读者在第 3、4 章就被第 5 章数值淹没。
- **chap5 是否杂糅**：初查 §5.1–§5.8 结构清晰（架构/场景/硬件/实验室/讨论/边界/极端/小结），**未见严重杂糅**；但需专项复核两点（见 §2.3）：
  1. §5.5.9「仿真到实物迁移性讨论」与 §5.6「证据边界」、§6 展望是否内容重叠；
  2. §5.5 系列小节与 §5.7「极端电缆巡检场景设计」是否有结果重复摆放。

### 2.3 可提前实验的"建议"（仅建议，Mac 端不落地）

> 这些是"如果要让前章不依赖后章结果"的备选，均为**建议**，本轮按"不增加实验"处理。

- 建议 A：将 §5.5.5 的 ES-EKF DVL dropout / 磁畸变最小对照（现成 24-run 数据）在**第 3 章内**放一张"方法验证小表"（仅 1 张、标 n），使 §3.5 自洽，不再纯指向第 5 章。**（数据已存在，属"图表重组"而非新实验）**
- 建议 B：将 §5.7.7 的 CBF 60 s 净空最小结论，在**第 4 章 §4.4.7 CBF 小节**放一句量化锚点（最小净空区间），使控制方法章有最小自证。**（同样是复用现有结果）**
- 若坚持"前章零结果"，则 A/B 不做，仅按 §2.2 剥离——这是**默认路径**。

---

## 3. P3 变量名 / 文件名 / verb / 原始 variable 残留

`\verb` 全书 **0** 处（已受控）。问题集中在 `\texttt{}` 与 `\path{}`，分两类：

### 3.1 类型一：数学符号误用 `\texttt{}`（应转数学环境）—— 违反公式规范

**chap03 §3.3–§3.4 最严重**，把状态/协方差/观测符号用 `\texttt{}` 表达，而同节紧接着又有规范的 `\(\boldsymbol{x}\)` 数学定义，造成"同一符号两种字体"：

| 位置 | 残留符号（`\texttt`） | 建议 |
|---|---|---|
| [auv-chap03.tex:182-187](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L182-L187) | `p` `q` `v` `b_a` `b_g` `x_nom` `δx` `F` `Q` `H` `R` | 全改为 `\(\boldsymbol{p}\)`、`\(\boldsymbol{q}\)`…与 190/194/200 行公式统一 |
| [auv-chap03.tex:216-229](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L216-L229) | `d_lat` `θ_rel` `z_sonar=[...]` `H_sonar` `R_sonar` `B=[B_x,...]` `d_depth` `θ_cable` `||B_obs-...||²` | 全转数学：`\(d_{\mathrm{lat}}\)`、`\(\theta_{\mathrm{rel}}\)`、`\(\boldsymbol{R}_{\mathrm{sonar}}\)` 等 |
| [auv-chap03.tex:261-267](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L261-L267) | `d_lat` `R_sonar` `R_mag` `R` | 同上转数学 |
| [auv-chap03.tex:280-285](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L280-L285) | `y=z-H·x_pred` `S=H·P·H^T+R` `y^T·S^(-1)·y` `R_nominal` `α` | 与 288/290 行公式重复，删 `\texttt` 版、留公式 |
| [auv-chap03.tex:282](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L282) | `R_online = α · R_nominal` | 转 `\(R_{\mathrm{online}}=\alpha R_{\mathrm{nominal}}\)` |
| [auv-chap03.tex:304-305](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L304-L305) | `c ≈ 1.0` `c ≈ 0.5` `c → 0` | 转 `\(c\approx1.0\)` 等 |
| [auv-chap02.tex:268](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap02.tex#L268) `r` / [381-383](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap02.tex#L381-L383) `h` `r_s` `r_g` / [426](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap02.tex#L426) `B_...` `M` `b` | 物理量符号 | 转数学环境 |
| [auv-chap02.tex:237](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap02.tex#L237) | `stepInput` `depth...` | 若为信号/量名转数学或叙述化；若为 API 名见 §3.2 |

### 3.2 类型二：文件名 / 变量名 / API 名 / 目录名 / 代码标识（应从正文删除或叙述化）—— 违反"命名不入正文"

| 位置 | 残留标识 | 类型 | 建议 |
|---|---|---|---|
| [auv-chap02.tex:58](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap02.tex#L58) | `combined_stress` | 场景配置名 | 改"联合应力工况"叙述，删标识 |
| [auv-chap02.tex:172-176](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap02.tex#L172-L176) | `apps/` `interfaces/` `behavior/` `algorithm/` `common/` | 源码目录名 | 表格保留"层名"语义，删目录路径列或改中文层名 |
| [auv-chap02.tex:179](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap02.tex#L179) | `AUVStateData` `AUVCommand` | 数据结构/类名 | 改"统一状态数据结构与指令数据结构"，删类名 |
| [auv-chap02.tex:653](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap02.tex#L653) | `perception_engine.py` `scenario_mag_distortion_*.yaml` | 文件名 | 改"感知引擎模块""磁畸变场景配置"，删文件名 |
| [auv-chap02.tex:691](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap02.tex#L691) | `Work_Cmd=0x02...` `common.protocol` | 帧字段/模块名 | 协议帧字段可作附录，正文改叙述；模块名删 |
| [auv-chap03.tex:40-42](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L40-L42) | `TransportDelayQueue` `SensorSampleCache` | 类名 | 改"传输延迟队列""传感器采样缓存"，删类名 |
| [auv-chap03.tex:249,253-254](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L249-L254) | `CableTrackingOutput` | 输出结构名 | 改"部署侧电缆跟踪输出"，删类名 |
| [auv-chap03.tex:304-305](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L304-L305) | `cov_to_conf` | 函数名 | 改"协方差到置信度映射函数"，删函数名（chap01:200 同名亦需处理） |
| [auv-chap01.tex:200](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap01.tex#L200) | `cov_to_conf` | 函数名 | 同上 |
| [auv-chap03.tex:319,321,329](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L319-L329) | `\path{scenario_dvl_dropout_{...}.yaml}` `\path{docs/experiment/benchmark_test_log.md}` `\path{scenario_mag_distortion_{...}.yaml}` | 文件/路径名 | **正文严禁**：改"DVL 丢包四档场景配置""基准测试日志"，删 `\path` 与相对路径 |
| [auv-chap05.tex:1223-1225,1542-1548,1554](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L1542-L1548) | `exit_at_end` `depthHeadingAutopilot` `Solve_Succeeded` `pvs.control_mode` `pvs.autonomy_motion_model` `native` `protocol_udp` `PVSSimWrapper.set_reference()` | 参数/接口/方法名 | 属执行链细节，正文改叙述（如"深度-航向自动驾驶接口""求解成功标志"），代码级标识移附录 |

> chap04 `\texttt`=0（已干净）；chap06 仅 `exit_at_end` 1 处（[auv-chap06.tex:25](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap06.tex#L25)）需叙述化。

### 3.3 例外（可保留）

- 硬件协议帧头 `$CKTH` / `$AUV`、寄存器地址 `0x01`、IP 段 `192.9.0.X`、引脚 `Trig1`、电平 `+Vdc/0Vdc`：属**硬件接口事实**，作为工程标注可保留（但 IP 具体末段 `.50/.100` 等建议核对是否需要脱敏，见 21 号"工程标识"约定）。

---

## 4. P4 AI 味削弱（主要 chap5，其余略有）

### 4.1 命中（chap05 filler，逐条）

| 位置 | 片段 | 建议 |
|---|---|---|
| [auv-chap05.tex:307](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L307) | "**至此**，前面四节已经交代了…这一组织思路与第 4 章…**一脉相承**" | 删"至此""一脉相承"，直接陈述本节任务 |
| [auv-chap05.tex:606](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L606) | "**值得注意的是**…" | 删"值得注意的是"，保留事实句 |
| [auv-chap05.tex:945](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L945) | "**综上**…" | 若为小节收尾可留一处，重复则删 |
| [auv-chap05.tex:1544](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L1544) | 本章小结段"**综上**…" | 小结处可保留 1 处"综合来看"，避免连用 |

### 4.2 全书连接词分布（供批量精简参考）

`值得注意的是/综上所述/换言之/具体而言/需要说明的是/这一…意味着/一方面…另一方面` 等：
chap01=2、chap02=5、chap03=4、chap04=3、chap05=2、chap06=1（`grep` 统计口径）。

### 4.3 处置原则

- **不逐句改写**，只做三类删除：① 空转连接词（至此/综上/一脉相承/值得注意的是）；② 自问自答式设问开头（"为什么…？答案是…"在 chap02:691、chap03 多处，学术化改为陈述）；③ 排比式"一方面…另一方面…"若无实义则合并。
- chap05 因正文已很长，**优先在小结、讨论段做凝练**（§5.5.9、§5.8），结果表段落保持简洁事实叙述即可。
- 保留用户偏好：减少破折号、精炼标点。

---

## 5. P5 Markdown ↔ LaTeX 映射协调（LaTeX 超前）

### 5.1 结论：LaTeX 是当前事实源且已超前于 canonical md

INDEX.md 已定：LaTeX 迁移只读 `04new`/`05new`。核对发现 **LaTeX 比 md 多出内容**，二者已漂移：

| 差异 | LaTeX | Markdown | 说明 |
|---|---|---|---|
| ENOB 前向引用 | chap02:631 有"**实测 ENOB 曲线见第 5.3.2 节**" | `02_system_design.md` **无**此句 | LaTeX 独有前向引用，md 未同步 |
| chap02 前向引用密度 | 7 处（§1.1） | md02 仅 3 处（`第3.3.3/3.2.2/5.3.2`，且 5.3.2 是"口径一致"而非"见曲线"） | LaTeX 追加了 3.2.1/5.4/3.2.3 等指向 |
| chap03 前向引用 | 8 处（§1.2） | md03 仅 1 处（`第5.5.5节`） | LaTeX 大幅扩写了指向第 5 章的转述 |
| chap04 前向引用 | 5 处（§1.3） | md04new 仅 1 处（`第5.5.4节`） | LaTeX 追加 5.5.8/5.7.7/5.6 等 |
| 数学符号跨度 | tex03 `\texttt`≈45 | md03 反引号 span=48 | md 的反引号 code-span 被机械迁成 `\texttt`，是 P3 根因 |

### 5.2 处置建议

1. **确立单向真源**：本轮所有修订**先改 LaTeX**（事实源），完成 P1–P4 后，**再把等价修订回灌 canonical md**（`02/03/04new/05new`），使二者语义一致，防止下次从 md 生成时又把旧问题带回来。
2. **P3 根因治理**：md 的行内 `` `符号` `` 迁移到 LaTeX 时不应统一变 `\texttt`——数学符号该进 `$…$`。建议在 md 侧也把纯数学符号从反引号改为 `$…$`，与 LaTeX 对齐，一次性消除重现。
3. **前向引用**：md 侧本就克制（前向引用少），说明"超前叙述"主要是 **LaTeX 扩写阶段引入**的。按 §1 修 LaTeX 即可，md 侧只需同步被删除的少数句。

### 5.3 待确认（需用户拍板的映射策略）

- 是否把"复用现有结果的图表重组"（§2.3 建议 A/B）落到前章 —— 这会改变 md/LaTeX 的章节内容边界，需决策后再同步。

---

## 6. 执行计划（分批，改前备份 + 改后构建）

> 遵循 21 号文档四原则；每批改完 `latexmk -xelatex` 构建并核 `\ref` 无 undefined、图表编号无跳变。

- **批 1（P1+错标 label，高优先）**：修 `fig:ch03-active-crossing`→`fig:ch02-active-crossing`（含 chap03:249 引用）；删/弱化 §1.1–§1.3 各前向小节号；删 chap04:536 跨章图表 `\ref`。
- **批 2（P3 数学符号，高优先）**：chap03 §3.3–§3.4、chap02 相关 `\texttt` 数学符号 → 数学环境。
- **批 3（P3 命名，高优先）**：文件名/类名/函数名/`\path` → 叙述化，代码级标识移附录（或删）。
- **批 4（P2 结果剥离，中）**：chap3 §3.5、chap4 §4.5 剥离第 5 章数值，保留方法侧。
- **批 5（P4 AI 味，中）**：按 §4.3 做删除式精简，优先 chap05 讨论/小结。
- **批 6（P5 回灌）**：把批 1–5 的等价改动同步回 `02/03/04new/05new` md。

## 6.1 用户已确认的处置决策（2026-08-13）

- **P2**：采用**剥离 + 图表重组 A/B**——chap3 §3.5、chap4 §4.5 剥离第 5 章数值；并复用现成数据在第 3 章放 ES-EKF 对照小表、第 4 章 CBF 小节放净空锚点，让前章自证（不新增实验）。
- **P1**：**不必全删指向**，但**弱化章号**（`第 5.5.8 节`→`实验章`），并**减少非必要的向后超前指向**；跨章结果数值/跨章图表 `\ref` 删除；错标 label 必修。
- **P3**：**数学符号 + 命名全清**（符号转数学环境、文件名/类名/函数名叙述化或移附录）；**硬件接口标识保留**（`$CKTH`、`Trig1`、IP 段、`0x01`、`+Vdc` 等不脱敏）。
- **P4**：删除式精简，不逐句改。
- **执行**：批 1 立即开始。

## 7. 执行进度记录

- 2026-08-13：完成全量静态审计，建立本文档；四类问题证据与位置已逐条留存。用户确认处置决策（见 §6.1）。
- 2026-08-13：进入**批 1**（P1 前向引用弱化 + 错标 label 修复）。
- 2026-08-13：**批 1 完成并验证**。
  - 错标 label：`fig:ch03-active-crossing` → `fig:ch02-active-crossing`（chap02:363/368 定义处 + chap03:249 引用处，均已同步）。
  - chap02 前向小节号全部弱化：275（`第 3.3.3 节`→`第 3 章状态估计`）、370（删`见第 5.4 节`→`其系统级实测验证属实验章内容`）、496（删`第 3.2.2/5.3.2 节`→`与后续状态估计与实验章口径一致`）、569（`第 3.2.1 节`→`第 3 章`）、631（**用户点名 ENOB**：删`实测 ENOB 曲线见第 5.3.2 节`→`其实测 ENOB 表征属实验章内容`）、647（`第 3.2.3 节`→`后续状态估计所采用的`）。
  - chap03 前向小节号弱化：175/246-247/269/298-299/323/331/339 全部改为`实验章`或`第 5 章`级别，删去 `第 5.4/5.5.5/5.5.11/5.6 节` 等小节号。
  - chap04 前向小节号弱化 + 跨章 `\ref` 删除：386（`第 5.5.8 节`→`实验章`）、502-503（`sec:ch05-5-7-7`→`实验章`）、522-523（三处小节号→`实验章及其边界总表`）、535-536（**删跨章 `\ref{tab:ch05-...}`/`\ref{fig:ch05-...}`**→`统一收纳于实验章`）、542（`第 5.6 节`→`实验章边界总表`）。
  - 静态复核：`grep` 确认 chap02-04 已无 `第 [3-9].[0-9]` / `§[3-9].[0-9]` / `\ref{...:ch0[56]...}` 前向命中；`fig:ch03-active-crossing` 仅存于备份目录。
  - 构建验证：`latexmk -xelatex` 成功，**179 页**，`.log` 无 undefined / multiply-defined 引用。
  - 说明：章级指向（`第 5 章`）按用户"弱化章号、不必全删"决策予以保留，属承上启下的必要指路。
- 2026-08-13：进入**批 2**（P3 数学符号 `\texttt` → 数学环境）。
- 2026-08-13：**批 2 完成并验证**。
  - chap03 §3.3.1（状态向量）：`p`/`q`/`v`/`b_a`/`b_g`/`x_nom`/`δx`/`F`/`Q`/`H`/`R`/`z` 全部转为 `\(\boldsymbol{p}\)`、`\(\boldsymbol{x}_{\mathrm{nom}}\)`、`\(\delta\boldsymbol{x}\)`、`\(\boldsymbol{F}\)` 等，与 190/194/200 行公式统一。
  - chap03 §3.3.2（声学）：`d_lat`→`\(d_{\mathrm{lat}}\)`、`θ_rel`→`\(\theta_{\mathrm{rel}}\)`、`z_sonar=[...]`→`\(\boldsymbol{z}_{\mathrm{sonar}}=[d_{\mathrm{lat}},\theta_{\mathrm{rel}}]^{\mathsf{T}}\)`、`H_sonar`/`R_sonar`→黑体数学；`[0,1]` 区间转数学。
  - chap03 §3.3.3（磁学）：`B=[B_x,B_y,B_z]^T`、`||B_obs-B_predicted(...)||²`、`d_lat`/`d_depth`/`θ_cable` 全转数学环境。
  - chap03 §3.3.4（接力）：`d_lat`/`R_sonar`/`R_mag`/`R` 转黑体数学。
  - chap03 §3.4.1（NIS/自适应 R）：`y=z-H·x_pred`/`S=H·P·H^T+R`/`y^T·S^(-1)·y`/`R_online=α·R_nominal`/`α` 全转数学环境；`[0,1]` 区间转数学。
  - chap03 §3.4.2（置信度）：`c≈1.0`/`c≈0.5`/`c→0` 转 `\(c\approx1.0\)` 等；`cov_to_conf` 函数名先改为"协方差到置信度的映射函数"（提前完成 P3 命名的一处）。
  - chap02 §2.3.1：`r`→`\(r\)`；§2.4.1：`h`/`r_s`/`r_g` 及斜距地距关系 `r_g=sqrt(r_s²-h²)`→`\(r_g=\sqrt{r_s^2-h^2}\)`；§2.4.2：`B_obs=M·B_env+b`、`M`(3×3)、`b`(3×1) 全转黑体数学。
  - 静态复核：`grep` 确认 chap02/chap03 剩余 `\texttt` 均为硬件标识（`$CKTH`/`Trig1`/`0x01`/`192.9.0.X`/`+Vdc` 等，保留）或代码标识（类名/文件名/API，留待批 3），无数学符号残留。
  - 构建验证：`latexmk -xelatex` 成功，**179 页**，无编译错误 / undefined 引用。
- 2026-08-13：进入**批 3**（P3 命名清理：文件名/类名/函数名/`\path` 叙述化，硬件标识保留）。
- 2026-08-13：**批 3 完成并验证**。
  - chap01:200：`cov_to_conf` 函数名删除，改"ES-EKF 协方差到置信度的映射函数"。
  - chap02（复核，批 1/2 已顺带处理）：`combined_stress`→"联合应力工况"、`AUVStateData`/`AUVCommand`→"统一状态数据结构与指令数据结构"、`perception_engine.py`→"感知引擎模块"、`scenario_mag_distortion_*.yaml`→"磁畸变场景配置"、`Work_Cmd=0x02...`→"急停帧"叙述，均已落地。
  - chap03:329：`\path{scenario_mag_distortion_{light,heavy}.yaml}` 删除，改"磁畸变（轻/重）场景通过专用配置生成"；同行 `1e-6 T`/`1e-8 T`→`\(10^{-6}\text{ T}\)`/`\(10^{-8}\text{ T}\)`（数学环境）。chap03 其余类名/`\path`（`TransportDelayQueue`/`SensorSampleCache`/`CableTrackingOutput`/`scenario_dvl_dropout`/`benchmark_test_log.md`）批 1/2 已叙述化。
  - chap05 命名清理：`max_iter`（math-var，3 处正文 + 2 处表头）→"迭代上限"；`CABLE_TRACKING`→"巡缆跟踪状态"；`exit_at_end`（表 1223 + 正文 1542/1544）→"任务层到达即退出"；`depthHeadingAutopilot`（表 1225 + 正文 1546/1554）→"定深定向自驾"；`Solve_Succeeded`→"求解成功"；`pvs.control_mode`/`pvs.autonomy_motion_model`/`native`/`protocol_udp`/`simulation_proxy`/`PVSSimWrapper.set_reference()`（正文 1546）→叙述化（"PVS 控制模式/运动模型""离线仿真代理""定深定向冒烟实验"）。
  - chap06:25：`exit_at_end`→"任务层到达即退出"、`offline simulation_proxy`→"离线仿真代理"、`native PVS/protocol_udp smoke`→"native PVS 定深定向冒烟"、`constant-depth/heading`→"定深定向"。
  - 静态复核：全书 `\verb`=0、`\path`=0；剩余 `\texttt` 仅硬件/协议标识（`$CKTH`/`$AUV`/`0x01-0x03`/`192.9.0.X`/`.50-.200`/`+Vdc`/`0Vdc`/`Trig1`），符合"硬件保留"决策，无软件命名/文件名/math-var 残留。
  - 构建验证：`latexmk -xelatex` 成功，**179 页**，`.log` 无 undefined / multiply-defined。
- 2026-08-13：进入**批 4**（P2 结果剥离 + 图表重组 A/B）。
- 2026-08-13：**批 4（剥离部分）完成并验证**。
  - chap04 §4.5.1 第三层（[auv-chap04.tex:517](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap04.tex#L517)）：删除"36 次运行全部完成""fallback 均为 0""p95≈9.8--9.9 ms""RMS 0.247→0.085"等第 5 章数值，改为方法侧定位 + "量化结果在实验章给出"。
  - chap04 §4.5.2（[auv-chap04.tex:523](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap04.tex#L523)）：删除"36/36""cross-track q95 0.206 m""最小净空 2.70--2.90 m""solver p95 23.84 ms""96 次运行"等，保留四条方法侧事实（无回退/authority 切换/降变化率/RMSE 非主结论）。
  - chap04 §4.6 小结（[auv-chap04.tex:542](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap04.tex#L542)）：删除净空区间与 0.247→0.085，改为"满足最小净空裕度""正式矩阵无求解回退"。
  - chap03 §3.5.1（[auv-chap03.tex:319-321](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L319-L321)）：删除 baseline n=1 三估计器"排序符合理论预期"整段（见下 §8 数据完整性）、P1 sweep"24/24 ok""XY RMSE 2.76--3.55 m"整段，保留判据与相位可观性机理结论。
  - chap03 §3.5.2（[auv-chap03.tex:327](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L327)）：删除"3.42±0.10 m vs baseline 4.62 m"跨实验对比，改为解释边界 + "数值交由实验章"。
  - 构建验证：`latexmk -xelatex` 成功，**179 页**，`.log` 无 undefined / multiply-defined。
  - **图表重组 A/B 暂缓**：原 §6.1 决策拟在 chap3 放 ES-EKF 对照小表、chap4 放 CBF 净空锚点。经数据核验（§8），chap3 ES-EKF 对照表所依赖的 baseline 三估计器数据**存在完整性问题**，不宜落地；CBF 锚点数据（D 组）坚实但涉及是否在前章保留数值，需用户复核 §8 后再定。故批 4 先只做"剥离"，"重组"部分待决策。

---

## 8. 数据完整性告警（批 4 核验中发现，需用户拍板）

> 触发点：拟在 chap3 建"ES-EKF 对照小表"（§6.1 决策 A）时，回溯核验落地数据源，发现原正文结论与落地记录相互矛盾。**本条不是叙述问题，而是证据链问题**，故单列。

### 8.1 ES-EKF baseline 排序结论与落地数据矛盾（高）

- 原 chap03 §3.5.1 与 canonical md 均称："三种方法在干净环境下精度排序符合理论预期：ES-EKF 优于 Std-EKF 优于 Raw DR"。
- 落地记录 [benchmark_test_log.md:80-86](file:///Users/bytedance/coding/AUV-Master-Project/docs/experiment/benchmark_test_log.md#L80-L86) 的实际数字：

  | 方法 | XY RMSE | Z RMSE |
  |---|---|---|
  | Raw DR | **4.305 m** | 0.030 m |
  | Std-EKF | 4.378 m | 0.005 m |
  | ES-EKF | 4.375 m | 0.005 m |

  即**水平 RMSE 上 Raw DR 反而最小**，ES-EKF/Std-EKF 几乎并列；仅 Z 轴 EKF 明显优（0.005 vs 0.030）。同文件第 86 行自注：该 MCAP 的 ground truth（`/auv/visual/truth_marker` 10 Hz）与 DVL 存在系统性初始偏移，导致 EKF 校正反引入误差，需用 `dvl_fixed_final` 修复数据重算——**该修复数据在仓库中未找到落地文件**。
- 处置：批 4 已把该矛盾结论**从方法章（chap3）删除**（改为"验证不发散"的判据式表述），不再声称 XY 排序。**但**若正文他处（如 canonical md、附录）仍宣称该排序，需一并订正；根因（缺 `dvl_fixed_final` 修复数据）建议用户决定是补数据还是永久改为"仅 Z 轴/工具链可用"口径。

### 8.2 磁畸变 3.42 m 与 baseline 4.62 m 属跨实验拼接（中）

- 3.42±0.10 m 来自 [P1 sensor sweep results.csv](file:///Users/bytedance/coding/AUV-Master-Project/log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv)（约 45 s、`mpc_mode=ua`）；4.62 m 来自另一实验 [H1 UA-MPC ablation results.csv](file:///Users/bytedance/coding/AUV-Master-Project/log/thesis_sweep/20260612_172535_h1_uampc_main_ablation/results.csv)（约 74 s、`baseline-MPC`）。二者**时长与 MPC 模式均不同**，并列作"磁畸变 vs baseline"不严格。
- 处置：批 4 已将该并列从 chap3 删除。实验章若保留该对比，应显式标注两者口径差异或改为同口径对照。

### 8.3 数据坚实、可安全引用的组

- DVL dropout 四档 24/24 + 逐 seed XY RMSE（B 组，[P1 sweep CSV](file:///Users/bytedance/coding/AUV-Master-Project/log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv)）：原始逐 seed 完整、无告警，可复算。
- CBF low/mid/high 60 s 18/18、最小净空 2.70--2.90 m、solver p95 23.84 ms（D 组，[aggregate_report.md](file:///Users/bytedance/coding/AUV-Master-Project/results/control/terrain_controller_seed_sweep_20260810_171620_cbf_terrain_3seed_pid_mpc_60s/aggregate_report.md)）：聚合报告 + 逐 run CSV 齐全，可复算。

---

## 9. 批 5（P4 AI 味削弱）执行记录

- 2026-08-13：进入**批 5**（P4 AI 味删除式精简，优先 chap05）。
- 2026-08-13：**批 5 完成并验证**。
  - chap05:307：删段首``至此''、``一脉相承''→``延续第 4 章的鲁棒性分析''。
  - chap05:606：删``值得注意的是''，直接陈述事实句。
  - chap05:945：段首``综上''→``综合上述链路''（避免与 1544 处``综上''连用，1544 处按 §4.1 保留 1 处）。
  - chap02:255：删``至此''→``这样''。
  - chap04:319：``一脉相承''→``一致''。
  - 保留判定：`需要说明的是`（chap02:378/491、chap03:269）、`换言之`（chap04:135、513）均引出实义澄清，按``不逐句改、按需精简''原则保留；全书 `这意味着` 仅 4 处且承载因果，不动。
  - 复核：全书 filler 连接词（至此/一脉相承/值得注意的是/多余的综上）已清零或降至单处；AI 味整体密度本就低，未做过度改写。
  - 构建验证：`latexmk -xelatex` 成功，**179 页**，`.log` 无 undefined / multiply-defined。

## 10. 批 6（P5 回灌 markdown）执行记录

- LaTeX 已作为事实源完成批 1--5；canonical md（`02/03/04new/05new`）本轮完成等价改动回灌。
- 回灌项：P1 前向引用弱化、P3 命名/符号规范化、P2 §3.5/§4.5 结果剥离、P4 filler 删除；并按 §8 订正 md 中的 ES-EKF 排序结论与磁畸变跨实验对比。
- 依赖决策：§8 数据完整性处置（是否补 `dvl_fixed_final`、实验章口径）与图表重组 A/B 是否落地——仍待用户拍板，未落地部分不影响本轮回灌。
- 2026-08-13：**批 6 完成并验证**。
  - chap02 md：`至此，声、磁、光三类载荷…`→`这样，…`（[02_system_design.md:122](file:///Users/bytedance/coding/AUV-Master-Project/docs/thesis/paper/02_system_design.md#L122)），与 LaTeX chap02:255 对齐。
  - chap03 md §3.5：DVL 丢包判据式、磁畸变解释边界均已与 LaTeX chap03:317--329 逐段一致；结果转述（24/24、XY RMSE、3.42 vs 4.62）已在前批剥离，md 侧同步无残留。
  - chap04 md §4.4：**md 侧公式滞后是 P3 的 md 版本**——UA-MPC 代价/权重/约束原以 ` ``` ` 代码块 + 反引号符号（`control_scale`/`conf`/`α`/`u_k ≥ u_min` 等）表达。本轮全部转 `$…$` / `$$…$$` 数学环境，与 LaTeX `eq:ch04-*` 一致：
    - 运动学六方程、欧拉离散化、`min J`、跟踪/控制代价、置信度权重放大 $\rho(c)=(1-c)^\alpha$、S 型缩放 $s_u(c)$、硬约束表与速率/带宽约束表全部数学化。
  - chap05 md：§5.5.1 汇总表、§5.6 边界表英文别名（`native PVS smoke`/`kinematic proxy`/`simulation_proxy` 等）已同步叙述化，全量 token 复扫无残留。
  - 静态复核：md01/03/04/05 无非硬件反引号 code-span、无代码块公式；md02 反引号仅剩硬件/协议标识（`$CKTH`/`$AUV`/`0x01`/`192.9.0.X`/`Trig1`/`+Vdc` 等，按决策保留）。md02--04 无 `第 5.N.N 节` 小节级前向引用、无跨章 `\ref{...ch05...}`。
  - 构建验证：LaTeX 未改（回灌只动 md），`latexmk` 报 up-to-date，PDF **179 页**、`.log` 无 undefined / multiply-defined。

---

## 11. P3 命名残留复发（批 3 漏检项，批 6 期间发现）

> 触发点：批 6 回灌时对 chap05 做全量 token 复扫，发现批 3 的静态复核只检 `\texttt`/`\path`/`\verb`，**遗漏了以纯文本形式散落在 chap05 汇总表（§5.5.1）、证据边界总表（§5.6）与若干正文段的代码/配置/文件/函数标识**。这类残留既违反 P3（"变量名/文件名绝不可出现"），其英文短语又叠加 P4（AI 味）。用户在本轮明确点名"老问题少量重现，例如变量名，文件名绝不可出现"，故单列并处置。

### 11.1 命中清单（chap05 LaTeX，纯文本非 `\texttt`）

| 类型 | token 示例 | 典型位置 | 处置 |
|---|---|---|---|
| snake_case 配置/代理名 | `simulation_proxy`、`protocol_udp`、`kinematic log`、`kinematic proxy`、`manual setpoint` | [auv-chap05.tex:365](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L365)/[371](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L371)/[1221](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L1221)/[1224](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L1224) | 叙述化："离线仿真代理""UDP 协议链路""运动学日志""手动设定点/运动学代理" |
| camelCase 函数/配置名 | `depthHeadingAutopilot` | 371/1221/1224/1509 | "定深定向自驾" |
| 英文运行别名 | `native PVS smoke`、`constant-depth/heading`、`full-flow`、`host-relay`、`firmware echo`、`parse error`、`applied target speed`、`authority snapshot`、`quality-control policy`、`truth/measurement`、`guidance-level` | 371/372/1219/1220/1224/1226/1425/1427/1447/1509 | 叙述化："native PVS 定深定向冒烟""定深定向执行链""全流程""host-relay 路径""固件回显""解析错误""施加目标速度""授权快照""质量控制策略""真值与量测""制导级" |

- 注：`\texttt{\$AUV}`/`\texttt{\$CKTH}`（如 372/1548）为硬件/协议帧标识，按 §6.1 决策保留；`\includegraphics`/`\label` 内的资产文件名是路径而非正文，保留。
- 处置：本条在批 6 期间以 LaTeX 为事实源统一叙述化，再回灌 md（chap05 md 表格同样带 `native PVS smoke`/`kinematic proxy` 等英文别名，一并同步）。

---

## 12. 全量收口复核（批 1--6 + §11 完成后）

> 2026-08-13：四类问题的整改全部落地并回灌 md 后，做一次跨全书静态终检 + 构建验收，作为本轮闭环证据。

### 12.1 静态终检结果（全部通过）

| 检查项 | 命令口径 | 结果 |
|---|---|---|
| P1 前向小节号（chap02--04 引用 `第 [5-9].N`/`§[5-9].N`） | `grep -nE "第 [5-9]\.[0-9]\|§[5-9]\.[0-9]"` | **0 命中** |
| P1 跨章 `\ref` 指向 ch05/ch06（chap02--04） | `grep -nE "\\ref\{[^}]*ch0[56]"` | **0 命中** |
| P3 `\verb` / `\path`（全书） | `grep -c` | **0 / 0** |
| P3 残留 `\texttt`（全书） | token 枚举 | 仅硬件/协议标识：`$CKTH`×5、`$AUV`×5、`Trig1`、`0x01--0x03`、`192.9.0.X`/`.100/.101/.200/.50/.60`、`+Vdc`/`0Vdc`——**符合 §6.1"硬件保留"** |
| P3 纯文本代码标识（§11 命中项，chap05） | token 复扫 | **0 命中**（`simulation_proxy`/`protocol_udp`/`depthHeadingAutopilot`/`native PVS smoke`/`host-relay`/`parse error`/`authority snapshot` 等已全部叙述化） |
| P3 正文文件名/代码标识（全书 `.py/.yaml/.csv` + snake/camel） | 正则扫描（排除 `\label`/`\ref`/`\includegraphics`/图路径） | **0 命中** |
| P4 filler（至此/一脉相承/值得注意的是/综上所述） | `grep -nE` | **0 命中**；保留的 2 处 `综上`（[chap01:134](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap01.tex#L134)、[chap05:1544](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L1544)）均引出实义总结，按"不逐句改"保留 |
| P5 canonical md filler / 前向小节号 / 代码块公式 | `grep`（`04new`/`05new`/`03`/`02`） | filler=0、前向 `第 [5-9].N`=0、`04new` triple-backtick fence=**0**（公式已全数学化） |

- 说明：`docs/thesis/paper/05_experiments_and_discussion.md`（无 `new`）仍有 `到此为止`/`一脉相承`/`n=1` 老措辞，但按 [INDEX.md:22](file:///Users/bytedance/coding/AUV-Master-Project/docs/thesis/paper/INDEX.md#L22) 的 canonical 决策，无 `new` 后缀的 04/05 为历史对照、**不作正文事实源**，故不在本轮整改范围内，保持原样以留档。

### 12.2 构建验收

- `latexmk -xelatex -halt-on-error auv-thesis.tex`：**exit=0**。
- `Output written on auv-thesis.xdv (179 pages, 3523272 bytes)`——页数与本轮起始一致，无膨胀。
- `.log` 无 `undefined references`、无 `multiply-defined`、无 `Citation ... undefined`。

### 12.3 图表重组 B（CBF 净空锚点）落地确认

- LaTeX [auv-chap04.tex:503](file:///Users/bytedance/coding/AUV-Master-Project/thuthesis/data/auv-chap04.tex#L503) 与 md [04new_decision_and_control.md:281](file:///Users/bytedance/coding/AUV-Master-Project/docs/thesis/paper/04new_decision_and_control.md#L281) 均已含"最小离底净空稳定保持在 2.7--2.9 m 区间、低净空违规率与穿底率均为零"的方法侧最小锚点，且显式声明"完整统计及适用边界在实验章给出""不外推为所有极端电缆场景已安全闭合"，与 §8.3 D 组坚实数据一致。

### 12.4 本轮结论

- **P1（超前叙述）**：chap02--04 已无小节级前向引用与跨章结果 `\ref`；章级指路（`第 5 章`/`实验章`）按用户决策保留。错标 label `fig:ch03-active-crossing`→`fig:ch02-active-crossing` 已修并同步引用。
- **P2（前章占位/chap5 杂糅）**：chap3 §3.5、chap4 §4.5 已剥离 chap5 数值、保留方法侧结论；图表重组只做 B（CBF 锚点），A（ES-EKF 对照表）因 §8.1 数据完整性问题暂缓（待用户就 `dvl_fixed_final` 决策）。chap5 未额外吸入方法章内容，收口边界清晰。
- **P3（命名残留）**：数学符号全数学化、软件命名/文件名全叙述化或移附录、硬件标识保留；含 §11 的纯文本残留复发已清零。
- **P4（AI 味）**：filler 连接词清零/降至单处，未过度改写。
- **P5（MD-LaTeX 映射）**：以 LaTeX 为事实源，批 1--5 修订已等价回灌 canonical md，二者语义一致。

### 12.5 唯一遗留待用户拍板项

- **§8.1 ES-EKF baseline 排序的数据完整性**：矛盾结论已从正文删除、改判据式表述；但根因（缺 `dvl_fixed_final` 修复数据）仍需用户决定"补数据重算"还是"永久改为仅 Z 轴/工具链可用口径"。图表重组 A 依赖此决策，暂缓。此为 Mac 端不可自行解决项（不新增实验）。
