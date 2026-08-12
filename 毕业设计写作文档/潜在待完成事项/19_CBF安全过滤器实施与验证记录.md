# 19 CBF 安全过滤器实施与验证记录

## 目标

本轮目标是针对极端场景中的海底净空安全违约，增加一个不改变任务门限、不绕过置信度链路的控制安全层。实现口径为 guidance-level CBF filter：先对 terrain following 生成的候选深度进行安全过滤，再把 CBF 状态写入 controller debug，供后续 MCAP 审计使用。

## 已实施内容

1. `TerrainFollower` 增加 previewed seabed CBF：
   - barrier 定义为 `h = seabed_depth - depth - min_clearance`；
   - 海床深度取当前估计 `S_now` 与预瞄估计 `S_future` 中更保守者；
   - 在接近 barrier 时限制最大下潜速率；
   - 在低于 emergency clearance 时强制上浮；
   - 当净空已经远大于安全裕度时，不再长期保持过大的 barrier，避免把任务深度压到浅水。

2. 增加 CBF 速度门控：
   - 当前或预瞄 barrier 接近净空边界时，线性降低 `target_speed_mps`；
   - emergency clearance 下速度目标归零；
   - 速度缩放写入 `terrain_debug` 与 `/auv/controller/debug`。

3. 接入配置：
   - `brain_linux/config/params.yaml`
   - `brain_linux/config/params.protocol_udp_arbiter.yaml`
   - 默认 `min_clearance_m = 1.8`，高于分析指标中的 1.5 m 安全阈值。

4. 修复 protocol/PVS 代理中的 0 m/s 语义：
   - Mock AMD 不再把 `target_speed_mps == 0` 解释为“保持上一速度”；
   - PVS wrapper 中 `speed_mps <= 0` 映射为 `reference_rpm = 0`，正速度才使用最小 RPM。

## 验证结果

已通过：

```text
10 passed
```

覆盖测试包括：

1. 前视地形变浅时限制深度目标；
2. barrier 附近限制过快下潜；
3. 低净空 emergency rise；
4. 净空很大时不再把目标深度长期压在浅水。

构建与语法检查已通过：

```text
colcon build --packages-select auv_controller --symlink-install
py_compile terrain_engine.py / auv_controller_node.py / mock_amd_server.py / pvs_sim_wrapper.py
```

## Smoke 观察

`terrain_high` 原 native PVS 路径下，CBF debug 生效，但车辆深度执行链不能稳定跟随 depth setpoint，因此该 smoke 不能用于评价 CBF 是否真正消除违约。观测到的现象是 target depth 已经上浮，但真实 depth 长时间固定或执行异常，安全违约主要来自仿真执行链而不是 CBF 公式。

尝试临时把 `terrain_high` 改为 kinematic setpoint 后，安全指标可降到 0，但 depth sensor 全程贴近 0 m、净空 13 m 以上，属于无效验证；该配置改动已撤回。

`combined_cable_extreme_proxy` 30 s full-flow baseline smoke 可正常完成，fallback 为 0，solver p95 约 9.47 ms，安全指标为 0。但本次短 smoke 的 `analyze_bag.py` 只能合成 diagnostics，且显示净空偏大，因此只能作为“未破坏运行链路”的冒烟证据，不能单独宣传为 CBF 正式消除安全违约。

## terrain_high 可信执行链修复

本次修复目标是让 `terrain_high` 的安全验证不再依赖行为树状态抖动或错误 depth 口径。修复后采用 `/auv/manual/setpoint` 固定发布 terrain-following 目标，decision node 通过 `bypass_to_manual_setpoint=true` 转发到 controller，controller 输出的 `target_depth_m` 经 protocol UDP Para1 传给 Mock AMD，再由 PVS kinematic setpoint proxy 执行。

关键修复点：

1. Mock AMD 下行解析改为缓存 `parse_downlink_packet()` 的 `ProtocolDownlinkState`，depth、heading 和 RPM 反推速度均以统一解析结果为准；
2. signed RPM 不再取绝对值，负 RPM 或低于 `reference_rpm_min` 的命令不会被反推成正向速度；
3. `common.protocol.build_downlink_packet()` 支持直接从 dict payload 读取 `target_depth_m`，避免底层调用时 Para1 被默认 0 覆盖；
4. `CommandArbiter._normalize_mpc_command()` 保留 `target_depth_m`，避免 autonomous payload 在仲裁后丢失 depth setpoint；
5. `terrain_high` PVS 配置切换为 `depthHeadingAutopilot + kinematic_setpoint`，并将初始速度/流速置 0，用于验证 setpoint 执行链；
6. `scripts/run_terrain_benchmark.sh` 增加可选 manual terrain setpoint driver，并补齐残留 PVS 进程清理规则。

补充验证：

```text
tests/test_protocol_contract.py tests/test_mock_amd_server.py brain_linux/src/auv_bridge/test/test_arbiter.py
32 passed

brain_linux/src/auv_controller/test/test_terrain_engine_cbf.py
10 passed

colcon build --packages-select auv_bridge auv_controller --symlink-install
2 packages finished
```

## terrain_high CBF 小矩阵结果

运行配置：

```text
AUV_TERRAIN_MANUAL_SETPOINT=true
AUV_TERRAIN_ENABLE_BEHAVIOR_TREE=false
AUV_TERRAIN_TARGET_ALTITUDE_M=3.0
AUV_TERRAIN_TARGET_SPEED_MPS=0.4
bash scripts/run_terrain_benchmark.sh 30 {pid,mpc} terrain high
```

结果目录：

```text
PID: results/control/terrain_following_20260810_140727/pid_terrain
MPC: results/control/terrain_following_20260810_140845/mpc_terrain
```

| run | duration s | clearance min m | clearance mean m | clearance RMSE to 3m | safety violation 1.5m | penetration | depth RMSE diag m | CBF active samples | speed scale range | solver p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PID terrain_high CBF | 29.56 | 2.70 | 2.88 | 0.138 | 0.0 | 0.0 | 0.528 | 46 / 577 | 0.37-1.00 | n/a |
| MPC terrain_high CBF | 29.61 | 2.70 | 3.25 | 0.455 | 0.0 | 0.0 | 1.075 | 145 / 593 | 0.20-1.00 | 17.94 |

## terrain_high CBF 60 s 复核

按上一节相同执行链和 manual setpoint bypass，将 `terrain_high × {PID,MPC}` 从约
30 s 延长到 60 s：

```text
AUV_TERRAIN_MANUAL_SETPOINT=true
AUV_TERRAIN_ENABLE_BEHAVIOR_TREE=false
AUV_TERRAIN_TARGET_ALTITUDE_M=3.0
AUV_TERRAIN_TARGET_SPEED_MPS=0.4
bash scripts/run_terrain_benchmark.sh 60 both terrain high
```

结果目录：

```text
results/control/terrain_following_20260810_144704
PID bag: /auv_data/bags/20260810_144717
MPC bag: /auv_data/bags/20260810_144846
```

汇总文件：

```text
results/control/terrain_following_20260810_144704/cbf_terrain_recheck_summary.csv
results/control/terrain_following_20260810_144704/cbf_terrain_recheck_summary.json
results/control/terrain_following_20260810_144704/cbf_terrain_recheck_report.md
```

| run | duration s | clearance min m | clearance mean m | clearance RMSE to 3m | safety violation 1.5m | penetration | depth RMSE diag m | CBF active samples | speed scale range | solver p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PID terrain_high CBF 60 s | 59.22 | 2.70 | 3.07 | 0.361 | 0.0 | 0.0 | 0.861 | 17 / 119 | 0.395-1.000 | n/a |
| MPC terrain_high CBF 60 s | 59.55 | 2.70 | 3.25 | 0.435 | 0.0 | 0.0 | 0.922 | 31 / 120 | 0.107-1.000 | 21.44 |

本次复核说明 30 s 小矩阵不是单纯启动瞬态：延长到 60 s 后，PID 与 MPC 仍保持
最小净空 2.70 m，1.5 m 低净空违规率和海床穿透率均为 0。CBF speed gate 仍有实际
作用，MPC 最低 speed scale 进一步降至约 0.107。负边界也更清楚：MPC p95 求解时间
升至 21.44 ms，仍不能写成满足 10 ms 实时目标。

## terrain low/mid/high CBF 60 s 单 seed 矩阵

在确认 `terrain_high` 60 s 复核后，将同一可信执行链扩展到 low/mid/high 三档地形。
为保持执行链一致，`terrain_low` 与 `terrain_mid` 配置也对齐到
`depthHeadingAutopilot + kinematic_setpoint`，并将初始速度和横流设为 0；地形幅值、
尺度、octave 和坡度仍保留各自 low/mid/high 因子。

运行命令：

```text
AUV_BENCHMARK_SKIP_PREBUILD=1
AUV_TERRAIN_MANUAL_SETPOINT=true
AUV_TERRAIN_ENABLE_BEHAVIOR_TREE=false
AUV_TERRAIN_TARGET_ALTITUDE_M=3.0
AUV_TERRAIN_TARGET_SPEED_MPS=0.4
bash scripts/run_terrain_benchmark.sh 60 both terrain low
bash scripts/run_terrain_benchmark.sh 60 both terrain mid
```

矩阵汇总文件：

```text
results/control/cbf_terrain_matrix_20260810_145822/cbf_terrain_recheck_summary.csv
results/control/cbf_terrain_matrix_20260810_145822/cbf_terrain_recheck_summary.json
results/control/cbf_terrain_matrix_20260810_145822/cbf_terrain_recheck_report.md
```

| run | duration s | clearance min m | clearance mean m | clearance RMSE to 3m | safety violation 1.5m | penetration | depth RMSE diag m | CBF active samples | speed scale range | solver p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PID terrain_low CBF 60 s | 59.17 | 2.90 | 3.09 | 0.185 | 0.0 | 0.0 | 0.363 | 49 / 118 | 0.648-1.000 | n/a |
| MPC terrain_low CBF 60 s | 59.72 | 2.90 | 3.09 | 0.170 | 0.0 | 0.0 | 0.276 | 63 / 119 | 0.587-1.000 | 22.87 |
| PID terrain_mid CBF 60 s | 59.85 | 2.80 | 3.11 | 0.267 | 0.0 | 0.0 | 0.359 | 33 / 120 | 0.581-1.000 | n/a |
| MPC terrain_mid CBF 60 s | 59.92 | 2.80 | 3.08 | 0.264 | 0.0 | 0.0 | 0.588 | 38 / 120 | 0.469-1.000 | 25.12 |
| PID terrain_high CBF 60 s | 59.22 | 2.70 | 3.07 | 0.361 | 0.0 | 0.0 | 0.861 | 17 / 119 | 0.395-1.000 | n/a |
| MPC terrain_high CBF 60 s | 59.55 | 2.70 | 3.25 | 0.435 | 0.0 | 0.0 | 0.922 | 31 / 120 | 0.107-1.000 | 21.44 |

该矩阵说明，在 manual setpoint bypass 与 kinematic setpoint proxy 的统一口径下，
low/mid/high 三档 60 s 单 seed 共 6 个 run 均保持 1.5 m 低净空违规率为 0、海床穿透率为
0，最小净空随地形强度从 2.90 m 降至 2.70 m。CBF speed gate 在六个 run 中均有实际触发。
负边界同步保留：MPC p95 为 21.44--25.12 ms，最差出现在 `terrain_mid`，不能宣传为
10 ms 实时目标内。

执行链可信性审计：

1. depth sensor 不再贴近 0 m，low/mid/high 的稳态净空均回到 3 m 目标附近；
2. `/auv/control/setpoint` 固定为目标离底 3.0 m，controller 输出的 filtered depth 进入 Mock AMD 后，PVS depth 随 setpoint 回到 11-13 m 区间；
3. 稳态净空接近目标 3 m，且 1.5 m safety violation 与 seabed penetration 均为 0；
4. CBF speed gate 有实际作用，60 s 全矩阵 speed scale 最低约 0.107；
5. MPC solver fallback 为 0，但 60 s 全矩阵 p95 为 21.44--25.12 ms，超过 10 ms 实时目标，需在后续宣传中单独标注为性能边界。

## 当前结论边界

可以说：

1. 已完成 CBF guidance filter、预瞄 barrier、低净空上浮、速度门控与诊断字段；
2. 单元级数学行为通过测试；
3. protocol/PVS 对 0 m/s 停车语义、target depth Para1 传递和 signed RPM 反推速度的明显问题已修复；
4. `terrain_low/mid/high` 在可信 kinematic setpoint proxy 下完成 PID/MPC 60 s 单 seed 矩阵，安全违约率与海床穿透率均为 0；
5. combined full-flow 短 smoke 未引入 solver fallback 回归。

暂时不能说：

1. CBF 已经正式消除所有极端场景安全违约；
2. CBF 后多 seed 矩阵或 native PVS depthHeadingAutopilot 执行链已经完成；
3. native PVS depthHeadingAutopilot 路径已经可信修复；
4. CBF 改善了跟踪精度或任务完成率。

## 后续建议

下一步不要继续堆叠 CBF 参数，而应把验证边界转为多 seed、原生执行链或 R22 闭环：

1. 若继续补 CBF，只做 low/mid/high 多 seed 复核或 native PVS depthHeadingAutopilot 专项验证，不再重复单 seed low/mid/high；
2. 对 MPC 继续做实时性审计，当前 60 s 全矩阵 p95 为 21.44--25.12 ms，不能直接宣传 10 ms 实时性；
3. 论文主线可将 low/mid/high 60 s 单 seed 矩阵写为 CBF 安全性补强，但必须标注 manual setpoint/kinematic proxy、single seed 和 MPC 实时性边界；
4. 对 native PVS depthHeadingAutopilot 另立问题，不与本次 kinematic setpoint proxy 的安全结果混写；
5. R22 原生声磁--地形--横流闭环仍是单独缺口，不由 CBF terrain 复核替代。
