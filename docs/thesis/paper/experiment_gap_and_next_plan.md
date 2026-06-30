# 实验缺口矩阵与下一步计划

## 概述

本文档按论文充分性而不是最低答辩要求判断当前实验是否足够。结论是：当前材料已经能支撑系统架构、近底 terrain-following 主结果、MPC 深度回退理由和复杂路径制导支线，但还不足以支撑完整的"高不确定性海缆巡检 AUV"论文闭环。主要缺口集中在多种子统计、UA-MPC 主消融、电缆巡检真实性场景和硬件实测。

## 章节证据覆盖矩阵

### 第 1 章：背景与意义

| 章节 | 当前证据 | 主要缺口 | 补充方式 | 优先级 |
|---|---|---|---|---|
| 1.1–1.3 背景与现状 | 仓库内主要是工程证据 | 海风损失、DL/T 标准、ROV/AUV 对比需要正式引用 | 补文献和行业报告，不跑代码 | P0 |
| 1.4 创新点 | 系统架构、terrain、MPC 支线、不确定性接口 | 创新表述需避免超出现有结果 | 在 paper 层统一收敛措辞 | P0 |

### 第 2 章：系统设计

| 章节 | 当前证据 | 主要缺口 | 补充方式 | 优先级 |
|---|---|---|---|---|
| 2.1 标准对齐 | 有指标意图，缺正式摘录 | 0.05 nT、0.2 m 埋深误差来源需确认 | 补标准引用和传感器手册 | P0 |
| 2.2 双脑架构 | `docs/internals/`、`docs/real_deployment/` 完整 | 需要转成论文段落和图注 | 使用现有架构图和协议文档 | P0 |
| 2.3 磁场模型 | 有建模方向 | 三相交流、屏蔽、螺旋漏磁推导不足 | 补理论推导和实验台验证 | P2 |
| 2.4 声呐与标定 | 有接口概念 | 侧扫几何、lever-arm 标定结果不足 | 先写模型，后补标定实验 | P2 |
| 2.5 通信与隔离 | UDP 协议、ESTOP、±15V 隔离 | 7 处协议偏差详情需整理 | 整理偏差表写入论文 | P1 |

### 第 3 章：状态估计

| 章节 | 当前证据 | 主要缺口 | 补充方式 | 优先级 |
|---|---|---|---|---|
| 3.2 时空同步 | Mock AMD 多速率采样 | 高精度时间同步（PTP） | 现场数据补充 | P2 |
| 3.3 ES-EKF 声磁协同 | baseline n=1 单次对比 | DVL/mag/sonar/combined 多 seed 缺失 | 跑 `run_thesis_sweep.py` 聚合 | P1 |
| 3.4 不确定性量化 | NIS/自适应 R 接口 | NIS 触发率、自适应 R 触发率 | 聚合统计 + 曲线 | P1 |
| 3.5 仿真验证 | baseline 单次可用 | 多场景多种子鲁棒性曲线 | 3–5 seed × 4 场景 | P1 |

### 第 4 章：决策与控制

| 章节 | 当前证据 | 主要缺口 | 补充方式 | 优先级 |
|---|---|---|---|---|
| 4.2 行为树 | BT vs FSM n=1 | 多场景 BT 节点覆盖率 | 增加场景对比 | P2 |
| 4.3 轨迹生成 | 之字形 + 电缆跟踪设计 | 扫描间距计算、覆盖率表 | 补公式和统计表 | P2 |
| 4.4 UA-MPC | 接口已实现 | baseline-MPC vs UA-MPC 主消融 | 3 场景 × 3–5 seed | P1 |
| 4.5 控制鲁棒性 | terrain、MPC x/y/yaw | 极端安全边界、控制平滑度 | 补对比表 | P1 |

### 第 5 章：实验与讨论

| 章节 | 当前证据 | 主要缺口 | 补充方式 | 优先级 |
|---|---|---|---|---|
| 5.2 数字孪生 | 9 个 PVS chaos + terrain | 与真实电缆巡检差距明显 | 设计电缆几何与近底横流场景 | P1 |
| 5.3 硬件集成 | SOP 多，实测少 | Jetson-AMD、转台、故障注入结果不足 | 北京现场或实验室补测 | P3 |
| 5.4 电缆实验台 | 当前证据不足 | 10A 电缆台、HSF-500、埋深反演缺失 | 搭台并记录误差表 | P3 |
| 5.5 Sim-to-Real | emulated Jetson 文档 | 真机算力和真实网络延迟缺失 | Jetson 真机重跑 CPU/MEM/IPOPT | P2 |

## 补实验优先级

### P0：文档充分性与证据边界

不跑新实验也必须完成的工作。包括证据边界确认、章节映射、指标解释和"不宜声称"清单。当前 `docs/thesis/paper/` 目录就是 P0 的主要产物。

| 任务 | 状态 | 说明 |
|---|---|---|
| 统一 n=1 标注 | 已完成 | 所有表格已标注 n=1 或 smoke |
| 统一"不宜声称"清单 | 已完成 | paper/INDEX.md 中已列出 |
| 补协议 7 处偏差表 | 待补 | 需整理到 2.5 节 |
| 补 DL/T 1278-2025 引用 | 待补 | TODO: cite |
| baseline/ua 3 seed smoke-to-stat | 已完成 | `log/thesis_sweep/20260612_163001_c2_baseline_3seed/results.csv`，聚合见 `results/thesis_sweep_aggregates/20260612_163001_c2_baseline_3seed/` |

### P1：多种子统计与主消融

最能提高论文可信度的软件实验：

| 实验 | 场景 | 算法 | seeds | 主指标 | 优先级 |
|---|---|---|---:|---|---|
| Baseline 重复统计 | baseline | ES-EKF / UA mode | 3 | XY RMSE, Z RMSE, CEP50 | 已完成第一轮 |
| Terrain 低成本复验 | low/mid/high | PID terrain | 1/档 | clearance RMSE, min, violation | 已完成第一轮 |
| Terrain 重复统计 | low/mid/high | PID terrain | 3–5/档 | clearance RMSE, min, violation | 最高 |
| DVL dropout sweep | 10/30/60/90% | ES-EKF / UA mode | 3/档 | XY RMSE, Z RMSE, CEP50 | 已完成第一轮 |
| Mag/Sonar/Combined sweep | light/heavy/sonar/combined | ES-EKF / UA mode | 3/场景 | XY RMSE, Z RMSE, CEP50 | 已完成第一轮 |
| UA-MPC 主消融初版 | baseline + dvl_60 + combined | baseline-MPC / UA-MPC | 3/场景/模式 | XY RMSE, Z RMSE, CEP50 | 已完成第一轮 |
| UA-MPC 控制侧消融 | baseline + dvl_60 + combined | baseline-MPC / UA-MPC | 3–5 | lateral RMSE, fallback rate, control effort | 待补 |

### P2：模型与系统迁移

| 实验 | 说明 | 优先级 |
|---|---|---|
| NIS/R 自适应触发率聚合 | baseline + chaos 场景的 NIS 曲线和触发统计 | 中 |
| UA-MPC 参数灵敏度 | `low_conf_scale`、`sigma_xy_ref`、控制惩罚权重 | 中 |
| Jetson 真机算力 | 重跑 CPU/MEM/IPOPT 求解时间 | 中 |
| 磁场理论推导 | 三相交流、屏蔽因子、螺旋漏磁公式 | 中 |
| 声呐几何标定 | 侧扫斜距公式、多径影响分析 | 中 |

### P3：硬件和实验室电缆台

依赖现场条件，若短期无法完成，应写成实验方案和未来工作：

| 实验 | 说明 | 验收标准 |
|---|---|---|
| Jetson-AMD UDP 时延 | p50/p95/p99、丢包率、序列号跳变 | p50 < 5 ms, p99 < 50 ms |
| 转台九参数磁标定 | 消除硬磁/软铁干扰 | 标定后残差 < 0.05 nT |
| 故障注入闭环 | 断网、低压、模拟漏水 | 响应时间 < 1 s |
| 10A 电缆实验台 | 模拟电缆磁场反演 | 埋深误差 < 0.2 m |
| HSF-500 埋深反演 | 不同掩埋深度下的反演精度 | 误差统计 mean±std |

## 建议新增消融

### UA-MPC 主消融

UA-MPC 主消融应至少包含 baseline-MPC 与 UA-MPC 在 baseline、`dvl_dropout_60` 和 `combined_stress` 下的对比，每个场景 3 seed 起步，理想为 5 seed。指标包括 lateral RMSE、heading RMSE、solve time、fallback rate、控制量变化率和安全违规率。

### 不确定性映射消融

比较 hard switch 与 sigmoid 权重、不同 `low_conf_scale`、不同 `sigma_xy_ref` 和不同控制惩罚权重。该实验不需要覆盖所有场景，优先选择 baseline 与 `combined_stress`，以回答"不确定性权重是否真的改变控制行为"。

### 电缆巡检真实性消融

比较普通 PVS chaos、terrain-only、path-only 和 cable-extreme 四类场景。这样可以把"传感器噪声鲁棒性"、"近底安全性"、"复杂路径能力"和"海缆巡检真实性"区分开，避免把某一类实验过度解释成完整任务能力。

## 表格模板

以下为待补实验的表格模板，实际执行后填入数据：

| 实验 | 场景 | 控制/估计算法 | seeds | 主指标 | 当前状态 |
|---|---|---|---:|---|---|
| ES-EKF 鲁棒性 | baseline + DVL/mag/sonar/combined | ES-EKF / Std-EKF / Raw DR | 3–5 | XY RMSE, Z RMSE, NIS | 待补 |
| UA-MPC 主消融 | baseline + dvl_dropout_60 + combined_stress | baseline-MPC / UA-MPC | 3–5 | lateral RMSE, fallback rate | 待补 |
| Terrain 重复统计 | low/mid/high | PID terrain | 3–5 | clearance RMSE, min, violation | 待补 |
| 电缆极端场景 | S curve / hairpin / buried gap | PID/LOS/MPC/UA-MPC | 3–5 | cable offset RMSE, route completion | 待设计 |
| 硬件链路 | Jetson-AMD | UDP binary protocol | 3–5 | latency p50/p95, packet loss | 待现场 |
| 电缆台 | 10A + HSF-500 | 声磁反演 | 3–5 | buried-depth error | 待实验 |
| 协议偏差 | 7 处偏差 | — | — | 描述、来源、修复 | 待整理 |

## 当前可执行下一步

如果只能补一轮软件实验，建议优先执行 P1 中的 baseline 重复统计和 terrain PID low/mid/high 重复统计。这两组实验成本最低、对论文充分性提升最大。若时间允许，再补 DVL dropout 4 场景 sweep 和 baseline-MPC vs UA-MPC 的三场景对比。硬件实验可以先写清方案、指标和验收标准，等现场条件具备后补数据。
