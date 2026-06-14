# T1 — 实验体系总览（论文 §1.4 / §5.1 配套）

> **目的**：作为论文写作和复现实验的入口文档。把仓库内一切与"通过仿真验证控制算法 / ES-EKF 正确性 / Jetson 部署可用性"相关的资产（代码、scenario、命令、数据集）一一列清，并给出与论文章节、创新点的精确对照。
>
> **配套**：本板块其它 7 篇 thesis 文档（[INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/INDEX.md)）。

---

## 1. 实验体系全图

```
                                ┌────────────────────────────────────┐
                                │      Phase 4 thesis 文档族         │
                                │  T1 (本文) · T2 · T3 · T4 · T5 ·   │
                                │            T6 · T7 · T8            │
                                └─────────────┬──────────────────────┘
                                              │
              ┌───────────────────────────────┼────────────────────────────────┐
              │                               │                                │
   ┌──────────▼────────────┐   ┌──────────────▼───────────┐    ┌───────────────▼─────────────┐
   │   仿真后端（双轨）    │   │   ROS2 brain（决策/控制） │    │   离线分析与 sweep harness  │
   │   PVS（轻量 Python）   │   │   行为树 + UA-MPC + ES-EKF│    │   tools/*.py + scripts/*.sh │
   │   HoloOcean（UE4 高保真）│  │   /auv/state/covariance  │    │   多种子 / 参数 / 算力       │
   └──────────┬────────────┘   └──────────────┬───────────┘    └───────────────┬─────────────┘
              │                               │                                │
              └───────────────────────────────┴────────────────────────────────┘
                                              │
                              ┌───────────────▼────────────────┐
                              │  $AUV_DATA_ROOT/bags/<TS>/...  │
                              │  $AUV_DATA_ROOT/results/...    │
                              │  rosbag mcap + CSV + PNG + MD  │
                              └────────────────────────────────┘
```

---

## 2. 论文创新点 ↔ 代码 ↔ 数据集对照表

> 论文 §1.4 写有 N 个创新点；本节把每一个创新点逐项映射到代码文件、ROS topic / 环境变量、scenario 与数据集。**这一节是论文写作时直接抓素材的索引**。

### 创新点 1：声磁协同硬件冗余架构（§1.4 / §2.2）
- 仿真侧覆盖范围：本对话 scope 不直接覆盖（硬件电路属排除项）。
- 仿真侧间接论证：透过 §2.2 / §2.4 异步双脑通信延迟 + 杆臂改正模型在仿真侧已用 [auv_localization_node.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_localization/auv_localization/auv_localization_node.py) 时空同步逻辑跑通，相关数据见 [docs/experiment/experiment_modes_validation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/experiment_modes_validation.md)。

### 创新点 2：基于不确定性（Uncertainty-Aware）的自适应路径跟踪 MPC（§1.4 / §4.4）
| 子环节 | 代码位置 | 实验数据 |
|---|---|---|
| Sigmoid 平滑置信度 → 控制权重 | [auv_mpc_controller.py L159-260](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py#L159-L260) | T5（消融） |
| `(1-conf)^α` 跟踪权重放大 | [auv_mpc_controller.py L227-230](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py#L227-L230) | T5 |
| `mpc_mode={ua,baseline}` 消融开关 | [auv_mpc_controller.py L162-164 / L218 / L249](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py#L162-L164) | T5 |
| `AUV_MPC_MODE` env 注入 | [mpc_controller.py L115-118](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py#L115-L118) | T5 |
| EKF P 协方差 → 置信度耦合（**真正的"不确定性感知"闭环**） | [auv_controller_node.py 286-310](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py)（`_on_covariance` / `_confidence_from_cov`） | T4 |
| `cov_to_conf.{enable,sigma_xy_ref,sigma_z_ref}` ROS 参数 | 同上 | T4 |
| 参数敏感性 sweep（`AUV_MPC_PARAM_OVERRIDES`） | [mpc_controller.py L120-128](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py#L120-L128) + [run_thesis_sweep.py --param-grid](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py) | T7 |

### 创新点 3：感知不确定性的量化度量（§3.4）
| 子环节 | 代码位置 | 实验数据 |
|---|---|---|
| 基于 NIS 的滑动窗口 + 自适应 R | [es_ekf.py L138-145 / L376-415](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L138-L145) | T4 |
| `get_nis_stats()` 暴露统计 | [es_ekf.py L417](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L417) | T4 |
| 离线 NIS 导出 + 卡方阈值 | [tools/uncertainty_metrics.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/uncertainty_metrics.py) | T4 |

### 创新点 4：行业标准对齐的 scenario 库（§5.2）
| 子环节 | 代码位置 | 实验数据 |
|---|---|---|
| 9 个 scenario yaml | [scenarios/](file:///home/auv_user/auv_ws/AUV-Master-Project/scenarios) | T6 |
| sweep harness（笛卡尔积 scenario × seed × mode × param） | [tools/run_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py) | T3 / T5 / T7 |
| 三档 sweep 薄壳 | [run_dvl_sweep.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_dvl_sweep.sh) / [run_mag_sweep.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_mag_sweep.sh) / [run_combined_sweep.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_combined_sweep.sh) | T3 / T5 |

### 创新点 5：双脑算力对齐与仿真→实物迁移（§5.5）
| 子环节 | 代码位置 | 实验数据 |
|---|---|---|
| Jetson 仿真侧 CPU/MEM/IPOPT 时延采样 | [scripts/run_jetson_emulated_bench.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_jetson_emulated_bench.sh) | T7 |
| 参数敏感性方差分解 | `tools/run_thesis_sweep.py::write_sensitivity_summary` | T7 |

---

## 3. 命令索引（按论文章节）

> 全部命令的工作目录默认为 `/home/auv_user/auv_ws/AUV-Master-Project`。

### §3.5 / §5.1.2 — baseline 端到端
```bash
# 编译（只需首次或代码变动后）
source /opt/ros/humble/setup.bash
cd brain_linux && colcon build --cmake-clean-cache \
    --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3 -DPYTHON_EXECUTABLE=/usr/bin/python3
# 跑 120s 端到端
cd ../scripts && bash start_experiment.sh --sim-backend pvs --bridge-backend zenoh_json --duration 120
# ES-EKF 三路对比（替换 mcap 路径）
python3 tools/offline_ekf_benchmark.py \
    --input log/experiments/benchmark_120s/rosbag_mcap/rosbag_mcap_0.mcap \
    --output-dir results/localization/$(date +%Y%m%d) --verbose
```

### §3.5.1 / §3.5.2 / §3.6 — ES-EKF 鲁棒性
```bash
bash scripts/run_dvl_sweep.sh        # DVL 丢包 4 档 × 5 种子 × 2 mode
bash scripts/run_mag_sweep.sh        # 磁畸变 2 档 × 5 种子 × 2 mode
```

### §4.5 — UA-MPC 消融
```bash
bash scripts/run_combined_sweep.sh   # 综合应力 3 场景 × 5 种子 × 2 mode
python3 tools/mpc_test.py            # 三场景单次基准
```

### §4.2 — 决策对比
```bash
python3 tests/benchmark_bt_vs_fsm.py
```

### §4.3.1 — 之字形扫描
```bash
bash scripts/run_terrain_benchmark.sh 60
```

### §5.5.1 — sim-to-real 敏感性
```bash
python3 tools/run_thesis_sweep.py \
    --scenarios baseline,combined_stress \
    --seeds 0,1,2 --mpc-modes ua \
    --param-grid 'low_conf_scale:1.5,3.0;smoothness_k:0.5,2.0' \
    --duration 90
```

### §5.5 — Jetson 算力
```bash
bash scripts/run_jetson_emulated_bench.sh
```

---

## 4. 关键术语速查

| 术语 | 含义 | 来源 |
|---|---|---|
| **ES-EKF** | Error-State EKF, 15 维误差状态 (p, v, δθ, b_a, b_g) | [es_ekf.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py) |
| **UA-MPC** | Uncertainty-Aware MPC, 论文 §4.4 主创新点 | [auv_mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py) |
| **NIS** | Normalized Innovation Squared, 卡方分布检验白化 | [es_ekf.py L376-415](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L376-L415) |
| **置信度** `conf` | [0,1] 标量，越大表示感知越可信，由 EKF P trace 推导 | [auv_controller_node.py 286-310](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py) |
| **sweep harness** | 多种子 × 多场景 × 多 mode × 多参数自动化跑批 | [run_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py) |
| **PVS** | Python REMUS-100 简化仿真后端，跑得快 | [start_pvs_sim.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_pvs_sim.sh) |
| **HoloOcean** | UE4 高保真水下仿真，跑得慢但视觉真实 | [start_holoocean_sim.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_holoocean_sim.sh) |
| **CEP50** | Circular Error Probable 50%，定位误差中位数 | EKF 性能指标 |
| **drift** | 相比真值的累计漂移最大值 | EKF 性能指标 |
| **AUV_MPC_MODE** | env 切换 UA / baseline 消融 | [mpc_controller.py L115-118](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py#L115-L118) |
| **AUV_MPC_PARAM_OVERRIDES** | env 注入 weights JSON（参数 sweep 用） | [mpc_controller.py L120-128](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py#L120-L128) |

---

## 5. 实验设计的逻辑链（论文 §5.5.2 论据底座）

> 这条链是论文里"用仿真推进实物验证、且仿真内容逻辑严密"的核心论据，必须在论文写作时显式呈现。

```
①  scenarios/*.yaml（合成可控扰动：DVL 丢包 / 磁畸变 / 声呐杂波 / 综合应力）
       ↓ 输入仿真
②  sweep harness（笛卡尔积多种子，统计 RMSE/CEP50 mean+std，n>=5）
       ↓ 提取均值/方差
③  param-grid（同一仿真上扫参数，方差分解定位 sim-to-real 敏感参数）
       ↓ 标定关键 weights
④  Jetson 算力 bench（仿真侧 CPU/MEM/IPOPT 时延，先于真机锁定算力预算）
       ↓ 满足时延约束
⑤  真机部署（scope 外，但接口与 ②③④ 一致，无需再改算法）
```

每一环节都对应一个 thesis 文档（②=T3+T5, ③=T7 §敏感性, ④=T7 §Jetson, ⑤=T2 间接 + [user-guide/real_hardware_sop.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/user-guide/real_hardware_sop.md)）。

---

## 6. Pre-Snapshot @ Phase 4

**已就绪**（Phase 1–3 累计）：
- ES-EKF 全套 + NIS 自适应 R + correct_mag
- UA-MPC（CasADi+IPOPT）+ sigmoid + 消融开关
- EKF→MPC 置信度耦合（端到端跑通）
- 9 scenarios + sweep harness + param-grid + 方差分解
- Jetson 仿真侧 bench
- 4 篇 docs/experiment 单次实测日志

**Phase 4 收口**：本 thesis 文档族 + E6 链路闭合（C1）。

## 7. Post-Snapshot 占位

> 全部交付完成后回填到 [thesis_experiment_phase4_postsnapshot.md](file:///home/auv_user/auv_ws/AUV-Master-Project/.trae/documents/thesis_experiment_phase4_postsnapshot.md)。
