> **2026-10-23 当前入口**：[尺寸、分页、正文润色与遗失输入保留记录](20261023/README.md)。以下为 2026-10-22 历史验收，当前状态与重跑命令以上述入口为准。

# 全仓图像展示性治理记录

当前状态 **NEEDS_REVIEW**。本轮修改图源/生成器/正式图像，保留研究数据、数值和结论；用户暂缓项及无法重绘项未提升为通过。

- 范围：32 个当前原生源 / 34 页；48 个论文图组 / 54 次实际插入。冻结历史 21 份保留。
- 原生页状态：`{'PASS_POLISH': 34}`；论文资产：`{'PASS_POLISH': 42, 'USER_DEFERRED_INPUTS': 11}`。
- 论文：180 页；48 个含图物理页逐张打开。最终页面哈希须与 [看图记录](paper_visual_review.json) 相符。
- 追加式备份 309 文件，校验 `True`；两份嵌套扩展开销旧副本采用用户认可的旧主图恢复基线，并未声称取得原嵌套副本。

## 重跑与只读验收

```sh
python3 tools/figure-polish/workflow.py run
python3 tools/figure-polish/workflow.py verify
```

第一条只重放已有缓存绘图，含备份、自测、生成器、原生导出、候选图像哈希门、论文构建和 fresh 验收；不运行仿真/逆解。第二条不改图源、正式产物、研究输入或论文 PDF，仅生成复检证据并验证前后哈希。退出码 2 表示尚有待复核/用户暂缓项，不能解释为全量通过。

## 本轮口径和工具

- [POLICY.md](POLICY.md)：用户允许最小字号妥协，9 pt 作为建议；仍禁止遮字、溢出、改数值和宽泛豁免。原严格规范未修改。`PASS_POLISH` 专指本轮口径，不代表原严格 9 pt 门槛通过；原 inspector 的待验字段未被删除。
- [环境与字体实测](environment.json)、[11项暂缓决定](deferral_decisions.json)另列；`inventory.json` 是初始范围清单，最终状态以本页和 `acceptance.json` 为准。
- [主图源22页看图记录](native_visual_review.json)、[同步副本12页独立看图记录](snapshot_visual_review.json)分别绑定全图与高风险局部哈希；副本另核对源文件及像素一致性。
- 原生固定层序/网格布局，draw.io Desktop 24.7.17，Playwright 1.63 / Chromium 153；本轮不需要 ELK。共享目录子进程执行失败通过同哈希本机浏览器缓存修复。
- Matplotlib 3.10.7：真实 Agg 文字测量、形状/连线/图例检查；3D 遮挡和集合图元仍要求实际看图。draw.io 字体为 Noto Serif CJK SC；新绘 Matplotlib 为 FandolSong，旧的真实宋体不会谎称已换为同一字库。
- [FONT_EMBEDDING.md](FONT_EMBEDDING.md)：Fandol CFF 以 Type3 矢量轮廓嵌入，解决跨阅读器错误；中文 PDF 全文检索能力存在限制，原生 Python 与标签测量记录保留。
- 实测：原生缺陷/合法/变异 17 项 `PASS`；Matplotlib 10 项测试 `True`；源再生成幂等 `True`；只读保护 `True`。

## 当前剩余问题

- `USER_DEFERRED_INPUTS` — `docs/thesis/figures/experiments/control/r13_v2_authority_modes_ua.pdf`：用户暂缓；缺 r13_v2_authority_policy_summary_by_scenario_mode.csv；旧图字体/图例仍待修复。
- `USER_DEFERRED_INPUTS` — `docs/thesis/figures/experiments/control_mpc/05_mpc_combined_summary.pdf`：用户确认这些输入稍后从旧电脑迁移；历史 MPC 四时序绘图输入未定位；不能通过重跑仿真冒充旧试验的纯排版重绘。
- `USER_DEFERRED_INPUTS` — `docs/thesis/figures/experiments/decision_bt_vs_fsm/03_complexity_comparison.pdf`：用户确认这些输入稍后从旧电脑迁移；历史函数级复杂度输入包 results/decision/bt_vs_fsm/20260608_173806 未定位；静态成图已看，未以当前算法重算替代。
- `USER_DEFERRED_INPUTS` — `docs/thesis/figures/hardware/adc_enob/ch4_enob_vs_osr.pdf`：用户确认这些输入稍后从旧电脑迁移；缺 hardware_wrappers/fangkong_adc/raw_data/enob/20260809T161036/ch4_enob_results.json 与原绘图生成器。
- `USER_DEFERRED_INPUTS` — `docs/thesis/figures/hardware/adc_enob/ch4_noise_spectral_density.pdf`：用户确认这些输入稍后从旧电脑迁移；缺同一 ADC 原始短接噪声序列/频谱缓存及原绘图生成器；不从图片猜造数值。
- `USER_DEFERRED_INPUTS` — `docs/thesis/figures/hardware/pc104_cross_layer/pc104_cross_layer_fault_timeline.pdf`：用户暂缓；缺 pc104_cross_layer_fault_sync_20260822_222112；现有图例/时间线仍需原输入复核。
- `USER_DEFERRED_INPUTS` — `docs/thesis/figures/hardware/pc104_cross_layer/pc104_cross_layer_soak_30min.pdf`：用户暂缓；缺 pc104_cross_layer_fault_sync_20260822_225436；柱图、RSS 图例和底部说明仍遮挡数据。
- `USER_DEFERRED_INPUTS` — `docs/thesis/figures/hardware/pc104_fault_injection/pc104_fault_timeline.pdf`：用户暂缓；缺 pc104_fault_injection_formal_v2_20260822/fault_timeline.csv；故障位和 watchdog 图例遮住曲线。
- `USER_DEFERRED_INPUTS` — `docs/thesis/figures/hardware/pc104_timing/pc104_firmware_echo_timing.pdf`：用户暂缓四组 PC104；缺 pc104_udp_timing_echo_300s_20260822/udp_timing_samples.csv。
- `USER_DEFERRED_INPUTS` — `docs/thesis/figures/terrain_following/terrain_3d_pid_terrain_trajectory.pdf`：用户暂缓；同一地形原始包缺失，旧图仍含非目标中文字体。
- `USER_DEFERRED_INPUTS` — `docs/thesis/figures/terrain_following/terrain_tz_tracking_pid_mpc.pdf`：用户暂缓；缺 results/control/terrain_following_20260823_215036/ 原始 bag/PVS trace；保留现有字体和产物。

## 逐原生文件、逐页证据

| 图源 / 页 | 标签测量 | 状态 | 证据 | 问题 |
|---|---:|---|---|---|
| `AUV-Master-Mag/docs/figure/fig_arch_onion.drawio` / 0 | 30/30 | PASS_POLISH | [前](evidence/native/fig_arch_onion_before.png) / [后](evidence/native/fig_arch_onion_p0_after.png) / [局部](evidence/native/fig_arch_onion_p0_crop.png) | 无未解决原生布局缺陷 |
| `AUV-Master-Mag/docs/figure/fig_mission_fsm.drawio` / 0 | 12/12 | PASS_POLISH | [前](evidence/native/fig_mission_fsm_before.png) / [后](evidence/native/fig_mission_fsm_p0_after.png) / [局部](evidence/native/fig_mission_fsm_p0_crop.png) | 无未解决原生布局缺陷 |
| `AUV-Master-Mag/docs/figure/fig_perception_pipeline.drawio` / 0 | 18/18 | PASS_POLISH | [前](evidence/native/fig_perception_pipeline_before.png) / [后](evidence/native/fig_perception_pipeline_p0_after.png) / [局部](evidence/native/fig_perception_pipeline_p0_crop.png) | 无未解决原生布局缺陷 |
| `AUV-Master-Mag/docs/figure/fig_statemachine_hierarchy.drawio` / 0 | 9/9 | PASS_POLISH | [前](evidence/native/fig_statemachine_hierarchy_before.png) / [后](evidence/native/fig_statemachine_hierarchy_p0_after.png) / [局部](evidence/native/fig_statemachine_hierarchy_p0_crop.png) | 无未解决原生布局缺陷 |
| `AUV-Master-Mag/docs/figure/fig_zigzag_probe.drawio` / 0 | 8/8 | PASS_POLISH | [前](evidence/native/fig_zigzag_probe_before.png) / [后](evidence/native/fig_zigzag_probe_p0_after.png) / [局部](evidence/native/fig_zigzag_probe_p0_crop.png) | 无未解决原生布局缺陷 |
| `AUV-Master-Mag/thesis/figures/architecture/auv_code_layer_architecture.drawio` / 0 | 27/27 | PASS_POLISH | [前](evidence/native/auv_code_layer_architecture_before.png) / [后](evidence/native/auv_code_layer_architecture_p0_after.png) / [局部](evidence/native/auv_code_layer_architecture_p0_crop.png) | 已独立看图；同源/同像素复核：docs/internals/figures/architecture/auv_code_layer_architecture.drawio |
| `AUV-Master-Mag/thesis/figures/architecture/auv_ros2_node_topology.drawio` / 0 | 19/19 | PASS_POLISH | [前](evidence/native/auv_ros2_node_topology_before.png) / [后](evidence/native/auv_ros2_node_topology_p0_after.png) / [局部](evidence/native/auv_ros2_node_topology_p0_crop.png) | 已独立看图；同源/同像素复核：docs/internals/figures/architecture/auv_ros2_node_topology.drawio |
| `AUV-Master-Mag/thesis/figures/architecture/auv_runtime_dataflow.drawio` / 0 | 34/34 | PASS_POLISH | [前](evidence/native/auv_runtime_dataflow_before.png) / [后](evidence/native/auv_runtime_dataflow_p0_after.png) / [局部](evidence/native/auv_runtime_dataflow_p0_crop.png) | 已独立看图；同源/同像素复核：docs/thesis/figures/architecture/auv_runtime_dataflow.drawio |
| `AUV-Master-Mag/thesis/figures/architecture/auv_safety_arbiter_deployment.drawio` / 0 | 29/29 | PASS_POLISH | [前](evidence/native/auv_safety_arbiter_deployment_before.png) / [后](evidence/native/auv_safety_arbiter_deployment_p0_after.png) / [局部](evidence/native/auv_safety_arbiter_deployment_p0_crop.png) | 已独立看图；同源/同像素复核：docs/internals/figures/architecture/auv_safety_arbiter_deployment.drawio |
| `AUV-Master-Mag/thesis/figures/architecture/auv_system_autonomy_functional_loop.drawio` / 0 | 17/17 | PASS_POLISH | [前](evidence/native/auv_system_autonomy_functional_loop_before.png) / [后](evidence/native/auv_system_autonomy_functional_loop_p0_after.png) / [局部](evidence/native/auv_system_autonomy_functional_loop_p0_crop.png) | 已独立看图；同源/同像素复核：docs/thesis/figures/architecture/auv_system_autonomy_functional_loop.drawio |
| `AUV-Master-Mag/thesis/figures/architecture/auv_system_capability_map.drawio` / 0 | 15/15 | PASS_POLISH | [前](evidence/native/auv_system_capability_map_before.png) / [后](evidence/native/auv_system_capability_map_p0_after.png) / [局部](evidence/native/auv_system_capability_map_p0_crop.png) | 已独立看图；同源/同像素复核：docs/thesis/figures/architecture/auv_system_capability_map.drawio |
| `AUV-Master-Mag/thesis/figures/architecture/auv_system_subsystem_organization.drawio` / 0 | 23/23 | PASS_POLISH | [前](evidence/native/auv_system_subsystem_organization_before.png) / [后](evidence/native/auv_system_subsystem_organization_p0_after.png) / [局部](evidence/native/auv_system_subsystem_organization_p0_crop.png) | 已独立看图；同源/同像素复核：docs/thesis/figures/architecture/auv_system_subsystem_organization.drawio |
| `AUV-Master-Mag/thesis/figures/architecture/auv_system_verification_deployment_ladder.drawio` / 0 | 19/19 | PASS_POLISH | [前](evidence/native/auv_system_verification_deployment_ladder_before.png) / [后](evidence/native/auv_system_verification_deployment_ladder_p0_after.png) / [局部](evidence/native/auv_system_verification_deployment_ladder_p0_crop.png) | 已独立看图；同源/同像素复核：docs/thesis/figures/architecture/auv_system_verification_deployment_ladder.drawio |
| `AUV-Master-Mag/thesis/figures/architecture/auv_v2_dual_brain_async_hardware.drawio` / 0 | 16/16 | PASS_POLISH | [前](evidence/native/auv_v2_dual_brain_async_hardware_before.png) / [后](evidence/native/auv_v2_dual_brain_async_hardware_p0_after.png) / [局部](evidence/native/auv_v2_dual_brain_async_hardware_p0_crop.png) | 已独立看图；同源/同像素复核：docs/thesis/figures/architecture/auv_v2_dual_brain_async_hardware.drawio |
| `AUV-Master-Mag/thesis/figures/architecture/auv_v2_five_layer_functional_architecture.drawio` / 0 | 8/8 | PASS_POLISH | [前](evidence/native/auv_v2_five_layer_functional_architecture_before.png) / [后](evidence/native/auv_v2_five_layer_functional_architecture_p0_after.png) / [局部](evidence/native/auv_v2_five_layer_functional_architecture_p0_crop.png) | 已独立看图；同源/同像素复核：docs/thesis/figures/architecture/auv_v2_five_layer_functional_architecture.drawio |
| `AUV-Master-Mag/thesis/figures/architecture/auv_v2_five_layer_functional_architecture.drawio` / 1 | 14/14 | PASS_POLISH | [前](evidence/native/auv_v2_five_layer_functional_architecture_before.png) / [后](evidence/native/auv_v2_five_layer_functional_architecture_p1_after.png) / [局部](evidence/native/auv_v2_five_layer_functional_architecture_p1_crop.png) | 已独立看图；同源/同像素复核：docs/thesis/figures/architecture/auv_v2_five_layer_functional_architecture.drawio |
| `AUV-Master-Mag/thesis/figures/architecture/auv_v2_uncertainty_highway.drawio` / 0 | 11/11 | PASS_POLISH | [前](evidence/native/auv_v2_uncertainty_highway_before.png) / [后](evidence/native/auv_v2_uncertainty_highway_p0_after.png) / [局部](evidence/native/auv_v2_uncertainty_highway_p0_crop.png) | 已独立看图；同源/同像素复核：docs/thesis/figures/architecture/auv_v2_uncertainty_highway.drawio |
| `docs/internals/figures/architecture/auv_code_layer_architecture.drawio` / 0 | 27/27 | PASS_POLISH | [前](evidence/native/auv_code_layer_architecture_before.png) / [后](evidence/native/auv_code_layer_architecture_p0_after.png) / [局部](evidence/native/auv_code_layer_architecture_p0_crop.png) | 无未解决原生布局缺陷 |
| `docs/internals/figures/architecture/auv_ros2_node_topology.drawio` / 0 | 19/19 | PASS_POLISH | [前](evidence/native/auv_ros2_node_topology_before.png) / [后](evidence/native/auv_ros2_node_topology_p0_after.png) / [局部](evidence/native/auv_ros2_node_topology_p0_crop.png) | 无未解决原生布局缺陷 |
| `docs/internals/figures/architecture/auv_safety_arbiter_deployment.drawio` / 0 | 29/29 | PASS_POLISH | [前](evidence/native/auv_safety_arbiter_deployment_before.png) / [后](evidence/native/auv_safety_arbiter_deployment_p0_after.png) / [局部](evidence/native/auv_safety_arbiter_deployment_p0_crop.png) | 无未解决原生布局缺陷 |
| `docs/thesis/figures/architecture/auv_runtime_dataflow.drawio` / 0 | 34/34 | PASS_POLISH | [前](evidence/native/auv_runtime_dataflow_before.png) / [后](evidence/native/auv_runtime_dataflow_p0_after.png) / [局部](evidence/native/auv_runtime_dataflow_p0_crop.png) | 无未解决原生布局缺陷 |
| `docs/thesis/figures/architecture/auv_system_autonomy_functional_loop.drawio` / 0 | 17/17 | PASS_POLISH | [前](evidence/native/auv_system_autonomy_functional_loop_before.png) / [后](evidence/native/auv_system_autonomy_functional_loop_p0_after.png) / [局部](evidence/native/auv_system_autonomy_functional_loop_p0_crop.png) | 无未解决原生布局缺陷 |
| `docs/thesis/figures/architecture/auv_system_capability_map.drawio` / 0 | 15/15 | PASS_POLISH | [前](evidence/native/auv_system_capability_map_before.png) / [后](evidence/native/auv_system_capability_map_p0_after.png) / [局部](evidence/native/auv_system_capability_map_p0_crop.png) | 无未解决原生布局缺陷 |
| `docs/thesis/figures/architecture/auv_system_subsystem_organization.drawio` / 0 | 23/23 | PASS_POLISH | [前](evidence/native/auv_system_subsystem_organization_before.png) / [后](evidence/native/auv_system_subsystem_organization_p0_after.png) / [局部](evidence/native/auv_system_subsystem_organization_p0_crop.png) | 无未解决原生布局缺陷 |
| `docs/thesis/figures/architecture/auv_system_verification_deployment_ladder.drawio` / 0 | 19/19 | PASS_POLISH | [前](evidence/native/auv_system_verification_deployment_ladder_before.png) / [后](evidence/native/auv_system_verification_deployment_ladder_p0_after.png) / [局部](evidence/native/auv_system_verification_deployment_ladder_p0_crop.png) | 无未解决原生布局缺陷 |
| `docs/thesis/figures/architecture/auv_thesis_technical_route.drawio` / 0 | 17/17 | PASS_POLISH | [前](evidence/native/auv_thesis_technical_route_before.png) / [后](evidence/native/auv_thesis_technical_route_p0_after.png) / [局部](evidence/native/auv_thesis_technical_route_p0_crop.png) | 无未解决原生布局缺陷 |
| `docs/thesis/figures/architecture/auv_v2_behavior_tree_illustration.drawio` / 0 | 27/27 | PASS_POLISH | [前](evidence/native/auv_v2_behavior_tree_illustration_before.png) / [后](evidence/native/auv_v2_behavior_tree_illustration_p0_after.png) / [局部](evidence/native/auv_v2_behavior_tree_illustration_p0_crop.png) | 无未解决原生布局缺陷 |
| `docs/thesis/figures/architecture/auv_v2_dual_brain_async_hardware.drawio` / 0 | 16/16 | PASS_POLISH | [前](evidence/native/auv_v2_dual_brain_async_hardware_before.png) / [后](evidence/native/auv_v2_dual_brain_async_hardware_p0_after.png) / [局部](evidence/native/auv_v2_dual_brain_async_hardware_p0_crop.png) | 无未解决原生布局缺陷 |
| `docs/thesis/figures/architecture/auv_v2_emergency_transition.drawio` / 0 | 23/23 | PASS_POLISH | [前](evidence/native/auv_v2_emergency_transition_before.png) / [后](evidence/native/auv_v2_emergency_transition_p0_after.png) / [局部](evidence/native/auv_v2_emergency_transition_p0_crop.png) | 无未解决原生布局缺陷 |
| `docs/thesis/figures/architecture/auv_v2_five_layer_functional_architecture.drawio` / 0 | 8/8 | PASS_POLISH | [前](evidence/native/auv_v2_five_layer_functional_architecture_before.png) / [后](evidence/native/auv_v2_five_layer_functional_architecture_p0_after.png) / [局部](evidence/native/auv_v2_five_layer_functional_architecture_p0_crop.png) | 无未解决原生布局缺陷 |
| `docs/thesis/figures/architecture/auv_v2_five_layer_functional_architecture.drawio` / 1 | 14/14 | PASS_POLISH | [前](evidence/native/auv_v2_five_layer_functional_architecture_before.png) / [后](evidence/native/auv_v2_five_layer_functional_architecture_p1_after.png) / [局部](evidence/native/auv_v2_five_layer_functional_architecture_p1_crop.png) | 无未解决原生布局缺陷 |
| `docs/thesis/figures/architecture/auv_v2_mission_lifecycle_flow.drawio` / 0 | 24/24 | PASS_POLISH | [前](evidence/native/auv_v2_mission_lifecycle_flow_before.png) / [后](evidence/native/auv_v2_mission_lifecycle_flow_p0_after.png) / [局部](evidence/native/auv_v2_mission_lifecycle_flow_p0_crop.png) | 无未解决原生布局缺陷 |
| `docs/thesis/figures/architecture/auv_v2_mission_state_machine.drawio` / 0 | 17/17 | PASS_POLISH | [前](evidence/native/auv_v2_mission_state_machine_before.png) / [后](evidence/native/auv_v2_mission_state_machine_p0_after.png) / [局部](evidence/native/auv_v2_mission_state_machine_p0_crop.png) | 无未解决原生布局缺陷 |
| `docs/thesis/figures/architecture/auv_v2_uncertainty_highway.drawio` / 0 | 11/11 | PASS_POLISH | [前](evidence/native/auv_v2_uncertainty_highway_before.png) / [后](evidence/native/auv_v2_uncertainty_highway_p0_after.png) / [局部](evidence/native/auv_v2_uncertainty_highway_p0_crop.png) | 无未解决原生布局缺陷 |

## 逐论文图组

| 图号 | 状态 | 实际物理页 | 产物与前后证据 |
|---|---|---|---|
| 1.1 | PASS_POLISH | 29 | `hydropact350_coils` [前](evidence/paper-assets/hydropact350_coils_before.png) / [后](evidence/paper-assets/hydropact350_coils_after.png)<br>`haiying_t180` [前](evidence/paper-assets/haiying_t180_before.png) / [后](evidence/paper-assets/haiying_t180_after.png)<br>`fsea_p200` [前](evidence/paper-assets/fsea_p200_before.png) / [后](evidence/paper-assets/fsea_p200_after.png) |
| 1.2 | PASS_POLISH | 33 | `auv_thesis_technical_route` [前](evidence/paper-assets/auv_thesis_technical_route_before.png) / [后](evidence/paper-assets/auv_thesis_technical_route_after.png) |
| 2.1 | PASS_POLISH | 38 | `auv_system_autonomy_functional_loop` [前](evidence/paper-assets/auv_system_autonomy_functional_loop_before.png) / [后](evidence/paper-assets/auv_system_autonomy_functional_loop_after.png) |
| 2.2 | PASS_POLISH | 41 | `auv_v2_dual_brain_async_hardware` [前](evidence/paper-assets/auv_v2_dual_brain_async_hardware_before.png) / [后](evidence/paper-assets/auv_v2_dual_brain_async_hardware_after.png) |
| 2.3 | PASS_POLISH | 42 | `auv_v2_five_layer_functional_architecture` [前](evidence/paper-assets/auv_v2_five_layer_functional_architecture_before.png) / [后](evidence/paper-assets/auv_v2_five_layer_functional_architecture_after.png) |
| 2.4 | PASS_POLISH | 44 | `auv_system_verification_deployment_ladder` [前](evidence/paper-assets/auv_system_verification_deployment_ladder_before.png) / [后](evidence/paper-assets/auv_system_verification_deployment_ladder_after.png) |
| 2.5 | PASS_POLISH | 45 | `foxglove_cable_tracking_console` [前](evidence/paper-assets/foxglove_cable_tracking_console_before.png) / [后](evidence/paper-assets/foxglove_cable_tracking_console_after.png) |
| 2.6 | PASS_POLISH | 48 | `single_phase_field_direction` [前](evidence/paper-assets/single_phase_field_direction_before.png) / [后](evidence/paper-assets/single_phase_field_direction_after.png) |
| 2.7 | PASS_POLISH | 50 | `three_phase_helical_field` [前](evidence/paper-assets/three_phase_helical_field_before.png) / [后](evidence/paper-assets/three_phase_helical_field_after.png) |
| 2.8 | PASS_POLISH | 53 | `fwhm_depth_principle` [前](evidence/paper-assets/fwhm_depth_principle_before.png) / [后](evidence/paper-assets/fwhm_depth_principle_after.png) |
| 2.9 | PASS_POLISH | 54 | `cable_active_crossing_observability` [前](evidence/paper-assets/cable_active_crossing_observability_before.png) / [后](evidence/paper-assets/cable_active_crossing_observability_after.png) |
| 2.10 | PASS_POLISH | 61 | `tmr8637_axis_calibration_report` [前](evidence/paper-assets/tmr8637_axis_calibration_report_before.png) / [后](evidence/paper-assets/tmr8637_axis_calibration_report_after.png) |
| 2.11 | PASS_POLISH | 62 | `tmr8637_noise_psd_report` [前](evidence/paper-assets/tmr8637_noise_psd_report_before.png) / [后](evidence/paper-assets/tmr8637_noise_psd_report_after.png) |
| 2.12 | PASS_POLISH | 64 | `auv_console_operator_interface` [前](evidence/paper-assets/auv_console_operator_interface_before.png) / [后](evidence/paper-assets/auv_console_operator_interface_after.png) |
| 2.13 | PASS_POLISH | 66 | `auv_v2_emergency_transition` [前](evidence/paper-assets/auv_v2_emergency_transition_before.png) / [后](evidence/paper-assets/auv_v2_emergency_transition_after.png) |
| 2.14 | PASS_POLISH | 67 | `auv_v2_mission_lifecycle_flow` [前](evidence/paper-assets/auv_v2_mission_lifecycle_flow_before.png) / [后](evidence/paper-assets/auv_v2_mission_lifecycle_flow_after.png) |
| 3.1 | PASS_POLISH | 71 | `auv_v2_uncertainty_highway` [前](evidence/paper-assets/auv_v2_uncertainty_highway_before.png) / [后](evidence/paper-assets/auv_v2_uncertainty_highway_after.png) |
| 3.2 | PASS_POLISH | 82 | `cable_acoustic_magnetic_perception_pipeline` [前](evidence/paper-assets/cable_acoustic_magnetic_perception_pipeline_before.png) / [后](evidence/paper-assets/cable_acoustic_magnetic_perception_pipeline_after.png) |
| 4.1 | PASS_POLISH | 90 | `auv_v2_mission_state_machine` [前](evidence/paper-assets/auv_v2_mission_state_machine_before.png) / [后](evidence/paper-assets/auv_v2_mission_state_machine_after.png) |
| 4.2 | PASS_POLISH | 91 | `auv_v2_behavior_tree_illustration` [前](evidence/paper-assets/auv_v2_behavior_tree_illustration_before.png) / [后](evidence/paper-assets/auv_v2_behavior_tree_illustration_after.png) |
| 4.3 | USER_DEFERRED_INPUTS | 94 | `03_complexity_comparison` [前](evidence/paper-assets/03_complexity_comparison_before.png) / [后](evidence/paper-assets/03_complexity_comparison_after.png) |
| 4.4 | PASS_POLISH | 95 | `04_expansion_cost` [前](evidence/paper-assets/04_expansion_cost_before.png) / [后](evidence/paper-assets/04_expansion_cost_after.png) |
| 4.5 | PASS_POLISH | 97 | `normalized_coverage_time_tradeoff` [前](evidence/paper-assets/normalized_coverage_time_tradeoff_before.png) / [后](evidence/paper-assets/normalized_coverage_time_tradeoff_after.png) |
| 4.6 | USER_DEFERRED_INPUTS | 103 | `05_mpc_combined_summary` [前](evidence/paper-assets/05_mpc_combined_summary_before.png) / [后](evidence/paper-assets/05_mpc_combined_summary_after.png) |
| 5.1 | USER_DEFERRED_INPUTS | 114 | `ch4_enob_vs_osr` [前](evidence/paper-assets/ch4_enob_vs_osr_before.png) / [后](evidence/paper-assets/ch4_enob_vs_osr_after.png)<br>`ch4_noise_spectral_density` [前](evidence/paper-assets/ch4_noise_spectral_density_before.png) / [后](evidence/paper-assets/ch4_noise_spectral_density_after.png) |
| 5.2 | PASS_POLISH | 116 | `mag_chain_noise_ros_comparison` [前](evidence/paper-assets/mag_chain_noise_ros_comparison_before.png) / [后](evidence/paper-assets/mag_chain_noise_ros_comparison_after.png) |
| 5.3 | PASS_POLISH | 117 | `01_mag_extrinsics_residual` [前](evidence/paper-assets/01_mag_extrinsics_residual_before.png) / [后](evidence/paper-assets/01_mag_extrinsics_residual_after.png) |
| 5.4 | PASS_POLISH | 118 | `trajectory_colored_by_b` [前](evidence/paper-assets/trajectory_colored_by_b_before.png) / [后](evidence/paper-assets/trajectory_colored_by_b_after.png) |
| 5.5 | PASS_POLISH | 119 | `complex_iq_fit` [前](evidence/paper-assets/complex_iq_fit_before.png) / [后](evidence/paper-assets/complex_iq_fit_after.png) |
| 5.6 | PASS_POLISH | 122 | `eskf_param_sensitivity` [前](evidence/paper-assets/eskf_param_sensitivity_before.png) / [后](evidence/paper-assets/eskf_param_sensitivity_after.png) |
| 5.7 | USER_DEFERRED_INPUTS | 126 | `terrain_tz_tracking_pid_mpc` [前](evidence/paper-assets/terrain_tz_tracking_pid_mpc_before.png) / [后](evidence/paper-assets/terrain_tz_tracking_pid_mpc_after.png) |
| 5.8 | USER_DEFERRED_INPUTS | 127 | `terrain_3d_pid_terrain_trajectory` [前](evidence/paper-assets/terrain_3d_pid_terrain_trajectory_before.png) / [后](evidence/paper-assets/terrain_3d_pid_terrain_trajectory_after.png) |
| 5.9 | PARTIAL_USER_DEFERRED | 135 | `r13_v2_control_rate_paired` [前](evidence/paper-assets/r13_v2_control_rate_paired_before.png) / [后](evidence/paper-assets/r13_v2_control_rate_paired_after.png)<br>`r13_v2_authority_modes_ua` [前](evidence/paper-assets/r13_v2_authority_modes_ua_before.png) / [后](evidence/paper-assets/r13_v2_authority_modes_ua_after.png)<br>`r13_v2_p_track_boxplot_ua` [前](evidence/paper-assets/r13_v2_p_track_boxplot_ua_before.png) / [后](evidence/paper-assets/r13_v2_p_track_boxplot_ua_after.png) |
| 5.10 | PASS_POLISH | 139 | `cable_dlt1278_scorecard_fresh1` [前](evidence/paper-assets/cable_dlt1278_scorecard_fresh1_before.png) / [后](evidence/paper-assets/cable_dlt1278_scorecard_fresh1_after.png) |
| 5.11 | PASS_POLISH | 141 | `pvs_closedloop_recovery_prior_alignment` [前](evidence/paper-assets/pvs_closedloop_recovery_prior_alignment_before.png) / [后](evidence/paper-assets/pvs_closedloop_recovery_prior_alignment_after.png) |
| 5.12 | PASS_POLISH | 142 | `11_fwhm_stability_comparison` [前](evidence/paper-assets/11_fwhm_stability_comparison_before.png) / [后](evidence/paper-assets/11_fwhm_stability_comparison_after.png) |
| 5.13 | PASS_POLISH | 143 | `12_fwhm_stability_sensitivity` [前](evidence/paper-assets/12_fwhm_stability_sensitivity_before.png) / [后](evidence/paper-assets/12_fwhm_stability_sensitivity_after.png) |
| 5.14 | PASS_POLISH | 144 | `13_shape_guard_held_out_validation` [前](evidence/paper-assets/13_shape_guard_held_out_validation_before.png) / [后](evidence/paper-assets/13_shape_guard_held_out_validation_after.png) |
| 5.15 | PASS_POLISH | 146 | `71_current_magnetic_simulation_closure` [前](evidence/paper-assets/71_current_magnetic_simulation_closure_before.png) / [后](evidence/paper-assets/71_current_magnetic_simulation_closure_after.png) |
| 5.16 | PASS_POLISH | 147 | `77_defense_robustness_thesis_summary` [前](evidence/paper-assets/77_defense_robustness_thesis_summary_before.png) / [后](evidence/paper-assets/77_defense_robustness_thesis_summary_after.png) |
| 5.17 | PASS_POLISH | 148 | `51_shallow_survey_ros_pvs_chain` [前](evidence/paper-assets/51_shallow_survey_ros_pvs_chain_before.png) / [后](evidence/paper-assets/51_shallow_survey_ros_pvs_chain_after.png) |
| 5.18 | PASS_POLISH | 150 | `r2_reference_lifecycle` [前](evidence/paper-assets/r2_reference_lifecycle_before.png) / [后](evidence/paper-assets/r2_reference_lifecycle_after.png) |
| 5.19 | PASS_POLISH | 151 | `r2_trajectory_pressure` [前](evidence/paper-assets/r2_trajectory_pressure_before.png) / [后](evidence/paper-assets/r2_trajectory_pressure_after.png) |
| 5.20 | USER_DEFERRED_INPUTS | 152 | `pc104_firmware_echo_timing` [前](evidence/paper-assets/pc104_firmware_echo_timing_before.png) / [后](evidence/paper-assets/pc104_firmware_echo_timing_after.png) |
| 5.21 | USER_DEFERRED_INPUTS | 154 | `pc104_fault_timeline` [前](evidence/paper-assets/pc104_fault_timeline_before.png) / [后](evidence/paper-assets/pc104_fault_timeline_after.png) |
| 5.22 | USER_DEFERRED_INPUTS | 155 | `pc104_cross_layer_fault_timeline` [前](evidence/paper-assets/pc104_cross_layer_fault_timeline_before.png) / [后](evidence/paper-assets/pc104_cross_layer_fault_timeline_after.png) |
| 5.23 | USER_DEFERRED_INPUTS | 156 | `pc104_cross_layer_soak_30min` [前](evidence/paper-assets/pc104_cross_layer_soak_30min_before.png) / [后](evidence/paper-assets/pc104_cross_layer_soak_30min_after.png) |
| 5.24 | PASS_POLISH | 157 | `jetson_mpc_latency_and_success` [前](evidence/paper-assets/jetson_mpc_latency_and_success_before.png) / [后](evidence/paper-assets/jetson_mpc_latency_and_success_after.png) |

## 尺寸、回滚及可追溯性

实际插入使用 XeTeX 的 FmN/ImN 序列、源 PDF 页尺寸和实际变换矩阵核对，未猜测印刷页偏移；[acceptance.json](acceptance.json) 含逐次毫米尺寸、提取字形子集最小字号及 Agg 标签基准字号。Type3 中文与公式下标不能仅靠 PDF 抽字判定完整字高。
前图优先来自本轮开始前的工作树导出备份；fig_perception_pipeline 与 fig_zigzag_probe 的基线 PNG 为 LFS 指针，故从已备份原生源在锁定字体环境重渲染，明确不冒充缺失的历史位图。快照无独立旧导出时保留原生备份并核对当前源/像素身份。完整 2× 图、SHA-256、命令和原始备份在 `.diagram-governance/runs/20261021_presentation_polish/`。
保护已有脏工作树，未执行 reset/checkout/提交/推送。两份嵌套副本恢复基线的用户决定详见运行目录 `backup_gaps.json`；不隐藏原始逐字节备份缺口。
研究工作完成度及现场许可不因本轮图像治理升级。完整原生图可编辑；历史仿真、真实 PC104、离线分析和真实部署边界继续区分。
