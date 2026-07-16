# 电缆验收图像来源

## 源 run
- operator/scorecard/timeline/burial（`_fresh1/2/3` 后缀）：`results/cable_ops_report/acceptance_fresh{1,2,3}_20260706_1357xx/`
- 3f_replay_top_view：**`/auv_data/bags/20260709_134856/rosbag`** + `results/cable_ops_report/replay_e2e/_configs/heavy.yaml`（订正：原记录的 `replay_e2e/*/rosbag/rosbag_0.mcap` 只含 `/auv/cable/tracking`，无 `/auv/state/filtered` 里程计；真源见 `docs/experiment/visual_feedback_migration_20260705.md:269`）
- pvs_closedloop_*：`results/cable_ops_report/closedloop_e2e/*/tracking.jsonl`
- direction_a_online_prior_alignment：`results/cable_ops_report/direction_a_decoupled/20260706_221801/rosbag/rosbag_0.mcap`
- cable_tracking_dynamic_fresh1（gif/末帧）：`results/cable_ops_report/acceptance_fresh1_20260706_135331/tracking.jsonl`

## 图内中文化重跑（2026-08-06 · 组 8）

- 脚本 `tools/plot_cable_operator_products.py`、`tools/plot_cable_dlt1278_scorecard.py` 已完成图内统一中文（文泉驿正黑，`axes.unicode_minus=False`，字体块在 `main()` 内 matplotlib 导入后注入）。
- **`_ascii_label()` 处理**：两脚本原有 `_ascii_label()` 会把中文强转 ASCII（`海缆位移`→`route displacement` 等）；本轮改为**直接返回原始中文**，并**去掉文本框的 `family="monospace"`**（monospace 无 CJK 字形），使 WQY 正黑生效。
- **保留英文的项**（内部标识符，译了会误导/破坏溯源）：验收检查项 key（`min_tracking_samples`/`burial_sigma_over_limit_ratio` 等）、已实现项名（`route_deviation`/`burial_profile`/`tracking_confidence`）、就绪度值（`ready`）。
- 重跑命令：
  - `python3 tools/plot_cable_operator_products.py --report-dir results/cable_ops_report/acceptance_fresh1_20260706_135331 --output-dir <tmp>`
  - `python3 tools/plot_cable_dlt1278_scorecard.py --summary results/cable_ops_report/acceptance_fresh{1,2,3}_.../inspection_summary.json --output <tmp>/cable_dlt1278_scorecard.png`
  - timeline/burial 由已中文化的 `plot_cable_tracking_fullflow.py` 对 fresh1 `tracking.jsonl` 生成 12/13 号图后改名迁入。
  - 生成到 `<tmp>` 后 `cp` 迁入本目录并按 `operator_*_fresh1` / `cable_dlt1278_scorecard_fresh{1,2,3}` / `inspection_window_timeline_fresh1` / `burial_sigma_window_diagnosis_fresh1` 命名。
- **C 类文本框图（operator_acceptance_summary、scorecard）**：按决策 2 本轮只中文化不整改内容；DL/T 扣分项（海缆埋深不足 16 分、埋深估计精度未达 0.15m）如实呈现，属"实验效果不佳"证据，交实验分支决定。
- **待本轮后续处理（组 9-10）**：pvs_closedloop / direction_a / 3f_replay（3f 顺带改白底）/ cable_tracking gif 末帧尚未中文化。

## 图内中文化重跑（2026-08-06 · 组 9）

- 脚本 `tools/plot_pvs_closedloop_recovery.py`（+`_apply_zh_style()`，29 处译）、`tools/plot_direction_a_online_prior.py`（main 内字体块，23 处译）、`tools/plot_replay_top_view.py`（字体块 + 7 处译 + **黑底改白底**）已完成图内统一中文。
- **replay_top_view 改白底**：原 `#07131d` 深色背景 + 白字/白色比例尺，改为白底黑字（比例尺、坐标轴、图例均改深色），适配 A4 打印。
- **保留英文的项**：`reason_code`/`min_confidence`/`valid_burial_ratio`/`sigma_over` 等内部诊断标识符、`mid`/`heavy` 档位内部名。
- 重跑命令：
  - `python3 tools/plot_pvs_closedloop_recovery.py --output-dir <tmp>`（默认读 `results/cable_ops_report/closedloop_e2e/`）
  - `python3 tools/extract_cable_tracking_jsonl.py --bag results/cable_ops_report/direction_a_decoupled/20260706_221801/rosbag --output-jsonl <tmp>/da.jsonl --topic /auv/cable/diagnostics` 后 `python3 tools/plot_direction_a_online_prior.py --diagnostics-jsonl <tmp>/da.jsonl --output <tmp>/direction_a_online_prior_alignment.png`
  - `python3 tools/plot_replay_top_view.py --bag /auv_data/bags/20260709_134856/rosbag --tracking-config results/cable_ops_report/replay_e2e/_configs/heavy.yaml --output <tmp>/3f_replay_top_view.png`
- 核验 pvs recovery/direction_a/3f：中文正常、负号正常、内部标识保留、白底生效；已 cp 迁入本目录。
- **卡点 #4（已修复，无数据丢失）**：3f 源 bag 曾在 `_SOURCE.md` 记为 `replay_e2e/*/rosbag`（仅含 tracking 话题，无里程计），实为 `/auv_data/bags/20260709_134856/rosbag`；已订正上方源 run。

## 图内中文化重跑（2026-08-06 · 组 10）

- 脚本 `tools/make_cable_tracking_gif.py`（17 处译 + main 内字体块 + 状态框去 `monospace`）已完成图内统一中文。
- **状态框去 monospace**：原 `family="monospace"` 无 CJK 字形→去掉后由文泉驿正黑渲染；原固定宽度对齐（`:7.2f`）随之去除，改为常规中文冒号排版。
- **保留英文的项**：状态框 `industrial_ready`、`mode` 值（`quality_limited`）、`sigma` 等内部标识符。
- 重跑命令：`python3 tools/make_cable_tracking_gif.py --tracking-jsonl results/cable_ops_report/acceptance_fresh1_20260706_135331/tracking.jsonl --output <tmp>/cable_tracking_dynamic_fresh1.gif --last-frame-png <tmp>/cable_tracking_dynamic_fresh1_last_frame.png`
- 核验末帧（1237 帧最后一帧）：四面板标题/轴标/图例/状态框全中文、负号正常、内部标识保留；已 cp gif + 末帧 png 迁入本目录。
- **数据说明**：源为 fresh1 验收 run（`置信度 0.875`、埋深反演有非空序列），与组 7 fullflow 的 C 类弱数据（置信度恒 0.5、埋深 sigma 全空）不同——本图数据正常，不属 C 类。

## 论文压缩降级记录（2026-08-18，批次 D 叙述凝练/整图移出正文）

- `3f_replay_top_view.png`（原 `fig:ch05-pvs-closedloop-topview`）：**从正文降级归档，图片文件保留本目录不删**。理由：该图为 \(n=1\) 回放的二维俯视科普性插图，明确标注是"为便于向非专业读者解释车辆如何贴回电缆廊道"；同一次六自由度闭环恢复的权威证据已由 `pvs_closedloop_recovery_prior_alignment.png`（`fig:ch05-pvs-closedloop-recovery`，中/重档各 \(n=3\)）在正文给出。正文改以一句括注指向本图随附录 A.9/Artifact Manifest 归档。
- 数值/结论权威源：`fig:ch05-pvs-closedloop-recovery`（auv-chap05.tex §5.5.11 第三环）+ 六自由度闭环验收表 `tab:ch05-...`（同节）。
- `operator_acceptance_summary_fresh1.png`（原 `fig:ch05-cable-operator-summary`）：**从正文降级归档，图片文件保留本目录不删**。理由：该图为验收汇总文本框截图，其 NOT READY/扣分项（总分 24、最差项 16、埋深不足与埋深精度未达 0.15 m）已在 §5.5.10 正文完整复述，并由 `cable_dlt1278_scorecard_fresh1.png`（`fig:ch05-dlt-scorecard-run1`）以评分卡形式在正文给出，图文重复。正文改为一句列举指向本图随附录 A.8/Artifact Manifest 归档。

## 论文压缩降级记录（2026-08-18，L2 表-图去重）

- `direction_a_online_prior_alignment.png`（原 `fig:ch05-direction-a-prior-alignment`）：**从正文降级归档，图片文件保留本目录不删**。理由：该图为解耦轻量闭环 \(n=1\) 逐帧诊断时序，其六项稳态量（磁观测被激励/在线修正被接受/拒绝原因/横偏拟合质量/垂直分离/累积平移修正）与"近共面闭环对照"列，逐行等同于紧邻其后的表 `tab:ch05-decoupled-loop`，图表功能完全重复。同节六自由度闭环恢复的权威证据由 `pvs_closedloop_recovery_prior_alignment.png`（`fig:ch05-pvs-closedloop-recovery`，中/重档各 \(n=3\)）在正文给出。正文改为一句括注指向本图随附录 A.9/Artifact Manifest 归档。
- 数值权威源：表 `tab:ch05-decoupled-loop`（auv-chap05.tex §5.5.11 第二环）。
