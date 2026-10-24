# draw.io 治理检查点（2026-10-18）

本轮已经完成基线备份、32 个当前图源与全部页面清点、固定版本环境、自测 17/17、复杂/简单试点，以及在试点后继续修复六张图。备份位于忽略目录 `.diagram-governance/runs/20261018_governance/backup`；本目录的 `semantic-baseline.json`、`evidence/baseline/` 和 `evidence/fresh/` 供跨会话审查。运行前原有大量未提交改动，未对其做重置或清理。

已安全写回并同步生成器与正式导出物的权威图源：

| 图源 | 已核对结果 |
|---|---|
| `AUV-Master-Mag/docs/figure/fig_mission_fsm.drawio` | 0 几何错误；正式 PNG 全图及危险局部已打开；未被论文直接引用。 |
| `AUV-Master-Mag/docs/figure/fig_statemachine_hierarchy.drawio` | 0 几何错误；正式 PNG 全图及危险局部已打开；未被论文直接引用。 |
| `AUV-Master-Mag/docs/figure/fig_arch_onion.drawio` | 0 几何错误；五层和右侧闭环固定规则网格，正式 PNG 与局部已打开；未被论文直接引用。 |
| `docs/thesis/figures/architecture/auv_system_capability_map.drawio` | 0 几何错误；反馈标签和工程迁移边已核对；正式 PDF 用 `--crop` 解决默认导出多出空白第二页；未被论文直接引用。 |
| `docs/thesis/figures/architecture/auv_system_verification_deployment_ladder.drawio` | 0 几何错误；六阶段两行三列；论文物理页 43 最小图字约 10.67 pt，整页和局部已打开。 |
| `docs/thesis/figures/architecture/auv_thesis_technical_route.drawio` | 0 几何错误；双列纵向技术路线；论文物理页 33 最小图字约 9.33 pt，正式 PNG、连线局部与论文整页已打开；单图幂等见 `technical_route_idempotence.json`。 |
| `docs/thesis/figures/architecture/auv_v2_five_layer_functional_architecture.drawio` | 两页各 0 几何错误；完整语义集合核对；论文物理页 41 最小图字约 9.33 pt，整页和危险局部已打开。 |
| `docs/thesis/figures/architecture/auv_v2_uncertainty_highway.drawio` | 0 几何错误；论文物理页 67 最小图字约 9.67 pt，整页和局部已打开。 |

当前 fresh 检查为 **32 文件、34 页：FAIL 19，BLOCKED 0，NEEDS_REVIEW 15，PASS 0**。`PASS 0` 是如实保留的总门槛状态；几何清零不等于实际论文尺寸、所有导出物和全部页面看图均已通过。原始论文阅读尺寸基线的另外六张图仍约为 5–6 pt：`auv_system_autonomy_functional_loop`、`auv_v2_dual_brain_async_hardware`、`auv_v2_emergency_transition`、`auv_v2_mission_lifecycle_flow`、`auv_v2_mission_state_machine`、`auv_v2_behavior_tree_illustration`。其中状态机虽几何清零，论文尺寸仍未通过。

本轮重编译的 `auv-thesis.pdf` 为 173 页；技术路线图扩大后占用的版面比基线更多。完整论文页数仍需与此前 160–170 页的写作目标协调，不能以缩小图中文字换取页数。

下一轮应修复 12 个权威源，随后同步其 7 个快照：

- `AUV-Master-Mag/docs/figure/fig_perception_pipeline.drawio`、`fig_zigzag_probe.drawio`。
- `docs/internals/figures/architecture/auv_code_layer_architecture.drawio`、`auv_ros2_node_topology.drawio`、`auv_safety_arbiter_deployment.drawio`。
- `docs/thesis/figures/architecture/auv_runtime_dataflow.drawio`、`auv_system_autonomy_functional_loop.drawio`、`auv_system_subsystem_organization.drawio`、`auv_v2_behavior_tree_illustration.drawio`、`auv_v2_dual_brain_async_hardware.drawio`、`auv_v2_emergency_transition.drawio`、`auv_v2_mission_lifecycle_flow.drawio`。

逐文件、逐页错误对象 ID 和可点击的前后图像见 [`summary.md`](summary.md)。应优先处理论文中 5–6 pt 的六张图，并对几何清零但字号不足的状态机单独改版；每张图仍需候选渲染、真实文字/形状/连线检查、正式导出、实际 PDF 页内字号和全图及危险局部看图。不得通过缩字、删内容或降低检查阈值获取通过。

重建已完成修复并全量复检：`bash tools/diagram-governance/rebuild-approved.sh`。只读图源验收：`node tools/diagram-governance/cli.mjs verify --all --fresh`。二者当前均因真实剩余问题而非零退出。加入技术路线图后，重建脚本再次执行，17/17 自测和 34 页 fresh 检查均完成，仍为 19 FAIL、15 NEEDS_REVIEW。先前两次重建比较了 32 个图源和 28 个正式导出物：53/60 字节相同；七个 PDF 因导出元数据不同而字节不同，抽取文本与页面渲染一致。`auv_system_capability_map.pdf` 的单页裁切修复后再次重导，栅格哈希一致。新技术路线图图源、PNG、SVG、内嵌图 PNG 再导字节一致，PDF 72 dpi 栅格一致，详见 [`idempotence.json`](idempotence.json) 和 [`technical_route_idempotence.json`](technical_route_idempotence.json)。
