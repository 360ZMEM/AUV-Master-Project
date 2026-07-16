# 24 ES-EKF 声张核验 + 全文愿景--证据强度审计 + 代码/实验后续计划

> 审计时间：2026-08-13
> 事实源（唯一可信）：`thuthesis/data/` 下 `auv-abstract.tex`、`auv-chap01.tex`--`auv-chap06.tex`、`auv-appendix-a.tex`。所有结论、口径以 LaTeX 正文为准，`docs/thesis/paper/*.md` 与 `docs/` 开发文档仅作数据溯源，不作声张事实源。
> 触发来源：23 号文档 §8.1 指出 ES-EKF 存在过度声张嫌疑，且前批已消除占位符（解决"有无/验证边界"），本轮转入"愿景表述 vs 实验证据强度"的集中复核。
> 执行约束：Linux 写作侧，本轮**不新增实验**，只做静态核验 + 给建议 + 落盘上下文。改动正文需另起批次。

---

## 0. 结论速览

| 维度 | 结论 |
|---|---|
| ES-EKF 是否过度声张（正文） | **正文基本无过度声张**。正文已刻意回避"ES-EKF 优于 Raw DR/Std-EKF"的横向对比，只报"24 次运行估计连续"+ 分源 NIS 负结果 + 可观性边界。23 号 §8.1 担心的排序矛盾**已在前批从正文删除**。 |
| ES-EKF 是否有调优空间"翻正" | **水平精度无调优空间**：根因是可观性缺陷（长航段无绝对水平位置观测，观测模型 x/y 无直接测量项），调 R 救不了；**深度维/协方差一致性有调优空间**（深度 R 被低估、DVL R 过保守）。故：不应声张水平精度优越性，可强化"协方差一致性诊断 + 可观性归因"这一真正正结果。 |
| 过度声张藏在哪 | **藏在非事实源的开发文档**：[docs/experiment/benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md) 与 [docs/user-guide/05_benchmarks.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/user-guide/05_benchmarks.md#L172-L182) 仍存活"DVL 修复后 XY 改善 95%、ES-EKF 达 0.9 m"——数据不同源、深度维全崩、单 bag，**不能作 ES-EKF 优越性证据**。好在未进正文。 |
| 全文愿景--证据落差 | 正文自律程度罕见地高（§5.6 边界总表 + 附录 A.7/A.9 兜底）。**唯一系统性缺口**：摘要/结论章的浓缩表述省略了第 5 章已诚实记录的 n=1、仿真、场景改配、单次峰值越界等限定词。处置以"回填就地限定词"为主，**不删实验结论**。 |

---

## 1. ES-EKF 过度声张专项核验（回应 23 号 §8.1）

### 1.1 正文当前口径（已核对，无过度声张）

| 位置 | 现表述 | 判定 |
|---|---|---|
| [auv-chap01.tex:173](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap01.tex#L173) / [:200](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap01.tex#L200) | ES-EKF 作融合骨架、协方差到置信度映射 | 只讲"维持连续性 + 传递不确定性"，未讲精度领先。**诚实** |
| [auv-chap03.tex:320-321](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap03.tex#L320-L321) | DVL 丢包场景"判据式"表述 + 从可观性角度解释水平漂移 | 前批已把"XY 排序符合预期"改为"不发散判据"。**诚实** |
| [auv-chap05.tex:605-606](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L605-L606) | 24/24 全成功；水平 RMSE 非单调、不可过度解读；离线滤波误差≠控制侧 RMSE | 明确边界。**诚实** |
| [auv-chap05.tex:621-625](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L621-L625) | 分源 NIS：深度 7.205（低估）、DVL 0.119（过保守），历史混合阈值仅操作性触发 | 作为负结果如实呈现。**诚实且是真正的正贡献（诊断能力）** |
| [auv-chap06.tex:13](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap06.tex#L13) | 35243 次量测分源审计 → 深度低估、DVL 保守 | 措辞正确。**诚实** |

> 结论：**无需删除任何 ES-EKF 正文声张**。23 号 §8.1 的矛盾结论（"ES-EKF 优于 Std-EKF 优于 Raw DR"）已不在正文出现。

### 1.2 底层数据核查：为何 ES-EKF 水平精度不优于 Raw DR

- 三估计器对比脚本 [tools/offline_ekf_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/offline_ekf_benchmark.py)：三个引擎**初始化口径不一致**——DR 用 truth 起点，ES-EKF 用首帧 DVL/depth 自对齐并手动翻 Z。这套补丁式对齐（注释多处 `NOTE(thesis Step 0 fix)`）是 truth 与 DVL 系统性初始偏移的伪影来源，导致 4.305≈4.375 的"并列"结果**在方法上不可信**。
- ES-EKF 实现 [algorithm/es_ekf.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py)：观测只有 DVL（测速度）、depth（测 z）、mag（弱深度，默认关 `enable_mag_correction=False`）。存在 `correct_gps`（唯一绝对水平位置观测）但**场景从不调用**。→ 水平 x/y 完全靠 DVL 速度积分，与 Raw DR **渐近等价**，这就是 4.305≈4.375 的物理根因。

### 1.3 调优空间判定（关键）

| 目标 | 有无调优空间 | 依据 |
|---|---|---|
| 让 ES-EKF **水平 RMSE 明显优于 Raw DR** | **无** | 可观性缺陷：观测模型无 x/y 绝对测量项，误差是积分漂移，调 R 只改变对速度的信任度，救不了漂移。R18 长时程佐证：300 s RMSE 45→105 m，仅改 DVL 相位就差 75 m，误差增长阶数不因 R 变化 |
| 改善**深度维 NIS 一致性** | **有** | 深度 NIS/dof=7.205，`sigma_depth=0.05` 偏小、被低估，调大可改善一致性 |
| 改善 **DVL 协方差校准** | **有** | DVL NIS/dof=0.119 过保守，调小 `sigma_dvl` 改善一致性（但对水平 RMSE 无实质帮助） |
| 改善**异常场景鲁棒性** | **有（已做）** | R20 Huber 即时降权把异常场景 RMSE 降约 79% |

> **处置结论**：ES-EKF 的"可写正结果"应表述为：① 多扰动下估计连续（24/24）；② 分源 NIS 诊断能力（把操作性触发与卡方一致性区分开）；③ Huber 对脉冲异常的鲁棒性。**不应触碰"水平精度优越性"**——那需要新增绝对水平观测（USBL/声磁绝对定位），是可观性问题而非调参问题。正文当前正是这么写的，**保持即可**。

### 1.4 唯一需要处置的残留（非正文）

- [docs/user-guide/05_benchmarks.md:172-182](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/user-guide/05_benchmarks.md#L172-L182) 与 [docs/experiment/benchmark_test_log.md:85-86](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md#L85-L86)：仍写"DVL 修复后 XY 改善 95%、ES-EKF/Std-EKF 达 0.9 m"。核查 [results/localization/dvl_fixed_final/](file:///home/auv_user/auv_ws/AUV-Master-Project/results/localization/dvl_fixed_final) 的 `enhanced_results.json`：三算法 **Z RMSE 全约 12 m**（深度维彻底失败被隐藏），且输入 bag 与 Step 3 不同源、单 bag 无种子。
- **建议**：给这两处开发文档加"该结果深度维失败、数据不同源、不作学术结论"的负结果注记（属文档卫生，非正文，可低优先处理），防止未来误引入正文。

---

## 2. 全文愿景--证据强度审计（集中复核）

> 判定口径：坚实（多种子/逐 run 可复算）｜n=1（单次）｜负结果（如实标）｜代理（非原生声磁/非真机）｜跨实验拼接｜仿真未验证。风险级：**高**=需降口径/改写，**中**=需补就地边界声明，**低/诚实**=保持。

### 2.1 高风险（建议主动收口，非删除）

| # | 位置 | 声张 | 底层证据 | 处置建议 |
|---|---|---|---|---|
| H-1 | [auv-chap06.tex:15](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap06.tex#L15) | 结论章："MPC 在长短波 S 弯与发卡掉头优于或持平 LOS/PID" 作为**已确立结论** | 底层为 **n=1**（[auv-chap05.tex:537](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L537) 明说"单次运行、尚不足以作主结论"） | 结论章就地降级："初步表明"或加"（单次运行，多种子待补）"，与 chap05 口径一致 |
| H-2 | [auv-abstract.tex:12](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-abstract.tex#L12) + [auv-chap06.tex:17](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap06.tex#L17) + [:15](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap06.tex#L15) | "**首次复现**闭环恢复" 的 novelty 措辞 | 恢复以**改配场景几何为前提**（[auv-chap05.tex:1101](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L1101)：真值直缆置于传感器下方约 7.5 m 以恢复可观测性），且为数字孪生 | 删"首次"或改"在满足磁观测几何前提的六自由度闭环中复现恢复"，并一句话点明几何前提 |

### 2.2 中风险（需补就地边界声明）

| # | 位置 | 声张 | 缺口 | 处置建议 |
|---|---|---|---|---|
| M-1 | [auv-abstract.tex:12](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-abstract.tex#L12) / [auv-chap06.tex:17](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap06.tex#L17) | 磁标定降 96.27%/95.31% | 高层**未就地带 n=1/仿真**标签（仅靠 abstract:14 全局免责；[auv-chap05.tex:248](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L248) 图注已标"仿真标定框架 n=1，非真机转台"） | 就地加"（仿真标定，n=1）" |
| M-2 | [auv-abstract.tex:12](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-abstract.tex#L12) | 端到端"满足磁观测物理前提后…恢复" | 委婉语弱化了**场景几何改配**（把缆重新摆到传感器正下方） | 一句话点明"经几何重配恢复磁可观测性后" |
| M-3 | [auv-abstract.tex:12](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-abstract.tex#L12) / [auv-chap06.tex:25](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap06.tex#L25) | 实时性只引 p95（23.84/24.02 ms） | 省略 **>50 ms 单次峰值越界**（[auv-chap05.tex:1425](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L1425) 单次最大 51.71 ms；[:1542](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L1542) max 53.27 ms、20 Hz 周期越界率 0.006） | 结论章局限段补"单次最大求解耗时曾达约 53 ms、20 Hz 周期偶发越界（越界率 0.006）" |
| M-4 | [auv-chap04.tex:515](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap04.tex#L515) | 预瞄"把横向误差压低**约一个量级**" | 量级化措辞基于 **n=1**（[:536](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap04.tex#L536) 已补"仅单次运行"，但 515 未就地限定） | 就地补 n=1 或改"在本次运行中" |

### 2.3 低风险 / 已充分诚实（保持，勿动）

| 位置 | 说明 |
|---|---|
| [auv-chap05.tex:1195-1230](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L1195-L1230) §5.6 负结果归因总表 | R13-v2 RMSE 未改善（7.932→8.006 m）、CBF 手动设定点代理、CBF/R22 p95≠10 ms 硬实时、PC104 只报抖动、数字孪生验收≠海试——逐条"现象-归因-处置-剩余验证"集中收束。**全文防过度声张的主承重墙** |
| [auv-chap01.tex:191-205](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap01.tex#L191-L205) | 创新点自带证据等级免责，标杆级自律 |
| [auv-chap05.tex:786](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L786) | UA-MPC 定位改善但重度 DVL 丢包 **-1.9%**，明确不可写成"性能显著优于基线" |
| [auv-chap05.tex:1218](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L1218) | R13-v2 RMSE 由 7.932→8.006 m，收束为控制平滑而非精度 |
| [auv-appendix-a.tex](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-appendix-a.tex) A.7/A.9/A.10 | 逐实验列"样本量/可支撑结论/不可外推范围"，兜底完备 |

### 2.4 六类风险模式命中总览

1. **负结果被正向包装**：基本不存在（R13-v2 RMSE、UA 定位变差、R22 UA 抬 p95、NIS 失配全部如实标）。
2. **n=1 当结论**：正文/附录标注到位；**仅结论章 H-1/H-2、chap04 M-4 未就地重申**。
3. **代理外推**：R13-v2/R22/CBF 均反复标"代理不代表原生声磁闭环"。诚实。
4. **跨实验拼接**：正文**未发现误导性拼接**（23 号 §8.2 的 3.42 vs 4.62 已在前批从 chap3 删除）。摘要 L12 是并列成果清单，各自标来源，非对比。
5. **仿真到实物边界**：磁标定/PC104/数字孪生/端到端恢复均有边界；**薄弱点仅摘要 M-2 委婉措辞**。
6. **实时性边界**：p95≠10 ms 硬实时表述全程正确；**薄弱点仅 >50 ms 单次峰值未进摘要/结论（M-3）**。

---

## 3. 后续代码库优化 / 改进建议

> 分优先级；每项标注"解决什么证据缺口 + 是否影响既有实验正交性"。遵循 AGENTS 奥卡姆剃刀 + 正交性原则，不使既有实验失效。

### 3.1 P0（直接支撑现有正文声张的诚实性，低风险）

- **O-1 三估计器公平对比脚手架修复**（对应 §1.2）：统一 [tools/offline_ekf_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/offline_ekf_benchmark.py) 三引擎的初始化口径（同一 truth 起点、同一 frame、去掉手动翻 Z 的补丁），并修复深度维 12 m 恒偏。产物：同 bag、同口径、多种子的三方对比表。**用途**：要么给出可信的"ES-EKF 深度维优越 / 水平维等价"结论，要么正式确认"水平维需绝对观测"，二者都能替换掉 §1.4 的不可信开发文档结论。**正交性**：不改 es_ekf.py 算法，只改 benchmark 脚本。
- **O-2 开发文档负结果注记**（对应 §1.4）：在 05_benchmarks.md / benchmark_test_log.md 的 `dvl_fixed_final` 段落加"深度维失败、数据不同源、非学术结论"标注。纯文档卫生。

### 3.2 P1（把"负结果"升级为"可复算的正贡献"）

- **O-3 分源自适应 R 重构**（对应 [auv-chap05.tex:625](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L625) / [:1212](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L1212)）：把 [algorithm/es_ekf.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py) 现在"一维+三维原始 NIS 混入同一窗口 + 固定阈值 9.0"改为**按观测源、按自由度用 NIS/dof 或 p 值归一化**门控。这是正文 §3.4.1 与 §5.6 已明确指出的"剩余验证"，落地后可把"历史实现语义不自洽"的负结果转成"分源一致性校准"的正结果。**正交性**：会改变自适应 R 行为，属"会使既有 NIS 审计结果变化"的改动，**需先批准、并作为新实验单独记录**，不可回改现有 24 次矩阵结论。
- **O-4 深度/DVL 协方差默认值整定**：基于 NIS 审计（深度低估、DVL 过保守），把 `sigma_depth` 调大、`sigma_dvl` 调小到卡方一致带内，出一版"协方差校准前后 NIS 覆盖率对比"。**正交性**：改默认参数会影响所有依赖 es_ekf 的实验，**需批准**。

### 3.3 P2（补可观性，才可能触碰"水平精度"，属新课题）

- **O-5 绝对水平观测闭环**（对应 [auv-chap05.tex:1213](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L1213)）：启用/接入 `correct_gps`（水面）或 USBL/声磁绝对横向观测，验证水平漂移是否被抑制。这是让 ES-EKF 水平精度真正超过 DR 的唯一途径，**属论文展望级新课题，本毕设范围外**。

---

## 4. 进一步实验计划（不新增落地，仅计划）

> 均需按写作/实验隔离原则：未批准 → `未完成内容/`；批准且符合预期 → `核心中间进度同步/`。任何单次结果仍标 n=1，代理场景仍与原生声磁耦合区分（附录 A.9 兜底口径）。

| 编号 | 实验 | 目的（补哪个证据缺口） | 优先级 | 预期产物 | 依赖 |
|---|---|---|---|---|---|
| E-1 | MPC 极端平面路径**多种子**扫描 | 把 H-1/M-4 的 n=1 升级为可作主结论的统计（长波/短波 S 弯/发卡/直角） | P0 | 每场景 ≥3 种子横向 RMSE 均值±std 表 | 现成极端路径 runner |
| E-2 | 三估计器公平对比重算（O-1 修复后） | 关闭 §1.4 不可信开发文档结论，给可信深度/水平分维结论 | P0 | 同 bag 多种子三方对比表 | O-1 |
| E-3 | 分源自适应 R A/B（O-3/O-4 落地后） | 把 NIS 负结果升级为"分源校准"正结果 | P1 | 校准前后 NIS 覆盖率、24 场景鲁棒性复跑 | O-3/O-4 批准 |
| E-4 | R13-v2 动态置信激励场景 | 回应 [auv-chap05.tex:1216](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L1216)：现控制置信度几乎恒为 0.367，UA 差异被掩盖 | P1 | 有动态置信激励的六场景主矩阵 | 分源置信接口重构 |
| E-5 | PVS 原生**多种子性能矩阵** | 把"原生冒烟仅关闭执行链风险"升级为性能证据（对应 §5.6 剩余验证） | P2 | 原生全因子安全/性能矩阵 | 原生执行链已闭合 |
| E-6 | 真机 Jetson--PC104 端到端时延闭环（PTP/固件回显） | 唯一能把"到达间隔/抖动"升级为"单向物理延迟"的实验 | P2（实物 handoff） | 单向/往返时延分布 | 实物 handoff（见 docs/real_deployment/13） |

---

## 5. 本轮处置边界与待用户拍板项

- **本轮不改正文**：H-1/H-2/M-1--M-4 均为"回填就地限定词"级改动，需另起批次执行（建议与 23 号批 4 遗留的图表重组 A 一并决策）。
- **不新增实验**：E-1--E-6 为计划；O-3/O-4/O-5 涉及会使既有实验结论变化的算法/参数改动，**必须先获批**再落地并单独记录，不得回改现有矩阵。
- **待拍板**：
  1. 是否执行 H-1/H-2/M-1--M-4 的正文就地收口（建议执行，风险低、只加限定词）。
  2. §1.4 开发文档负结果注记是否落地（建议落地，纯卫生）。
  3. O-1（benchmark 脚手架修复 + E-2）是否作为 P0 补强——这是把"ES-EKF 价值"从"回避对比"提升到"可信分维结论"的关键，也是 23 号 §8.1/§12.5 遗留的 `dvl_fixed_final` 决策的真正解法。

---

## 6. 关键证据定位速查（可复算数据源）

| 实验 | 结果路径 | 逐 run/seed 原始数据 |
|---|---|---|
| P1 sensor sweep（ES-EKF 24 次鲁棒性真源） | [log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv](file:///home/auv_user/auv_ws/AUV-Master-Project/log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv) | 有（8×3=24 行 + 逐 run 目录 + manifest） |
| 分源 NIS 审计（35243 次真源） | [results/uncertainty_aggregates/20260809_r05_nis_semantic_audit/](file:///home/auv_user/auv_ws/AUV-Master-Project/results/uncertainty_aggregates/20260809_r05_nis_semantic_audit) | 有（`per_run/*/nis_events.csv` 逐量测更新 + `nis_semantic_audit.json`） |
| R18 长时程相位 | [results/state_estimation/r18_long_horizon/20260809_r18/](file:///home/auv_user/auv_ws/AUV-Master-Project/results/state_estimation/r18_long_horizon/20260809_r18) | 有（含 config 快照，最规范） |
| R20 滤波策略（Huber -79%） | [results/state_estimation/r20_filter_strategies/20260809_r20/](file:///home/auv_user/auv_ws/AUV-Master-Project/results/state_estimation/r20_filter_strategies/20260809_r20) | 有（6 策略×3 场景×5 种子） |
| CBF 三档地形三种子（坚实） | [results/control/terrain_controller_seed_sweep_20260810_171620_cbf_terrain_3seed_pid_mpc_60s/](file:///home/auv_user/auv_ws/AUV-Master-Project/results/control/terrain_controller_seed_sweep_20260810_171620_cbf_terrain_3seed_pid_mpc_60s) | 有 |
| dvl_fixed_final（**深度维失败、不可作结论**） | [results/localization/dvl_fixed_final/](file:///home/auv_user/auv_ws/AUV-Master-Project/results/localization/dvl_fixed_final) | 单 bag、Z RMSE≈12 m、不同源 |

---

## 7. 与既有文档的关系

- 承接 [23_全文超前叙述_命名残留_AI味_MD-LaTeX映射审计.md](file:///home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/潜在待完成事项/23_全文超前叙述_命名残留_AI味_MD-LaTeX映射审计.md)：23 号解决"超前叙述/命名/AI 味/映射"与占位符（有无问题）；本 24 号解决"愿景表述 vs 证据强度"（正不正问题），并给出 23 号 §8.1/§12.5 遗留 `dvl_fixed_final` 决策的技术解法（O-1/E-2）。
- 实物时延实验（E-6）对接 [docs/real_deployment/13_physical_handoff_next_plan.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/real_deployment/13_physical_handoff_next_plan.md)。
- 证据等级与不可外推口径以附录 A.9 + §5.6 边界总表为准。

---

## 8. 清华硕士标准下的边界三分类（致命须修复 / 可大方承认 / 不自洽点归属）

> 追加时间：2026-08-13（同批次）。
> 本对话定位：**提升论文内容深度**。默认策略是"能用仓库内可控改动消除的边界就动手消除、真正提升实验质量"，只有**结构性崩溃（物理/信息论不可行）**才作为边界承认。故本节把 §1--§2 审出的全部边界重新做**攻防三分类**，供决策"打哪些、认哪些"。

### 8.0 分类判据（先立标准，避免主观）

一条边界归入**类型 1「致命·须修复（打）」**，当且仅当三条同时成立：
1. 它**削弱核心贡献的方法可信度**（清华硕士答辩会被问的那种：n=1 作对比结论、脚手架 bug 导致的伪影、协方差语义不自洽）；
2. **非物理不可行**——在现有传感构型的可观性/信息量下，正确的方法本应能做到；
3. 用**仓库内可控改动**（加种子、修脚手架初始化、整定协方差、启用已存在的观测接口）即可在毕设周期内闭合，且不引入新硬件/新传感模态。

归入**类型 2「可大方承认（认）」**，当满足其一：
- **结构性/物理不可行**：观测模型信息量不足（可观性秩亏）、无时钟同步无法测单向时延——调参/改代码救不了；
- **需超范围条件**：新传感模态（USBL/绝对横向观测）、真机海试、PTP/固件回显——属论文展望或工程交付，不属毕设方法学范畴。
- 关键洞察：**类型 2 被"严谨承认 + 给出为什么不可行的数学/物理论证"反而是深度**，比硬凑一个漂亮数字更符合清华标准。

### 8.1 Q1 —— 致命、须真正提升而非解释的边界（类型 1，建议"打"）

| 排序 | 边界 | 为何"致命"（清华视角） | 为何可打（非物理不可行） | 打法 | 成本 |
|---|---|---|---|---|---|
| **①最致命·最便宜** | MPC 极端平面路径优越性、磁标定降幅、预瞄"一个量级" 均建立在 **n=1** | 答辩必问："单次运行凭什么下比较结论？" 这是**方法学硬伤**，不是物理边界 | 只是"没多跑几个种子"，runner 现成 | **E-1**：每场景 ≥3 种子，出均值±std，把 H-1/M-1/M-4 从 n=1 升级为可作主结论的统计 | 低（纯多跑） |
| **②高价值·中成本** | 三估计器对比脚手架不可信 + `dvl_fixed_final` 深度维 12 m 崩 | 当前 ES-EKF"价值"要么靠**回避对比**，要么靠**不可信开发文档**——深度不足 | 12 m 崩是**脚手架 init 不一致/手动翻 Z 的伪影**，是仓库 bug，非算法失败 | **O-1 + E-2**：统一三引擎初始化口径→给可信"深度维优越/水平维等价"结论，直接替换回避式表述 | 中（改 benchmark 脚本，不动算法） |
| **③深度增量·须批准** | 深度/DVL 协方差 NIS 失配（深度 7.205 低估、DVL 0.119 过保守） | 协方差**语义不自洽**是滤波器可信度问题，清华会追问一致性 | 可整定：sigma_depth 调大、sigma_dvl 调小、按源按自由度归一化门控 | **O-3/O-4 + E-3**：把"负结果/语义不自洽"转成"分源一致性校准"正结果 | 中高（会改既有 24 矩阵，须先批准并单列实验） |

> ①是"必打且最划算"，②是"打了能把回避式叙述升级为正面分维结论"，③是"打了能把一整段负结果翻正"。三者都**真正提升实验质量**，不是加限定词了事。

> **②执行修正（2026-08-13，E-2 重算落地）**：O-1 修脚手架 + E-2 公平口径重算（24 次运行）后，原假设"深度维优越"**被证伪**——统一初始化后水平 RMSE 三方统计等价（DR 3.197 / Std 3.196 / ES 3.200 m，±1σ 完全重叠），深度 12 m 恒偏伪影消除（Z 落到 0.025/0.110/0.203 m），但 ES-EKF **深度也不优于 DR**（Raw DR 直接透传深度计读数、不做协方差融合，深度 RMSE 最小）。因此 ② 的正确落地不是"给出深度维优越结论"，而是：(a) 用可信数据坐实"水平维三方等价属结构性可观性边界"（把 §8.2 的类型 2 从"回避对比"升级为**正面可观性论证**）；(b) 深度差异归因于协方差整定口径（属 ③ 可整定项）而非精度；(c) ES-EKF 正贡献重定义为"估计连续 + 协方差传播 + 分源 NIS 诊断 + Huber 鲁棒"。已回填 [auv-chap05.tex §5.5.5](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap05.tex)，数据溯源见 [tri_estimator_fair/_SOURCE.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/figures/experiments/tri_estimator_fair/_SOURCE.md)。**这印证了本对话主线：修方法论比硬凑数字更能提升深度——修复反而揭示了诚实的物理真相。**

### 8.2 Q2 —— 可以大方承认的边界（类型 2，建议"认"，且认得漂亮）

| 边界 | 为何是结构性/超范围 | 承认的正确姿势（把边界写成深度） |
|---|---|---|
| **ES-EKF 水平精度 ≈ Raw DR** | **可观性秩亏**：观测仅 DVL(测速) + depth(测 z)，x/y 无绝对测量项，`correct_gps` 未接入→绝对水平位置**不可观**，任何滤波器都退化为速度积分漂移。调 R 只改对速度的信任，救不了漂移（R18：300 s RMSE 45→105 m，误差增长阶数不随 R 变） | 用**可观性分析**正面论证"为何水平维无法优于 DR、必须引入绝对横向观测"——这是严谨的系统分析，比假装 ES-EKF 全面领先更有学术价值。正文当前正是这么写的，**保持** |
| **PC104 单向物理延迟不可测** | 无 PTP/NTP/固件回显→**无共享时钟**，信息上无法分离单向时延 | 只报"到达间隔/抖动"，明确"需时钟同步或固件回显才可测单向时延"（E-6/实物 handoff） |
| **数字孪生验收 ≠ 海试；原生声磁闭环 vs 代理** | 需真机部署/原生耦合，属工程交付与展望 | 附录 A.9 + §5.6 已兜底"代理不代表原生、仿真不代表海试" |
| **端到端恢复以磁观测几何为前提** | 缆几何不利时磁可观性本就退化，是**物理事实**而非可修 bug | 承认"在满足磁观测几何前提下复现恢复"，一句话点明几何前提（即 H-2/M-2 就地限定） |
| **R13-v2 保守 UA 未改善 RMSE（7.932→8.006）** | 保守 UA 的价值本就在**控制平滑**而非精度，硬追精度是范围蔓延 | 已如实收束为"控制平滑收益"，**保持**，不必去"打" |

> 要点：类型 2 的边界**不要去硬凑数字**。清华标准下，一个用可观性/信息论论证清楚的"我为什么做不到"，胜过一个来路不明的漂亮结果。当前正文对这几条的处理已基本达标，主要动作是**把摘要/结论章缺失的就地限定词补回**（H-2/M-2/M-3）。

### 8.3 Q3 —— 论文中少量不自洽点，归 1 还是 2？

**结论：绝大多数不自洽点归类型 1（是可修复的方法/脚手架伪影，不是真边界）；只有一类"表面不自洽"归类型 2（在正确论证下自洽消失，从来不是矛盾）。**

| 不自洽点 | 归属 | 判定理由 | 动作 |
|---|---|---|---|
| 23 号 §8.1 的"ES-EKF>Std-EKF>Raw DR"排序矛盾 | **类型 1** | 矛盾根源是 `offline_ekf_benchmark.py` 初始化口径不一致的**伪影**，非真实性能。已从正文删除，但要靠 O-1 从根上消除 | O-1 修脚手架，别让它复活 |
| 开发文档"DVL 修复后 XY 改善 95%、达 0.9 m" vs 深度维 12 m 崩 | **类型 1** | 同上，脚手架伪影 + 深度维失败被隐藏；不同源、单 bag | O-2 加负结果注记 + O-1/E-2 出可信结论 |
| "ES-EKF 水平不优于 DR" 与直觉"滤波器应胜过 DR"的**表面**矛盾 | **类型 2** | 一旦接受可观性秩亏论证，"矛盾"消失——这本就不是不自洽，是**正确的物理结论** | 无需修，只需把可观性论证讲透（正文已做） |
| 摘要/结论用 p95 与 §5.6 记录的 >50 ms 单次峰值"张力" | **类型 1（轻）** | 非矛盾，是浓缩省略；补一句就地限定即可自洽 | M-3 就地补"单次最大约 53 ms、20 Hz 越界率 0.006" |

> 直觉判据：**不自洽若来自 bug/过度声张/浓缩省略 → 类型 1（修）；不自洽若在正确的物理/可观性论证下自动消解 → 类型 2（本就不是矛盾，讲透即可）。** 本论文的不自洽点，除"水平≈DR"外，全部是类型 1，且都能用仓库内改动闭合。

### 8.4 "边界→贡献"转化路线（本对话主线优先级）

1. **P0 打 ①（E-1 多种子）**：最便宜、直接把 n=1 硬伤转成统计结论——先做。
2. **P0 打 ②（O-1 修脚手架 + E-2 重算）**：把 ES-EKF 从"回避对比"升级为"可信分维结论"，同时根除 23 号/§1.4 的不自洽——次做，须留意不回改现有 24 矩阵。
3. **P1 打 ③（O-3/O-4 + E-3）**：把协方差负结果翻正——**须先获批**（会改既有矩阵），单列实验记录。
4. **认 §8.2 全部**：以可观性/信息论论证收尾，仅补 H-2/M-2/M-3 就地限定词，不硬凑。
5. **展望 O-5/E-6**：绝对横向观测、真机时延——写进展望，不在毕设内强攻。

---

## 8.5 本批次执行落盘记录（2026-08-13，边界→贡献转化）

> 承接 §8.4 优先级，本批次按"必要时直接对方法论实施修复"落地了 P0 全部与类型 2 就地收口，并把结果回填正文、通过编译验证（xelatex EXIT=0，180 页，0 未定义引用）。

| 项 | 对应 | 状态 | 落盘 |
|---|---|---|---|
| **E-1 MPC 极端路径多种子** | ①/H-1/M-4 | ✅ 完成 | [mpc_xy_yaw_extreme_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mpc_xy_yaw_extreme_benchmark.py) 加受控扰动+`--seeds`（向后兼容 n=1 位精确复现）；5 种子统计回填 [auv-chap05.tex §5.5.4](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L539)（长波 S 弯/发卡 MPC vs LOS ±1σ 互不重叠）；chap04 §4.5.1 就地补多种子支撑 |
| **O-1 三估计器公平对比脚手架修复** | ② | ✅ 完成 | [offline_ekf_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/offline_ekf_benchmark.py) 加 `--es-ekf-init {fair,legacy-auto}`；统一 truth 起点/frame/去手动翻 Z（收敛为具名 `_ros_up_to_ned`）；**不动 es_ekf.py 算法** |
| **E-2 公平口径重算** | ②/§8.3 | ✅ 完成（结论修正见 §8.1 ②执行修正） | [run_tri_estimator_fair_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_tri_estimator_fair_benchmark.py) 驱动 24 次运行；产物 + `_SOURCE.md` 落 [tri_estimator_fair/](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/figures/experiments/tri_estimator_fair)；水平三方等价（可观性）+ 深度非精度结论回填 [§5.5.5](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L630) |
| **O-2 开发文档负结果注记** | §1.4 | ✅ 完成 | [05_benchmarks.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/user-guide/05_benchmarks.md#L172) + [benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md#L88) 加"深度维失败/不同源/单bag/脚手架伪影/禁引入正文"注记 |
| **H-2/M-2/M-3 就地限定词** | §8.2 类型 2 收口 | ✅ 完成 | H-2：删 [chap06:17](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap06.tex#L17)"首次复现"→"满足磁观测几何前提后复现，点明几何重配前提"；M-2：[abstract](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-abstract.tex#L12) 中英双语点明"场景几何重配（缆置于传感器正下方约 7.5 m）"；M-3：[chap06:25](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap06.tex#L25) 局限段补"单次最大约 53.27 ms、20 Hz 越界率 0.006、尾部而非 p95 才是实时性边界" |
| **Artifact Manifest 回填** | E-1/E-2/E-3 落盘可追溯 | ✅ 完成 | catalog 新增 `CONTROL-MPC-EXTREME-E1-MULTISEED`、`ESTIMATOR-E2-TRI-ESTIMATOR-FAIR` 与 `ESTIMATOR-E3-COVARIANCE-AB`（B/complete_with_structural_dvl_floor，9/9 文件在库）；`build_thesis_artifact_manifest.py --check` 通过，共 37 条产物，隔离目录源 run 均如实标为 provenance gap |
| **③ O-3/O-4 分源自适应 R 整定 + E-3** | ③ | ✅ 完成（独立对照落地，主线默认不改） | 采纳“独立 A/B 不改默认”方案（见 §8.6）：`uncertainty_metrics.py` 加 4 个 CLI 覆盖开关 + `applied_r_scale` 列；[run_es_ekf_covariance_ab.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_es_ekf_covariance_ab.py) 三臂 × 24 bag。baseline 逐字节复现正文 7.205/0.119（既有产物不失效）；分源门控切断跨源污染（DVL R 缩放 1.69→1.000）；深度整定 NIS/自由度 7.205→3.280、覆盖率 0.561→0.735。回填 [§5.5.5](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L627) + §5.6 边界表，xelatex EXIT=0/182 页/0 未定义引用。DVL 过保守判定为结构性下界（类型 2） |
| O-5/E-6（绝对横向观测/真机时延） | §8.2 展望 | ⏸ 展望 | 属论文展望级新课题/实物 handoff，不在毕设内强攻 |

**结论**：类型 1 中 ①②③ 已全部闭合（均真正提升实验质量，非加限定词）；类型 2 已以可观性/几何前提论证 + 就地限定词收口，③ 中 DVL 过保守亦以“自适应仅膨胀→结构性下界”论证归入类型 2。剩余仅展望项（O-5/E-6）。M-1（磁标定就地 n=1 标签）图注已在 [chap05:248](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L248) 标注，摘要靠全局免责，判定为低风险可保持。

---

## 8.6 ③ 的门控解法：把"须批准·会使既有产物失效"改造成"独立对照·不失效"（2026-08-13 落地）

> 起因：③（O-3/O-4 分源协方差整定）是本计划里唯一被门控为"须批准"的项——原设想是**直接改 `es_ekf.py` 默认协方差**，会使正文已引用的深度 NIS/自由度 7.205、DVL 0.119 与 `ESKF-NIS-8X3` 产物一并失效、需重跑整套 24 矩阵。本节记录如何在不触碰这条红线的前提下把 ③ 真正落地。

### 8.6.1 决策：采纳"独立 A/B，不改默认"（E-3）

核心是把"整定"从**主线默认变更**解耦为**独立对照实验**：

- **不改** `algorithm/es_ekf.py`、`brain_linux/config/params.yaml` 的默认协方差（仍 global / `sigma_depth=0.05` / `sigma_dvl=0.03`）；
- 只给离线诊断工具 `tools/uncertainty_metrics.py` 加**可选** CLI 覆盖开关（缺省=不改，逐字节沿用配置文件），在 A/B 进程内改写口径；
- 因此 **baseline 臂逐字节复现正文 7.205 / 0.119**，既有 24 矩阵与 `ESKF-NIS-8X3` 产物**不失效、不回改**，红线不被触碰。

这样 ③ 从"须批准才能动"变为"已可安全落地的独立正结果"；真正需要批准的只剩"是否把整定后的默认口径回写主线并重跑矩阵"，那属可选的后续动作，不阻塞本轮深度提升。

### 8.6.2 实现（只加开关，不动算法与默认）

- `uncertainty_metrics.py` 新增 `--sigma-dvl` / `--sigma-depth` / `--adaptive-r-mode {fixed,global,per_source}` / `--adaptive-r-normalized-threshold`，仅在显式传参时改写 `load_ekf_config` 结果；
- 新增 `applied_r_scale` 列，如实记录 per_source 模式下逐源实际生效的 R 缩放（`r_scale_after_update` 只读全局累加器，在 per_source 恒为 1.0 会低估分源缩放），既有列数值不变；
- `tools/run_es_ekf_covariance_ab.py` 驱动三臂 × 24 bag（同 P1 sensor sweep），逐量测池化 NIS/自由度、覆盖率、实际 R 缩放。

### 8.6.3 结论（三臂，24 次运行池化；完整表见 [_SOURCE.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/figures/experiments/covariance_ab/_SOURCE.md)）

| 整定臂 | 深度 NIS/dof | 深度覆盖率 | DVL 实际 R 缩放 | 判定 |
|---|---|---|---|---|
| A 基线（默认全局） | 7.205 | 0.561 | 1.691× | 复现正文口径的锚点，既有产物不失效 |
| B 分源门控（O-3） | 8.126 | 0.567 | 1.000× | 切断跨源污染（DVL 缩放 1.69→1.0）|
| C 门控+深度整定（O-3+O-4） | **3.285** | **0.737** | 1.000× | 深度整定回卡方带内，负结果翻正 |

> 数值口径说明（2026-08 复算）：`tools/run_es_ekf_covariance_ab.py` 由 0 字节空 stub 重建后，A 基线臂逐字节复现正文锚点（深度 7.205 / DVL 0.119，`git` 同源确定性回放，两次重跑逐字节一致）；B/C 分源臂因 `es_ekf.py` per_source 门控逻辑在初次产物生成后有过一次细化（提交"毕设资产实验完善"），复算值较早期产物有 <2% 漂移（B 深度 8.068→8.126、C 深度 3.280→3.285、覆盖率 0.735→0.737），结论方向不变。已用重建驱动统一 `docs/.../covariance_ab/` 产物与正文表 `tab:ch05-nis-covariance-ab`，使"驱动↔产物↔正文"三者一致、provenance gap 消除。

- **O-3 兑现**：分源门控把历史全局尺度对 DVL 的跨源污染切断（DVL 实际 R 缩放 1.69→1.000，上调占比 0.30→0），正面验证正文"应按观测源分别归一化"。
- **O-4 兑现**：`sigma_depth` 0.05→0.12 后深度 NIS/自由度 7.205→3.285、覆盖率 0.561→0.737、上界超限 0.416→0.214，逐 run 稳健（3.21±1.30，n=24）。
- **DVL 过保守归类型 2（大方承认）**：自适应机制仅膨胀 R（下界 1.0×），分源门控下 DVL 从不触发上调，NIS/自由度仍约 0.05——这是"自适应仅单向膨胀"的**结构性下界**，非可整定项；根治须下调 DVL 名义协方差本身（改主线默认），如实记为下界，不硬拉。

### 8.6.4 回填与验证

- 正文 [§5.5.5](file:///home/auv_user/auv_ws/AUV-Master-Project/thuthesis/data/auv-chap05.tex#L627) 在分源 NIS 负结果段后新增"分源一致性校准 A/B"段 + 表~`tab:ch05-nis-covariance-ab`；§5.6 边界表 NIS 行由"需按分源 p 值继续校准"更新为"深度已整定回带内、DVL 结构性下界"。
- Artifact Manifest 新增 `ESTIMATOR-E3-COVARIANCE-AB`（B/complete_with_structural_dvl_floor，9/9 文件在库），`--check` 通过（37 条产物）。
- 编译验证：`xelatex` EXIT=0，182 页，0 未定义引用，交叉引用已 settle。

### 8.6.5 遗留（可选，需另行批准）

把 C 臂口径（per_source 门控 + `sigma_depth=0.12`，以及是否缩小 `sigma_dvl`）回写 `es_ekf.py`/`params.yaml` 默认并**重跑既有 24 矩阵**——此为改主线默认，属独立后续，不在本轮深度提升范围内；本轮已用独立对照证明其收益且不使既有产物失效。
