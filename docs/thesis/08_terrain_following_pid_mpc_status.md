# 地形跟随 PID/MPC 当前状态与 MPC 支线结论

**日期**: 2026-06-10  
**定位**: 固化地形跟随实验、PID/PVS 与 guidance-level MPC 对比、MPC 深度控制回退理由，以及 MPC 在 `x/y/yaw` 平面制导层面的补充优势分析。

---

## 1. 总结

- **地形跟随主线**: 采用 `PID/PVS terrain`。该方案在 60s terrain benchmark 和 low/mid/high ablation 中均能稳定保持约 `3m` 离底高度，且无 `<1.5m` 安全违规。
- **MPC 支线**: 不再把 MPC 作为深度/离底高度主控制器；保留 MPC 作为 `guidance-level reference generator`，用于说明其在复杂平面路径、预瞄路径跟踪和速度规划中的潜在价值。
- **论文边界**: MPC 不是完全失败，它已经接入真实仿真闭环，也能改善部分 baseline；但在当前低层执行器限制、PVS 内环滤波和在线求解负担下，深度控制/terrain-following 指标没有超过调优后的 PID/PVS。

---

## 2. Terrain Benchmark 主结果

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
