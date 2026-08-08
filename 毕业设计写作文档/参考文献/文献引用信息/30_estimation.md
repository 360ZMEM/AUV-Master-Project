# 状态估计类文献候选（对应引用点 B3 / B8 / B9 / A11 / A13；部分 A10）

> 每条含：题录 + 摘要要点 + 链接 + DOI + 对应引用点 + 状态。
> 状态：`已检索` = 有摘要+链接可供人工下载；`待补` = 尚未检索到权威条目。
> 覆盖引用点：B3(ES-EKF/Sola)、B8(多源融合)、B9(DVL/INS)、A11(误差状态推导)、A13(NIS 卡方一致性/自适应 R)、A10(50Hz 工频陷波)。

---

## E1 · ES-EKF 误差状态卡尔曼滤波（引用点 B3 / A11，用于 §3.1.1 / §3.3.1）
- **题录**：Solà J. Quaternion kinematics for the error-state Kalman filter[R/OL]. arXiv:1711.02508, 2017.
- **DOI**：10.48550/arXiv.1711.02508
- **摘要要点**：ESKF 领域引用极高的权威技术报告，系统推导四元数运动学、SO(3) 李群结构、旋转扰动/导数/积分，并给出用于 IMU 积分的误差状态卡尔曼滤波精确公式（名义状态非线性积分 + 误差状态线性化 + 误差注入 + reset）。**核心优势：姿态误差用 3 维旋转向量 δθ 表示（最小参数化），避免四元数过参数化奇异，且误差在零点附近线性化精度高。直接支撑 §3.1.1「ES-EKF 相对标准 EKF 的姿态奇异优势」（B3）与 §3.3.1 误差状态转移方程推导（A11）。**（开放获取）
- **链接**：https://arxiv.org/abs/1711.02508
- **状态**：已检索
- **备注**：GB/T 7714 中 arXiv 预印本可著录为「[R/OL]. arXiv:1711.02508」或作为技术报告 [R]。若答辩需正式出版物，ESKF 的经典期刊出处可用 Madyastha V, Ravindra V, Mallikarjunan S, Goyal A. Extended Kalman filter vs. error state Kalman filter for aircraft attitude estimation[C]//AIAA GNC. 2011. DOI 10.2514/6.2011-6615。

## E2 · DVL 辅助惯性组合导航（引用点 B9，用于 §3.2.1）
- **题录（经典，最贴合工程）**：Hegrenæs Ø, Berglund E. Doppler water-track aided inertial navigation for autonomous underwater vehicles[C]//OCEANS 2009 IEEE-Bremen. Bremen: IEEE, 2009: 1-10.
- **DOI**：10.1109/OCEANSE.2009.5278307
- **摘要要点**：Kongsberg HUGIN 1000 AUV 实测评估的 DVL 水跟踪（water-track）辅助 INS 系统，含实时海流估计，可在 USBL/DVL 底跟踪缺失或传感器 dropout/故障时维持导航精度与鲁棒性。**本文 DVL/INS 组合导航（B9）的经典工程出处，与本文「DVL 丢底导致运动估计退化」直接对应。**
- **链接**：https://doi.org/10.1109/OCEANSE.2009.5278307
- **补充文献 1（中文，含卡方检验隔断野值，兼顾 B9 + A13）**：章彩霞, 刘锡祥, 黄永江, 等. 基于紧组合的 SINS/DVL/USBL 导航算法[J]. 水下无人系统学报, 2023, 31(6): 847-855. DOI 10.11993/j.issn.2096-3920.2022-0076 —— **用卡方检验判断 DVL/USBL 数据野值并隔断、实时更新量测方程维数**，DVL 失效时定位误差仅增 5.2%。同时支撑 B9 与 A13（NIS/卡方一致性）。
- **补充文献 2（DVL 中断的协方差传播，兼顾 B9 + UA 主题）**：Huang J, Liu Z, Li H, et al. A DVL aided loosely coupled inertial navigation strategy for AUVs with attitude error modeling and variance propagation[R/OL]. arXiv:2601.19509, 2026 —— 姿态误差感知的 DVL 速度变换 + 基于协方差的方差传播，3D 位置 RMSE 改善 78.3%。与本文「不确定性/协方差流转」主题高度契合。
- **状态**：已检索

## E3 · NIS 卡方一致性检验与自适应 R（引用点 A13，用于 §3.4.1）
- **题录（经典奠基）**：Bar-Shalom Y, Li X R, Kirubarajan T. *Estimation with Applications to Tracking and Navigation*[M]. New York: John Wiley & Sons, 2001.
- **DOI**：10.1002/0471221279
- **摘要要点**：跟踪与导航估计领域的权威教材，提出并系统化归一化新息平方（NIS）与 NEES 一致性检验——在滤波模型正确假设下 NIS 服从卡方分布，可在线判断滤波器噪声假设是否与实测一致（据此检测 filter inconsistency / divergence）。**本文 §3.4.1「NIS 阈值带 / 自适应 R」的方法奠基出处（A13）。**
- **链接**：https://doi.org/10.1002/0471221279
- **补充文献 1（在线 NIS 检验专论，开放获取）**：Piché R. Online tests of Kalman filter consistency[J]. International Journal of Adaptive Control and Signal Processing, 2016, 30(1): 115-124. DOI 10.1002/acs.2571（预印本 2014）—— 证明 NIS 检验等价于多种模型批判过程，可在线应用、不需真值。适合作 §3.4.1 NIS 阈值/卡方带的直接引用。
- **补充文献 2（NIS 自动调参，现代）**：Chen Z, Biggie H, Ahmed N, et al. Kalman filter auto-tuning through enforcing chi-squared normalized error distributions with Bayesian optimization[C]. 2023（arXiv:2306.07225）—— 指出 NIS/NEES 仅在滤波器正确调参时才严格卡方分布，可作「自适应 R / 调参」讨论的补充。
- **状态**：已检索

## E4 · 多源传感器融合（水下导航）（引用点 B8，用于 §1.2.3 / §3.3.4）
- **题录**：Zhang Q, Tian Y, Ji D. Submarine cable inspection and marine robot applications: A literature review[J]. InUS Transactions, 2025, 1(1): 1-19.
- **DOI**：10.23380/inustrans.2025.1.1.1
- **摘要要点**：见 20_detection.md D1。综述专门梳理视觉/声学/磁/多传感器数据融合技术在海缆巡检中的进展与优劣，指出各单一模态的失效场景与融合互补必要性。**直接支撑 §1.2.3 / §3.3.4「多源传感器融合」（B8）。**（与 D1 同一文献，跨主题复用）
- **链接**：https://doi.org/10.23380/inustrans.2025.1.1.1
- **补充文献（自适应/鲁棒融合，含 NIS 思想）**：GNSS/SINS/DVL integrated navigation algorithm based on adaptive differential Kalman filtering（Semantic Scholar，2023-2024）—— 自适应差分卡尔曼滤波抑制污染量测噪声，提升组合导航鲁棒性。可作 B8 现代融合方法补充（需二次确认完整题录与 DOI）。
- **状态**：已检索

---

## 待补 / 待检索
- A10（§3.2.3 50 Hz 工频陷波滤波器设计 / 磁频谱）：正在补检索（keyword: 50Hz power-line notch filter design magnetometer / IIR notch）。经典出处可用数字信号处理教材（Oppenheim & Schafer《Discrete-Time Signal Processing》）中的 notch/comb 滤波器章节，或工频干扰抑制专论。
