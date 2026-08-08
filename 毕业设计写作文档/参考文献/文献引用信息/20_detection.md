# 探测技术类文献候选（对应引用点 A3–A9, A12；部分支撑 B8）

> 每条含：题录 + 摘要要点 + 链接 + DOI + 对应引用点 + 状态。
> 状态：`已检索` = 有摘要+链接可供人工下载；`待补` = 尚未检索到权威条目。
> 覆盖引用点：A3(SSS/SBP)、A4/A5(DL/T 1278 / fluxgate / 三相漏磁)、A6(Biot-Savart)、A7(铠装涡流屏蔽/螺旋绞合)、A8(斜距几何)、A9(九参数标定)、A12(磁反演埋深)。

---

## D1 · 声学探测（SSS / SBP）与埋深确定（引用点 A3 / A8，用于 §1.2.1 / §2.4.1）
- **题录（AUV 巡检综述，最贴合）**：Zhang Q, Tian Y, Ji D. Submarine cable inspection and marine robot applications: A literature review[J]. InUS Transactions, 2025, 1(1): 1-19.
- **DOI**：10.23380/inustrans.2025.1.1.1
- **摘要要点**：浙江大学团队综述，系统梳理海缆巡检中的视觉/声学/磁法/多源融合技术及其优劣，指出 SSS 只能探测裸露或有标记的电缆、对掩埋电缆无效，MBES 可给出 3D 海底地形，掩埋电缆在 15°–60° 入射角有可区分的后向散射特征；AUV 正成为海缆巡检主平台。**同时支撑 A3（声学局限）与 B8（多源融合动机）。**（开放获取）
- **链接**：https://doi.org/10.23380/inustrans.2025.1.1.1
- **补充文献 1（埋深声学，工程细节最全）**：Wunderlich J, Ingulfsen J A, Müller S. Burial depth determination of cables using acoustics — Requirements, issues and strategies[J]. Hydrographische Nachrichten, 2016 (105): 50-54. DOI 10.23784/HN105_11 —— 给出海上风电海缆 DOB（depth-of-burial）测量的精度要求（垂向 5–10 cm RMS 或 5% 斜距 / 10% 埋深），含 SBP 作为声学电缆探测手段的性能分析，**直接支撑 §2.4.1 斜距几何/埋深精度指标（A8）**。（题录经期刊官网 dhyg.de 核实：作者 Jan Arvid Ingulfsen / Sabine Müller；页码 HN105:50-54，非早前记录的 6-11；DOI 属 DHyG 自有体系，Crossref 不可解析。）
- **补充文献 2（国内综合探测方法选择）**：岑贞锦, 蒋道宇, 张维佳, 蔡驰. 海底电缆检测技术方法选择分析[J]. 南方能源建设, 2017, 4(3): 85-91,96. DOI 10.16516/j.gedi.issn2095-8676.2017.03.016 —— 对比磁力仪/管线仪/侧扫声呐/多波束/TSS350，含 TSS350 有源三分量磁探测原理与埋深测量，海南联网海缆实例。中文出处，便于国内答辩引用。
- **状态**：已检索

## D2 · DL/T 1278 海底电力电缆运行规程（引用点 A4 / A5，用于 §1.2.2 / §2.1.1 指标条款）
- **题录（拟）**：国家能源局. 海底电力电缆运行规程: DL/T 1278—2025[S]. 北京: 中国电力出版社, 2025.
- **DOI**：无（电力行业标准，无 DOI；以标准号 + 发布机构为准）
- **摘要要点**：电力行业标准，规定海底电力电缆运行、检测、埋深与路由巡检的技术要求，本文以其对磁探测灵敏度（0.05 nT 级）与埋深反演误差（0.2 m 级）的条款作为设计指标来源（正文 §1.2.2 / §2.1.1 引用点 A4/A5）。
- **链接**：需人工检索（工标网 / 国家标准全文公开系统 / 电力出版社）；本仓库 `相关附件和参照/相关国家标准和行业论文/` 可能已有原文。
- **状态**：待补（**待用户确认**：①标准号年份是 2025 还是 2013 修订版；②0.05 nT / 0.2 m 是否直接出自该标准条款，还是本项目自定设计目标——需核对 §2.1.1 原文「TODO: cite 确认来源」A5）
- **备注**：GB/T 7714 中标准的著录格式为「主要责任者. 标准名称: 标准编号[S]. 出版地: 出版者, 出版年.」——若无正式出版者，可写「[S]. 北京: 中国电力出版社, 2025.」并在正文首次出现处标注 [S]。

## D3 · 三相交流海缆工频磁场建模（Biot-Savart）与漏磁探测（引用点 A4 / A6 / A7，用于 §1.2.2 / §2.3.1 / §2.3.2）
- **题录（三芯交流磁场 Biot-Savart 模型，最贴合 A6）**：孙运坤, 李尤, 曹向东, 等. 基于工频磁特征的近岸海底电缆 UAV 航磁定位方法[J]. 水下无人系统学报, 2026, 34(1): 37-46.
- **DOI**：10.11993/j.issn.2096-3920.2025-0083
- **摘要要点**：**基于毕奥-萨伐尔定律和矢量叠加原理，建立三芯交流电缆从电流到磁场的完整正演模型**，综合考虑电缆几何结构、三相电流时变特性与空间磁场叠加；构建工频磁特征频域信号提取算法以在强噪声下识别弱磁信号，结合地磁方向逆向解析实现米级定位（实测误差 ≤1.8 m）。**直接支撑 §2.3.1 Biot-Savart 圆柱坐标解析解（A6）与 §1.2.2 三相漏磁抵消（A4）。**（中文，开放获取）
- **链接**：https://doi.org/10.11993/j.issn.2096-3920.2025-0083
- **补充文献 1（交流磁场建模 vs 传统直流）**：Su Q, Zhang Y, Chen Y, et al. Precise identification method of submarine cable routes based on weak magnetic detection and AC modeling[C]//2025 International Conference on Sensing, Measurement & Data Analytics (ICSMD). IEEE, 2025. DOI 10.1109/ICSMD67131.2025.11365331 —— 建立交流（AC）磁场模型（区别于传统直流偶极子），分析航向角/航速/探测角对磁场强度的影响。
- **补充文献 2（工业系统佐证三相抵消）**：Megger Magtrack 海缆跟踪定位系统技术资料 —— 明确指出「平衡三相电缆磁场理论上为零，需相间几安培不平衡才能跟踪」，四个三轴 fluxgate + 倾角计实现厘米级 3D 定位。可作 §1.2.2「三相抵消导致漏磁弱」的工业实证（A4/A7）。
- **状态**：已检索
- **备注**：A6 若需经典电磁学教材出处（Biot-Savart 定律本身），可补 Griffiths D J. *Introduction to Electrodynamics*[M]. 4th ed. Cambridge University Press, 2017（§5.2.2 Biot-Savart），或 Jackson J D. *Classical Electrodynamics*[M]. 3rd ed. Wiley, 1998。

## D4 · 磁反演电缆定位与埋深估计（引用点 A12，用于 §3.3.3 反演精度）
- **题录（深度学习端到端反演）**：Liu Y, Wu Y, Li G, et al. Submarine cable detection using an end-to-end neural network-based magnetic data inversion[J]. Journal of Geophysics and Engineering, 2024, 21(3): 884-896.
- **DOI**：10.1093/jge/gxae045
- **摘要要点**：针对传统磁异常反演（场分离/去噪/Euler 反卷积）参数需手调、易产生伪解的问题，提出端到端深度学习方法直接从原始磁场数据映射到电缆位置，合成实验定位精度优于传统 Euler 法，采用聚类+最大置信度选优避免伪解。**支撑 §3.3.3 磁反演/埋深估计（A12）的现代方法对照。**（开放获取，Oxford UP）
- **链接**：https://doi.org/10.1093/jge/gxae045
- **补充文献（磁偶极子微元 + APSO 反演，含精度数字）**：Submarine cable routing location based on weak magnetic detection and APSO inversion algorithm —— 建立空间磁偶极子微元模型 + 自适应粒子群反演，1 m 处路由反演误差 5.51%，1.5 m 处埋深定位误差 9.7%。可作 A12 反演精度的量化对照（需进一步核实完整题录与 DOI）。
- **状态**：已检索

## D5 · 磁强计九参数（硬/软铁）椭球标定（引用点 A9，用于 §2.4.2 在线标定）
- **题录**：Cui X, Li Y, Wang Q, Zhang M. Three-axis magnetometer calibration based on optimal ellipsoidal fitting under constraint condition[C]//2018 IEEE/ION Position, Location and Navigation Symposium (PLANS). IEEE, 2018: 1017-1024.
- **DOI**：10.1109/PLANS.2018.8373378
- **摘要要点**：建立磁干扰的椭球模型（硬铁偏置向量 V + 软铁 3×3 矩阵 A，共 9 参数），以带约束的最优椭球拟合（最小二乘）求解标定参数并补偿，将测量椭球还原为球面以提升航向精度。**直接对应 §2.4.2「九参数在线标定（硬软铁）」的方法出处（A9）。**
- **链接**：https://doi.org/10.1109/PLANS.2018.8373378
- **补充文献（经典强基线，可选）**：Vasconcelos J F, Elkaim G, Silvestre C, Oliveira P, Cardeira B. Geometric approach to strapdown magnetometer calibration in sensor frame[J]. IEEE Transactions on Aerospace and Electronic Systems, 2011, 47(2): 1293-1306. DOI 10.1109/TAES.2011.5751259 —— 椭球拟合磁标定领域高被引经典，可作 A9 的权威奠基出处（需二次确认题录）。
- **状态**：已检索

---

## 待补 / 待用户确认
- D2（DL/T 1278）：标准号年份、0.05 nT/0.2 m 指标来源需核对本仓库标准原文与正文 A5。
- A7（铠装涡流屏蔽因子 / 螺旋绞合几何数值仿真）：目前 D3 的三芯磁场模型部分覆盖；如需专门的「金属护套涡流屏蔽衰减」定量文献，可再检索一轮（keyword: submarine cable armor eddy-current shielding attenuation）。
