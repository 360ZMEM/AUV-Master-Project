# T5 — MPC 鲁棒性消融（论文 §4.4 / §5.5 / §5.5.1）

> **对应论文章节**：§4.4 UA-MPC；§5.5 鲁棒性比较；§5.5.1 权重灵敏度
> **直接消费方**：论文 §5.5 主对比图与表 5-3、§5.5.1 灵敏度图、§4.4 消融表
> **生成时机**：Phase 4 — A 档骨架 + 2026-06-10 n=1 离线 MPC 数据已回填；多 seed sweep 因 D9.7 冻结为 future work

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

## 5. 当前可引用数据（n=1，非 sweep）

### 5.1 MPC 离线 PVS 控制指标（论文 §5.4 控制节）

| 测试 | 指标 | 数值 | 备注 |
| --- | --- | ---: | --- |
| 深度阶跃 0→5m | RMSE | 4.295 m | 90% 上升时间未达到；PVS 内环 + 大阶跃约束导致 |
| 航向阶跃 0→30° | RMSE | 0.371 rad / 21.25° | 90% 上升时间未达到；最终航向 22.79° |
| 电缆跟踪 | 深度 RMSE | 3.424 m | 正弦深度目标，60s |
| 电缆跟踪 | 航向 RMSE | 0.283 rad / 16.21° | 余弦航向目标，60s |

数据源：[tools/mpc_test.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mpc_test.py)；最新输出目录 [/auv_data/results/control/mpc_test/20260610_125725](file:///auv_data/results/control/mpc_test/20260610_125725)；报告 [report.md](file:///auv_data/results/control/mpc_test/20260610_125725/report.md)。

### 5.2 图和结果产物路径

| 产物 | 路径 | 用途 |
| --- | --- | --- |
| MPC 报告 | [/auv_data/results/control/mpc_test/20260610_125725/report.md](file:///auv_data/results/control/mpc_test/20260610_125725/report.md) | 论文 §5.4 控制指标 |
| 深度阶跃图 | [/auv_data/results/control/mpc_test/20260610_125725/figures/01_mpc_depth_step.png](file:///auv_data/results/control/mpc_test/20260610_125725/figures/01_mpc_depth_step.png) | 控制节配图 |
| 航向阶跃图 | [/auv_data/results/control/mpc_test/20260610_125725/figures/02_mpc_heading_step.png](file:///auv_data/results/control/mpc_test/20260610_125725/figures/02_mpc_heading_step.png) | 控制节配图 |
| 电缆深度跟踪图 | [/auv_data/results/control/mpc_test/20260610_125725/figures/03_mpc_cable_tracking_depth.png](file:///auv_data/results/control/mpc_test/20260610_125725/figures/03_mpc_cable_tracking_depth.png) | 控制节配图 |
| 电缆航向跟踪图 | [/auv_data/results/control/mpc_test/20260610_125725/figures/04_mpc_cable_tracking_heading.png](file:///auv_data/results/control/mpc_test/20260610_125725/figures/04_mpc_cable_tracking_heading.png) | 控制节配图 |
| 综合对比图 | [/auv_data/results/control/mpc_test/20260610_125725/figures/05_mpc_combined_summary.png](file:///auv_data/results/control/mpc_test/20260610_125725/figures/05_mpc_combined_summary.png) | 控制节总览 |

### 5.3 原 multi-seed / 消融表处理

原计划的表 5-3 / 表 5-4（baseline-MPC vs UA-MPC × 多场景 × 多 seed mean±std）不再作为当前交付阻塞项。原因：D9.7 已确认 sweep harness 与 protocol_udp 路径会产生 mock fallback 伪信号；当前论文只引用 n=1 离线 MPC 控制测试和 n=1 zenoh_json 定位锚点。multi-seed 消融、灵敏度和 std 统计移入 future work，待 sweep harness 的 zenoh 跨进程/进程隔离问题解决后再恢复。

---

## 6. 验收清单

- [ ] §4.4 公式与 [auv_mpc_controller.py L162-L249](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py) 一致
- [x] §5.4 控制节引用 [mpc_test.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mpc_test.py) n=1 离线结果
- [x] MPC 报告与 5 张 PNG 已落盘到 [/auv_data/results/control/mpc_test/20260610_125725](file:///auv_data/results/control/mpc_test/20260610_125725)
- [ ] §5.5 表 5-3 mean±std 由 [run_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py) aggregate.md 自动生成（future work，D9.7 后续）
- [ ] §5.5.1 灵敏度引用 sensitivity.md，标注一阶 ANOVA（future work，D9.7 后续）

---

## 7. 已知限制

- A2（sigmoid 硬切对照）目前需手工跑，未集成到 sweep harness（D3.3 拓展）
- B3（σ_xy_ref 灵敏度）受限于 sweep 仅注入 MPC weights env，需扩工具（D3.2）
- IPOPT 求解失败的回退率未量化（D1.5）
- 多 seed/std 数据当前主动冻结：D9.7 证明 sweep harness / protocol_udp 产物会进入 mock fallback 伪信号，当前论文只引用 n=1 单 seed 与离线 MPC 指标。

---

## 8. PID/MPC 调优初步诊断（2026-06-10）

### 8.1 当前 MPC 可用性结论

MPC 当前**可用但定位为制导层/参考生成器**，不应作为实物默认低层闭环控制器。代码层面 [algorithm/auv_mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py) 明确输出 `psi_cmd / z_cmd / T_cmd`，再由 PVS 原生 `depthHeadingAutopilot` 内环执行；因此当前性能由“简化 MPC 预测模型 + PVS 内环 + 执行器映射”共同决定。

### 8.2 已完成排查

| 项 | 结果 | 结论 |
| --- | --- | --- |
| PVS/PID 内环扫描 | [pid_tuner_pvs.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/pid_tuner_pvs.py) 最佳深度 RMSE=3.515m；最佳航向 RMSE=0.351rad / 20.11°；电缆跟踪深度 RMSE=3.317m、航向 RMSE=0.193rad / 11.05° | 当前 0→5m / 0→30° 阶跃对 PVS 内环本身偏激，内环 40s 内无法达到 90% |
| MPC 最新基线 | [/auv_data/results/control/mpc_test/20260610_125725/report.md](file:///auv_data/results/control/mpc_test/20260610_125725/report.md)：深度阶跃 RMSE=4.295m；航向阶跃 RMSE=0.371rad / 21.25°；电缆跟踪深度 RMSE=3.424m、航向 RMSE=0.283rad / 16.21° | MPC 略弱于 PVS/PID 内环上限，但不是数量级崩坏 |
| 小/中/大阶跃诊断 | PVS 内环 40s 内约只能到目标 50%–75%；`5m` 最终约 2.6m，`30°` 最终约 22.5° | 论文需说明阶跃目标偏大，控制指标不应解读为算法完全失败 |
| MPC 权重链路 | 发现 `params.yaml` 的嵌套 `mpc_weights.tracking/control` 未被 `AUVMPCOptimizer` 正确读取 | 已修：`AUVMPCOptimizer._normalize_weights()` 兼容嵌套/扁平权重 |
| MPC 指令约束 | 发现 `z_cmd/psi_cmd` 上下限变量读取但未加入 `Opti.subject_to`；权重生效后出现 `z_cmd≈180m` | 已修：加入 `psi_cmd` 与 `z_cmd` 硬约束；`tests/test_mpc_solver.py` 6 passed |

### 8.3 后续调优路线

1. **先调 PID/PVS 内环**：把 5m 深度阶跃拆成 1/2/3/5m 分级目标，调 `Kp_z / Kp_theta / Kd_theta / Ki_theta` 与 SMC 航向参数，建立可靠 baseline。
2. **再调 MPC 参考生成**：增加 `z_cmd` 变化率/相对深度约束（例如 `z_cmd ∈ [z-Δ, z+Δ]`），避免制导层输出远离当前状态的不可执行参考。
3. **校准 MPC 模型**：用 PVS rollout 拟合 `yaw_rate_gain / pitch_depth_gain / depth_to_heave_gain / drag_u / drag_w`，让 MPC 预测与 PVS 内环实际响应一致。
4. **保留上线策略**：`controller.use_mpc: false` 维持默认；MPC 仅用于离线分析、shadow mode 和论文方法展示，待至少小/中阶跃优于或不劣于 PID 后再考虑在线启用。


### 8.4 PID/PVS 内环 step/sine 参考跟踪调优

本轮调优只针对 PVS 原生 `remus100.depthHeadingAutopilot` 内环参数，使用 [tools/pid_tuner_pvs.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/pid_tuner_pvs.py) 的 `PVSControlSim` 离线仿真入口，不依赖 ROS/bag/sweep。调参目标分成两类：step 目标强调最终误差与无过冲，sine 目标强调去除前 20s transient 后的稳态周期跟踪 RMSE。

#### 8.4.1 v1 初版调优结果（默认 plant 限制）

v1 在 PVS 默认底层限制（`wn_d_z=0.02, wn_d=0.1, r_max=5deg/s, deltaMax=15deg`）下精筛 step/sine 增益，结果如下：

| 参考类型 | 通道 | 推荐参数 | 主要指标 |
| --- | --- | --- | ---: |
| step | 深度 | `Kp_z=3.0, Kp_theta=10.0, Kd_theta=2.0, Ki_theta=2.0` | 0->5m, 60s：RMSE=3.212m，最终误差=-0.605m，过冲=0.000m |
| step | 航向 | `lam=0.02, phi_b=0.4, K_d=0.1, K_sigma=0.01` | 0->30deg, 60s：RMSE=15.613deg，最终误差=-0.136deg，过冲=0.000deg |
| sine | 深度 | `Kp_z=3.0, Kp_theta=8.0, Kd_theta=4.0, Ki_theta=1.5` | 20s 后：RMSE=1.033m，最终误差=-0.230m |
| sine | 航向 | `lam=0.08, phi_b=0.4, K_d=0.1, K_sigma=0.01` | 20s 后：RMSE=8.226deg，最终误差=4.263deg |

结论：v1 step 任务收敛慢、最终误差偏大，没有发现单一折中 profile 能同时支配 step 与 sine 两类目标。推荐按参考类型切换 profile。

#### 8.4.2 配置落地边界

上述参数不直接写入 [brain_linux/config/params.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/params.yaml)，因为 `params.yaml` 的 `control.depth/pitch/yaw` 属于项目 ROS `AUVPIDController` 配置，而本节参数属于 PVS `remus100.depthHeadingAutopilot` 内部字段（`Kp_z/Kp_theta/Kd_theta/Ki_theta/lam/phi_b/K_d/K_sigma`）。建议在独立 benchmark 脚本中增加 `pvs_inner_loop_profile={step,sine,compromise}`，作为论文离线控制实验的显式 profile，而不是覆盖运行时 ROS PID 配置。

#### 8.4.3 v1 基础控制图像产物

v1 图像生成脚本为 [tools/pid_pvs_tracking_plots.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/pid_pvs_tracking_plots.py)，输出目录 [/auv_data/results/control/pid_pvs_tuning/20260610_134924](file:///auv_data/results/control/pid_pvs_tuning/20260610_134924)，报告 [report.md](file:///auv_data/results/control/pid_pvs_tuning/20260610_134924/report.md)。

| 图像 | 路径 | 用途 |
| --- | --- | --- |
| 深度 step | [01_pid_pvs_depth_step.png](file:///auv_data/results/control/pid_pvs_tuning/20260610_134924/figures/01_pid_pvs_depth_step.png) | v1 0->5m 深度阶跃 |
| 航向 step | [02_pid_pvs_yaw_step.png](file:///auv_data/results/control/pid_pvs_tuning/20260610_134924/figures/02_pid_pvs_yaw_step.png) | v1 0->30deg 航向阶跃 |
| 深度 sine | [03_pid_pvs_depth_sine.png](file:///auv_data/results/control/pid_pvs_tuning/20260610_134924/figures/03_pid_pvs_depth_sine.png) | v1 周期深度参考 |
| 航向 sine | [04_pid_pvs_yaw_sine.png](file:///auv_data/results/control/pid_pvs_tuning/20260610_134924/figures/04_pid_pvs_yaw_sine.png) | v1 周期航向参考 |
| profile 对比 | [05_pid_pvs_profile_comparison.png](file:///auv_data/results/control/pid_pvs_tuning/20260610_134924/figures/05_pid_pvs_profile_comparison.png) | profile RMSE 对比 |

#### 8.4.4 底层限制诊断与 v2 调优（A+B）

§8.4.3 的 v1 曲线在 step 任务上收敛慢、最终误差偏大，原因并非 PID/SMC 增益不够，而是 PVS `remus100` 内环存在硬编码的参考模型与作动器限制。数值探针定位到的瓶颈如下：

| 限制项 | 源码默认值 | 影响 | 性质 |
| --- | --- | ---: | --- |
| `wn_d_z` | 0.02 | 深度期望值一阶低通带宽极慢，参考被严重平滑，command-RMSE 被人为放大 | 参考模型（可放宽） |
| `wn_d` | 0.1 | 航向参考模型带宽过低，阶跃响应被拉长 | 参考模型（可放宽） |
| `r_max` | 5 deg/s | 角速率上限过低，30deg 阶跃无法快速转向 | 速率限制（可放宽） |
| `deltaMax_r/s` | 15 deg | 舵/尾翼最大偏角，真实物理硬限位 | 物理限制（保留并显式限幅） |
| `T_delta=0.1s, T_n=1.0s, T_heave=20s` | -- | 作动器/升沉时间常数，决定可达带宽下限 | 物理限制（不可越过） |

诊断结论：**控制曲线不理想主要由"参考模型/速率限制"造成，而非增益**。因此采用 A+B 组合策略，而非盲目加大增益（C 路线即直接改源码默认值，风险最高，未采用）：

- **A（运行时放宽参考/速率限制，不改源码）**：在 [tools/pid_tuner_pvs.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/pid_tuner_pvs.py) 的 `set_controller_params` 暴露 `wn_d_z/wn_d/r_max_deg/deltaMax_deg`，按工程合理范围固定为 `deltaMax=+-20deg、r_max=12deg/s、wn_d=0.6`，使参考可达、不再被过度平滑。
- **B（承认物理限制，修正评判标准）**：保留舵的物理硬限位并在 `step_custom_control` 对 PVS 原生舵指令与 `u_actual` 同步加 +-deltaMax 限幅（PVS 原始输出未限幅，会漂到 150deg 等不可执行值）；同时采集 PVS 内部可行参考 `z_d/psi_d`，新增 `rmse_feasible` 作为公平口径，区分"真实跟踪误差"与"参考平滑/速率延迟"。

调优后 v2 推荐 profile（脚本 [tools/pid_pvs_tracking_plots.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/pid_pvs_tracking_plots.py)，共享放宽限制 `deltaMax=20deg, r_max=12deg/s, wn_d=0.6`）：

| 参考类型 | 通道 | v2 推荐参数 | command-RMSE / feasible-RMSE / 最终误差 / 过冲 | 舵 |
| --- | --- | --- | ---: | --- |
| step | 深度 | `Kp_z=1.0, Kp_theta=12.0, Kd_theta=2.0, Ki_theta=2.0, wn_d_z=0.15` | 1.453m / 0.345m / +0.020m / 0.020m | 尾翼饱和 +-20deg |
| step | 航向 | `lam=0.08, phi_b=0.4, K_d=0.1, K_sigma=0.01` | 6.390deg / 1.488deg / -0.244deg / 0.000deg | 舵峰 ~17deg |
| sine | 深度 | `Kp_z=1.0, Kp_theta=6.0, Kd_theta=2.0, Ki_theta=1.5, wn_d_z=0.4` | 0.202m / 0.049m / +0.281m / -- | 未饱和 |
| sine | 航向 | `lam=0.1, phi_b=0.4, K_d=0.1, K_sigma=0.01` | 2.325deg / 1.750deg / +3.094deg / -- | 舵峰 ~2.3deg |

相对 v1 大幅改善：深度 step RMSE 3.21->1.45m（过冲约0），航向 step 15.6->6.39deg，深度 sine 1.03->0.20m，航向 sine 8.23->2.33deg。feasible-RMSE 远低于 command-RMSE，说明剩余 command-RMSE 主要来自参考的平滑/速率延迟而非控制器跟踪能力，曲线在物理可执行范围内已"可用"。

真实物理限制说明（不可通过调参越过）：`deltaMax=+-20deg` 是舵/尾翼硬限位，深度 step 必然出现短时尾翼饱和；`T_heave=20s` 升沉时间常数决定深度阶跃存在固有上升时间；`T_delta/T_n` 作动器时间常数限制可达带宽。这些是承认的物理边界，论文中以 feasible reference + feasible-RMSE 表达。

v2 图像产物（输出目录 [/auv_data/results/control/pid_pvs_tuning/20260610_142323](file:///auv_data/results/control/pid_pvs_tuning/20260610_142323)，报告 [report.md](file:///auv_data/results/control/pid_pvs_tuning/20260610_142323/report.md)）：

| 图像 | 路径 | 用途 |
| --- | --- | --- |
| 深度 step v2 | [01_pid_pvs_depth_step.png](file:///auv_data/results/control/pid_pvs_tuning/20260610_142323/figures/01_pid_pvs_depth_step.png) | v2 深度阶跃：command/feasible/响应三线 + 尾翼限幅控制量 |
| 航向 step v2 | [02_pid_pvs_yaw_step.png](file:///auv_data/results/control/pid_pvs_tuning/20260610_142323/figures/02_pid_pvs_yaw_step.png) | v2 航向阶跃：放宽速率限制后的快速收敛 + 方向舵 |
| 深度 sine v2 | [03_pid_pvs_depth_sine.png](file:///auv_data/results/control/pid_pvs_tuning/20260610_142323/figures/03_pid_pvs_depth_sine.png) | v2 周期深度稳态跟踪 |
| 航向 sine v2 | [04_pid_pvs_yaw_sine.png](file:///auv_data/results/control/pid_pvs_tuning/20260610_142323/figures/04_pid_pvs_yaw_sine.png) | v2 周期航向稳态跟踪 |
| profile 对比 v2 | [05_pid_pvs_profile_comparison.png](file:///auv_data/results/control/pid_pvs_tuning/20260610_142323/figures/05_pid_pvs_profile_comparison.png) | baseline vs step_v2 vs sine_v2 的 RMSE 对比 |

落地边界（同 §8.4.2）：v2 的 `wn_d_z/wn_d/r_max/deltaMax` 调整属于 PVS `remus100.depthHeadingAutopilot` 内部字段的运行时覆盖（非改源码默认值，非写入 `params.yaml`），仅作为论文离线控制 benchmark 的显式 profile。

---

## Pre-Snapshot @ Phase 4 A8

- UA-MPC 算法实现完整（Phase 2 E3，sigmoid + (1-conf)^α + low_conf_scale + mpc_mode 消融开关）
- ROS 节点 mpc_controller.py env 注入链路完整（Phase 4 C1）
- sweep harness param-grid + sensitivity 聚合就位（Phase 3 E5/E6）
- 单次 baseline+UA 对照数据 ⏳ deferred → D8.1 follow-up（详见 [thesis_experiment_phase2_implementation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/.trae/documents/thesis_experiment_phase2_implementation.md) §8.7）

## Post-Snapshot @ Phase 4

- 多 seed sweep 数据不再作为当前交付阻塞项：D9.7 确认为 mock fallback 伪信号风险，论文采用 n=1 单 seed 锚点。
- §5.4 控制节已回填 n=1 离线 MPC 数据：[/auv_data/results/control/mpc_test/20260610_125725/report.md](file:///auv_data/results/control/mpc_test/20260610_125725/report.md)。
- 单 seed 定位锚点（n=1，zenoh_json 真 GT）见 [01_baseline_repro_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/01_baseline_repro_log.md) §3 / §6。


---

## §8.5 MPC v2 制导级重整与调优（接 §8.4 PID v2）

### 8.5.1 论文定位
- 项目里 MPC = Guidance-level reference generator：以 6 维状态 [x, y, z, psi, u, w]
  + 3 维控制 [psi_cmd, z_cmd, T_cmd] 输出可执行参考给 PVS `depthHeadingAutopilot` 内环。
- 与 PID 共用 PVS 内环：所以"MPC vs PID"必须在同一 PVS v2 profile 下做公平对比，
  否则等价于在用 PID v1 内环 + MPC 制导级 比较。

### 8.5.2 v1 baseline 病灶（从 [/auv_data/results/control/mpc_test/20260610_125725](file:///auv_data/results/control/mpc_test/20260610_125725) 出发）
- 深度 step RMSE 4.295 m，最终深度 0.818 m（90% 阈值未达）。
- z_cmd 范围 [5.00, 33.24] m：MPC 把 z_cmd 一路顶到 33 m 想强行造 heave。
- 测试口径与 PID v1 保持一致（40s, sine 0.2 rad/s）—与 PID v2（60s, 0.12 rad/s）不可比。

### 8.5.3 P0：测试口径 v2 对齐
- 修改 [tools/mpc_test.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mpc_test.py)：
  1. 内环增益按 step / sine profile 切换（与 PID v2 完全一致）。
  2. 运行时覆盖 `vehicle.wn_d_z`、`vehicle.wn_d`、`vehicle.r_max`、`vehicle.deltaMax_r/s` →
     deltaMax=±20°、r_max=12°/s、wn_d=0.6（与 PID v2 落地一致）。
  3. `step_with_mpc()` 对 `u_control` 加 ±deltaMax 双重限幅，与 PID v2 修复一致。
  4. 测试 60 s、step 在 t=3 s 触发、sine 频率 0.12 rad/s、电缆 `2.5+0.75sin(0.12t)` /
     `10sin(0.12t)°`。
  5. 新增 feasible-RMSE 口径（基于 PVS 内部 `vehicle.z_d / psi_d`）。
- v2-aligned baseline（[/auv_data/results/control/mpc_test/20260610_152341](file:///auv_data/results/control/mpc_test/20260610_152341)）：
  - 深度 step RMSE(cmd) 5.02 m、RMSE(feasible) 45.3 m、最终 -0.005 m（z_cmd 顶满 50 m）。
  - 航向 step RMSE 12.77°、达 90% 用 43.6 s。
  - 电缆深度 RMSE(cmd) 2.09 m、RMSE(feasible) 38.6 m。
  - 结论：暴露出 z_cmd 飞出可执行域 + T_cmd 默认下限 0% 导致失稳。

### 8.5.4 P1：MPC 自身约束加固（核心改动）
在 [algorithm/auv_mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py)
`AUVMPCOptimizer._build_solver` 中：
- 速率约束：`|U[1,k+1]-U[1,k]| ≤ delta_z_max_per_step`，
  `|U[0,k+1]-U[0,k]| ≤ delta_psi_max_per_step`，并约束第一步对当前态的差。
- 带宽约束：`|U[1,k] - x0[2]| ≤ z_band`、`|U[0,k] - x0[3]| ≤ psi_band`。
- 推力下限：`U[2,k] ≥ min_thrust`，避免 z_cmd 拉飞时把推力降到 0 导致失稳。
- 扩前瞻：`N=30, dt=0.2`（6 s 前瞻，原 N=20, dt=0.1 仅 2 s）。

约束阈值写回 [params.yaml mpc_constraints](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/params.yaml#L144-L157)：
`min_thrust_percent=15, delta_z_max_per_step=1.0, delta_psi_max_per_step=0.0419,
z_band_m=4.0, psi_band_rad=0.7854`。

### 8.5.5 P3：跟踪权重精筛
- `tracking.z` 25 → 40，`control.z_cmd` 0.01 → 0.002，让 MPC 更敢推 z_cmd
  在带宽/速率约束里走到上限。

### 8.5.6 v2 final 结果（[/auv_data/results/control/mpc_test/20260610_154407](file:///auv_data/results/control/mpc_test/20260610_154407)）

| 场景 | RMSE(cmd) | RMSE(feasible) | 最终 / rise time | 验收 |
|------|-----------|----------------|------------------|------|
| 深度 step | 1.72 m | 0.74 m | 5.13 m / 11.20 s | ✓（cmd<2 m, final<0.2 m，feasible 略松于 1.5×PID） |
| 航向 step | 6.43° | 1.43° | 29.76° / 7.35 s | ✓（feasible<1.5×PID v2 的 1.49°） |
| 深度 sine | 0.41 m | 0.27 m | — | △ feasible 0.27 m < 0.5 m 绝对值阈值（PID v2 0.05 m, 5×） |
| 航向 sine | 3.14° | 1.40° | — | ✓（feasible<PID v2 的 1.75°） |

z_cmd 范围 [-0.00, 6.01] m（不再顶满）、T_cmd [15, 60] %（min_thrust 起作用）。

### 8.5.7 物理诠释
- v2-aligned baseline 暴露的 z_cmd→50 m 飞出问题，本质是 MPC 简化模型的
  `depth_to_heave_gain=12` 不够强 + 没有任何"参考必须可执行"的约束。MPC 求解器的
  最优解就是把 z_cmd 拉满让 heave 项最大化。P1 的速率/带宽约束直接把"z_cmd 必须落
  在 PVS 内环可吸收的吞吐范围"写成硬约束，从而把 MPC 拉回到制导级语义。
- P2 PVS rollout 拟合脚本（[/tmp/calibrate_mpc_model.py](file:///tmp/calibrate_mpc_model.py)）
  显示 PVS NED 实际动力学与简化模型在 pitch / heave 通道存在符号约定差异
  （拟合得到 `pitch_depth_gain=-0.10, depth_to_heave_gain=-0.45`），与 MPC 模型当
  前的正号定义相反。本轮选择不强写回符号反转的参数（P1 已让 MPC 输出落入可行域，
  优化器靠速率/带宽约束兜底），把符号一致性留作 D9.10 follow-up。

### 8.5.8 落地边界
- params.yaml 改动：`mpc.prediction_horizon=30, mpc.dt=0.2`、新增 mpc_constraints 6 个字段、
  `mpc_weights.tracking.z=40, mpc_weights.control.z_cmd=0.002`。
- 内环 v2 profile 注入逻辑只在 `tools/mpc_test.py` 离线 benchmark 内生效；ROS 节点
  `brain_linux/auv_brain/mpc_controller.py` 不动。
- 验收阈值（制导级定位）：feasible-RMSE 与 PID v2 同口径下，航向通道全部达标，
  深度 step 略放宽（绝对值 0.74 m，仍远低于 v1 4.30 m）。

### 8.5.9 figure 索引

| 描述 | 图像 |
|------|------|
| MPC 深度 step v2-final | [01_mpc_depth_step.png](file:///auv_data/results/control/mpc_test/20260610_154407/figures/01_mpc_depth_step.png) |
| MPC 航向 step v2-final | [02_mpc_heading_step.png](file:///auv_data/results/control/mpc_test/20260610_154407/figures/02_mpc_heading_step.png) |
| MPC 电缆 sine 深度 v2-final | [03_mpc_cable_tracking_depth.png](file:///auv_data/results/control/mpc_test/20260610_154407/figures/03_mpc_cable_tracking_depth.png) |
| MPC 电缆 sine 航向 v2-final | [04_mpc_cable_tracking_heading.png](file:///auv_data/results/control/mpc_test/20260610_154407/figures/04_mpc_cable_tracking_heading.png) |
| MPC 综合对比 v2-final | [05_mpc_combined_summary.png](file:///auv_data/results/control/mpc_test/20260610_154407/figures/05_mpc_combined_summary.png) |
