# 硕士论文实验体系 — Phase 3 实施计划（E4 → Final）

> **本文件路径**：`.trae/documents/thesis_experiment_phase3_e4_to_final.md`  
> **依赖前置**：  
> - `.trae/documents/thesis_experiment_uplift_plan.md`（总规划，已批准）  
> - `.trae/documents/thesis_experiment_phase2_implementation.md`（Phase 2，已批准并部分落地）  
> **本对话 scope**：仿真验证控制算法、ES-EKF 正确性、Jetson 部署可用性  
> **本对话排除**：硬件电路、纯磁场（九参数标定）、实物部署（不改对外接口）、图像美观性、论文写作浓缩

---

## 0. Executive Summary

总规划 17 项 TODO 已完成 12 项（Step 0、S1–S4、E1、E2、E3）。E4 已 in_progress。本计划聚焦**剩余 5 项**：

1. **E4** — EKF 协方差 → MPC 置信度耦合（继续完成，已搭好桥头堡：EKF 节点已发 `/auv/state/covariance`）
2. **E5** — 三场景 sweep 命令薄壳（DVL / 磁 / 综合）
3. **E6** — 参数扰动 sweep + 敏感性分解
4. **Final-A** — 8 篇 `docs/thesis/*.md` 骨架 + 数据回填
5. **Final-B** — Post-Snapshot 总结 + 文档偏差闭环 + INDEX 链接

每一步都设计了**单独可落、单独可回退、并行最大化**的梯度路径。

---

## 1. 现状定格（Pre-Snapshot @ Phase 3 开端）

### 1.1 已落地（不重复，仅记录）

| # | 阶段 | 文件 | 关键改动 |
|---|---|---|---|
| 1 | Step 0 | [es_ekf.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py) / [offline_ekf_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/offline_ekf_benchmark.py) | 4 个阻断 bug 修复 |
| 2 | S1 | [start_experiment.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment.sh) | CLI flag 增强、finalize 轮询、env 注入 |
| 3 | S2 | [scenarios/](file:///home/auv_user/auv_ws/AUV-Master-Project/scenarios) + [run_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py) | 9 个 yaml + sweep harness |
| 4 | S3 | [uncertainty_metrics.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/uncertainty_metrics.py) | NIS proxy + 真 NIS（E2 一并落） |
| 5 | S4 | [run_jetson_emulated_bench.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_jetson_emulated_bench.sh) | /proc 采样 |
| 6 | E1 | [es_ekf.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py) | `correct_mag()` + `feature_flags.enable_mag_correction` |
| 7 | E2 | [es_ekf.py L138-145](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L138-L145) + [_correct() L376-415](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L376-L415) | NIS 滑动窗口 + 自适应 R + `get_nis_stats()` |
| 8 | E3 | [auv_mpc_controller.py L159-260](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py#L159-L260) + [mpc_controller.py L114-117](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py#L114-L117) | sigmoid + (1-conf)^α + AUV_MPC_MODE env 贯通 |

### 1.2 关键现状发现（影响 E4 实施路径）

- **EKF 节点已经在发协方差**：[auv_localization_node.py L461-463](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_localization/auv_localization/auv_localization_node.py#L461-L463) 把 15×15 P 矩阵 reshape 成 225 元素 `Float32MultiArray` 发到 `/auv/state/covariance`。
- 因此 Phase 2 计划中 "新建 `ekf_covariance_publisher.py`" 的备选路径 = **直接复用 `/auv/state/covariance` topic**，更省工，符合 Phase 2 §3 E4 节"实现走两路"中的"备选路径"。
- **MPC 控制节点**：[auv_controller_node.py L150 / L187](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py#L150) 已有 `_latest_confidence` 字段但实际只透传 `setpoint["confidence"]`（来自上游 setpoint 发布者，为 placeholder）。这就是 E4 的注入点。
- **MPC 内部 confidence 流**：6 处使用，集中在 [mpc_controller.py L94/136/172/174/185/239](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py)，所有路径都基于 `setpoint.get("confidence", 1.0)`，因此**无需改 MPC 内部，只需在 controller_node 把 setpoint["confidence"] 覆盖**即可。

### 1.3 待解决的剩余风险

| # | 项 | 现状 | 风险 |
|---|---|---|---|
| R1 | E4 协方差融合系数 | sigma_xy_ref 默认值未确定 | 默认值过严 → conf ≈ 0；过松 → 失敏 |
| R2 | sweep 时长 | 单 run 120s × 70 runs = 2.3h；全网格更长 | 跑不完；需"smoke + full" 双档 |
| R3 | docs/thesis 数据未生成 | 实验未跑全 | 需先骨架后回填，否则 TBD 满天飞 |
| R4 | T8 drift log | 文档差异点散落多处 | 需一次梳理而非每篇追加 |

---

## 2. 交付物清单（Phase 3 范围）

### 2.1 代码与配置（按梯度顺序）

| 阶段 | 文件 | 类型 | 论文章节 | 回退档 |
|---|---|---|---|---|
| E4-a | [auv_controller_node.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py) | 改 | §4.4 主创新点 | ROS 参数 `enable=false` 一键关 |
| E4-b | 同上 + [mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py)（仅扩参，可选） | 改 | §4.4 | env `AUV_MPC_MODE=baseline` 关闭整链 |
| E5 | `scripts/run_dvl_sweep.sh` / `run_mag_sweep.sh` / `run_combined_sweep.sh` | 新建 | §3.5.1 / §3.5.2 / §4.5 | 删脚本回退到底层 python 命令 |
| E6 | [run_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py) | 改 | §5.5 | 不传 `--param-grid` 完全等价旧行为 |

### 2.2 文档（`docs/thesis/*.md` 8 篇）

| # | 文件 | 论文章节 | 内容要点 |
|---|---|---|---|
| T1 | `docs/thesis/00_overview.md` | §1 / §5.1 | 实验体系全图、术语、命令索引、Pre/Post-Snapshot 总览 |
| T2 | `docs/thesis/01_baseline_repro_log.md` | §3.5 baseline / §5.1.2 | Step 0 修复后 baseline 重跑日志 + RMSE/CEP50 表 |
| T3 | `docs/thesis/02_es_ekf_validation.md` | §3.5.1 / §3.5.2 / §3.6 | ES-EKF 三路对比 + DVL 丢包鲁棒 + 磁畸变扰动 |
| T4 | `docs/thesis/03_uncertainty_quantification.md` | §3.4 / §4.4.2 | NIS 白化检验 + EKF P 时间序列 + UA-MPC 耦合 |
| T5 | `docs/thesis/04_mpc_robustness_ablation.md` | §4.5 | baseline-MPC vs UA-MPC × 7 场景 × 5 种子消融 |
| T6 | `docs/thesis/05_scenario_recipes.md` | §5.2 | 9 个 yaml 物理含义 + 覆盖矩阵 + 新手 SOP |
| T7 | `docs/thesis/06_jetson_deploy_emulated.md` | §5.5 | Jetson 仿真侧 CPU/MEM/延迟 |
| T8 | `docs/thesis/99_repo_doc_drift_log.md` | — | 文档差异修订日志（顺手） |

每篇模板（仿照 [benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md)）：

```
# <标题>
**日期** / **目的** / **依赖代码 commit 范围**
## 1. 命令清单（新手可直接复制）
## 2. 期望产出（路径 + 文件清单）
## 3. 实验结果（表格 + 关键图引用）
## 4. 错误处理（提及，不展开）
## 5. 与论文章节映射
```

---

## 3. 详细实施步骤

### Step E4 — EKF P → MPC 置信度耦合（任务 #13，in_progress）

**Why**：§4.4 主创新点 "Uncertainty-Aware MPC" 的真协方差通路落地。否则 MPC 拿到的只是 placeholder confidence。

**修改文件**：[brain_linux/src/auv_controller/auv_controller/auv_controller_node.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py)

**How**：

1. **import 段**：补 `from std_msgs.msg import Float32MultiArray`、`import math`、`import numpy as np`（已有则跳过）。

2. **`__init__` 内**（紧跟 L187 `_latest_confidence` 后，约 L188 处）：
   ```python
   # E4 — EKF 协方差驱动的置信度（论文 §4.4）
   self._latest_p_trace_xy = float('nan')
   self._latest_p_trace_z = float('nan')
   self.declare_parameter('cov_to_conf.enable', True)
   self.declare_parameter('cov_to_conf.sigma_xy_ref', 1.0)
   self.declare_parameter('cov_to_conf.sigma_z_ref', 0.5)
   self._cov_conf_enable = bool(self.get_parameter('cov_to_conf.enable').value)
   self._sigma_xy_ref = float(self.get_parameter('cov_to_conf.sigma_xy_ref').value)
   self._sigma_z_ref = float(self.get_parameter('cov_to_conf.sigma_z_ref').value)
   # AUV_MPC_MODE=baseline 时整条短路（与 sweep 一致）
   env_mode = os.environ.get('AUV_MPC_MODE', 'ua').strip().lower()
   if env_mode == 'baseline':
       self._cov_conf_enable = False
   ```

3. **`__init__` 内** 添加订阅（紧跟其他 sub 后，约 L199）：
   ```python
   self.cov_sub = self.create_subscription(
       Float32MultiArray, '/auv/state/covariance', self._on_covariance, 20
   )
   ```

4. **新增回调方法**（建议放在其他 `_on_*` 回调附近）：
   ```python
   def _on_covariance(self, msg: Float32MultiArray) -> None:
       """订阅 ES-EKF 15x15 P 矩阵，缓存关键 trace 用于置信度映射。"""
       data = list(msg.data)
       if len(data) != 225:
           return
       p = np.asarray(data, dtype=float).reshape(15, 15)
       self._latest_p_trace_xy = float(p[0, 0] + p[1, 1])
       self._latest_p_trace_z = float(p[2, 2])

   def _confidence_from_cov(self) -> float | None:
       """trace_xy → conf = exp(-trace_xy / sigma_xy_ref)；返回 None 表示不可用。"""
       if not self._cov_conf_enable:
           return None
       if not math.isfinite(self._latest_p_trace_xy):
           return None
       sigma = max(self._sigma_xy_ref, 1e-6)
       conf = math.exp(-self._latest_p_trace_xy / sigma)
       return max(0.0, min(1.0, conf))
   ```

5. **注入点**：找到 `_on_setpoint` 或 `_on_timer` 内构造 setpoint dict 处（grep `setpoint["confidence"]`），在传入 controller 之前覆盖：
   ```python
   conf_from_cov = self._confidence_from_cov()
   if conf_from_cov is not None:
       setpoint["confidence"] = conf_from_cov
       self._latest_confidence = conf_from_cov
   ```

**回退点**：
- 最稳：ROS 参数 `cov_to_conf.enable=false`（订阅仍生效但不覆盖 setpoint）
- 极速：`AUV_MPC_MODE=baseline`（自动短路）
- 极端：删除注入点 5 行（订阅与回调可保留，做日志即可）

**验证**：
```bash
cd /home/auv_user/auv_ws/AUV-Master-Project
colcon build --packages-select auv_controller --symlink-install
source install/setup.bash
# 启动一次仿真 30s，订阅协方差与 confidence
bash scripts/start_experiment.sh --sim-backend pvs --duration 30 --mpc-mode ua &
sleep 5
ros2 topic echo /auv/state/covariance --once
ros2 topic echo /auv/controller/debug --once | grep confidence
```
通过条件：协方差 225 维数据非零；debug 中 confidence 不再恒为 1.0。

---

### Step E5 — 三场景 sweep 命令薄壳（任务 #14）

**Why**：让新手一行复现 §3.5.1 / §3.5.2 / §4.5 三大组实验。

**新建文件**（每个 ≤ 30 行，`set -euo pipefail` + 透传 `"$@"`）：

#### 5.1 `scripts/run_dvl_sweep.sh`（§3.5.1）
```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"
exec python3 tools/run_thesis_sweep.py \
    --scenarios baseline,dvl_dropout_10,dvl_dropout_30,dvl_dropout_60,dvl_dropout_90 \
    --seeds 0,1,2,3,4 --mpc-modes baseline,ua --duration 120 "$@"
```

#### 5.2 `scripts/run_mag_sweep.sh`（§3.5.2）
```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"
exec python3 tools/run_thesis_sweep.py \
    --scenarios baseline,mag_distortion_light,mag_distortion_heavy \
    --seeds 0,1,2,3,4 --mpc-modes baseline,ua --duration 120 "$@"
```

#### 5.3 `scripts/run_combined_sweep.sh`（§4.5）
```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"
exec python3 tools/run_thesis_sweep.py \
    --scenarios baseline,sonar_clutter,combined_stress \
    --seeds 0,1,2,3,4 --mpc-modes baseline,ua --duration 120 "$@"
```

**回退点**：脚本是 wrapper，删除直接跑底层命令即可。

**验证**：
```bash
chmod +x scripts/run_*_sweep.sh
bash scripts/run_dvl_sweep.sh --duration 30 --seeds 0  # smoke：5 scen × 2 mode = 10 runs
ls log/thesis_sweep/*/results.csv | tail -1
```
通过条件：results.csv 行数 = `scen × seed × mode`。

---

### Step E6 — 参数扰动 + 敏感性分解（任务 #15）

**Why**：§5.5 "Sim-to-Real 敏感性讨论" 需要参数对结果的方差贡献。

**修改文件**：[tools/run_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py)

**How**：

1. CLI 加 `--param-grid 'low_conf_scale:1.5,3.0,5.0;confidence_smoothness_k:4,8,16'`
2. 解析为 `dict[str, list[float]]` → 笛卡尔积扩到外层循环，每组合通过 env `AUV_MPC_PARAM_OVERRIDES` 注入（JSON 字符串），由 [mpc_controller.py L114-117](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py#L114-L117) 附近读取：
   ```python
   overrides_json = os.environ.get("AUV_MPC_PARAM_OVERRIDES", "")
   if overrides_json:
       try:
           overrides = json.loads(overrides_json)
           weights_cfg.update(overrides)
       except Exception:
           pass
   ```
3. 输出 `sensitivity.csv` 列：`low_conf_scale, smoothness_k, scenario, seed, mpc_mode, xy_rmse, ctrl_smooth`
4. 简化方差分解：用 `pandas.groupby + var()` 计算每参数的方差贡献占比；写 `sensitivity_summary.md`（4-5 行表格）

**回退点**：不传 `--param-grid` 则旧行为完全等价。`AUV_MPC_PARAM_OVERRIDES` 留空时也不影响 MPC 默认参数。

**验证**：
```bash
python3 tools/run_thesis_sweep.py \
    --scenarios baseline --seeds 0 --mpc-modes ua \
    --param-grid 'low_conf_scale:1.5,3.0' --duration 30
# 期望：results.csv 2 行；sensitivity.csv 同 2 行；sensitivity_summary.md 出现
```

---

### Step Final-A — 8 篇 docs/thesis 骨架与回填（任务 #16）

**Why**：把代码 + sweep 结果绑成论文章节闭环。

**操作分三步**：

#### A.1 建骨架（无需运行实验，仅依赖现有数据）

```bash
mkdir -p docs/thesis
```
按 §2.2 表格依次创建 8 个 .md。每篇填好头部、命令清单、期望产出、错误处理、章节映射；"实验结果"段先填 `<TBD>` 占位（baseline 已有数据的 T2 例外）。

#### A.2 跑最小验证 sweep 后回填表格

```bash
# Smoke runs（约 8-10 分钟）
bash scripts/run_dvl_sweep.sh --duration 30 --seeds 0
bash scripts/run_mag_sweep.sh --duration 30 --seeds 0
bash scripts/run_combined_sweep.sh --duration 30 --seeds 0
# 不确定性度量
python3 tools/uncertainty_metrics.py --input log/thesis_sweep/<latest>/baseline_seed0_ua/<bag>.mcap
# Jetson emulated
bash scripts/run_jetson_emulated_bench.sh --duration 60
```

把以下 CSV/PNG 摘要回填到 T2~T7 "实验结果" 段：
- `log/thesis_sweep/<ts>/results.csv` → T3/T5
- `<bag_dir>/uncertainty_*.csv` 与 PNG → T4
- `log/jetson_emu/<ts>/cpu_mem.csv` 与 boxplot → T7
- 现有 `docs/experiment/benchmark_test_log.md` 数据 → T2

#### A.3 各篇关键内容速览

- **T1 `00_overview.md`**：实验体系全图（mermaid）→ Pre/Post-Snapshot → 命令脚手架索引（链到所有 sweep 脚本与 tools）→ 章节映射矩阵
- **T2 `01_baseline_repro_log.md`**：完全继承 [benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md) 数据，补 Step 0 修复点说明
- **T3 `02_es_ekf_validation.md`**：三路对比 + DVL 丢包 RMSE 表（4 档）+ 磁畸变 2 档；图引 `tools/offline_ekf_benchmark.py --export both` 生成的 PNG/PDF
- **T4 `03_uncertainty_quantification.md`**：NIS 时间序列图（来自 [uncertainty_metrics.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/uncertainty_metrics.py)）+ r_scale 自适应轨迹 + EKF P trace_xy 与 confidence 同图叠图
- **T5 `04_mpc_robustness_ablation.md`**：baseline vs ua 在 7 场景的 RMSE/ctrl_smooth 双指标对比表 + boxplot
- **T6 `05_scenario_recipes.md`**：9 yaml 物理意义说明 + 覆盖矩阵（场景 × 论文章节）+ 新手 SOP
- **T7 `06_jetson_deploy_emulated.md`**：CPU%/MEM/100ms 滚动延迟分布；明确"emulated, not on-device"
- **T8 `99_repo_doc_drift_log.md`**：见 Final-B

---

### Step Final-B — Post-Snapshot 总结 + drift log + INDEX（任务 #17）

**Why**：闭环。

**修改文件**：

1. **新建** `docs/thesis/99_repo_doc_drift_log.md`：
   - Item 1：`benchmark_test_log.md` Step 2 中"已修复 kill → kill -INT" → 实际现在是 finalize 轮询 + SIGTERM 兜底（来自 S1）
   - Item 2：`rosbag_analysis_validation.md` 中 Std-EKF 异常现象 → 部分根因 = Step 0 B3（四元数未归一化），引修复点
   - Item 3：`docs/user-guide/05_benchmarks.md` ↔ 新 sweep 体系交叉链接（双向引用）
   - Item 4：`docs/internals/09_es_ekf.md` 新 NIS / 自适应 R / `correct_mag()` 接口补充

2. **修改** [docs/INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/INDEX.md)：末尾追加 thesis 板块，列出 8 篇文档链接。

3. **回填** [`.trae/documents/thesis_experiment_uplift_plan.md`](file:///home/auv_user/auv_ws/AUV-Master-Project/.trae/documents/thesis_experiment_uplift_plan.md) §9 Post-Snapshot：
   - 8 篇文档清单 + 行数（`wc -l docs/thesis/*.md`）
   - sweep 实际跑了多少 / 计划 70 runs
   - baseline vs UA-MPC 在高扰动场景的 RMSE 改善百分比
   - Jetson emulated 60s 跑下 CPU P95 / RSS Peak / 100ms 滚动延迟 P95
   - `git diff --stat HEAD~N..HEAD` 概要

4. 同步回填本计划（Phase 3）§8 Post-Snapshot。

**回退点**：文档可逐篇独立交付；Post-Snapshot 不影响代码。

**验证**：
```bash
ls docs/thesis/ | wc -l        # ≥ 8
grep -r "TBD" docs/thesis/      # 应为空（除非显式留作 Phase 4）
grep -c "thesis" docs/INDEX.md  # ≥ 1
```

---

## 4. 风险与回退矩阵

| 风险 | 阶段 | 影响 | 回退路径（梯度） |
|---|---|---|---|
| E4 sigma_xy_ref 默认值不合适 | E4 | conf 走极端 | (a) 调 ROS 参数；(b) `cov_to_conf.enable=false`；(c) `AUV_MPC_MODE=baseline` |
| E4 covariance 订阅引入抖动 | E4 | MPC 输出抖振 | (a) 加低通滤波到 `_latest_p_trace_xy`；(b) 关订阅 |
| E5 sweep 单 run 失败 | E5 | 表格不全 | run_thesis_sweep 已写 `failures.log` 隔离，事后单跑补齐 |
| E5 70 runs 跑不完 | E5 | 时间超 | smoke = `--duration 30 --seeds 0`（10 分钟）；full 留过夜 |
| E6 参数网格爆炸 | E6 | 跑不动 | 默认 3×3=9 组；文档建议先 `--seeds 0 --duration 30` |
| Final 实验数据未跑全 | Final-A | TBD 满天飞 | 先骨架（步骤 A.1）即可交付；A.2/A.3 留次轮 |
| T8 drift 信息散落 | Final-B | 写不全 | 单文件梳理；INDEX 链接独立可加 |

**并行性**：
- E4 必须先（其他后续依赖 UA-MPC 真协方差耦合）
- E5 三脚本互独立 → 可并行写
- E5 之后 → E6（共用 sweep 基础）
- Final-A 文档骨架可在 E4 完成后**与 E5/E6 并行写**
- Final-A 数据回填依赖 E5 实跑结果
- Final-B 完全独立（不依赖任何代码改动），可任何时候开写

---

## 5. 假设与决策（沿用前置 plan）

- **D1 = B**：磁观测仅 sim 钩子（已落 E1）
- **D2 = B**：UA-MPC 走 sigmoid + EKF 协方差耦合 + 消融（E3 ✅、E4 进行中）
- **D3 = A**：Step 0 全修 + 重跑（已落）
- 不引入新仿真后端
- 不动 Jetson 对外接口
- 文档语言：中文为主

---

## 6. 验证总表

| 阶段 | 命令 | 通过条件 |
|---|---|---|
| E4 | `bash scripts/start_experiment.sh --duration 30 --mpc-mode ua` + `ros2 topic echo /auv/state/covariance --once` | 协方差非零；debug confidence 不恒 1.0 |
| E5 | `bash scripts/run_dvl_sweep.sh --duration 30 --seeds 0` | results.csv 出 10 行（5×2） |
| E6 | `python3 tools/run_thesis_sweep.py ... --param-grid 'low_conf_scale:1.5,3.0' --duration 30 --seeds 0 --mpc-modes ua` | sensitivity.csv 出 2 行；summary.md 有方差占比 |
| Final-A | `ls docs/thesis/ \| wc -l ≥ 8` | 8 篇 .md 全在 |
| Final-B | `grep thesis docs/INDEX.md` 与 `grep TBD docs/thesis/` | INDEX 有链接；TBD 不残留 |

---

## 7. 任务 → TODO 镜像

| TODO # | 阶段 | 状态（开本计划时） |
|---|---|---|
| 13 | E4 EKF→MPC 耦合 | in_progress（本计划主线） |
| 14 | E5 sweep 命令薄壳 | pending |
| 15 | E6 参数敏感性 | pending |
| 16 | Final 8 篇 docs/thesis/*.md | pending |
| 17 | Final Post-Snapshot + drift log + INDEX | pending |

---

## 8. Post-Snapshot（Phase 4 解锁后回填）

> Phase 3 计划在 Phase 4 P2 收口后由 D7.2 终端解锁会话二次回填；以下为最终交付盘点。Phase 3 与 Phase 2 共享 thesis md 文档族，本节仅记 Phase 3 增量。

### 8.1 8 篇文档行数 + 总词数

> 行数同 Phase 2 §8.1（合计 1488 行）；词数（中文按字符近似）：

| 文件 | 行数 | 字符数（含中英） |
| --- | ---: | ---: |
| INDEX.md | 78 | ≈ 2.4 K |
| 00_overview.md | 186 | ≈ 7.5 K |
| 01_baseline_repro_log.md | 155 | ≈ 5.5 K |
| 02_es_ekf_validation.md | 145 | ≈ 5.6 K |
| 03_uncertainty_quantification.md | 172 | ≈ 6.6 K |
| 04_mpc_robustness_ablation.md | 190 | ≈ 7.6 K |
| 05_scenario_recipes.md | 204 | ≈ 7.8 K |
| 06_jetson_deploy_emulated.md | 180 | ≈ 7.0 K |
| 07_drift_log_and_known_issues.md | 178 | ≈ 7.0 K |
| **合计** | **1488** | **≈ 57 K** |

### 8.2 sweep 实际 run 数 / 失败率

参见 Phase 2 §8.2 表（共享数据，避免重复）。要点：

- E4-E6 sweep harness 与脚本 ✅ 全部就位（Phase 3 计划已落地）
- B1 smoke 进行中（dvl_dropout_60 × 2 mode × 1 seed × 60s = 4 runs，已能跑通）
- B2 / B3 / mag / combined sweep deferred（解锁条件：D7.2 已解，仅排队执行）
- baseline 60s real run（11:33 落盘 bag）已成功 mcap 后处理

### 8.3 UA-MPC 相对 baseline-MPC xy_rmse 改善百分比（按场景）

参见 Phase 2 §8.3（共享）。本会话 B1 smoke 6 个 sweep run 全部 bench_failed（sensor topic 缺失，根因详见 Phase 2 §8.7 D8.1）；UA-MPC vs baseline 多 seed 对照阻塞，留作 D8 follow-up。

### 8.4 Jetson emulated 60s 实测指标

> 完整表格参见 Phase 2 §8.4。论文阈值层面三大指标 p95 全部达标：
>
> - `/auv/state/filtered` p95 = **42.34 ms** (< 50 ms ✅)
> - `/auv/control/setpoint` p95 = **62.10 ms** (< 200 ms ✅)
> - 传感器主链 ~34 Hz，period 稳定（标准差 < 1 ms）
>
> 关键发现：`/auv/control/confidence` 60s 内 0 条消息——这是 [drift log D3.x](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/07_drift_log_and_known_issues.md) "confidence 话题未发布"的实测证据；论文 §3.5 / §4.4 引用置信度链路时需以 `/auv/state/covariance` 为唯一上行通道（73 Hz, 全程发布 ✅）。

### 8.4a 离线 EKF 算法对照（同一 113311 bag）

> 完整表格参见 Phase 2 §8.4a。单 seed n=1 锚点：

| 算法 | XY RMSE (m) | Z RMSE (m) | CEP50 (m) |
| --- | ---: | ---: | ---: |
| Raw DR | 15.053 | 0.137 | 9.636 |
| Std EKF | 15.116 | 0.137 | 9.661 |
| ES-EKF | 15.116 | **20.848 ⚠** | 9.661 |

> ES-EKF Z 维 20.8 m 异常源自首帧自动对齐时 z 偏移 24 m（D8.2 已登记）。论文 §4.3 ES-EKF 对照需先解 D8.2 再下结论。

### 8.5 git 改动文件清单

参见 Phase 2 §8.5（共享）。Phase 3 增量（与 Phase 2 之外）：

- `tools/mcap_period_stats.py`（新文件，本会话任务 2 产出）
- `tools/run_thesis_sweep.py` 的 `--param-grid` / `sensitivity_summary` 段
- `scripts/run_dvl_sweep.sh` / `run_mag_sweep.sh` / `run_combined_sweep.sh` 三个 sweep 薄壳

`git status -s` 显示 30+ 文件 modified（覆盖 algorithm/brain_linux/tools/scripts/docs 五大域）。

### 8.6 与 Phase 1 Pre-Snapshot 的 delta 总结（一句话）

> Phase 1 仅有单 seed benchmark + ROS 节点拓扑；Phase 2/3/4 收口后，仓库新增 9 篇 thesis md（1488 行）+ 6 个 sweep / bench 脚本 + 3 个核心算法 patch（自适应R / sigmoid / param overrides）+ 1 个 mcap 后处理工具，使论文 §3.4 / §3.5 / §4.4 / §4.5 / §5.2 / §5.4 / §5.5 / §5.5.1 / §5.6 全部章节获得至少一份代码或文档锚定。

### 8.7 与 Phase 4 收口的延续

- Phase 3 计划的 Final-A / Final-B 任务（写 8 篇 md + Post-Snapshot + INDEX）由 Phase 4 §3 §4 §8 完整执行，本会话 P2 step 完成
- 后续会话承接：B1-B3 多 seed 数据回填到 thesis md 占位、C 档画图、Phase 1 §8 占位（如有）

---

## 9. 不在本次范围（明确排除）

- 图像美观性（统一字体/色板/坐标轴样式）→ Phase 4
- 论文写作浓缩（AI 二次加工正文）→ Phase 4
- 实物部署（不改 Jetson 对外接口）
- 硬件电路、九参数标定相关代码

以上 4 项**计划已固定**，本次只交付支撑它们的代码与数据基础。
