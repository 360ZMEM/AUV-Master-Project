# T6 — Scenario Recipes（场景配方手册）

> **对应论文章节**：§5.2 仿真场景设计
> **直接消费方**：`tools/run_thesis_sweep.py`、`scripts/start_experiment.sh --scenario <yaml> --seed <int>`、论文 §5.2 / §5.4 / §5.5
> **生成时机**：Phase 4 — A 档（全静态可写完）

---

## 1. 场景库总览

`scenarios/` 目录共含 9 个 YAML 配方 + 1 个 `README.md`，覆盖三个一级维度：**通信/传感丢包**、**磁干扰**、**声呐杂波**，外加 1 个 **baseline** 与 1 个 **combined_stress**。所有场景统一 `duration_s: 120`、`sim_backend: pvs`（默认 PVS REMUS-100；HoloOcean 可通过 CLI 覆盖）、`mpc_mode: ua`（默认 UA-MPC，对照组通过 sweep 矩阵切换）。

| 文件 | name | 一句话物理含义 | 主调参数 | 论文截图位 |
| --- | --- | --- | --- | --- |
| [scenario_baseline.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/scenarios/scenario_baseline.yaml) | baseline | 干净参考 run，所有 chaos 关闭 | — | §5.4 baseline 表 |
| [scenario_dvl_dropout_10.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/scenarios/scenario_dvl_dropout_10.yaml) | dvl_dropout_10 | 10% DVL 丢包，短冻结窗 0.5–1.5 s | `chaos.dvl_freeze.drop_rate=0.10` | §5.4 表 5-2 |
| [scenario_dvl_dropout_30.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/scenarios/scenario_dvl_dropout_30.yaml) | dvl_dropout_30 | 30% DVL 丢包，中冻结窗 0.5–2.5 s | `drop_rate=0.30` | §5.4 表 5-2 |
| [scenario_dvl_dropout_60.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/scenarios/scenario_dvl_dropout_60.yaml) | dvl_dropout_60 | 60% DVL 丢包，长冻结窗 1.0–4.0 s | `drop_rate=0.60` | §5.4 表 5-2 |
| [scenario_dvl_dropout_90.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/scenarios/scenario_dvl_dropout_90.yaml) | dvl_dropout_90 | 90% 近全丢，超长冻结 2.0–6.0 s（failsafe 检验） | `drop_rate=0.90` | §5.4 失效边界图 |
| [scenario_mag_distortion_light.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/scenarios/scenario_mag_distortion_light.yaml) | mag_distortion_light | 轻度磁饱和，~10% 事件触发 | `chaos.mag_saturation_threshold_t=1e-6` | §5.4 mag 节 |
| [scenario_mag_distortion_heavy.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/scenarios/scenario_mag_distortion_heavy.yaml) | mag_distortion_heavy | 重度磁饱和 ~50% + 声呐 1.5×；饱和阈值收紧 100× | `mag_saturation_threshold_t=1e-8` + `sonar_noise_scale=1.5` | §5.4 mag 节 |
| [scenario_sonar_clutter.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/scenarios/scenario_sonar_clutter.yaml) | sonar_clutter | 浅水多径杂波，声呐噪声 ×3 | `perception.sonar_noise_scale=3.0` | §5.4 声呐节 |
| [scenario_combined_stress.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/scenarios/scenario_combined_stress.yaml) | combined_stress | 综合应力：30%DVL+IMU 漂+深度毛刺+磁饱和+流速 0.3 m/s | 见 §3 | §5.4 综合表 + §5.5 鲁棒比较 |

---

## 2. 三维分组与覆盖矩阵

把 9 个场景按"故障维度"重排，便于论文中绘制覆盖矩阵：

| 维度 \ 强度档位 | 无 (off) | 轻 (light) | 中 (medium) | 重 (heavy) | 极端 (extreme) |
| --- | --- | --- | --- | --- | --- |
| **DVL 丢包** | baseline | dvl_dropout_10 | dvl_dropout_30 | dvl_dropout_60 | dvl_dropout_90 |
| **磁干扰（饱和+噪声）** | baseline | mag_distortion_light | — | mag_distortion_heavy | — |
| **声呐杂波（noise scale）** | baseline (1.0×) | — | — | sonar_clutter (3.0×) | — |
| **复合扰动** | baseline | — | — | combined_stress | — |

### 2.1 物理参数 ↔ 代码消费方映射

| 配置字段 | 数值范围 | 消费源文件 | 消费符号 |
| --- | --- | --- | --- |
| `chaos.dvl_freeze.drop_rate` | 0.0–0.90 | [mock_amd_chaos.py](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/mock_amd_chaos.py) | DVL 包级丢包概率 |
| `chaos.dvl_freeze.freeze_window_s` | [0.5, 6.0] s | [mock_amd_chaos.py](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/mock_amd_chaos.py) | 冻结窗随机区间 |
| `chaos.imu_drift.bias_rate` | 0.0 / 1e-3 | [mock_amd_chaos.py](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/mock_amd_chaos.py) | IMU bias 漂移率 (rad/s²) |
| `chaos.depth_spike.{rate_hz, amplitude_m}` | 0/0.05 Hz, 0/0.5 m | [mock_amd_chaos.py](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/mock_amd_chaos.py) | 深度毛刺 |
| `chaos.mag_saturation_threshold_t` | null / 1e-6 / 1e-7 / 1e-8 | [perception_engine.py](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/perception_engine.py) | 三轴磁饱和阈值（Tesla） |
| `perception.imu_acc_noise_scale` | 1.0 / 1.5 | [perception_engine.py](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/perception_engine.py) | 加速度计噪声乘子 |
| `perception.sonar_noise_scale` | 1.0 / 1.5 / 2.0 / 3.0 | [perception_engine.py](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/perception_engine.py) | 声呐噪声乘子 |
| `perception.cable_current_amp` | 500 A（全场景固定） | [perception_engine.py](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/perception_engine.py) | 母船拖缆电流，触发 cable-induced mag 噪声 |
| `flow.current_speed_mps` | 0.0 / 0.3 | sim 后端 | 海流速度（联立 PVS 流场） |
| `mpc_mode` | baseline / ua | [auv_mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py) | env `AUV_MPC_MODE` 覆盖 |

> 字段缺省值见 [scenarios/README.md](file:///home/auv_user/auv_ws/AUV-Master-Project/scenarios/README.md) Schema 节。

---

## 3. combined_stress 拆解（论文 §5.5 鲁棒主图素材）

`combined_stress` 是论文 §5.5 主鲁棒比较的关键场景，单个 yaml 内同时打开 5 个扰动源，对应论文中"模拟现场最不利组合"的物理意图：

| 扰动源 | 数值 | 对应论文叙事 |
| --- | --- | --- |
| `chaos.packet_loss_prob = 0.05` | 5% 总线丢包 | 模拟低带宽 acoustic modem |
| `chaos.dvl_freeze.drop_rate = 0.30` + window `[1.0, 3.0] s` | 中等 DVL 丢包 | 浊水/杂草遮挡 |
| `chaos.imu_drift.bias_rate = 0.001` | IMU bias 缓慢漂移 | 无热漂温补的 MEMS |
| `chaos.depth_spike.rate_hz = 0.05` + `amplitude_m = 0.5` | 平均 20 s 一次的 0.5 m 深度毛刺 | 压力传感 EMI |
| `chaos.mag_saturation_threshold_t = 1.0e-7` | 中度磁饱和 | 母船电磁场近场 |
| `perception.imu_acc_noise_scale = 1.5` | 加速度计噪声 1.5× | 振动耦合 |
| `perception.sonar_noise_scale = 2.0` | 声呐噪声 2× | 浑浊浅水 |
| `flow.current_speed_mps = 0.3` | 0.3 m/s 海流 | 长江口/近海典型 |

> 论文中务必同时给出 baseline、单维度场景、combined_stress 三层数据，证明 UA-MPC 的鲁棒性增益是叠加生效，而非单点偶然。

---

## 4. 选择决策树（新手 SOP）

```
┌──────────────────────────────────────────┐
│ Q1: 你要回答论文中的哪个问题？          │
└──────────────────────────────────────────┘
        │
        ├─ "我的 ES-EKF 在干净环境下收敛吗？"
        │      → scenario_baseline + 任意 mpc_mode
        │      → §5.4 baseline 表数据源
        │
        ├─ "DVL 丢包到什么强度算法仍可用？"
        │      → 跑 dvl_dropout_{10,30,60,90} 全系列
        │      → 推荐 seeds=0..4, mpc_modes=baseline,ua
        │      → §5.4 表 5-2 + 论文中 RMSE-vs-drop_rate 折线图
        │
        ├─ "磁饱和如何影响航向估计？"
        │      → mag_distortion_{light,heavy}
        │      → 配 ablation：mpc_mode=ua 与 baseline
        │      → §5.4 mag 节
        │
        ├─ "UA-MPC 相对 baseline-MPC 能带来多少提升？"
        │      → combined_stress + dvl_dropout_60 各 5 seed
        │      → mpc_modes=baseline,ua
        │      → §5.5 主鲁棒比较图 + 表 5-3
        │
        └─ "我想做权重灵敏度分析（论文 §5.5.1）"
               → 任选 1–2 个有代表性场景（baseline + combined_stress）
               → 配合 --param-grid '{"q_pos": [10,20,40], "r_u": [0.1,0.5]}'
               → tools/run_thesis_sweep.py 内置 sensitivity 聚合
```

---

## 5. 标准命令模板

### 5.1 单场景单种子（新手起步、调试用）

```bash
cd /home/auv_user/auv_ws/AUV-Master-Project
bash scripts/start_experiment.sh \
  --scenario scenarios/scenario_baseline.yaml \
  --seed 0 \
  --duration 120
```

输出落盘：`/auv_data/bags/<timestamp>/`，含 rosbag、`run_metadata.json`、`auto_activate.log`。

### 5.2 单维度 sweep（论文表数据来源）

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline,dvl_dropout_10,dvl_dropout_30,dvl_dropout_60,dvl_dropout_90 \
  --seeds 0,1,2,3,4 \
  --mpc-modes ua \
  --output-root /auv_data/sweeps/dvl_axis
```

聚合产物：
- `summary.csv` — 每 run 一行（scenario × seed × mpc_mode × RMSE/NIS/cost）
- `aggregate.md` — 论文级 markdown 表，按 scenario 分组 mean±std
- `sensitivity.md` — 若使用 `--param-grid`，按参数维度的方差分解

### 5.3 完整论文级 sweep（A vs UA 对比 + 综合）

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline,dvl_dropout_30,dvl_dropout_60,mag_distortion_heavy,sonar_clutter,combined_stress \
  --seeds 0,1,2,3,4 \
  --mpc-modes baseline,ua \
  --output-root /auv_data/sweeps/thesis_main
```

> 总 run 数 = 6 × 5 × 2 = 60，单 run ≤ 120 s + 启停 ~30 s，约 2.5 h。

### 5.4 Smoke 档（CI / 提前发现配置错误）

```bash
bash scripts/run_dvl_sweep.sh --smoke    # 仅 dvl_dropout_30, seed=0, mpc=ua, duration=30s
bash scripts/run_mag_sweep.sh --smoke
bash scripts/run_combined_sweep.sh --smoke
```

> 详见 [run_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py) 与 [scripts/run_*_sweep.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/)。

### 5.5 参数灵敏度（论文 §5.5.1 直接素材）

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios combined_stress \
  --seeds 0,1,2 \
  --mpc-modes ua \
  --param-grid '{"q_pos":[10,20,40],"q_yaw":[0.1,1.0,5.0],"r_u":[0.05,0.1,0.5]}' \
  --output-root /auv_data/sweeps/sensitivity
```

> Param-grid 通过 env `AUV_MPC_PARAM_OVERRIDES` (JSON) 注入到 [mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py)（Phase 4 C1 修复点）。`weights_cfg` 在 ROS 节点初始化时被 dict.update 覆盖。

---

## 6. 验收清单（写论文时逐项核对）

- [ ] 论文 §5.2 给出本表（§1）逐行 yaml 物理含义
- [ ] §5.4 表 5-2 / 表 5-3 数据来自 `tools/run_thesis_sweep.py` aggregate.md，附种子列表与提交哈希
- [ ] §5.5 combined_stress 的 5 维扰动逐项在文中列举（§3 表）
- [ ] §5.5.1 灵敏度图引用 sensitivity.md，标明 between/total variance 比例
- [ ] 任何超出现有 9 个 yaml 的实验，需新增 `scenarios/scenario_<id>.yaml` 并在本文件 §1 表与 [INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/INDEX.md) 同步增行

---

## 7. 已知限制

1. 9 个 yaml 中所有 chaos profile 均为**事件级 Bernoulli**（drop_rate）+ **窗口随机均匀采样**，未覆盖周期性故障（如风扇 EMI 谐波）。论文 §6 future work 应注明。
2. `flow.current_speed_mps` 仅 `combined_stress` 启用 0.3 m/s，未做 0.1/0.5/1.0 m/s 流速维度扫描——论文若需流速 robustness 单独成节，需新增 `scenario_flow_*.yaml` 三档并补 sweep。
3. `cable_current_amp` 全系列固定 500 A，未做拖缆电流维度扫描；论文 §3.4.3 仅作为常量条件。
4. `sim_backend: pvs` 全部默认 PVS；HoloOcean 后端在 §5.5 jetson 实测段才启用，由 sweep CLI `--sim-backend holoocean` 显式覆盖。

---

## Pre-Snapshot @ Phase 4 A3

- 9 个 yaml + README.md ✅ 已就位
- [run_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py) `--param-grid` (L365) + `parse_param_grid` (L374) + `write_sensitivity_summary` (L534/541) ✅
- 三档 sweep 薄壳 [scripts/run_dvl_sweep.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_dvl_sweep.sh) / [run_mag_sweep.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_mag_sweep.sh) / [run_combined_sweep.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_combined_sweep.sh) ✅
- E6 链路 [mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py) `AUV_MPC_PARAM_OVERRIDES` 解析 ✅（Phase 4 C1 完成）

## Post-Snapshot @ Phase 4

待 Phase 4 收口前由 [thesis_experiment_phase4_consolidation_plan.md](file:///home/auv_user/auv_ws/AUV-Master-Project/.trae/documents/thesis_experiment_phase4_consolidation_plan.md) §10 回填。
