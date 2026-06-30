# 论文文档自洽性整理、PDF 重生成与图片迁移操作日志

**日期**: 2026-06-20
**目的**: 记录"实验深入挑刺与自洽性提升"阶段收尾时，对 `docs/thesis/paper` 正文层做的遗漏检查与整理、用 pandoc 重新生成 `docs_pdf`、以及实验图片迁移与大规模扫参的重要命令。本日志面向"之后自己独立更新文档"，每一步都保留命令、输出路径和关键判断依据。

**阅读边界**: 本文件是 2026-06-20 的文档维护执行日志，记录的是**怎么把已落盘的真口径/公平口径实验结果同步进论文正文层与 PDF**，不是实验结论本身。正文结论以 [docs/thesis/paper/05_experiments_and_discussion.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/05_experiments_and_discussion.md) 为准，真口径数据权威来源是 [docs/thesis/08_terrain_following_pid_mpc_status.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/08_terrain_following_pid_mpc_status.md) §8。

---

## 0. 三层文档体系与本次维护的定位

更新文档前必须先认清三层结构，避免"改错层"：

| 层级 | 路径 | 职责 | 本次是否改动 |
|---|---|---|---|
| 论文正文层 | `docs/thesis/paper/` | 面向毕设 1–5 章的段落式叙述 | ✅ 主改动对象 |
| 工程证据层 | `docs/thesis/` | 实验依据、真口径数据、已知偏差与边界 | 仅作权威来源引用，不改 |
| 原始运行日志 | `docs/experiment/` | 单次实验命令、输出、坑点（含本文件） | ✅ 新增本文件 |

更新原则：**工程证据层（doc 08 §8 等）一旦因重跑产生新口径数据，正文层必须跟着同步，否则正文表格会与自己引用的图/证据层自相矛盾。** 本次遗漏的根因正是 doc 08 §8（2026-06-20 真口径/公平口径重跑）已落盘，但 paper 第 4/5 章仍停留在旧污染数据。

---

## Step 1: 检查 paper 正文层的更新遗漏

### 1.1 用 grep 定位 stale 数据

排查命令（在仓库根目录执行）：

```bash
# 旧 terrain datum bug 假象数 + 旧 MPC 改善百分比 + 旧 run 时间戳
grep -rn -E '0\.1752|4\.0768|4\.0207|20260610_175154|20260610_204314|38\.56|37\.05|21\.50|21%–39%|2\.8230|2\.8844' docs/thesis/
```

**关键发现**：第 4/5 章正文仍在引用以下已被取代的旧数据，与 doc 08 §8 矛盾：

| 位置 | 旧（污染/不公平口径） | 应替换为（真口径/公平口径，来源 doc 08） |
|---|---|---|
| 05 §5.5.2 terrain 主结果表 | `20260610_175154`，clearance_mean≈4.0m、RMSE 0.1752、depth_error_rmse≈7m | §8.2 `20260619_222639`（real_altitude、clearance_mean 1.95–2.70m、depth N/A） |
| 05 §5.5.4 MPC x/y/yaw 表 | `20260610_204314`，37.05%/21.50%/38.56% | §8.7 `20260620_011831` 公平口径四场景表 |
| 05 第 204 行证据清单 | 旧 run 路径 + "未全面超过 LOS" | 新 run 路径 + "仅直角 chicane LOS 更优" |
| 05 第 458 行本章小结 | `0.1752 m`、21%–39% | 真口径区间 0.56–1.14m + 公平口径结论 |
| 04 §4.5.1 第一/二层 | `0.1752 m`、21%–39% "分米级" | 真口径 ≈1.14m"米级以内" + 公平口径结论 |
| 04 §4.6 小结 | "分米级离底误差" | "米级以内（真口径，见 §4.5.1）" |
| pvs_extreme §场景2 | 改善约 38.56% | 改善约 51%（2.277m vs 4.69m） |
| 05 §5.1.1 实验架构表 | 表头重复两遍（笔误） | 删除多余表头行 |

### 1.2 整理原则（已与需求方确认）

- **数据口径**：旧数据全部"更新为真口径并加溯源注"——即替换为新数值，并在每处加 `> 数据口径` 引用块，注明取代的旧 run、修复原因（datum bug / +2.0m harness bug）、引用 doc 08 §8.x，以及 n=1 诚实边界。
- 不删除 doc 08 §2/§5.4 的旧表（它们带 ⚠️ 前后对比标记，是修复溯源的一部分）。

### 1.3 落地的编辑

逐处用真口径/公平口径数据替换，并加溯源块。两组核心新数据：

**真口径 terrain 主结果（doc 08 §8.2，`20260619_222639`）**：

| 指标 | PID baseline | PID terrain | MPC baseline | MPC terrain |
|---|---:|---:|---:|---:|
| seabed_clearance_min_m | 1.600 | 1.000 | 1.400 | 1.400 |
| seabed_clearance_mean_m | 2.699 | 1.954 | 2.657 | 2.647 |
| seabed_clearance_rmse_to_3m | 0.558 | 1.136 | 0.602 | 0.612 |
| depth_error_rmse_m | 6.493 | N/A | 6.427 | N/A |
| solve_time_mean_ms | nan | nan | 12.93 | 10.59 |
| solver_fallback_ratio | nan | nan | 0.000 | 0.1429 |

**公平口径 MPC x/y/yaw（doc 08 §8.7，`20260620_011831`）**：

| 场景 | yaw-only | LOS | MPC best | 结论 |
|---|---:|---:|---:|---|
| s_turn_long_wave | 0.093 | 1.047 | 0.055 | MPC 全胜（−41% / −95%） |
| hairpin_180deg | 4.69 | 4.69 | 2.277 | MPC 全胜（−51%） |
| s_turn_short_wave | 2.597 | 1.657 | 1.655 | MPC −36% vs yaw、与 LOS 持平 |
| chicane_90deg | 3.596 | 0.659 | 1.452 | 诚实边界：LOS 最优 |

> **关键判据（为什么数值会"翻案"）**：旧 MPC harness 的参考构建含 `+2.0m` 常值下游偏置，把整条 MPC 参考推到最近点下游、迫使 MPC 切弯，人为放大其横向 RMSE；两条 PID 基线无此偏置 → 对比不公平。删除该偏置（保留 `k*v*dt` 真预瞄项）后公平复跑，MPC 在多数工况优于或持平基线。详见 doc 08 §8.7。

### 1.4 验收

复跑 1.1 的 grep，确认正文层（04/05/pvs）已无未加溯源注的裸 stale 数；剩余命中应只落在 doc 08（带 ⚠️ 的旧表）和 doc 09（已标注 §0 重生成）这两个"保留作对比/溯源"的位置。

---

## Step 2: 重新生成 docs_pdf（pandoc）

### 2.1 环境探测（先确认引擎与字体）

```bash
pandoc --version | head -1          # pandoc 2.9.2.1
command -v xelatex || echo "no xelatex"   # 本环境无 xelatex
command -v wkhtmltopdf               # 有 wkhtmltopdf
fc-list | grep -i "zen hei"          # WenQuanYi Zen Hei（CJK 字体齐备）
```

**结论**：本环境缺 xelatex，[build_docs_pdf.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/build_docs_pdf.sh) 的 `detect_engine` 会自动回退到 **wkhtmltopdf**，无需额外安装。

### 2.2 生成命令

```bash
# 只转 docs/thesis 全树（本次确认范围 = 整个 docs/thesis），输出镜像到 docs_pdf/thesis/
bash scripts/build_docs_pdf.sh thesis
```

可选：`bash scripts/build_docs_pdf.sh thesis/paper` 只转正文层；`ENGINE=xelatex bash scripts/build_docs_pdf.sh thesis` 在装了 xelatex 的机器上强制走 LaTeX 引擎。

### 2.3 wkhtmltopdf 路径的关键陷阱（脚本已内置处理）

wkhtmltopdf 默认**禁止访问本地文件**，正文里 `../figures/...` 相对路径图片会被 `Blocked access to file` 丢弃。脚本的解法是两段式转换（见 [build_docs_pdf.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/build_docs_pdf.sh#L104-L124) `convert_one`）：

1. 先 `pandoc --self-contained` 把图片 base64 内嵌成自包含 HTML；
2. 再 `pandoc ... --pdf-engine=wkhtmltopdf` 渲染该 HTML 出 PDF。

因此图片能进 PDF 的前提是**图片已经在仓库内**（见 Step 3 的迁移），相对路径能被 `--resource-path` 解析到。

### 2.4 结果

```text
[build-pdf] 完成：成功 29，失败 2，输出根目录 docs_pdf/
```

29 个正文文档全部成功，关键章节 PDF（如 `04_decision_and_control.pdf` 约 7.7MB）体积反映 4 张 MPC 轨迹图已 base64 内嵌。

**2 个失败可忽略**：`control_mpc/_source_report.md` 与 `decision_bt_vs_fsm/_source_report.md` 是从原始 run 里**原样复制**的报告，内部用相对原 run 目录的 `figures/01_*.png` 引用图，脱离原目录无法解析。它们不是论文正文，失败不影响交付。

### 2.5 验收

```bash
ls -la --time-style=+%H:%M docs_pdf/thesis/paper/*.pdf docs_pdf/thesis/08_*.pdf
# 确认时间戳为本次生成时刻、04/05 章 PDF 体积偏大（图片已内嵌）
```

---

## Step 3: 图片迁移与大规模扫参命令总结

### 3.1 图片是怎么迁移到本仓库的

**机制**：`/auv_data`（gitignore，不随仓库同步）里是全部实验 run；只把**每类实验的关键参考 run** 的图迁到仓库内 `docs/thesis/figures/experiments/`，使正文能用相对路径引用并随仓库同步。迁移由 [scripts/sync_thesis_figures.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/sync_thesis_figures.sh) 完成。

迁移逻辑（脚本要点）：

- `MANIFEST` 数组硬编码"目标子目录 | 源 run（相对 `/auv_data`）| 报告文件名"四类主线实验；
- 每次运行 `rm -rf` 目标子目录再重建（**幂等**，可反复覆盖）；
- 复制 `figures/*.png`，并生成 `_SOURCE.md`（记录源 run、同步时间）+ 复制 run 自带的 `*.csv` / report，保留实验条件溯源。

```bash
bash scripts/sync_thesis_figures.sh            # 默认 /auv_data
bash scripts/sync_thesis_figures.sh --dry-run  # 只预览将要复制什么
AUV_DATA=/path/to/data bash scripts/sync_thesis_figures.sh   # 换数据根
```

### 3.2 本次发现的图片遗漏与修复（重要）

排查时发现 [sync_thesis_figures.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/sync_thesis_figures.sh) 的 MANIFEST 里 `control_mpc_xy_yaw_extreme` 仍指向**旧污染 run** `20260610_204314`（仓库内图是 06-18 同步的旧图），而公平口径新 run `20260620_011831` 从未被同步。修复：

```bash
# 1) 改 MANIFEST 指向公平口径 run（手工编辑脚本第 30 行）
#    control_mpc_xy_yaw_extreme|results/control/mpc_xy_yaw_extreme/20260620_011831|
# 2) 重新同步
bash scripts/sync_thesis_figures.sh
# 3) 校验：_SOURCE.md 指向新 run，best_comparison.csv 数值与 §5.5.4 表一致
cat docs/thesis/figures/experiments/control_mpc_xy_yaw_extreme/_SOURCE.md
cat docs/thesis/figures/experiments/control_mpc_xy_yaw_extreme/best_comparison.csv
```

新 run 还多出 `s_turn_long_wave_xy_v4_short_realtime.png`（MPC 全胜的代表图），已加进 04 章 §4.5.2 图组。

> **更新文档的通用顺序**：先确认 `/auv_data` 里有新 run → 改 MANIFEST → 跑 sync 脚本迁图 → 改正文表格/图引用 → 跑 `build_docs_pdf.sh` 出 PDF。Step 1→3 是因果链，顺序不能乱（图没迁进仓库，PDF 里就是旧图或空图）。

### 3.3 terrain 图的另一条生成路径（非迁移，而是脚本直出）

terrain following 6 张图不走 `/auv_data` 迁移，而是由 [tools/plot_terrain_following_figures.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/plot_terrain_following_figures.py) 直接读 bag/CSV 出图到 `docs/thesis/figures/terrain_following/`。本轮已用真口径主结果重生成（见 doc 09 §0）：

```bash
python3 tools/plot_terrain_following_figures.py \
  --main-result results/control/terrain_following_20260619_222639 \
  --ablation-summary results/control/pid_terrain_ablation_20260610_summary.csv \
  --terrain-config config/bridge_params.protocol_udp.pvs.terrain.yaml \
  --output-dir docs/thesis/figures/terrain_following \
  --target-clearance-m 3.0
```

### 3.4 大规模扫参实验是怎么组织的（重要命令总结）

本轮极大规模调试遵循 **C0→C1→C2–C5→P1→H1→H2** 的"低成本、少调试、可回滚"阶梯（详见 [docs/experiment/experiment_gap_conduct_plan.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/experiment_gap_conduct_plan.md)）。核心入口是 `tools/run_thesis_sweep.py`（场景 × seed × mpc_mode 笛卡尔积）+ `tools/aggregate_thesis_sweep.py`（聚合）。

| 阶段 | 目的 | 代表命令 |
|---|---|---|
| C0 | 命令契约 dry-run（不启仿真） | `python3 tools/run_thesis_sweep.py --scenarios baseline --seeds 0 --mpc-modes ua --duration 10 --label c0_contract --dry-run` |
| C1 | 单场景短时 smoke | `python3 tools/run_thesis_sweep.py --scenarios baseline --seeds 0 --mpc-modes ua --duration 20 --label c1_baseline_smoke` |
| C2 | baseline 3 seed 重复统计 | `python3 tools/run_thesis_sweep.py --scenarios baseline --seeds 0,1,2 --mpc-modes ua --duration 30 --label c2_baseline_3seed` |
| C3 | terrain PID low/mid/high | `bash scripts/run_terrain_benchmark.sh 30 pid terrain low`（mid/high 同理） |
| C4 | DVL dropout 四档 | `python3 tools/run_thesis_sweep.py --scenarios dvl_dropout_10,dvl_dropout_30,dvl_dropout_60,dvl_dropout_90 --seeds 0 --mpc-modes ua --duration 30 --label c4_dvl_1seed` |
| C5 | mag/sonar/combined | `python3 tools/run_thesis_sweep.py --scenarios mag_distortion_light,mag_distortion_heavy,sonar_clutter,combined_stress --seeds 0 --mpc-modes ua --duration 30 --label c5_sensor_1seed` |
| H1 | UA-MPC 主消融（场景×模式×seed） | `python3 tools/run_thesis_sweep.py --scenarios baseline,dvl_dropout_60,combined_stress --seeds 0,1,2 --mpc-modes baseline,ua --duration 60 --label h1_uampc_main_ablation` |
| H2 | UA-MPC 参数灵敏度 | `python3 tools/run_thesis_sweep.py --scenarios combined_stress --seeds 0,1,2 --mpc-modes ua --duration 60 --param-grid 'low_conf_scale:1.5,3.0,5.0' --label h2_uampc_low_conf_scale` |

每轮 sweep 后立即聚合（成本极低，只读 `results.csv`）：

```bash
python3 tools/aggregate_thesis_sweep.py \
  --input log/thesis_sweep/<run>/results.csv \
  --output-dir results/thesis_sweep_aggregates/<run>
```

控制侧 / 不确定性指标另有聚合器：

```bash
python3 tools/aggregate_control_metrics.py --input <h1_run>     # lateral RMSE / control rate / fallback
python3 tools/aggregate_uncertainty_metrics.py --input <run>    # NIS / 自适应 R 触发率
```

**组织约束（避免踩坑）**：

- `run_thesis_sweep.py` 默认追加 `--bridge-backend protocol_udp`、`--arbiter-profile`、`--auto-activate` 三项低层契约，**不能去掉**，否则 bag 缺 IMU/DVL/depth，`offline_ekf_benchmark.py` 会报 No IMU samples。
- `run_terrain_benchmark.sh` 会临时改 `brain_linux/config/feature_flags.yaml` 并在退出时恢复；若中途被强杀，必须手工核对 `.feature_flags_backup.yaml` 与 `feature_flags.yaml` 是否复原。
- 证据边界铁律：`n=1` 只能写 smoke / 单次；≥3 seed 聚合后才写 mean±std；emulated Jetson ≠ 真机；9 个 PVS chaos ≠ 完整海缆巡检海试；MPC ≠ 全面优于 PID/LOS。

### 3.5 三组确定性过渡实验（F1/F2/F3，离线可复现）

除 PVS 扫参外，本轮还补了三组无需实时仿真的确定性脚本（详见 [docs/thesis/11_transition_experiments_F1_F2_F3.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/11_transition_experiments_F1_F2_F3.md)）：

```bash
python3 tools/helical_cable_magnetic_scan.py        # F1 三相螺旋漏磁
python3 tools/es_ekf_extrinsics_benchmark.py --true-profile medium \
  --estimation-modes calibrated,no_lever_arm,no_mounting_angle   # F2 外参敏感度
python3 tools/jitter_boundary_ekf_benchmark.py      # F3 DVL 网络抖动边界
```

三脚本均 matplotlib Agg 出图 + CSV 落盘到 `$AUV_DATA_ROOT/results/<sub>/<TS>/`，固定 seed 可复现。

---

## 4. 之后独立更新文档的最小检查清单

1. **查新口径**：工程证据层（尤其 doc 08 §8、doc 09 §0）是否有新重跑取代旧数据？`grep` 旧 run 时间戳定位正文 stale 数。
2. **迁图**：`/auv_data` 有新关键 run → 改 [sync_thesis_figures.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/sync_thesis_figures.sh) MANIFEST → `bash scripts/sync_thesis_figures.sh` → 核对 `_SOURCE.md` 与 CSV。
3. **改正文**：替换数值 + 加溯源块（注明旧 run、修复原因、引用 doc 08 §x、n=1 边界）；同步更新嵌入图文件名。
4. **出 PDF**：`bash scripts/build_docs_pdf.sh thesis`，确认成功数、关键章节 PDF 体积、时间戳。
5. **回归 grep**：确认正文层无裸 stale 数（仅保留 doc 08/09 带标注的对比/溯源位置）。
