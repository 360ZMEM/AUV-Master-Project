# 当前接续入口（2026-10-23）

用户已确认历史输入丢失，并接受 11 幅旧图作为不可重绘资产保留。本轮已采样并逐一看图，22 个原 PDF/PNG 未改；既有遮挡和字体限制保留记录，不再以等待迁移输入阻塞当前排版任务。此前 `NEEDS_REVIEW` 为历史验收结论，不回改为严格通过。

本轮尺寸、分页、正文润色及最新验收请见 [20261023/README.md](20261023/README.md)、[逐项记录](20261023/acceptance.json) 和 [实际看图记录](20261023/final_visual_review.json)。另见 [原生图前后对照](20261023/NATIVE_BEFORE_AFTER.md) 与 [发布图字号调整清单](20261023/publication_asset_manifest.json)。论文仍为 180 页；第 1 章图片按用户要求保持。本轮 318 份基线备份在 `.diagram-governance/runs/20261023_compact_thesis/backup/`，原 309 份历史备份保留。

当前重跑与只读验收命令：

```sh
python3 tools/figure-polish/compact_20261023.py run
python3 tools/figure-polish/compact_20261023.py verify
python3 tools/figure-polish/compact_20261023.py prose_audit
```

这两条主流程以 `COMPLETE_WITH_RETAINED_ASSETS` 验收当前授权范围；不会把保留旧图改记为已修复。未执行 Git 提交、重置或推送。

---

以下保留 2026-10-22 历史接续全文；其中等待迁移、旧重跑入口及退出码要求只适用于当时版本。

# 全仓图像润色接续记录（2026-10-22）

本轮可执行治理与全流程重放已经完成；最终结论以 [逐文件/页报告](README.md) 和 [acceptance.json](acceptance.json) 为准。整体仍为 **NEEDS_REVIEW**，11 幅旧图等待用户迁移输入或后续确认，没有把范围缩成已通过子集。

## 已完成的实际工作

- 当前自有 draw.io 32 源/34 页，含 21 个主图源/22 页及 11 份同步副本/12 页；冻结历史 21 份未改。所有标签经过 Chromium 真实文字和实际形状安全区测量，最终布局规则错误为 0。全图及高风险局部均已实际打开，记录分别在 `native_visual_review.json`、`snapshot_visual_review.json`。
- 布局和读者解释同步到真实生成器与正式 PDF/SVG/PNG；平台与软件职责层级区分、变量中文解释、分层网格、协议总线与连接路线均已处理。五层图按用户决定保留两页同组图及原生可编辑性。
- 主论文实际使用的 25 幅 Matplotlib 图完成真实 Agg 测量和针对性修复；候选看图/哈希门通过后已同步正式资产及所需发布副本。仅重放已有输入和原理示例，不重跑逆解或仿真。输入哈希前后相同。
- 原生缺陷/合法/变异测试 17/17、Matplotlib 测试 10/10 通过。32 原生文件和同步说明合计 33 文件再生成零变化；实际论文插入按 XeTeX 引用顺序/变换核对，共 48 图组、53 资产、54 次插入。
- `thuthesis/build/auv-thesis/auv-thesis.pdf` 为 180 页，48 个含图物理页逐张查看；没有删除研究内容以抵消图像增高。旧 169/236 页备份不变，研究结论、原数据和现场许可不因润色升级。
- 全流程 `run` 已真实跑完，其完成回执保留为运行目录的 `full_workflow_completion.json`；之后又补齐副本独立看图门，最后执行单独 `verify`。最新回执为 `workflow_completion.json`，须显示 `completed: true`；退出码 2 表示仍有待补输入，不是执行失败或全量 PASS。

## 当前验收口径

用户明确允许最小字号妥协，9 pt 为建议，详见 [POLICY.md](POLICY.md)。`PASS_POLISH` 仅表示本轮口径通过，不表示原严格字号规范通过；原规范和 inspector 待验字段未删。自动测量不能完整覆盖 3D 遮挡/集合图元，已结合实际看图；宋体 CFF 的 Type3 矢量嵌入及中文检索限制见 [字体记录](FONT_EMBEDDING.md)。环境锁定及实际字体文件见 [environment.json](environment.json)。

## 剩余 11 幅：保留原图，等待真实输入

1. 地形两图及 R13 authority 图：用户「不首先修复，留待后续确认」。缺 `results/control/terrain_following_20260823_215036/` 的 bag/PVS trace，以及 `r13_v2_authority_policy_summary_by_scenario_mode.csv`。三幅旧图仍有非目标中文字体。
2. PC104 四图：用户「暂缓这四组，保留待复核」。缺 `pc104_udp_timing_echo_300s_20260822`、`pc104_fault_injection_formal_v2_20260822`、`pc104_cross_layer_fault_sync_20260822_222112`、`pc104_cross_layer_fault_sync_20260822_225436`；其中故障/长稳图例遮挡仍未修复，不能计为通过。
3. ADC ENOB/频谱两图、复杂度图 4.3、MPC 图 4.6：用户「这些输入稍后从旧电脑迁移」。分别需要 `hardware_wrappers/fangkong_adc/raw_data/enob/20260809T161036/`、`results/decision/bt_vs_fsm/20260608_173806/`、`results/control/mpc_test/20260806_191823/` 及原绘图生成器/完整缓存。这四图已静态查看，原输入重绘尚未验证。

具体资产路径、问题和用户决定见 [完整报告](README.md)、[暂缓记录](deferral_decisions.json)。收到真实输入后，只为对应缺项增加绘图适配器、核对输入哈希并重新看图，不用新试验替代历史证据，不反复请求已经明确的授权。

## 备份与恢复

运行目录为 `.diagram-governance/runs/20261021_presentation_polish/`，初始 218 文件已追加至 309 文件；`baseline_manifest.json`、`backup/` 保存本轮覆盖前的工作树原件，验收校验完整。最新只读保护文件数以 `readonly_integrity.json` 为准，要求 `changed: []`。

两份嵌套扩展开销副本 `decision_bt_vs_fsm/figures/04_expansion_cost.pdf/.png` 在覆盖前未单独捕获。用户已明确接受旧主图作为回滚基线，清单标记 `USER_ACCEPTED_CANONICAL_COPY`，原嵌套哈希未知，不能冒充逐字节原件。详情在 `backup_gaps.json`、`recovery/nested_expansion/`。两份基线 PNG 实为 LFS 指针时保留指针，并从备份原生源生成明确标注的前图，不冒充历史位图。

没有执行 reset/checkout、提交或推送。旧检查点保存在运行目录 `checkpoints/RESUME_before_final_acceptance.md`。

## 重跑入口

在仓库根目录执行：

```sh
python3 tools/figure-polish/workflow.py run
python3 tools/figure-polish/workflow.py verify
```

`run` 包含备份、环境锁检查、27 项检查器测试、生成器幂等、原生导出、缓存绘图、哈希门提升、论文构建与 fresh 验收。`verify` 仅重建检查证据，保护图源、正式资产、研究输入与现有论文 PDF，并核对前后哈希；不会自动把未看过的新图计为通过。二者当前均应以 2 退出并保留 11 个 `USER_DEFERRED_INPUTS`。
