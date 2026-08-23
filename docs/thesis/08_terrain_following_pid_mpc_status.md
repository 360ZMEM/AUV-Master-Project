# 地形跟随 PID/MPC 当前状态与 MPC 支线结论

**日期**: 2026-08-23
**定位**: 固化地形跟随实验、PID/PVS 与 guidance-level MPC 对比、PVS 深度内环诊断，以及 MPC 在 `x/y/yaw` 平面制导层面的补充优势分析。本文档 §2--§8 保留历史演进，当前正式口径以 §9 为准。

---

## 1. 总结

- **地形跟随主线**: 采用 `PID/PVS terrain`。该方案在 60s terrain benchmark 和 low/mid/high ablation 中均能稳定保持约 `3m` 离底高度，且无 `<1.5m` 安全违规。
- **MPC 支线**: 不再把 MPC 作为深度/离底高度主控制器；保留 MPC 作为 `guidance-level reference generator`，用于说明其在复杂平面路径、预瞄路径跟踪和速度规划中的潜在价值。
- **论文边界**: MPC 不是完全失败，它已经接入真实仿真闭环，也能改善部分 baseline；但在当前低层执行器限制、PVS 内环滤波和在线求解负担下，深度控制/terrain-following 指标没有超过调优后的 PID/PVS。

---

## 2. Terrain Benchmark 主结果

> ⚠️ **本节表为 2026-06-10 旧口径（`20260610_175154`），已受 §8.1 度量 datum bug 污染（`clearance_mean≈4.0m` 系常值 datum 假象、`depth_error_rmse≈7m` 口径错误）。论文请引用 §8.2 的 P0 真口径重跑表（`20260619_222639`）。以下表保留仅作修复前后对比。**

**结果目录**: `results/control/terrain_following_20260610_175154/`  
**日志**: `/tmp/terrain_pid_mpc_60_mergedcfg.log`  
**地形配置**: `config/bridge_params.protocol_udp.pvs.terrain.yaml`

| 指标 | PID baseline | PID terrain | MPC baseline | MPC terrain |
|---|---:|---:|---:|---:|
| duration_s | 59.5169 | 59.4934 | 58.8287 | 55.2146 |
| diagnostics_sample_count | 596 | 589 | 595 | 499 |
| estimated_sample_count | 1191 | 1168 | 1187 | 1105 |
| seabed_clearance_min_m | 2.7984 | 3.1725 | 2.8094 | 2.7978 |
| seabed_clearance_mean_m | 4.0207 | 3.1752 | 4.0768 | 3.6660 |
| seabed_clearance_std_m | 0.7941 | 0.0011 | 0.8013 | 0.6232 |
| seabed_clearance_rmse_to_3m | 1.2932 | 0.1752 | 1.3423 | 0.9121 |
| clearance < 1.5m ratio | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| depth_error_rmse_m | 7.0340 | 7.8248 | 7.3466 | 7.3517 |
| speed_mean_mps | 1.1025 | 0.7148 | 1.1028 | 1.0964 |

关键解释：

- terrain-following 主指标是 `seabed_clearance_*`，不是 `depth_error_rmse_m`。
- `constant_depth_m=3.0` 在 terrain 模式中表示目标离底高度 3m，不是绝对深度 3m。
- `PID terrain` 的 clearance RMSE 为 `0.1752m`，是目前最强结果。
- `MPC terrain` 相比 `MPC baseline` 有改善，但 RMSE `0.9121m` 仍明显弱于 PID。

---

## 3. Low/Mid/High Terrain Ablation

**汇总文件**: `results/control/pid_terrain_ablation_20260610_summary.csv`

| 地形档位 | 配置 | RMSE to 3m | mean | std | min | <1.5m ratio | duration |
|---|---|---:|---:|---:|---:|---:|---:|
| low | `bridge_params.protocol_udp.pvs.terrain_low.yaml` | 0.0709m | 3.0218m | 0.0675m | 2.8612m | 0.0 | 28.78s |
| mid | `bridge_params.protocol_udp.pvs.terrain_mid.yaml` | 0.1735m | 3.1735m | 0.0028m | 3.1634m | 0.0 | 28.24s |
| high | `bridge_params.protocol_udp.pvs.terrain_high.yaml` | 0.0586m | 2.9932m | 0.0582m | 2.8765m | 0.0 | 23.21s |

论文可用结论：PID/PVS terrain 在不同地形强度下均能稳定保持约 `3m` 离底高度，且没有安全违规；地形强度 ablation 可作为主线结果的稳健性补充。

---

## 4. 为什么深度/离底高度不用 MPC

### 4.1 控制层定位

本项目中的 MPC 是 **guidance-level reference generator**，输出：

- `psi_cmd`: 目标航向；
- `z_cmd`: 目标深度；
- `T_cmd`: 推力百分比。

MPC 并不直接控制舵面，最终深度与航向仍由 PVS `depthHeadingAutopilot` 执行。因此，MPC 的深度输出会受到低层参考滤波、舵角限制、角速率限制和 PVS 内环动态的共同约束。

### 4.2 深度通道的工程限制

MPC 深度控制不佳不是单一调参问题，而是以下因素叠加：

- **执行链路长**: `MPC z_cmd -> PVS depthHeadingAutopilot -> stern plane -> pitch/heave -> depth`，中间存在内环滤波和物理限幅。
- **模型简化明显**: MPC 内部模型只保留 `[x,y,z,psi,u,w]`，没有完整显式建模 pitch、舵面一阶动态和 PVS 内环状态。
- **符号敏感**: 已修复 `theta_approx = -pitch_depth_gain * depth_err`，但 heave/pitch 的闭环耦合仍难以由简化模型完全刻画。
- **terrain 参考平滑**: 地形跟随目标本身连续平滑，调优后的 PID/PVS v2 与该任务非常匹配，MPC 的预瞄优势不明显。
- **在线求解负担**: 真实 ROS 仿真中曾出现 IPOPT `Maximum_Iterations_Exceeded`，已加 `fail_safe_fallback`，但实时性风险仍高于 PID。

### 4.3 调参结果

| 轮次 | 核心改动 | 结果 | 结论 |
|---|---|---:|---|
| r1 `z80_smooth_free` | `tracking.z=80`、`z_cmd=0.0005`、`delta_z=1.2` | RMSE `0.4741m` | 明显优于原 MPC，但仍弱于 PID |
| r2 `z120_aggressive` | `tracking.z=120`、`z_cmd=0.0002`、`delta_z=1.5` | phase 收尾 timeout | 激进参数不稳定，不保留 |
| r3/r4/r5 quick | heave/pitch boost、tight band、fast horizon | 未形成更优有效结果 | 不保留 |

最终处理：`brain_linux/config/params.yaml` 已恢复到调参前 MPC v2 参数；深度/terrain-following 主线回退 PID/PVS。

### 4.4 【毕设可接受】写法

> 本文实现了 PID/PVS 与 guidance-level MPC 两类控制策略，并在统一的地形跟随仿真平台中进行对比。实验表明，在当前 AUV 低层执行器限制和 PVS 内环结构下，经过参数同步和符号修正后的 MPC 能够改善固定深度策略，但其在线优化输出仍需经过内层深度航向控制器执行，存在模型失配与求解实时性负担。相比之下，针对连续平滑地形参考调优后的 PID/PVS 控制器在离底高度保持任务中取得了更低误差和更稳定响应。因此，本文最终选用 PID/PVS 作为地形跟随主控制方案，将 MPC 作为对照算法和未来可扩展方向。

---

## 5. MPC x/y/yaw 支线实验

### 5.1 支线目标

由于 MPC 在深度控制上不适合作为主线，本支线转向验证 MPC 在平面制导层面的潜在优势：

- `x/y`: 多步路径预瞄，降低急弯/蛇形路径的横向偏差；
- `yaw`: 生成受速率约束的 guidance heading；
- `speed`: 在高曲率段主动降速，这是固定速度 PID 航向跟踪不具备的能力。

### 5.2 实验脚本

**脚本**: `tools/mpc_xy_yaw_extreme_benchmark.py`  
**最新结果目录**: `/auv_data/results/control/mpc_xy_yaw_extreme/20260610_204314/`  
**核心输出**:

- `/auv_data/results/control/mpc_xy_yaw_extreme/20260610_204314/best_comparison.csv`
- `/auv_data/results/control/mpc_xy_yaw_extreme/20260610_204314/summary_metrics.csv`
- `/auv_data/results/control/mpc_xy_yaw_extreme/20260610_204314/figures/`

该 benchmark 构造了三类极端平面路径：

| 场景 | 设计目的 |
|---|---|
| `s_turn_short_wave` | 短波长蛇形路径，考察连续左右急转 |
| `chicane_90deg` | 多个 90° 折线急弯，考察局部预瞄和速度规划 |
| `hairpin_180deg` | 180° 掉头，考察极端曲率下的横向偏差 |

对照控制器：

- `pid_yaw_only_fixed_speed`: 只跟踪局部切线 yaw，固定速度；代表基础 PID 航向控制器不具备路径预瞄时的情况。
- `pid_los_fixed_speed`: 带 LOS 几何预瞄但固定速度；代表更强工程 baseline。
- `mpc_preview_speed`: MPC 使用短时域路径预瞄，并可通过 `T_cmd` 主动调整速度。

### 5.3 MPC 调优轮次

本支线共测试 5 组 MPC 变体：

| 变体 | 目的 |
|---|---|
| `xy_v1_balanced` | 平衡横向、航向和速度代价 |
| `xy_v2_track_hard` | 增强 `x/y` tracking 权重 |
| `xy_v3_speed_flexible` | 降低速度/推力惩罚，允许高曲率段主动减速 |
| `xy_v4_short_realtime` | 缩短 horizon，观察实时性折中 |
| `xy_v5_yaw_strict` | 大幅提高 yaw 权重，测试能否降低航向误差 |

### 5.4 最新结果

> ⚠️ **本表（`20260610_204314`）受 §8.7 所述 harness `+2.0m` 偏置 bug 影响，人为放大了 MPC 横向 RMSE，已被 §8.7 公平口径表（`20260620_011831`）取代。论文请引用 §8.7。**

| 场景 | 最佳 MPC 变体 | PID yaw-only lateral RMSE | LOS lateral RMSE | MPC lateral RMSE | MPC 相对 yaw-only 改善 | PID yaw-only yaw RMSE | MPC yaw RMSE | MPC success | mean solve |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `s_turn_short_wave` | `xy_v3_speed_flexible` | 2.5965m | 1.6574m | 1.6345m | 37.05% | 58.51° | 67.31° | 1.000 | 13.62ms |
| `chicane_90deg` | `xy_v1_balanced` | 3.5961m | 0.6586m | 2.8230m | 21.50% | 44.61° | 30.87° | 1.000 | 9.82ms |
| `hairpin_180deg` | `xy_v3_speed_flexible` | 4.6945m | 4.6925m | 2.8844m | 38.56% | 0.88° | 72.81° | 0.998 | 18.59ms |

### 5.5 结果解释

MPC 支线结论需要限定：

- MPC 对 **yaw-only 固定速度 PID** 的 `x/y` 横向误差有稳定改善，三类极端路径改善约 `21%–39%`。
- MPC 没有全面超过 **带 LOS 预瞄的强 baseline**。在 `s_turn_short_wave` 中 MPC 与 LOS 接近；在 `chicane_90deg` 中 LOS 仍明显更好；在 `hairpin_180deg` 中 MPC 明显优于 LOS。
- `yaw RMSE` 不是所有场景都更低。特别是 hairpin 场景中，MPC 为降低横向偏差会采取切弯/主动速度调整，导致局部切线 yaw 误差变大。因此不能把 MPC 写成“纯航向跟踪优于 PID”。
- 支线更适合支持如下观点：MPC 的优势在于多步路径预瞄、速度规划和复杂路径下的横向误差控制，而不是替代低层 PID/PVS 做深度或纯 yaw 内环控制。

### 5.6 论文可用写法

> 在深度/离底高度控制中，由于 MPC 输出仍需经过 PVS 内层深度航向控制器执行，且地形跟随参考较平滑，调优后的 PID/PVS 取得了更优结果。为进一步分析 MPC 的适用边界，本文构造了短波长蛇形、90° chicane 和 180° hairpin 等平面极端路径。结果表明，MPC 在具备路径预瞄和速度调整能力时，相比仅跟踪局部航向且固定速度的 PID 基线，可降低约 21%–39% 的横向误差；但相对于加入 LOS 几何预瞄的强 baseline，MPC 并非在所有场景中占优。因此，本文将 MPC 定位为复杂路径制导与速度规划的扩展方向，而非深度控制主方案。

---

## 6. 已修复的工程问题

| 问题 | 现象 | 修复 |
|---|---|---|
| MPC 参数未同步到 ROS 仿真 | 离线调参有效，真实仿真仍像默认 MPC | `auv_controller_node.py` 将顶层 `mpc/mpc_model/mpc_weights/mpc_constraints` 注入 `MPCController` |
| ROS z 与 NED depth 混用 | MPC 看到负深度，target depth 为正深度 | 控制状态统一 `depth_ned=-position.z` |
| MPC guidance depth 未下发 | `guidance_depth` 只在 debug，不进入 bridge | `MpcCmd.target_depth_m` 优先使用 `ctrl_output.guidance_depth` |
| pitch/depth 符号错误 | 目标更深时给正 pitch，导致上浮趋势 | `theta_approx = -pitch_depth_gain * depth_err` |
| PVS v2 参数未进真实仿真 | 离线 profile 与 wrapper 不一致 | `sim_params.pvs.yaml` + `pvs_sim_wrapper.py` 同步 v2 参数和舵角限幅 |
| terrain benchmark 没用完整 bridge cfg | 显式传 terrain cfg 后丢失 protocol_udp/zenoh/pvs 段 | 新增完整合并配置 `bridge_params.protocol_udp.pvs.terrain.yaml` |
| 录包错过有效跟踪段 | 每个 phase 都 clean build，brain ready 太晚 | `AUV_SKIP_BRAIN_BUILD=1`，benchmark 预构建一次 |
| PID terrain 缺 diagnostics 后无法分析 | analyzer 直接失败 | `analyze_bag.py` 支持 odom + seabed cloud fallback 和 clearance 指标 |
| MPC 求解失败杀死节点 | IPOPT 失败抛出 RuntimeError | `MPCController` 增加 `fail_safe_fallback` |
| Mock AMD time timeout 刷屏 | 协议时间戳键/范围不一致 | 协议侧使用相对单调微秒，决策侧兼容键并只提示一次 |

---

## 7. 推荐论文结构

- **主实验**: terrain-following 使用 `PID/PVS terrain`，给出 60s 四组 benchmark 和 low/mid/high ablation。
- **对照实验**: `MPC terrain` 说明已接入、可改善 baseline，但受执行链路和实时性限制，没有超过 PID/PVS。
- **支线分析**: `MPC x/y/yaw extreme benchmark` 说明 MPC 在复杂平面路径预瞄和速度规划中有优势，但优势边界清晰。
- **未来工作**: 若要让 MPC 成为主控制器，需要把 MPC 从 guidance-level 下沉到更接近舵面/动力学层，或显式建模 PVS 内环状态和执行器动态。

---

## 8. 自洽性提升闭环（2026-06-20 更新）

> 本节记录"实验深入挑刺与自洽性提升"阶段的修复始末。**核心结论：早先 §2 的 terrain 主结果表（`20260610_175154`，`clearance_mean≈4.0m`、`depth_error_rmse≈7m`）受一个度量层 datum bug 污染，已被 P0 真口径重跑（`20260619_222639`）取代。** 控制器本身未发散，问题在分析/度量层。

### 8.1 度量 datum bug 的发现与修复（P0-1）

- **现象**：旧 summary 的 `seabed_clearance_mean_m≈4.0m`（远离 3m 目标）且四相高度一致、`depth_error_rmse_m≈7m` 巨大 → 被误读为"控制器跟踪失败/上漂"。
- **根因**：[analyze_bag.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/analyze_bag.py) 离底高度此前回退到一个**常值 datum**（固定海底基准）而非真实测高，使 clearance 恒偏；`depth_error_rmse_m` 又对 terrain 模式按"绝对目标深度"评分（但 terrain 模式目标深度随海底动态变化，该口径无意义）。
- **修复**：clearance 真值优先级改为 `real_altitude（/auv/sensors/altitude）> terrain_cloud（真点云）> diag_constant_datum`，并新增 `clearance_source` 审计字段；terrain 模式 `depth_error_rmse_m` 标 `nan`（N/A），另存 `depth_error_rmse_diag_m` 仅作审计。实测真测高 mean≈2.83m，证明此前 4.0m 系 datum 假象。

### 8.2 P0 真口径重跑主结果（取代 §2 旧表）

**结果目录**: `results/control/terrain_following_20260619_222639/`（warm-up 跳过 10s、truth-topic 四相统一 `/auv/sensors/ground_truth`、clearance 源 `real_altitude`）

| 指标 | PID baseline | PID terrain | MPC baseline | MPC terrain |
|---|---:|---:|---:|---:|
| duration_s | 59.11 | 59.80 | 59.50 | 59.51 |
| clearance_source | real_altitude | real_altitude | real_altitude | real_altitude |
| seabed_clearance_min_m | 1.600 | 1.000 | 1.400 | 1.400 |
| seabed_clearance_mean_m | 2.699 | 1.954 | 2.657 | 2.647 |
| seabed_clearance_std_m | 0.470 | 0.442 | 0.495 | 0.500 |
| seabed_clearance_rmse_to_3m | 0.558 | 1.136 | 0.602 | 0.612 |
| depth_error_rmse_m | 6.493 | **N/A** | 6.427 | **N/A** |
| depth_error_rmse_diag_m（仅审计） | 6.493 | 7.292 | 6.427 | 6.416 |
| speed_mean_mps | 1.112 | 0.724 | 1.112 | 1.112 |
| solve_time_mean_ms | nan | nan | 12.93 | 10.59 |
| solver_fallback_ratio | nan | nan | 0.000 | **0.1429** |
| truth_topic_used | ground_truth | ground_truth | ground_truth | ground_truth |

> ⚠️ **n=1 诚实边界（P2-a）**：本地形基准每相为**单次运行**（[run_terrain_benchmark.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_terrain_benchmark.sh) 仅 controllers×modes 循环、无重复/平均），统计置信有限，后续应补 ≥3 次重复给出 mean±std。引用本表时须标注 n=1。

关键解读（真口径）：
- 真测高下四相 `clearance_mean` 落在 1.95–2.70m，**不再是 4.0m 常值 datum**；clearance 随真地形起伏（`std≈0.44–0.50m`）。
- terrain 模式主指标仍是 `seabed_clearance_rmse_to_3m`，`depth_error_rmse_m` 正确标 N/A。
- 本次重跑中 PID/MPC terrain 的 clearance RMSE 接近（受 n=1 与本批配置影响），**不应过度解读相对优劣**；地形跟随能力的稳健结论以 low/mid/high ablation（§3）为准。

### 8.3 真 solve_time 实测（P0-2）

- **系统级**：rerun bag `/auv/controller/debug.solve_time_ms` 实测 mpc_baseline mean≈12.93ms、mpc_terrain mean≈10.59ms（此前 solve_time≈0ms 是未抽取真字段的假象）。
- **微基准**：[tools/mpc_solve_microbench.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mpc_solve_microbench.py) cold solver_internal mean≈10.77ms/p95≈11.35ms、warm≈4.88ms/p95≈5.0ms，与系统级 ≈10.6ms 互证。两口径自洽，论文 §5 统一引用真值。

### 8.4 solver_fallback 14.3%（P0-1 副产物，诚实记录）

mpc_terrain 相 **14.3% 步触发 `FALLBACK_LAST_OUTPUT`**。根因：`z_band=4.0m`/`delta_z_max_per_step=1.0m` 等带宽/速率约束在起始深度与目标差距过大（8m→3m）时求解不可行 → 与微基准 `--start-depth 8.0` 复现一致。这是 MPC 在大初始失配下的真实工程边界，须诚实记录而非隐藏。

### 8.5 WP-C 深度补偿回查结论（P0-3，保留 + 重写注释）

离线 A/B（[tools/wp_c_depth_ab.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/wp_c_depth_ab.py)）证明：现实浮力（−0.5~−2.0）A/B 均 sub-mm、plant 中性 A 不引入偏置、仅 8× 失配（−4.0）B 退化~14mm 而 A 保持 <1mm → WP-C 补偿为**良性鲁棒裕度**。原"≈0.02m/s 上漂"依据系 datum bug 误导，已推翻。**参数值不变**（`buoyancy_term=-0.5`/`ki_z=0.1`/`clamp=2.0`），仅将 [params.yaml L116-134](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/params.yaml#L116-L134) 注释重写为基于 A/B 实证的诚实物理依据。

### 8.6 闭环 vs "开挂真值"澄清（D8）

此前担忧的"控制器用了真值开挂"系误解。控制状态来源未改：估计链路正常走 ES-EKF/PVS，`/auv/sensors/ground_truth` **仅用于离线分析的误差评分基准**（truth-topic），不进入控制回路。本节仅作文档澄清，不改控制器状态来源。truth-topic 四相已统一到 `/auv/sensors/ground_truth`（P0-4，消除此前多 topic 混入 + first-arrived bug）。

### 8.7 WP-E：平面路径公平口径结论（取代 §5.4 旧表）

§5 的 MPC x/y/yaw 支线 harness 存在一个**真实不公平 bug**：`run_mpc` 参考构建含 `+2.0m` 常值下游偏置，把整条参考（含 k=0）推到最近点下游、迫使 MPC 切弯、人为放大其横向 RMSE；而两条 PID 基线（yaw-only 读精确最近切线、LOS 从当前位置前瞻）无此偏置 → 对比不公平。删除 `+2.0` 偏置（保留 `k*v*dt` 真预瞄项）后公平复跑（`20260620_011831`，5 variant 一致非偶然）：

| 场景 | MPC best lateral | yaw-only | LOS | 结论 |
|---|---:|---:|---:|---|
| `s_turn_long_wave`（60m/7m） | **0.055m** | 0.093 | 1.047 | MPC 全胜（−41% / −95%） |
| `hairpin_180deg` | **2.277m** | 4.69 | 4.69 | MPC 全胜（−51%） |
| `s_turn_short_wave` | 1.655m | 2.597 | 1.657 | MPC −36% vs yaw-only、与 LOS 持平 |
| `chicane_90deg` | 1.452m | 3.596 | **0.659m** | 诚实边界：直角 chicane 上 LOS 前瞻最优 |

**诚实结论**：公平口径下 MPC 在长波 S 弯、急转 hairpin、短波 S 弯三类工况均优于或持平基线；唯直角 chicane 上 LOS 前瞻更贴合分段直线。早先"MPC 不普遍优于基线"的判断源自 harness 的 +2.0m 偏置 bug，修复后已被推翻——但 chicane 这一诚实边界予以保留，不做过度宣称。

### 8.8 P1/P2 诚实边界声明汇总

- **磁通道空（P1-a）**：地形跟随实验**不含磁场采集链路**（[run_terrain_benchmark.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_terrain_benchmark.sh) 无磁 plumbing；summary `magnetic_sample_count=0`/`magnetic_peak_t=nan`）。这是设计如此，磁指纹证据见 F1 三相螺旋漏磁实验与论文第 3 章，不补采集。
- **extrinsics seed（P1-b）**：[es_ekf_extrinsics_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/es_ekf_extrinsics_benchmark.py) `--seeds` 默认已改为 `0,1,2`（3-seed 内建默认）；F2 结果按 3 seed 报告并附 `*_std`。
- **n=1（P2-a）**：见 §8.2 警示——地形基准单次运行，须标注。
- **双 INDEX 树（P2-b）**：`docs/thesis/INDEX.md`（工程证据层）与 `docs/thesis/paper/INDEX.md`（论文正文层）为两棵职责不同的平行树，已在各自 INDEX 标注主/从定位；`05_experiments_and_discussion.md` 与 `..._continued.md` 的续写关系已在 paper INDEX 标注。

---

## 9. 原生 PVS 深度内环与地形跟随最终复核（2026-08-23）

### 9.1 当前正式四相

正式结果目录为 `results/control/terrain_following_20260823_215036`。PID/MPC 的 baseline/terrain 四相使用相同初始深度、确定性地形、1.5 m/s 速度设定与 `0xEE` 深度—航向内环，并统一经 `/auv/control/mpc_cmd → arbiter → binary protocol → Mock AMD → PVS` 执行。统计跳过起始 10 s；净空来自 DVL，实际深度和三维轨迹来自 `/auv/sensors/ground_truth`，PVS 可行参考 $z_d$、舵角和积分状态来自 `pvs_control_trace.csv`。该批 bag 的 `/auv/diagnostics` 消息数为零，合成 diagnostics 不作为控制性能证据。

| 指标 | PID baseline | PID terrain | MPC baseline | MPC terrain |
|---|---:|---:|---:|---:|
| 最小净空（m） | 0.100 | 2.200 | 1.000 | 1.700 |
| 净空 RMSE（m） | 1.225 | 0.419 | 1.091 | 0.605 |
| PVS $z_d\rightarrow z$ RMSE（m） | 0.524 | 0.217 | 0.113 | 0.197 |
| 艉舵原始命令饱和率 | 0.4868 | 0.1859 | 0.0396 | 0.2159 |
| `<1.5 m` 比例 | 0.1977 | 0.0000 | 0.1474 | 0.0000 |
| MPC fallback | — | — | 0.0000 | 0.0000 |

固定 12 m 绝对深度不能替代地形跟随；两类 terrain 相均守住 1.5 m 阈值。PID terrain 的净空 RMSE 小于本次 MPC terrain，但两者相对同一 PVS 可行参考的内环 RMSE 均约为 0.2 m，因此差异主要来自制导参考与安全过滤层，而不是 PID 少经过一级内环。

### 9.2 PVS 迟钝根因与修改边界

严格原生默认参数为 `Kp_z=0.1`、`wn_d_z=0.02 rad/s`、`deltaMax=15 deg`。默认深度参考低通、级联增益、舵限与无 anti-windup 共同造成低带宽；此外旧链还叠加了启动零深度、低正值 RPM 被映射为停车、配置未加载、MPC guidance 未下发和 CBF 停车导致舵效丢失等问题。最终采用任务匹配 profile `Kp_z=1.0`、`wn_d_z=0.4 rad/s`、`Kp_theta=6.0`、`Kd_theta=2.0`、`Ki_theta=1.5`、`deltaMax=20 deg`，并在本地 adapter 加入积分冻结与限幅。上游 `/root/PythonVehicleSimulator` 源码未修改。

严格原生与任务匹配 profile 的深度 RMSE 为：阶跃 `3.491 → 1.453 m`，正弦 `1.132 → 0.202 m`；相对 PVS 可行参考的调优后 RMSE 分别为 0.345 m 和 0.049 m。该对照说明默认控制迟钝主要由参考模型带宽与执行包线共同形成，不应归因于单一比例增益。

### 9.3 图像与重跑判定

- 图 4.7 已改为严格原生默认和两套任务匹配 profile 的同对象对照；旧图把调过增益的 profile 标成默认基线，已废止。
- 图 5.2 已显示海底、3 m 几何目标、实际下发命令、PVS 可行参考和 AUV 真值深度五层信号；所有图例为不透明白底。
- 图 5.3 已由带近常量偏置的滤波轨迹改为 PVS 真值轨迹；重建海床与 DVL 沿程海床由 `r=0.94`、RMS `0.39 m` 改善为 `r=1.00`、RMS `0.03 m`。
- 当前图 5.4 为 R13-v2 三联图，不是地形曲线；其三个源图的 legend 也已统一为不透明白底。
- 图 5.2、图 5.3 与表 5.8 无需再重跑，当前单次四相足以支撑执行链和典型响应。
- 若论文要声称当前调优原生 PVS 配置具有稳健统计优势，仍需对 PID/MPC terrain 至少各补三次重复。既有低/中/高三档多种子矩阵使用 `kinematic_setpoint` 后端，只证明地形参考与安全过滤层，不能替代原生 PVS 多次重复。
