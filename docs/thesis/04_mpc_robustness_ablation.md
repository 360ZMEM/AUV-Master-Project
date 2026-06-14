# T5 — MPC 鲁棒性消融（论文 §4.4 / §5.5 / §5.5.1）

> **对应论文章节**：§4.4 UA-MPC；§5.5 鲁棒性比较；§5.5.1 权重灵敏度
> **直接消费方**：论文 §5.5 主对比图与表 5-3、§5.5.1 灵敏度图、§4.4 消融表
> **生成时机**：Phase 4 — A 档骨架 + 多 seed sweep 数据待补

UA-MPC（论文核心创新点 #2）的全部消融实验都汇集于此。表面问题：UA-MPC 相对 baseline-MPC 是否有效？拆开问：① 协方差→置信度耦合是否带来增益；② 权重 (1-conf)^α 形式相对线性是否更优；③ sigmoid 平滑相对硬切是否更稳；④ 权重对参数变动的灵敏度。

---

## 1. 消融维度与变体表

| 实验 ID | 变体 | 关键开关 | 期望相对 baseline-MPC 的指标变化 |
| --- | --- | --- | --- |
| **A0** | baseline-MPC | env `AUV_MPC_MODE=baseline` | — (基线) |
| **A1** | UA-MPC（默认） | env `AUV_MPC_MODE=ua` | RMSE ↓, 控制能量 ↓ |
| **A2** | UA-MPC, 关闭 sigmoid（硬切） | param `cov_to_conf.smoothing=hard` | UA-MPC 优势缩小 |
| **A3** | UA-MPC, α=1.0（线性） | env `AUV_MPC_PARAM_OVERRIDES='{"low_conf_alpha":1.0}'` | 与默认相比稳定性下降 |
| **A4** | UA-MPC, low_conf_scale=0 | env `AUV_MPC_PARAM_OVERRIDES='{"low_conf_scale":0.0}'` | 等效退化为 baseline-MPC |
| **B1** | 灵敏度: q_pos | param-grid `q_pos: [10,20,40]` | RMSE 单调 |
| **B2** | 灵敏度: r_u | param-grid `r_u: [0.05,0.1,0.5]` | 控制能量单调 |
| **B3** | 灵敏度: σ_xy_ref | ROS param `cov_to_conf.sigma_xy_ref: [0.5,1,2,5]` | 中间值最优（拐点） |

> A 系列对应论文 §4.4 消融表；B 系列对应论文 §5.5.1 灵敏度。

---

## 2. 实验场景矩阵

每个变体在以下场景上跑 5 seeds：

| 场景 | 用途 | 论文位置 |
| --- | --- | --- |
| baseline | 干净基线 | §5.5 表 5-3 头列 |
| dvl_dropout_30 | 中等丢包 | §5.5 主图 |
| dvl_dropout_60 | 重丢包 | §5.5 极端列 |
| mag_distortion_heavy | 磁干扰 | §5.5 多源章节 |
| sonar_clutter | 声呐噪声 | §5.5 多源章节 |
| combined_stress | 综合应力 | §5.5 主对比图 |

总 run 数 = 6 场景 × 4 变体 (A0-A3) × 5 seeds = 120 runs（A4 与 A0 等价，仅在敏感性脚注列举）；预计 ~5 小时。

---

## 3. 关键代码位置

UA-MPC 核心：[algorithm/auv_mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py)

| 模块 | 行号 | 含义 |
| --- | --- | --- |
| `mpc_mode` 分支 | L162-L164 | baseline / ua 切换入口 |
| sigmoid 置信度 | L218 | `conf = 1 / (1 + exp(-α(c-β)))` |
| `low_conf_scale` | L157, L227-L230 | UA-MPC 权重缩放系数 |
| `(1-conf)^α` 权重 | L249 | 跟踪权重缩放公式 |
| 求解器调用 | （IPOPT） | CasADi backend |

ROS 节点适配层：[brain_linux/src/auv_controller/auv_controller/mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py)

| 模块 | 行号 | 含义 |
| --- | --- | --- |
| `AUV_MPC_MODE` env 读取 | L115-L118 | 模式覆盖 |
| `AUV_MPC_PARAM_OVERRIDES` env 读取 | L120-L128 | 灵敏度参数注入（Phase 4 C1） |
| `weights_cfg.update(overrides)` | L127 | dict 合并 |

控制器节点协方差注入：[auv_controller_node.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py)

| 模块 | 行号 | 含义 |
| --- | --- | --- |
| `_on_covariance` | L286 | 订阅 `/auv/state/covariance` |
| `_confidence_from_cov` | L298 | 协方差 → 置信度 |
| `cov_to_conf.*` ROS 参数 | L194-L199, L548 | 暴露给 launch 与 sweep |

---

## 4. 复现命令

### 4.1 主消融（A0–A3，§5.5 表 5-3）

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline,dvl_dropout_30,dvl_dropout_60,mag_distortion_heavy,sonar_clutter,combined_stress \
  --seeds 0,1,2,3,4 \
  --mpc-modes baseline,ua \
  --output-root /auv_data/sweeps/mpc_ablation_main
```

聚合产物：`summary.csv` + `aggregate.md`，后者直接作为论文表 5-3 数据来源。

### 4.2 sigmoid vs 硬切（A2）

```bash
# 暂未在 sweep harness 中暴露；通过 ROS launch 修改 cov_to_conf.smoothing
ros2 launch auv_controller controller.launch.py cov_to_conf.smoothing:=hard
# 然后单独跑 dvl_dropout_60 + combined_stress 各 5 seeds
```

> A2 当前需手动跑；扩到 sweep 列入 future work。

### 4.3 α 线性 vs 默认（A3）

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios combined_stress \
  --seeds 0,1,2,3,4 \
  --mpc-modes ua \
  --param-grid '{"low_conf_alpha":[1.0,2.0]}' \
  --output-root /auv_data/sweeps/mpc_ablation_alpha
```

### 4.4 灵敏度（B1–B2，§5.5.1）

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios combined_stress \
  --seeds 0,1,2 \
  --mpc-modes ua \
  --param-grid '{"q_pos":[10,20,40],"q_yaw":[0.1,1.0,5.0],"r_u":[0.05,0.1,0.5]}' \
  --output-root /auv_data/sweeps/mpc_sensitivity
```

聚合：`sensitivity.md`（含 between/total variance）。论文 §5.5.1 直接引用。

### 4.5 σ_xy_ref 灵敏度（B3，pending 工具扩展）

> 当前 sweep harness 仅注入 MPC weights env，未注入 ROS 参数；σ_xy_ref 灵敏度需手工 5 档启动 + 数据后聚合。列入 [07_drift_log_and_known_issues.md D3.2](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/07_drift_log_and_known_issues.md)。

---

## 5. 期望表格模板（数据待 sweep 后回填）

### 5.1 论文表 5-3（主对比，所有数值 = mean±std, n=5）

| 场景 | baseline-MPC RMSE (m) | UA-MPC RMSE (m) | Δ% | baseline 控制能量 | UA 控制能量 | Δ% |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | _ | _ | _ | _ | _ | _ |
| dvl_dropout_30 | _ | _ | _ | _ | _ | _ |
| dvl_dropout_60 | _ | _ | _ | _ | _ | _ |
| mag_distortion_heavy | _ | _ | _ | _ | _ | _ |
| sonar_clutter | _ | _ | _ | _ | _ | _ |
| combined_stress | _ | _ | _ | _ | _ | _ |

### 5.2 论文表 5-4（消融）

| 变体 | combined_stress RMSE | dvl_dropout_60 RMSE | 备注 |
| --- | --- | --- | --- |
| A0 baseline-MPC | _ | _ | 控制无协方差感知 |
| A1 UA-MPC（默认） | _ | _ | 完整版本 |
| A2 UA-MPC w/o sigmoid | _ | _ | 硬切阈值 |
| A3 UA-MPC α=1.0 | _ | _ | 线性 |
| A4 UA-MPC scale=0 | ≈ A0 | ≈ A0 | 退化校验 |

### 5.3 §5.5.1 灵敏度（一阶 ANOVA）

| 参数 | between/total variance | 主效应趋势 |
| --- | --- | --- |
| q_pos | _ | _ |
| q_yaw | _ | _ |
| r_u | _ | _ |

---

## 6. 验收清单

- [ ] §4.4 公式与 [auv_mpc_controller.py L162-L249](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py) 一致
- [ ] §5.5 表 5-3 mean±std 由 [run_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py) aggregate.md 自动生成
- [ ] §5.5.1 灵敏度引用 sensitivity.md，标注一阶 ANOVA（D5.1）
- [ ] A4 退化校验通过（UA-MPC scale=0 与 baseline-MPC 数值偏差 < 1%）
- [ ] §5.5 combined_stress 多曲线图含 baseline-MPC vs UA-MPC 阴影带（5 seed std）

---

## 7. 已知限制

- A2（sigmoid 硬切对照）目前需手工跑，未集成到 sweep harness（D3.3 拓展）
- B3（σ_xy_ref 灵敏度）受限于 sweep 仅注入 MPC weights env，需扩工具（D3.2）
- IPOPT 求解失败的回退率未量化（D1.5）
- 多 seed 数据本会话因终端隔离不可执行（D7.2）

---

## Pre-Snapshot @ Phase 4 A8

- UA-MPC 算法实现完整（Phase 2 E3，sigmoid + (1-conf)^α + low_conf_scale + mpc_mode 消融开关）
- ROS 节点 mpc_controller.py env 注入链路完整（Phase 4 C1）
- sweep harness param-grid + sensitivity 聚合就位（Phase 3 E5/E6）
- 单次 baseline+UA 对照数据 ⏳ deferred → D8.1 follow-up（详见 [thesis_experiment_phase2_implementation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/.trae/documents/thesis_experiment_phase2_implementation.md) §8.7）

## Post-Snapshot @ Phase 4

- 多 seed sweep 数据本会话仍未交付：B1 smoke 4 runs + retry v2/v3 共 6 个 sweep bag 全部 `bench_failed`，根因登记为 D8.1（sweep harness 在 protocol_udp + auto-activate 下 brain stack 子进程未发布 `/auv/sensors/{imu,dvl,depth}` ROS topic）
- §4.1 / §5 表格仍为占位，待下一会话精细修复 sweep harness（参考时序：[docs/internals/11_experiment_state_machine.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/internals/11_experiment_state_machine.md) + [docs/experiment/terrain_benchmark_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/terrain_benchmark_log.md)）后回填
- 单 seed 锚点（n=1，仅 baseline 算法对照）见 [01_baseline_repro_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/01_baseline_repro_log.md) Post-Snapshot 段，不替代本篇多 seed 升级
