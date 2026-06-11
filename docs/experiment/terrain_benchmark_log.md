# Terrain Following Benchmark 最新运行日志

**日期**: 2026-06-10  
**定位**: 记录 terrain-following benchmark、MPC 深度调参、PID terrain ablation、Mock AMD 降噪，以及 MPC `x/y/yaw` 支线实验的真实命令、结果和坑点。论文侧总结见 [docs/thesis/08_terrain_following_pid_mpc_status.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/08_terrain_following_pid_mpc_status.md)。

---

## 1. 可用命令

### 1.1 正式四组 benchmark

```bash
cd /home/auv_user/auv_ws/AUV-Master-Project
bash scripts/preflight_clean.sh --quiet
bash scripts/run_terrain_benchmark.sh 60 both both_modes
```

输出结构：

```text
results/control/terrain_following_<timestamp>/
  pid_baseline/
  pid_terrain/
  mpc_baseline/
  mpc_terrain/
```

### 1.2 单独跑某一组

```bash
bash scripts/preflight_clean.sh --quiet
bash scripts/run_terrain_benchmark.sh 30 pid terrain
bash scripts/run_terrain_benchmark.sh 30 mpc terrain
```

### 1.3 指定地形配置

```bash
TERRAIN_BRIDGE_CFG=config/bridge_params.protocol_udp.pvs.terrain_high.yaml \
  bash scripts/run_terrain_benchmark.sh 30 pid terrain
```

注意：不要单独传旧的 `config/bridge_params_terrain.yaml`，它只有 `digital_twin` 覆盖项，缺少 `protocol_udp / zenoh / pvs` 完整段。

### 1.4 MPC x/y/yaw 支线

```bash
python3 tools/mpc_xy_yaw_extreme_benchmark.py
```

输出目录默认在：

```text
/auv_data/results/control/mpc_xy_yaw_extreme/<timestamp>/
```

---

## 2. 60s Terrain 正式结果

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

解读：

- `PID terrain` 是主结果，clearance RMSE `0.1752m`。
- `MPC terrain` 相比 `MPC baseline` 有改善，但未超过 PID terrain。
- terrain 模式主指标是 `seabed_clearance_*`，不要用 `depth_error_rmse_m` 作为论文主指标。

---

## 3. Low/Mid/High Ablation

**汇总文件**: `results/control/pid_terrain_ablation_20260610_summary.csv`

| terrain | result_dir | RMSE to 3m | mean | std | min | <1.5m ratio |
|---|---|---:|---:|---:|---:|---:|
| low | `results/control/terrain_following_20260610_190741` | 0.0709m | 3.0218m | 0.0675m | 2.8612m | 0.0 |
| mid | `results/control/terrain_following_20260610_191113` | 0.1735m | 3.1735m | 0.0028m | 3.1634m | 0.0 |
| high | `results/control/terrain_following_20260610_191446` | 0.0586m | 2.9932m | 0.0582m | 2.8765m | 0.0 |

三档均无安全违规，可作为论文地形强度消融表。

---

## 4. MPC 深度调参记录

目标：尝试把 `MPC terrain` 的 clearance RMSE 从 `0.9121m` 拉近到 `PID terrain` 的 `0.1752m`。

| 轮次 | 核心改动 | 结果 | 结论 |
|---|---|---:|---|
| r1 `z80_smooth_free` | `tracking.z=80`、`z_cmd=0.0005`、`delta_z=1.2` | RMSE `0.4741m` | 明显改善，但仍弱于 PID |
| r2 `z120_aggressive` | `tracking.z=120`、`z_cmd=0.0002`、`delta_z=1.5` | phase 收尾 timeout | 不保留 |
| r3/r4/r5 quick | heave/pitch boost、tight band、fast horizon | 未形成更优有效结果 | 不保留 |

工程修复：`MPCController` 已增加 `fail_safe_fallback`。IPOPT 失败时不再杀死控制节点，而是回退到上一帧有效输出或当前 setpoint。

最终策略：`brain_linux/config/params.yaml` 已恢复到调参前 MPC v2；terrain-following 主线回退 PID/PVS。

---

## 5. MPC x/y/yaw 支线

**脚本**: `tools/mpc_xy_yaw_extreme_benchmark.py`  
**最新输出**: `/auv_data/results/control/mpc_xy_yaw_extreme/20260610_204314/`

测试目的：在深度 MPC 不适合作为主线后，验证 MPC 是否能在平面路径制导中体现优势。该脚本构造了 PID yaw-only 固定速度不擅长的极端场景：

- `s_turn_short_wave`: 短波长连续 S 弯；
- `chicane_90deg`: 多个 90° 折线急弯；
- `hairpin_180deg`: 180° 掉头。

对照控制器：

- `pid_yaw_only_fixed_speed`: 只跟踪局部切线 yaw，固定速度；
- `pid_los_fixed_speed`: 带 LOS 几何预瞄但固定速度；
- `mpc_preview_speed`: MPC 使用路径预瞄并可调整速度。

最佳结果：

| 场景 | 最佳 MPC | PID yaw-only lateral RMSE | LOS lateral RMSE | MPC lateral RMSE | MPC 相对 yaw-only 改善 | MPC mean solve |
|---|---|---:|---:|---:|---:|---:|
| `s_turn_short_wave` | `xy_v3_speed_flexible` | 2.5965m | 1.6574m | 1.6345m | 37.05% | 13.62ms |
| `chicane_90deg` | `xy_v1_balanced` | 3.5961m | 0.6586m | 2.8230m | 21.50% | 9.82ms |
| `hairpin_180deg` | `xy_v3_speed_flexible` | 4.6945m | 4.6925m | 2.8844m | 38.56% | 18.59ms |

结论：

- MPC 对 yaw-only 固定速度 PID 的 `x/y` 横向误差有稳定改善。
- MPC 没有全面超过带 LOS 预瞄的强 baseline，尤其 `chicane_90deg` 中 LOS 更好。
- `yaw RMSE` 不应作为“全面优于 PID”的证据；MPC 在某些场景会为降低横向误差而切弯，导致局部切线 yaw 误差上升。

---

## 6. 已踩坑与修复

| 坑 | 现象 | 修复 |
|---|---|---|
| bridge cfg 不完整 | terrain cfg 单独使用后丢失 protocol_udp/zenoh/pvs | 新增 `bridge_params.protocol_udp.pvs.terrain*.yaml` |
| lean bag 缺 seabed cloud | 无法恢复 clearance | benchmark 使用 `--lean-bag-visual` |
| diagnostics 缺失 | analyzer 直接失败 | `analyze_bag.py` 支持 odom + seabed cloud fallback |
| PID readiness topic 错 | PID phase 等 `/auv/control/mpc_cmd` 超时 | PID baseline 等 `/cmd_vel`，MPC/terrain 等 `/auv/control/mpc_cmd` |
| IPOPT 求解失败杀节点 | `auv_controller_node` 退出 | `MPCController.fail_safe_fallback` |
| Mock AMD time timeout 刷屏 | 日志噪声大 | 相对单调微秒 + fallback 只提示一次 |

---

## 7. 论文建议

- terrain-following 主线写 `PID/PVS terrain`。
- MPC 深度写成“实现并验证，但受内环执行链路、模型失配和实时性限制，不作为主方案”。
- MPC 支线写成“复杂平面路径制导和速度规划具有潜在优势，但相对 LOS 强 baseline 并非全面胜出”。
- 避免写成“MPC 全面优于 PID”；应写成“不同控制层级和任务类型下的适用边界”。
