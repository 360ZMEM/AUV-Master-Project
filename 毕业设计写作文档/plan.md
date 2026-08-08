# plan.md — 代码到实物 AUV 部署的功能缺口计划

> 目的：梳理「当前代码（Jetson 主线仿真闭环）→ 部署到真实 AUV」尚未闭合的功能缺口，供写作（第二/五章 Sim-to-Real）与后续实物支线共用。
> 数据源：`docs/real_deployment/`（五阶段路线图）、`docs/JETSON_DEPLOYMENT_CONTEXT.md`（§2.5/§9/§10）。
> 最后更新：2026-08-06（初次建立）。
> 铁律（本仓固化，`docs/real_deployment/00_principles.md` / INDEX `#L95-L99`）：
> 1. **完全向后兼容**：新增脚本/工具/文档不动主线 launch/yaml/start_*.sh，仅正交新增。
> 2. **静态验证优先**：每脚本支持 `--dry-run`；提交前全 mock dry-run。
> 3. **mock AMD 默认**：`--target` 默认 `mock`；`real` 必须加 `--i-have-physical-auv`。

---

## 0. 现状定位（已闭合的能力）

**已具备**（`JETSON_DEPLOYMENT_CONTEXT` §1-§2）：
- PVS + `protocol_udp` 数字孪生电缆巡检闭环，Jetson Orin NX 16GB / 25W / 8 核可跑 60s smoke（bag 59.4s，magnetic/tracking/setpoint 三类 topic 非零）。
- 证据链：仿真 → 桥接 → ROS2 brain → cable_tracking_node（调 AUV-Master-Mag）→ 受仲裁器保护的 setpoint → rosbag → JSONL/CSV/MD/PNG → DL/T1278 风格评分与多 run 聚合。
- distorted-prior 闭环恢复（mid/heavy 各 3/3 ready/pass），但**默认关闭**、限定于数字孪生磁观测前提。
- 五阶段部署脚手架已就位：`scripts/real_deployment/{00_static_preflight..05_full_autonomy}.sh` + `kill_switch.sh`，支持 `mock/vxsim/real` 三 target。

**关键迁移设计**：`protocol_udp` 已是最高优先级后端 —— 未来仅需把 PC104 换一个 IP，即可仿真/实物共享同一套代码（计划书 `#L13`）。

---

## 1. 功能缺口清单（按五阶段梯度）

| 阶段 | 目标 | 已就绪 | **待闭合缺口** | 阻塞级别 |
|---|---|---|---|---|
| **S0 静态自检** | build+pytest+协议自检（无硬件） | 脚本+dry-run | — | ✅ 可跑 |
| **S1 通信审计** | `$AUV` 145B 上行字节序/scale/p95；`$CKTH` 72B 下行 0xEF 握手 | 脚本 + 协议文档 | 真机字节序/scale **实测标定**未做；p95 时延真机数据缺 | 🟡 需真机 |
| **S2 静态执行器自检** | 5 路通道极性 + 死区，回填 `physics_config.yaml` | 脚本 | 真实舵机/推进器极性、死区**未实测**；SMCL 舵机参数待回填 | 🟡 需真机上架 |
| **S3 影子导航** | `passive_mode:=true` 人驾，Jetson 算不发，RMSE 阈值 | 脚本 | 真机传感器（DVL/罗盘/磁）**入水实测**缺；RMSE 阈值待真实海况标定 | 🔴 需入水 |
| **S4 单回路闭环** | 恒定 setpoint，超调/稳态误差/响应时间 | 脚本 | Jetson 接管后**真实执行器闭环响应**未验证；控制参数 sim→real 迁移未定 | 🔴 需入水 |
| **S5 全自主巡检** | 行为树释放 + ros2 bag + DL/T1278 剖面 | 脚本 | 真实海缆环境**端到端未跑**；背景磁场去除、真实检测噪声未验证 | 🔴 需真实海缆 |

---

## 2. 未闭合的技术责任边界（`JETSON_DEPLOYMENT_CONTEXT` §9）

1. **Jetson CPU 余量偏紧**：正式 benchmark 需关闭桌面可视化，或拆分仿真/brain/可视化到不同机器。→ 写作需诚实标注资源边界（非无限余量）。
2. **cleanup 脚本 `BRIDGE_PID: unbound variable`**：健壮性缺陷，不阻塞 bag，但需修（§10 短期建议 1）。
3. **真实海缆环境证据缺失**：背景场去除、检测噪声、多种子统计、硬件实物证据 **尚未替代数字孪生证据**。← 这是 Sim-to-Real 的核心缺口。
4. **在线先验修正（distorted-prior）不能默认迁移真机**：依赖磁观测前提成立 + 传感器外参标定 + 去地磁背景 + bag 证明。
5. **HoloOcean 3D 未安装**：当前不作为 Jetson 可运行结论；写作涉及 HoloOcean 处必须标注可复现边界。

---

## 3. 严格边界（在线电缆 tracking 禁止消费，`§7`）

写作/实验都不得让在线链路消费以下真值（否则实验失效、违反奥卡姆正交原则）：
- `ground_truth.cable_closest_ned`、`ground_truth.cable_distance_m`
- 任何 `evaluation_*` 或仅仿真器可见的真值电缆状态
- 真机上的 `sensor_extrinsics_truth.*`
- 用高频广播原始传感器相对位置替代部署标定配置

---

## 4. 全链路测试分层（推进顺序，禁止跳级）

| 层 | 目标 | 入口 | 当前状态 |
|---|---|---|---|
| L0 静态 | 语法/导入/单测 | `pytest tests/test_cable_prior_adapter.py …` | ✅ |
| L1 轻量集成 | 上位机-Jetson-AMD 静态联调 | `scripts/run_integration_test.sh` | ✅ |
| L2 单 run 仿真 | PVS/protocol_udp 出 bag | `scripts/start_experiment.sh … --bag-profile cable_acceptance` | ✅ |
| L3 离线报告 | bag→JSONL/CSV/MD/PNG | `extract_cable_tracking_jsonl.py` + `dlt1278_cable_report.py` | ✅ |
| L4 多 run 统计 | ≥3 run 聚合 pass ratio | `tools/aggregate_cable_acceptance_runs.py` | ✅ |
| L5 扭曲先验恢复 | mid/heavy distorted 闭环 | `run_cable_closedloop_distorted.sh` + 打分 | ✅（数字孪生内） |
| **L6 真机准入** | 标定/IO 契约/急停/bag 证明 | `docs/real_deployment/08_cable_inspection_io_contract.md` | 🔴 **未完成** |

**结论**：L0–L5 已在数字孪生内闭合；**唯一的实质缺口是 L6（真机准入）**，其前置是 S1–S2 的真机标定与 S3 影子导航实测。

---

## 5. 对论文写作的映射（本对话关注）

- **第二章 2.2.3 仿真后端与实物层对比**：写清 PVS↔protocol_udp↔PC104-换IP 的迁移设计（本 plan §0）。
- **第五章 5.5.9 Sim-to-Real 迁移性讨论**：诚实呈现 §2 责任边界 + §4 的 L6 缺口，这本身就是高质量的工程讨论（负结果/边界即创新点的一部分）。
- **rating.md**：§2.3（真实海缆证据缺失）与 §3（禁止消费真值）需登记为「不可越界的约束」。

---

## 6. 标准依据（写作引用）
- `标准文档/自主式水下航行器设计方案2021.5.28.md` — AUV 物理 spec
- `标准文档/软件通信协议.md` — `$CKTH` 72B 下行 / `$AUV` 145B 上行
- `标准文档/VxWorks最新协议.md` — PC104 端解析约束
- DL/T 1278—2025（`标准文档/` 及 `相关附件和参照/相关国家标准和行业论文/` PDF）— 巡检任务工程依据

> 注：INDEX 中相对路径指向 `标准文档/`（仓库根同名目录）；`相关附件和参照/` 内亦有对应 PDF 副本，写作时以能读取的文本层版本为准。
