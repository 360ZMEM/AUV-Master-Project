# 决策与控制类文献候选（对应引用点 B1/B2/B4/B5/B6/B7/B10, A14）

> 每条含：题录 + 摘要要点 + 链接 + DOI + 对应引用点 + 状态。
> 状态：`已检索` = 有摘要+链接可供人工下载；`待补` = 尚未检索到权威条目。

---

## C1 · 行为树 vs FSM（引用点 B6，用于 §1.3.2 / §4.2）
- **题录**：Colledanchise M, Ögren P. *Behavior Trees in Robotics and AI: An Introduction*[M]. Boca Raton: CRC Press, 2018.
- **DOI**：10.1201/9780429489105 ；ISBN 978-1-138-59373-2 / eBook 9780429489105
- **摘要要点**：系统性论述行为树（BT）如何取代有限状态机（FSM）以获得模块化、可复用、可组合的机器人行为结构；FSM 随复杂度上升产生脆弱行为、难以在不破坏已有功能的前提下扩展；BT 用层级树结构组织切换逻辑，天然支持任务分层、Sequence/Fallback、reactive 抢占。**直接支撑本文"BT 相对 FSM 在故障可组合/应急可插入上的根本优势"论断。**
- **链接**：https://www.taylorfrancis.com/books/mono/10.1201/9780429489105 （另有开放预印本 arXiv:1709.00084 可先行阅读）
- **状态**：已检索
- **备注**：另有综述文章可补充 — Iovino M, Scukins E, Styrud J, Ögren P, Smith C. *A survey of behavior trees in robotics and AI*[J]. Robotics and Autonomous Systems, 2022（arXiv:2005.05842）。若需期刊而非专著出处可用此篇。

## C2 · MPC 稳定性与最优性综述（引用点 B4，用于 §1.3.1 / §4.4）
- **题录**：Mayne D Q, Rawlings J B, Rao C V, Scokaert P O M. Constrained model predictive control: Stability and optimality[J]. Automatica, 2000, 36(6): 789-814.
- **DOI**：10.1016/S0005-1098(99)00214-9
- **摘要要点**：MPC 领域被引 8000+ 的奠基综述，聚焦约束系统（线性/非线性）的模型预测控制，提炼保证闭环稳定性的核心原理（终端约束/终端代价/终端集），系统刻画已提出的大多数 MPC 方案。**支撑本文对 MPC"预测时域+在线约束优化"定位的权威出处。**
- **链接**：https://doi.org/10.1016/S0005-1098(99)00214-9 （开放 PDF：control.disp.uniroma2.it/galeani/CO/materiale/automatica2000.pdf）
- **状态**：已检索

## C3 · CasADi 非线性优化框架（引用点 B5，用于 §4.4.6 求解器实现）
- **题录**：Andersson J A E, Gillis J, Horn G, Rawlings J B, Diehl M. CasADi — A software framework for nonlinear optimization and optimal control[J]. Mathematical Programming Computation, 2019, 11(1): 1-36.
- **DOI**：10.1007/s12532-018-0139-4
- **摘要要点**：开源数值优化框架，专长于微分方程约束的最优控制问题（OCP→NLP 转写），自带算法微分（AD）得到雅可比稀疏结构，Python/MATLAB 接口。**本文 MPC 用 CasADi Opti 建模、符号微分的直接工具出处。**
- **链接**：https://doi.org/10.1007/s12532-018-0139-4
- **状态**：已检索

## C4 · IPOPT 内点法求解器（引用点 B5，用于 §4.4.6 求解器后端）
- **题录**：Wächter A, Biegler L T. On the implementation of an interior-point filter line-search algorithm for large-scale nonlinear programming[J]. Mathematical Programming, 2006, 106(1): 25-57.
- **DOI**：10.1007/s10107-004-0559-y
- **摘要要点**：IPOPT 求解器的实现论文，原-对偶内点法 + filter line-search，面向大规模非线性规划。**本文 MPC NLP 后端求解器（IPOPT）的权威出处。**
- **链接**：https://doi.org/10.1007/s10107-004-0559-y
- **状态**：已检索

## C5 · Fossen 船舶/水下动力学与运动控制教材（引用点 B1，用于 §2.2.3 / §4.1.1 / §4.4.1）
- **题录**：Fossen T I. *Handbook of Marine Craft Hydrodynamics and Motion Control*[M]. Chichester, UK: John Wiley & Sons, 2011.
- **DOI**：10.1002/9781119994138 ；ISBN 978-1-119-99149-6（1st ed, 2011）
- **摘要要点**：海洋载具（船舶/水下机器人）6-DOF 刚体动力学与运动控制的权威教材，系统给出 SNAME 记号下的运动学/动力学方程、附加质量与水动力阻尼、恢复力矩、以及制导-导航-控制（GNC）框架。**本文 AUV 6-DOF 动力学建模、体坐标系/地理坐标系变换、以及控制器设计记号的基础出处。**
- **链接**：https://doi.org/10.1002/9781119994138
- **状态**：已检索
- **备注**：另有第 2 版 Fossen T I. *Handbook of Marine Craft Hydrodynamics and Motion Control*[M]. 2nd ed. Wiley, 2021, ISBN 978-1-119-57505-4，内容更新（含更完整的制导与容错控制章节）。若需最新版可引第 2 版。

## C6 · REMUS 100 型 AUV 平台（引用点 B2，用于 §4.1.1 平台布局对标）
- **题录**：Purcell M, von Alt C, Allen B, Austin T, Forrester N, Goldsborough R, Stokey R. New capabilities of the REMUS autonomous underwater vehicle[C]//OCEANS 2000 MTS/IEEE Conference and Exhibition. Providence, RI: IEEE, 2000, 1: 147-151.
- **DOI**：10.1109/OCEANS.2000.881247
- **摘要要点**：WHOI 研制的 REMUS（Remote Environmental Monitoring UnitS）小型 AUV 平台论文，给出典型尺度（直径约 19 cm、长约 160 cm）、续航（约 22 h）、作业水深（约 100 m）及模块化载荷能力。**本文 AUV 平台尺度/续航/作业深度对标的经典出处，用于说明近底巡检型 AUV 的可行工程包络。**
- **链接**：https://doi.org/10.1109/OCEANS.2000.881247
- **状态**：已检索

## C7 · LOS 视线制导路径跟踪（引用点 B7，用于 §4.4.4 / §4.1.1 制导律）
- **题录（主）**：Breivik M, Fossen T I. Principles of guidance-based path following in 2D and 3D[C]//Proceedings of the 44th IEEE Conference on Decision and Control (CDC). Seville: IEEE, 2005: 627-634.
- **DOI**：10.1109/CDC.2005.1582226
- **摘要要点**：系统化提出基于制导（guidance-based）的路径跟踪原理，把视线（Line-of-Sight, LOS）制导律统一到 2D/3D 框架，给出前视距离（lookahead）与横向偏差的几何关系。**本文平面/三维路径制导（LOS）的核心方法出处。**
- **链接**：https://doi.org/10.1109/CDC.2005.1582226
- **补充文献 1**：Fossen T I, Pettersen K Y, Galeazzi R. Line-of-sight path following for Dubins paths with adaptive sideslip compensation of drift forces[J]. IEEE Transactions on Control Systems Technology, 2015, 23(2): 820-827. DOI 10.1109/TCST.2014.2338354 —— 含侧滑角自适应补偿，适合有流场扰动的 AUV 制导。
- **补充文献 2**：Fossen T I, Pettersen K Y. On uniform semiglobal exponential stability (USGES) of proportional line-of-sight guidance laws[J]. Automatica, 2014, 50(11): 2912-2917. DOI 10.1016/j.automatica.2014.10.018 —— LOS 制导律的稳定性理论证明。
- **状态**：已检索

## C8 · robust / uncertainty-aware MPC（引用点 B10，用于 §3.4.2 / §4.4.3 UA-MPC 理论基础）
- **题录**：Mayne D Q, Seron M M, Raković S V. Robust model predictive control of constrained linear systems with bounded disturbances[J]. Automatica, 2005, 41(2): 219-224.
- **DOI**：10.1016/j.automatica.2004.08.019
- **摘要要点**：tube-based robust MPC 的奠基论文，针对带有界扰动的约束线性系统，用标称轨迹 + 不变管（tube）保证在扰动下仍满足约束与稳定性。**本文"不确定性感知控制 / UA-MPC 在扰动下保持约束可行"论断的经典 robust MPC 理论出处。**
- **链接**：https://doi.org/10.1016/j.automatica.2004.08.019
- **状态**：已检索
- **备注**：如需 stochastic/chance-constrained 视角，可补 Mesbah A. Stochastic model predictive control: An overview and perspectives for future research[J]. IEEE Control Systems Magazine, 2016, 36(6): 30-44, DOI 10.1109/MCS.2016.2602087。

## C9 · 之字形 / lawnmower 覆盖路径规划（引用点 A14，用于 §4.3.1 扫描间距/覆盖率）
- **题录（经典分解法）**：Choset H, Pignon P. Coverage path planning: The boustrophedon cellular decomposition[C]//Field and Service Robotics. London: Springer, 1998: 203-209.
- **DOI**：10.1007/978-1-4471-1273-0_32
- **摘要要点**：提出 boustrophedon（"牛耕式"，即之字形/弓字形）单元分解法——将自由空间分解为可用简单往复扫描完全覆盖的单元，用扫描线（sweep line）宽度决定相邻航迹间距，是覆盖路径规划（CPP）领域最经典的完整性覆盖算法。**本文近底巡检"之字形/割草机式覆盖 + 扫描间距"策略的方法出处。**
- **链接**：https://doi.org/10.1007/978-1-4471-1273-0_32
- **补充文献 1（综述）**：Choset H. Coverage for robotics — A survey of recent results[J]. Annals of Mathematics and Artificial Intelligence, 2001, 31(1-4): 113-126. DOI 10.1023/A:1016639210559 —— CPP 领域权威综述，可作 A14 覆盖策略分类的总括出处。
- **补充文献 2（AUV 专用，最贴合）**：Yordanova V, Gips B. Coverage path planning with track spacing adaptation for autonomous underwater vehicles[J]. IEEE Robotics and Automation Letters, 2020, 5(3): 4774-4781. DOI 10.1109/LRA.2020.3003886 —— **直接针对 AUV 用侧扫声呐扫海底的航迹间距（track spacing）自适应**，含 nadir gap、传感器 swath 与覆盖率关系，最贴合本文 §4.3.1「扫描间距公式/覆盖率」。arXiv:2006.12896 可先行阅读。
- **状态**：已检索

---

## 本主题（40_control）检索完成
C1–C9 全部为「已检索」（含摘要+链接+DOI），对应引用点 B1/B2/B4/B5/B6/B7/B10 + A14 已覆盖。下一步交由用户人工登录院校认证下载 PDF → 放 `../文献PDF/`。
