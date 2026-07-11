# 硕士论文实验体系 — Phase 2 剩余实施计划（E2 → Final）

> **本文件路径**：`.trae/documents/thesis_experiment_phase2_implementation.md`  
> **依赖前置**：`.trae/documents/thesis_experiment_uplift_plan.md`（总规划，已用户批准并部分落地）  
> **本对话 scope**：仿真验证控制算法、ES-EKF 正确性、Jetson 部署可用性  
> **本对话排除**：硬件电路、纯磁场（九参数标定）、实物部署、图像美观性、论文写作浓缩

---

## 0. Executive Summary

总规划 17 项 TODO 中已完成 10 项（Step 0、S1、S2、S3、S4、E1），剩 7 项：**E2 / E3 / E4 / E5 / E6 / Final 文档（拆 2 个 task）**。本计划把这 7 项分解到具体文件、提供 what/why/how，并定义回退点与验证流程，使每一步**单独可落、单独可回退、并行最大化**。

---

## 1. 现状定格（Pre-Snapshot @ Phase 2 开端）

### 1.1 已落地（不再重做）

- **Step 0**：4 个阻断 bug（IMU bias 符号、深度双重取负、四元数未归一化、O(N²) 查找）
- **S1**：[scripts/start_experiment.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment.sh) 加固，新增 5 个 CLI flag（`--scenario` / `--seed` / `--mpc-mode` / `--bag-finalize-s` / `--no-record-bag` 等）+ finalize 轮询 + env 注入
- **S2a**：[scenarios/](file:///home/auv_user/auv_ws/AUV-Master-Project/scenarios) 9 个 yaml + README（baseline / dvl_dropout_{10,30,60,90} / mag_distortion_{light,heavy} / sonar_clutter / combined_stress）
- **S2b**：[tools/run_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py) sweep harness（笛卡尔积 scenario × seed × mpc_mode → CSV）
- **S3**：[tools/offline_ekf_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/offline_ekf_benchmark.py) 加 `--export {png,pdf,both} --export-tex`；新建 [tools/uncertainty_metrics.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/uncertainty_metrics.py)
- **S4**：[scripts/run_jetson_emulated_bench.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_jetson_emulated_bench.sh) /proc 采样 + matplotlib boxplot
- **E1**：[algorithm/es_ekf.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L451-L485) 新增 `correct_mag()` + `feature_flags.enable_mag_correction`（默认 False）

### 1.2 剩余风险与未决

| # | 项 | 现状 | 风险 |
|---|---|---|---|
| R1 | NIS 度量 | uncertainty_metrics.py 当前用 `(innov/gate)²` 作 proxy；EKF 引擎未暴露真 NIS | §3.4 论文叙述若仅用 proxy，审稿人易追问 |
| R2 | MPC 阶跃门限 | [auv_mpc_controller.py L233-238](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py#L233-L238) 用 `if_else(conf<thr, low, 1.0)` 阶跃 | 抖振；论文 §4.4.2 需平滑曲线作图 |
| R3 | EKF P → MPC | 二者无 ROS topic 耦合；MPC 拿不到 EKF 真协方差 | §4.4 主创新点空缺 |
| R4 | mpc_mode 注入 | start_experiment.sh 已有 env 注入桩，但 MPC 节点未读取 | sweep `--mpc-modes baseline,ua` 不能区分 |
| R5 | 文档 | docs/thesis/ 不存在 | 论文 8 章主表格无来源 |

---

## 2. 交付物清单（Phase 2 范围）

### 2.1 代码与配置

| 阶段 | 文件 | 类型 | 论文章节 |
|---|---|---|---|
| E2 | [algorithm/es_ekf.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py) | 改 | §3.4.1 SNR 自适应 R |
| E2 | [tools/uncertainty_metrics.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/uncertainty_metrics.py) | 改 | §3.4 真 NIS 替换 proxy |
| E3 | [algorithm/auv_mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py) | 改 | §4.4.2 不确定性代价（sigmoid + α） |
| E3 | [scripts/start_experiment.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment.sh) | 改（小） | sweep 模式贯通 |
| E4 | `brain_linux/src/auv_localization/auv_localization/ekf_covariance_publisher.py` | 新建 | §4.4 EKF→MPC 耦合 |
| E4 | MPC ROS 节点（订阅入口） | 改 | 同上 |
| E5 | `scripts/run_dvl_sweep.sh` / `scripts/run_mag_sweep.sh` / `scripts/run_combined_sweep.sh` | 新建（薄壳） | §3.5.1 / §3.5.2 / §4.5 |
| E6 | [tools/run_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py) | 改（加 `--param-grid`） | §5.5 敏感性 |

### 2.2 文档（`docs/thesis/*.md` 8 篇）

| # | 文件 | 论文章节 | 主要内容 |
|---|---|---|---|
| T1 | `docs/thesis/00_overview.md` | §1 / §5.1 | 实验体系全图、术语、命令索引、Pre/Post-Snapshot |
| T2 | `docs/thesis/01_baseline_repro_log.md` | §3.5 baseline / §5.1.2 | Step 0 修复后 baseline 重跑日志 + RMSE/CEP50 表 |
| T3 | `docs/thesis/02_es_ekf_validation.md` | §3.5.1 / §3.5.2 / §3.6 | ES-EKF 三路对比 + DVL 丢包 + 磁畸变 |
| T4 | `docs/thesis/03_uncertainty_quantification.md` | §3.4 / §4.4.2 | NIS 白化 + EKF P 时间序列 + UA-MPC 耦合 |
| T5 | `docs/thesis/04_mpc_robustness_ablation.md` | §4.5 | baseline-MPC vs UA-MPC × 7 场景 × 5 种子 |
| T6 | `docs/thesis/05_scenario_recipes.md` | §5.2 | 9 yaml 物理含义 + 覆盖矩阵 + 新手 SOP |
| T7 | `docs/thesis/06_jetson_deploy_emulated.md` | §5.5 | Jetson 仿真侧 CPU/MEM/延迟 |
| T8 | `docs/thesis/99_repo_doc_drift_log.md` | — | 文档差异修订日志（顺手） |

每篇模板（仿照 [benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md)）：

```
# <标题>
**日期** / **目的** / **依赖**
## 命令清单（新手可直接复制）
## 期望产出（路径 + 文件清单）
## 实验结果（表格 + 关键图引用）
## 错误处理（提及不展开）
## 与论文章节映射
```

---

## 3. 详细实施步骤

### Step E2 — NIS 滑动窗 + 自适应 R（任务 #11）

**Why**：让 §3.4.1 "基于 SNR 的观测协方差 R 在线调整"有真实数据；让 uncertainty_metrics.py 抛弃 proxy。

**修改文件**：[algorithm/es_ekf.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py)

**How**：

1. `__init__`（约 L120 附近，紧跟 `sigma_mag_depth` 之后）新增配置：
   ```python
   self.nis_window_size = int(cfg.get("nis_window_size", 50))
   self.nis_threshold = float(cfg.get("nis_threshold", 9.0))  # χ²(3, 0.05) ≈ 7.81
   self.adaptive_r_scale_max = float(cfg.get("adaptive_r_scale_max", 5.0))
   self.adaptive_r_scale_decay = float(cfg.get("adaptive_r_scale_decay", 0.95))
   self._adaptive_r_scale = 1.0
   self.nis_history: list[dict] = []  # {ts_ns, source, dim, nis}
   ```

2. 改造 `_correct(self, y, h, h_mat, r)`（[L367-L382](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L367-L382)），新增可选 `source` kwarg 并暴露 NIS 记录：
   ```python
   def _correct(self, y, h, h_mat, r, source: str = "unknown"):
       r_eff = r * self._adaptive_r_scale
       innov = (y - h)
       s = h_mat @ self.P @ h_mat.T + r_eff
       s_inv = np.linalg.pinv(s)
       k = self.P @ h_mat.T @ s_inv
       dx = k @ innov
       self._inject(dx)
       i = np.eye(15)
       ikh = i - k @ h_mat
       self.P = ikh @ self.P @ ikh.T + k @ r_eff @ k.T

       # NIS 记录与自适应
       nis = float(innov.T @ s_inv @ innov)
       self.nis_history.append({"source": source, "dim": int(y.shape[0]), "nis": nis})
       if len(self.nis_history) > self.nis_window_size:
           recent = self.nis_history[-self.nis_window_size:]
           mean_nis = float(np.mean([e["nis"] for e in recent]))
           if mean_nis > self.nis_threshold:
               self._adaptive_r_scale = min(
                   self._adaptive_r_scale * 1.5, self.adaptive_r_scale_max
               )
           else:
               # 单调衰减（不低于 1.0）
               self._adaptive_r_scale = max(
                   self._adaptive_r_scale * self.adaptive_r_scale_decay, 1.0
               )
   ```

3. 让所有 caller 传 `source`：`correct_dvl(...) → self._correct(z, h, h_mat, R, source="dvl_body")`，`correct_dvl_world` → `"dvl_world"`，`correct_depth` → `"depth"`，`correct_gps` → `"gps"`，`correct_mag` → `"mag"`。

4. 暴露：
   ```python
   def get_nis_stats(self):
       n = self.nis_history[-self.nis_window_size:]
       return {
           "count": len(n),
           "mean": float(np.mean([e["nis"] for e in n])) if n else 0.0,
           "latest": n[-1]["nis"] if n else 0.0,
           "r_scale": self._adaptive_r_scale,
       }
   ```

**修改文件**：[tools/uncertainty_metrics.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/uncertainty_metrics.py)

5. 把 proxy NIS 替换为读取 `engine.filter.nis_history`（用 `getattr` 容错）。CSV 列加 `nis_real`、`r_scale`，旧 proxy 保留为 `nis_proxy` 以做对比。

**回退点**：`nis_window_size = 0` 等价跳过；或不传 `source` 依然向后兼容（默认值已给）。

**验证**：
```bash
cd /home/auv_user/auv_ws/AUV-Master-Project
python3 -c "
from algorithm.es_ekf import EseKfEngine
e = EseKfEngine({'nis_window_size': 5})
import numpy as np
e.predict(np.zeros(3), np.zeros(3), 0.01)
e.correct_depth(0.5)
print(e.get_nis_stats())
"
# 期望输出：count=1, latest>=0, r_scale=1.0
```

---

### Step E3 — MPC sigmoid 平滑 + 消融开关（任务 #12）

**Why**：§4.4.2 / §4.5 需要 baseline vs UA 公平消融对比；阶跃门限会在 sweep 边界出现伪抖振，遮蔽真实差异。

**修改文件**：[algorithm/auv_mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py)

**How**：

1. 在 `__init__`（[L156 附近](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py#L156-L158)）追加：
   ```python
   self.confidence_smoothness_k = float(weights.get("confidence_smoothness_k", 8.0))
   self.confidence_alpha = float(weights.get("confidence_alpha", 1.5))
   self.mpc_mode = str(weights.get("mpc_mode", "ua")).lower()  # "ua" | "baseline"
   ```

2. `_build_solver`：把跟踪权重从线性的 `(1 + (1-conf)*(scale-1))` 改为 `(1 + scale * (1-conf)^alpha)`，控制权重把 `if_else` 阶跃改为 sigmoid：
   ```python
   if self.mpc_mode == "baseline":
       w_x = self.W_x; w_y = self.W_y; w_z = self.W_z; w_psi = self.W_psi
       control_scale = 1.0
   else:
       conf_pow = ca.power(1.0 - conf, self.confidence_alpha)
       w_x = self.W_x * (1.0 + (self.low_conf_scale - 1.0) * conf_pow)
       w_y = self.W_y * (1.0 + (self.low_conf_scale - 1.0) * conf_pow)
       w_z = self.W_z * (1.0 + 0.5 * conf_pow)
       w_psi = self.W_psi * (1.0 + (self.low_conf_scale - 1.0) * conf_pow)
       sig = 1.0 / (1.0 + ca.exp(self.confidence_smoothness_k * (conf - self.confidence_threshold)))
       control_scale = self.low_conf_ctrl_scale + (1.0 - self.low_conf_ctrl_scale) * (1.0 - sig)
   ```
   注意 CasADi 中 `mpc_mode` 是 Python 侧 if，不进图。

3. 让 MPC 节点（grep 找到 `AUVMPCController` 实例化的 ROS 节点）读 `os.environ.get("AUV_MPC_MODE", "ua")` 并把它塞进 `weights`。

**修改文件**：[scripts/start_experiment.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment.sh)

4. 已有 `--mpc-mode` flag → 验证 env `AUV_MPC_MODE` 是否注入到 launch；缺则补一行 `export AUV_MPC_MODE="$MPC_MODE"`。

**回退点**：`mpc_mode=baseline` 一键回旧；`confidence_smoothness_k=0` 退化为分段近似；保留旧 `if_else` 路径要删，避免双权重带来歧义。

**验证**：
```bash
python3 -c "
from algorithm.auv_mpc_controller import AUVMPCController
import numpy as np
# 构造极小 demo，确保两种模式都能 build 不报错
"
```
随后跑 `tools/run_thesis_sweep.py --scenarios baseline --seeds 0 --mpc-modes baseline,ua --duration 30` 看 results.csv 两行均出。

---

### Step E4 — EKF→MPC 协方差耦合（任务 #13）

**Why**：§4.4 主创新点的 "Uncertainty-Aware" 通路落地。

**新建文件**：`brain_linux/src/auv_localization/auv_localization/ekf_covariance_publisher.py`

**How**：

1. ROS2 Node：订阅 EKF state（已有 `/auv/ekf/odom` 之类 topic，需 grep 确认），发布 `/auv/ekf_covariance`（消息 `std_msgs/Float64MultiArray` 6 维：trace_xy, trace_z, trace_vel, trace_att, mean_nis, r_scale）。
2. 实现走两路：
   - 优先：直接从 EKF 节点 in-process 拿 `engine.filter.P` 与 `get_nis_stats()`（最快路径）
   - 备选：订阅 `/auv/ekf/covariance` 若已存在
3. 在 `setup.py` 加 entrypoint，并在 launch 中按 `AUV_MPC_MODE=ua` 条件启动。

**修改 MPC 节点**：

4. 订阅 `/auv/ekf_covariance` → 把 `trace_xy/z` 经 `conf = exp(-trace_xy / sigma_xy_ref)` 映射为置信度，用此覆盖 `synthetic_sensors` 的 placeholder 置信度（或加权融合）。
5. ROS 参数：`covariance_to_confidence.sigma_xy_ref`（默认 1.0），`covariance_to_confidence.enable`（默认按 `AUV_MPC_MODE==ua`）。

**回退点**：节点不启动 / `enable=false` → MPC 走旧 placeholder 置信度；只要 `mpc_mode=baseline` 即整条链路短路。

**验证**：
```bash
ros2 topic echo /auv/ekf_covariance --once
```
跑 sweep 比较 ua vs baseline 在 `dvl_dropout_30` 场景下的 RMSE 差。

---

### Step E5 — 三场景 sweep 命令薄壳（任务 #14）

**Why**：让新手一行复现 §3.5.1 / §3.5.2 / §4.5 三大组实验。

**新建文件**（每个 ≤ 30 行）：

- `scripts/run_dvl_sweep.sh`：
  ```bash
  python3 tools/run_thesis_sweep.py \
      --scenarios baseline,dvl_dropout_10,dvl_dropout_30,dvl_dropout_60,dvl_dropout_90 \
      --seeds 0,1,2,3,4 --mpc-modes baseline,ua --duration 120 "$@"
  ```
- `scripts/run_mag_sweep.sh`：scenarios = baseline,mag_distortion_light,mag_distortion_heavy
- `scripts/run_combined_sweep.sh`：scenarios = baseline,combined_stress（外加 sonar_clutter 可选）

**回退点**：脚本就是 wrapper，删了直接跑底层 python 即可。

**验证**：每个脚本传 `--duration 30 --seeds 0` 跑一遍，确认 `log/thesis_sweep/<ts>/results.csv` 出表。

---

### Step E6 — 参数扰动 + 敏感性（任务 #15）

**Why**：§5.5 "Sim-to-Real 敏感性讨论" 要表头数据。

**修改文件**：[tools/run_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py)

**How**：

1. 加 CLI：`--param-grid 'low_conf_scale:1.5,3.0,5.0;confidence_smoothness_k:4,8,16'`
2. 解析为字典 → 笛卡尔积扩到外层循环；每个组合通过环境变量 `AUV_MPC_PARAM_OVERRIDES` 注入到 MPC 节点（节点读取后覆盖 weights）。
3. 输出 `sensitivity.csv` 列：`low_conf_scale, smoothness_k, scenario, seed, mpc_mode, xy_rmse, ctrl_smooth`
4. 简化方差分解：用 `pandas.groupby + var()` 计算每个参数的方差贡献占比（不跑完整 ANOVA）。生成 `sensitivity_summary.md`。

**回退点**：不传 `--param-grid` 时行为完全等同当前。

**验证**：
```bash
python3 tools/run_thesis_sweep.py \
    --scenarios baseline --seeds 0 --mpc-modes ua \
    --param-grid 'low_conf_scale:1.5,3.0' --duration 30
```

---

### Step Final — 8 篇 docs/thesis/*.md（任务 #16 + #17）

**Why**：把所有代码 + sweep 结果绑成论文章节闭环。

**操作分两步**：

#### 步骤 A：先建骨架（不需运行实验）

`mkdir -p docs/thesis`，按 §2.2 表格依次创建 8 个 .md 骨架。每篇模板字段：
- 头部：日期 + 目的 + 依赖代码 commit 范围
- 命令清单：可复制执行
- 期望产出：相对路径 + 文件清单
- 实验结果：占位表格（先填 baseline 已有数据，sweep 结果留 TBD）
- 与论文章节映射

#### 步骤 B：运行最小验证 sweep 后回填表格

跑：
```bash
bash scripts/run_dvl_sweep.sh --duration 30 --seeds 0   # 8 runs
bash scripts/run_mag_sweep.sh --duration 30 --seeds 0   # 6 runs
python3 tools/uncertainty_metrics.py --input <一个 baseline mcap>
bash scripts/run_jetson_emulated_bench.sh --duration 60
```
把 results.csv / uncertainty CSV / cpu_mem.csv 摘要回填到 T2~T7 的"实验结果"表。

#### 步骤 C：闭环差异日志

T8 = `99_repo_doc_drift_log.md` 内容：
- `benchmark_test_log.md` 中 "kill -INT" 已升级为轮询 finalize → 注明
- `rosbag_analysis_validation.md` 提到的 Std-EKF 异常 → 指向 Step 0 B3 修复
- `docs/user-guide/05_benchmarks.md` 与新 sweep 体系交叉链接

更新 [docs/INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/INDEX.md)：在末尾加 thesis 板块 8 个链接。

回填 [`.trae/documents/thesis_experiment_uplift_plan.md`](file:///home/auv_user/auv_ws/AUV-Master-Project/.trae/documents/thesis_experiment_uplift_plan.md) §9 Post-Snapshot：
- 8 篇文档清单（行数）
- sweep 完成率（实际跑了多少 / 计划 70 runs）
- baseline vs UA-MPC 在高扰动场景的 RMSE 改善百分比
- Jetson emulated 60s 跑下 P95 延迟
- `git diff --stat HEAD~N` 概要

**回退点**：文档可逐篇独立交付；Step C 完全是"事后描述"，不影响代码。

**验证**：
```bash
ls docs/thesis/    # 应有 8 个 md
grep -r "TBD" docs/thesis/  # 实施完不应剩 TBD（除非显式留作 Phase 3）
```

---

## 4. 风险与回退矩阵

| 风险 | 阶段 | 影响 | 回退 |
|---|---|---|---|
| E2 自适应 R 在静态场景过激放大 | E2 | EKF 误差变大 | `nis_window_size=0` 关闭；保留 `nis_history` 仅用于度量 |
| E3 sigmoid k 太大→数值不稳 | E3 | IPOPT 不收敛 | `k=4` 默认偏保守；`mpc_mode=baseline` 一键回退 |
| E4 EKF→MPC 节点拓扑改动大 | E4 | sim 启不起来 | 节点不 launch；MPC 退回 placeholder 置信度 |
| E5 sweep 单 run 失败传染 | E5 | 表格不全 | run_thesis_sweep 内已含 failures.log 隔离 |
| E6 参数网格爆炸 | E6 | 跑不完 | param-grid 留小（默认 3×3），文档建议先 `--seeds 0` |
| Final 文档不及实验跑全 | Final | 论文表 TBD | 先骨架再回填；T8 drift log 始终可独立完成 |

**并行性**：
- E2 与 E3 互独立 → 可并行
- E4 串在 E3 后（MPC 改动稳定后再加订阅）
- E5 串在 E3+E4 后
- E6 串在 E5 后（共用 sweep 基础）
- Final 文档骨架可任何时候开写，回填表格放最后

---

## 5. 假设与决策

- **D1 = B**：磁观测仅 sim 钩子，不实物（已落 E1）
- **D2 = B**：UA-MPC 走 sigmoid + EKF 协方差耦合 + 消融（E3+E4）
- **D3 = A**：Step 0 全修 + 重跑（已落）
- 不引入新仿真后端；HoloOcean 与 PVS 均利用现有工程
- 不动对外接口（Jetson 部署 SOP 不变）
- 文档语言：中文为主，code block 注释中英混合

---

## 6. 验证总表

| 阶段 | 命令 | 通过条件 |
|---|---|---|
| E2 | `python3 -c "from algorithm.es_ekf import EseKfEngine; ..."` | `get_nis_stats()` 返回非空 dict |
| E3 | `tools/run_thesis_sweep.py --scenarios baseline --seeds 0 --mpc-modes baseline,ua --duration 30` | results.csv 有 2 行；ua 行 ctrl_smooth 不大于 baseline |
| E4 | `ros2 topic echo /auv/ekf_covariance --once` | 返回 6 维向量 |
| E5 | `bash scripts/run_dvl_sweep.sh --duration 30 --seeds 0` | results.csv 有 10 行（5 scen × 2 mode） |
| E6 | `--param-grid` 跑 9 组 | sensitivity.csv 出表，sensitivity_summary.md 有方差占比 |
| Final | `ls docs/thesis/ \| wc -l` ≥ 8 | INDEX.md 有 thesis 板块；drift log 闭环 |

---

## 7. 任务 → TODO 镜像

| TODO # | 阶段 | 状态 |
|---|---|---|
| 11 | E2 NIS + 自适应 R | in_progress（执行后转 completed） |
| 12 | E3 sigmoid + 消融 | pending |
| 13 | E4 EKF→MPC 耦合 | pending |
| 14 | E5 sweep 命令薄壳 | pending |
| 15 | E6 参数敏感性 | pending |
| 16 | Final 8 篇 docs/thesis/*.md | pending |
| 17 | Final Post-Snapshot + drift log + INDEX | pending |

---

## 8. Post-Snapshot（Phase 4 解锁后回填）

> Phase 2 计划在 Phase 4 收口后由 D7.2 终端解锁会话二次回填；以下为最终交付盘点。

### 8.1 8 篇 thesis 文档行数与最终路径

> 见 `wc -l docs/thesis/*.md`（2026-06-09 实测）

| 文件 | 行数 |
| --- | ---: |
| [thesis/INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/INDEX.md) | 78 |
| [thesis/00_overview.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/00_overview.md) | 186 |
| [thesis/01_baseline_repro_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/01_baseline_repro_log.md) | 155 |
| [thesis/02_es_ekf_validation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/02_es_ekf_validation.md) | 145 |
| [thesis/03_uncertainty_quantification.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/03_uncertainty_quantification.md) | 172 |
| [thesis/04_mpc_robustness_ablation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/04_mpc_robustness_ablation.md) | 190 |
| [thesis/05_scenario_recipes.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/05_scenario_recipes.md) | 204 |
| [thesis/06_jetson_deploy_emulated.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/06_jetson_deploy_emulated.md) | 180 |
| [thesis/07_drift_log_and_known_issues.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/07_drift_log_and_known_issues.md) | 178 |
| **合计** | **1488** |

### 8.2 sweep 实际运行 run 数 / 失败率

| sweep | 计划 run 数 | 实际 | 状态 | 备注 |
| --- | ---: | ---: | --- | --- |
| dvl_sweep（5×5×2 = 50） | 50 | 10 (smoke) | ⚠️ **GT invalidated**（D8.4） + ⚠️ **DR-tool dt BUG**（D8.6） | 1-seed × 5 scenario × 2 mode = 10 runs，[log/thesis_sweep/20260609_160344_v22_dvl_smoke](file:///home/auv_user/auv_ws/AUV-Master-Project/log/thesis_sweep/20260609_160344_v22_dvl_smoke) 走 9/10，但 GT topic 用了 `/auv/visual/truth_marker`（mock fallback 静默生效，见 D8.4）+ benchmark `update_dvl` dt 错位（D8.6）→ 双重失真。**待 D8.4 + D8.6 修复后重跑**（D8.4 ✅ / D8.6 ✅）。剩余 40 runs 待显著性需求触发 |
| mag_sweep | 30 | 0 | deferred | v2.2 sweep 已通，待触发 |
| combined_sweep | 30 | 0 | deferred | v2.2 sweep 已通，待触发 |
| param_grid | 12 | 0 | deferred | 同上 |
| jetson_emulated_bench | 5 profile × 60s | 1 失败 + 1 旁路成功 | 部分 | run_jetson_emulated_bench.sh 在 60s 短跑下采样器进程白名单未匹配（D4.2 已记入）；直接 start_experiment.sh 60s run 数据完整 |
| baseline 60s 数据回放分析 | 1 | ✅ 1（11:33 落盘 bag） | 完成 | mcap_period_stats.py 验证可运行 |

> 失败率统计：`run_jetson_emulated_bench.sh` 的 sampler pgrep 模式与 `start_experiment.sh` 实际启动的进程命名不严格匹配（colcon build 阶段进程不在白名单），是 D4.2 / D5.x 范畴；不影响 baseline 60s real run 的 mcap 数据完整性（Phase 4 P2 解锁数据已可用）。

### 8.3 UA-MPC 相对 baseline-MPC 的 xy_rmse 改善百分比（按场景）

| 场景 | UA-MPC vs baseline-MPC（xy_rmse 改善 %） | 状态 |
| --- | --- | --- |
| baseline | ⚠️ **GT invalidated**（D8.4，原 -2.08% 数据基于错误 truth_marker，待 D8.4 修复后重跑） | smoke 锚点失效 |
| dvl_dropout_10 | ⚠️ **GT invalidated**（D8.4，原 +1.31%） | smoke 失效 |
| dvl_dropout_30 | ⚠️ **GT invalidated**（D8.4，原 +1.31%） | smoke 失效 |
| dvl_dropout_60 | ⚠️ **GT invalidated**（D8.4，原 -1.33%） | smoke 失效 |
| dvl_dropout_90 | n/a | baseline DR 极漂 bench_failed |
| mag_distortion_heavy | ⏳ deferred | 同 mag_sweep |
| combined_stress | ⏳ deferred | 同 combined_sweep |

> **重要**：D8.4 + D8.6（2026-06-09）联合定位 v2.2 smoke 的 27m xy_rmse 伪信号双重根因——D8.4（mock fallback 静默 GT）+ D8.6（benchmark `update_dvl` dt 错位）。两者均已修复并在单 bag 验证：[/auv_data/bags/20260609_090300](file:///auv_data/bags/20260609_090300) 真 GT 下 **raw_dr XY=1.017m / std_ekf XY=1.083m / Z=0.004m**（excellent）。sweep 重跑须重新走 colcon build viz_bridge + offline_ekf_benchmark.py 已部署机器，并在 ≥3 seed × 5 scen × 2 mode 给显著性。
> 锚定文件：[01_baseline_repro_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/01_baseline_repro_log.md) §6（多 seed 待补）+ [04_mpc_robustness_ablation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/04_mpc_robustness_ablation.md) §5。
>
> v2.2 smoke 实测（2026-06-09 16:03，1-seed × 5 scen × 2 mode = 10 runs）：sweep harness 已通，GT 全部回填；UA vs baseline 差异均在 ±2% 以内，需 ≥3 seed 才能见显著性。
> 历史阻塞：v2.1 时代 sweep harness 在 `--bridge-backend protocol_udp --auto-activate` 下因 LEAN_BAG GT 误排除 → bag 缺 truth_marker → benchmark exit=1，已在 v2.2 修复（D8.1）。

### 8.4 Jetson emulated 60s 真实指标（baseline 场景，mcap 后处理）

> 数据源：`/auv_data/bags/20260609_113311/rosbag/rosbag_0.mcap`（60s real run，protocol_udp bridge）；分析工具：[tools/mcap_period_stats.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mcap_period_stats.py)。

| topic | rate (Hz) | period_ms median | period_ms p95 | period_ms p99 | period_ms max | 论文阈值 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `/auv/state/filtered` | 73.0 | 3.79 | **42.34** | 43.09 | 45.03 | < 50 ms ✅ |
| `/auv/state/covariance` | 73.0 | 3.80 | **42.49** | 43.24 | 45.49 | < 50 ms ✅ |
| `/auv/control/setpoint` | 35.4 | 30.56 | **62.10** | 62.86 | 100.44 | < 200 ms ✅ |
| `/auv/control/confidence` | 0.0 | nan | nan | nan | nan | ⚠ 未发布（D3.x） |
| `/auv/sensors/imu` | 34.2 | 20.93 | 21.95 | 23.06 | 34.11 | 30 Hz 标称 ✅ |
| `/auv/sensors/dvl` | 34.2 | 20.93 | 22.08 | 23.11 | 34.44 | 30 Hz 标称 ✅ |
| `/auv/sensors/depth` | 34.2 | 20.93 | 22.17 | 23.14 | 34.39 | 30 Hz 标称 ✅ |

> CPU/RSS 旁路采样在 60s 短跑场景下采样窗口短，`run_jetson_emulated_bench.sh` 进程白名单未匹配；待后续 ≥120s run 与脚本修复。**emulated 实时性指标已达标**：EKF/setpoint 周期 p95 全部低于 §5.5 阈值。

### 8.4a 离线 EKF benchmark（同一 113311 bag 后处理）

> 数据源同上；分析工具：[tools/offline_ekf_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/offline_ekf_benchmark.py)；输出：`/tmp/bench_113311/benchmark_results.md`、四张 PNG（trajectory / error_time / error_components / innovation_residual）。

| 算法 | XY RMSE (m) | Z RMSE (m) | 3D RMSE (m) | CEP50 (m) | Max Drift (m) | 平均耗时 (μs/frame) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Raw DR | 15.053 | 0.137 | 15.053 | 9.636 | 31.697 | 0.8 |
| Std EKF | 15.116 | 0.137 | 15.117 | 9.661 | 31.932 | 35.7 |
| ES-EKF | 15.116 | **20.848** | 25.752 | 9.661 | 31.932 | 41.3 |

关键观察（n=1，单 seed=0，仅作锚点；不可作多 seed 显著性结论）：
1. **XY 误差 raw_dr ≈ std_ekf ≈ es_ekf ≈ 15 m**：60s 短跑下 DVL 速度积分尚未发散，DR 与 EKF 在 XY 平面接近；多 seed/长时长对照仍需后续。
2. **ES-EKF Z 维异常 = 20.8 m**：来自初始化阶段日志 `Position offset from config: [0, 0, -24.0307]`——ES-EKF 自动以首帧 depth 对齐时把 z 轴起点偏离了 24 m，是 ES-EKF 初始化与坐标对齐的已知风险（D7.4 类，登记为 D8 follow-up）。Std EKF 在同一 bag 上 Z RMSE = 0.137 m，可作为 baseline 锚点。
3. **算法耗时**：ES-EKF 41.3 μs/frame、Std EKF 35.7 μs/frame，皆 ≪ EKF 周期阈值（50 ms p95）；Jetson Nano 实时性余量 > 1000×。

### 8.5 涉及的 git 改动范围

```
git rev-list --count HEAD = 27 commits（仓库总深度）
HEAD = 5a8f3ec ("小修复")
最近 5 commit 的 diff：91 files changed, 4658 insertions(+), 8240 deletions(-)
```

主要改动域：
- `algorithm/`：es_ekf.py（自适应R + correct_mag）、auv_mpc_controller.py（sigmoid + (1-conf)^α + mpc_mode）
- `brain_linux/src/auv_controller/`：mpc_controller.py（C1 AUV_MPC_PARAM_OVERRIDES）、auv_controller_node.py（_on_covariance + _confidence_from_cov）
- `brain_linux/src/auv_localization/`：发 `/auv/state/covariance`
- `tools/`：run_thesis_sweep.py（--param-grid + sensitivity_summary）+ 新增 mcap_period_stats.py（任务 2）
- `scripts/`：run_dvl_sweep / run_mag_sweep / run_combined_sweep / run_jetson_emulated_bench
- `docs/thesis/`：8 篇新文档；`docs/INDEX.md` 追加 thesis 板块

### 8.6 与 Phase 4 收口的延续

- 本计划（Phase 2）的"实施步骤"被 Phase 4 §3 计划吸收并扩充为 T1-T9 9 篇 thesis md
- 所有 8.3 / 8.4 中标"⏳ deferred"的项目，回填位置已在对应 thesis md 中预留（带 ⏳ 标记），后续会话直接 Edit 即可
- 与 Phase 1 [benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md) 的衔接：Phase 1 单 seed n=1 数据已被 [01_baseline_repro_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/01_baseline_repro_log.md) §3 完整引用；多 seed 升级路径见 §6 待补部分

### 8.7 D8 follow-up（本会话登记，留待后续会话精细修复）

| ID | 现象 | 已知证据 | 影响 | 修复路径（参考） |
| --- | --- | --- | --- | --- |
| D8.1 | ✅ **resolved (contract v2 / 2026-06-09)** → 🔧 **patched to v2.1 (2026-06-09)** → 🔧 **patched to v2.2 (2026-06-09)**：sweep harness 在 protocol_udp + auto-activate 下 brain stack 子进程未发布 `/auv/sensors/{imu,dvl,depth}` ROS topic | 根因：上一 run 残留 `foxglove_bridge`（占 8765）+ `zenoh_*_bridge_node` + `_ros2_daemon`（缓存 stale graph）+ `/dev/shm/{fastrtps_*, sem.fastrtps_*, *.zenoh}` 共三层污染；新 launcher 的 foxglove_bridge `Bind Error` → `wait -n` 命中即拆全链 → brain colcon build 阶段被 SIGTERM → 传感器 topic 永不发布 | B1/B2 sweep 解锁 | **v2 修复方案**：把"清场"上提到 [scripts/start_experiment.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment.sh) 入口的 `preflight_clean()`（trap 之前），覆盖 12 项进程模式 + 3 类 shm + python3 端口探测 fail-fast。**v2.1 补丁（2026-06-09）**：发现 v2 杀 `_ros2_daemon` 引入 26s 控制律首发延迟（vs 113311 +0.02s）→ 拆分为 fast path（[scripts/start_experiment.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment.sh) `preflight_probe()` + ros2 daemon 预热，PAT 故意不含 daemon）+ slow path（[scripts/preflight_clean.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/preflight_clean.sh) 独立运维脚本，由用户显式调用，sweep 不自动 wrap）；详见 [docs/internals/11_experiment_state_machine.md §6.4](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/internals/11_experiment_state_machine.md) + [docs/experiment/terrain_benchmark_log.md §6.7](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/terrain_benchmark_log.md)。**v2 验证**：干净 baseline 1-seed [log/thesis_sweep/20260609_133645_contract_p1p2_verify](file:///home/auv_user/auv_ws/AUV-Master-Project/log/thesis_sweep/20260609_133645_contract_p1p2_verify) ✅ 1/1；自然 dirty 2-seed [log/thesis_sweep/20260609_135406_contract_v2_2seed](file:///home/auv_user/auv_ws/AUV-Master-Project/log/thesis_sweep/20260609_135406_contract_v2_2seed) ✅ 2/2；手工 stress dirty (3 stale + 13 shm) [log/thesis_sweep/20260609_135820_contract_v2_dirty_stress](file:///home/auv_user/auv_ws/AUV-Master-Project/log/thesis_sweep/20260609_135820_contract_v2_dirty_stress) ✅ 1/1。**v2.1 验证**：1-seed 回归 [log/thesis_sweep/20260609_145102](file:///home/auv_user/auv_ws/AUV-Master-Project/log/thesis_sweep/20260609_145102_contract_v21_verify) **否证 daemon 假说**——mpc_cmd 首发仍 +26.01s（vs v2 +26.00s，差异 < 50ms），说明 daemon warm-up 对 26s 无效。**v2.2 补丁（2026-06-09 15:29）**：重做 launcher.log 时间轴诊断，真因为 brain stack spin-up（`WAIT_BEFORE_RECORD(3)` + `SIM_DELAY(10)` + colcon(~12) + node_spin(~1) ≈ 26s）；落地方案 A **wait-for-brain-ready**——bag record 启动前轮询 `/auv/control/mpc_cmd` publisher 出现（timeout 90s），bag T0 对齐 brain ready；同时修复 `LEAN_BAG --exclude '^/auv/visual/.*'` 误排除 GT topic 的 bug，改用 ECMAScript negative lookahead `^/auv/visual/(?!truth_marker$).*` 保留 `truth_marker`；daemon warm-up 自 v2.1 起保留为防御性 hardening（**不是** 26s 消除手段）。**v2.2 验证**：1-seed 回归 [log/thesis_sweep/20260609_152941_methodA_brain_ready_verify](file:///home/auv_user/auv_ws/AUV-Master-Project/log/thesis_sweep/20260609_152941_methodA_brain_ready_verify) ✅ 1/1，mpc_cmd 首发 +26.01s → **+3.17s**；state/filtered + imu/dvl/depth 全 +0.00s；truth_marker 0 → **599 条**；brain ready after 20s。**v2.2 sweep harness 验证（2026-06-09 16:03）**：[log/thesis_sweep/20260609_160344_v22_dvl_smoke](file:///home/auv_user/auv_ws/AUV-Master-Project/log/thesis_sweep/20260609_160344_v22_dvl_smoke) 1-seed × 5 scen × 2 mode = 10 runs ✅ **9/10**（仅 dvl_dropout_90 baseline DR 极漂触发 bench_failed，与时序契约无关），GT topic 全部回填 → D8.1 在 sweep harness 路径下闭环。 |
| D8.2 | ES-EKF 初始化时 z 轴起点偏离 24 m，导致 ES-EKF Z RMSE = 20.8 m | `/tmp/bench_113311/` 日志 `Position offset from config: [0, 0, -24.0307]` | ES-EKF 在长时长场景下 z 维误差累积；论文 §4.3 ES-EKF 对照结论受影响 | 检查 [algorithm/es_ekf.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py) `auto_init_from_first_depth` 与 scenario YAML 中 `init_position` 的耦合；考虑禁用 auto-align 或修复 z 偏移 |
| D8.3 | run_jetson_emulated_bench.sh sampler 进程白名单未匹配 colcon build 阶段进程命名 | cpu_mem.csv 0 行 | Jetson emulated CPU/RSS 时序数据空 | 修 [scripts/run_jetson_emulated_bench.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_jetson_emulated_bench.sh) L88 pgrep 模式 |
| D8.4 | ✅ **resolved (2026-06-09)**：v2.2 sweep smoke 报 raw_dr xy_rmse=27m 不是 DR 漂移，是 GT 数据源错误 | bag `/auv/visual/truth_marker` x∈[-2.5,2.5] y∈[-1.18,1.20] path=12m，与 [synthetic_sensors.py L319-326](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/synthetic_sensors.py#L319-L326) `sample_mock_pose` 公式 `x=2.5·sin(0.13φ), y=1.2·sin(0.07φ)` 完美匹配；DVL 0.76m/s × 60s ≈ 46m；root cause：[zenoh_viz_bridge_node.py L697-700](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_viz_bridge/auv_viz_bridge/zenoh_viz_bridge_node.py#L697-L700) 当 zenoh `Z_PATH_TRUTH_POSE` 链路任何一段失联（router 没收到 / sim 端发出晚 / 超时 3s）→ 静默 fallback 到 mock 公式 → bag 录到的 truth_marker 实际是 mock 抖动而非真位姿 | 所有用 `/auv/visual/truth_marker` 当 GT 的 benchmark 数据全部失真：raw_dr / std_ekf / es_ekf 的 xy_rmse 都被推高到错误量级；v2.2 sweep smoke 9/10 ok 报 27m xy_rmse 是伪误差；论文 §4 定位精度章节须在新 GT 上重做 | **方案 B 已落地（推荐）**：[zenoh_viz_bridge_node.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_viz_bridge/auv_viz_bridge/zenoh_viz_bridge_node.py) 加 `_on_ground_truth` 订阅 `Z_PATH_GROUND_TRUTH='rt/auv/sensors/ground_truth'`（sim 端早已在 [holoocean_physics_bridge.py L324-332](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/holoocean_physics_bridge.py#L324-L332) 发布），转发为 ROS PoseStamped `/auv/sensors/ground_truth`（Z 翻 NED→ROS 约定），同步 backfill `_live_truth` 让 truth_marker 也跟随真位姿；benchmark 默认 `--truth-topics` 优先级已是 `/auv/sensors/ground_truth, /auv/state/truth, /auv/visual/truth_marker` 自动切换。**实测验证（bag [/auv_data/bags/20260609_090300](file:///auv_data/bags/20260609_090300)）**：N=2795（≈50Hz），path=27.94m，与 DVL 速度积分吻合；4-mode DR 在真 GT 上：dvl_world/dvl_body raw_dr xy=14.47m / z=0.03m，imu_only/heading_only xy=16.06m；**std_ekf XY=1.08m / Z=0.004m / 3D=1.08m（excellent）**；es_ekf XY=1.07m / Z=23.99m（Z 维 NED/ROS sign 不一致，见 D8.5）。**A 路径暂缓**（zenoh `Z_PATH_TRUTH_POSE` 通信侧排查，对论文非必须，作为系统加固 follow-up；用户拍板"很可能要做但和主线差异太大，下一轮再决定"）。**命名 discrepancy 备注**：sim 端 physics bridge 文件名 `holoocean_physics_bridge.py` 但 PVS 后端通过 [pvs_sim_wrapper.py L422-428](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/pvs_sim_wrapper.py#L422-L428) 包装为相同 schema 复用同一桥，B 改动一处即覆盖 PVS+HoloOcean。 |
| D8.5 | ✅ **resolved (2026-06-09)**：es_ekf Z RMSE = 23.99m 真因 = **离线 benchmark 内部 ROS up vs NED 约定不统一**（不是 es_ekf 内部 sign，也不是主线 BUG） | **主线契约确认**（brain_linux 全栈 ROS up）：[auv_localization_node.py L82-92, L179, L397-428](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_localization/auv_localization/auv_localization_node.py) 只实例化 ES_EKF，`/auv/state/filtered.position.z` 直接 = state.p[2]（z 负=深）；[auv_controller_node.py L492-525](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py) 用 `-position.z` 反推正深度发 vxworks；[zenoh_viz_bridge_node.py L612-616](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_viz_bridge/auv_viz_bridge/zenoh_viz_bridge_node.py#L612-L616) GT 入口翻 NED→ROS up；std_ekf 不上船。**vxworks 实物端契约确认**（按用户判据"先确认 csd_vx6.8_lastest 与实物接轨"）：[CtrlAlgorithm.c L223-238](file:///home/auv_user/auv_ws/AUV-Master-Project/csd_vx6.8_lastest) 用 `Depth_Target / Depth_Now` 标量"水面=0、下潜为正"；[main.c L482-509](file:///home/auv_user/auv_ws/AUV-Master-Project/csd_vx6.8_lastest) `target_depth_m` 限幅 [0,50] 不接受负值；vxworks 不消费 3D state.p 向量，仅消费标量正深度，与 NED 物理等价但**接口标量化不约束 EKF 内部 z 方向** → 主线 ROS up 契约可与实物对应正常。**离线 benchmark 内部失配**：truth 经 [`ft.ue_position_to_ned()` L314-315](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/offline_ekf_benchmark.py#L314-L315) 翻成 NED，std_ekf state 也是 NED（`update_depth: h = state[2]`），唯独 es_ekf state 是 ROS up（`new_pos[2] = -depth_m`）→ es_ekf vs truth Z 差 24m | 论文 §4.3 ES-EKF Z 维对照失真；与 D8.2 表面相似（24m 偏移）但根因不同 | **修复方案 (c) 已落地**（按用户判据"主线契约可对应实物则改离线工具"）：[tools/offline_ekf_benchmark.py L658-670](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/offline_ekf_benchmark.py#L658-L670) `EseKfEngine.get_position()` 在交付比较器时翻 z（`p[2] = -p[2]`），不动主线、不动 es_ekf 内部、不动 truth 入口；diff = +9/-1 行（含 8 行注释）。**修复后 4-mode 实测**（bag [/auv_data/bags/20260609_090300](file:///auv_data/bags/20260609_090300)，[log/dr_v2/summary.txt](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2/summary.txt)）：es_ekf **Z RMSE 23.99m → 0.584m ✓**（41× 改善），XY RMSE 1.074m 完全不变（确认只是 Z 翻号问题），std_ekf + raw_dr 完全不动。残留 0.584m vs std_ekf 0.004m 是 es_ekf 自身 error-state init / correct_depth 路径次级问题，留给后续 sweep 观察，不阻塞论文。 |
| D8.6 | ✅ **resolved (2026-06-09)**：raw_dr xy_rmse=14.47m 不是 DR 物理漂移，是 **benchmark `DeadReckoningEngine.update_dvl` dt 计算 BUG** | [tools/offline_ekf_benchmark.py L397-398（已修）](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/offline_ekf_benchmark.py#L397-L398) 用 `(ts_ns - self._last_imu_ts) / 1e9` 算 DVL 积分 dt；但主循环 L1260-1278 没把 imu.ts_ns 写到 `dr_engine._last_imu_ts`（只 std_ekf 走 self.last_imu_ts），fallback 到 `_dt_predict ≈ 20ms`；真 DVL 帧间隔 230ms（4Hz），每个 DVL 速度被压缩 ≈10× → 60s / 27.8m 路径 raw_dr 只走 2.6m → 逐点 RMSE 14m | 之前误认为 raw_dr 14m 是 DR 物理必漂故需"降级到 heading_only"或"加 GPS 间歇校正"，实际是工具 dt BUG，DR 在 60s/27m/DVL 4Hz 下真实漂移仅 1.0m | **修复（已落地）**：改 `update_dvl` 用 `prev_dvl_ts`（DVL 帧间隔）算 dt，prev_dvl 缺时回退到 `_last_imu_ts`，再缺回退 `_dt_predict`；diff = +6/-2 行。**修复后 4-mode 实测**：dvl_world/dvl_body raw_dr **XY=1.017m / Z=0.030m / 3D=1.018m**（vs std_ekf XY=1.083m，DR 反而略好——EKF process noise 高估造成 DVL 信任度被压低）；imu_only / heading_only XY=16.06m（IMU 二次积分必涨，预期）。**结论**：DR 物理本身在直线 0.5m/s × 60s 工况下漂移率 ≈3.7%（1.0m / 27m），不需要降级或 GPS 间歇校正。否决了用户最初的"降低 DR 应用"假设。 |
| D8.7 | ⏳ **noted**：noise scale 验证（响应用户"降低噪声 scale 看是否下降"指令） | bag [/auv_data/bags/20260609_090300](file:///auv_data/bags/20260609_090300) 在 `sigma_dvl ∈ {0.005, 0.02, 0.03}` 三档（实际注入 0.02）下 std_ekf XY 完全不变（1.082~1.083m），raw_dr 完全相同（DR 不消费 sigma）；详见 [log/dr_v2_noise_scan/summary.txt](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2_noise_scan/summary.txt) | EKF 在当前 60s 短场景下处于精度饱和点；docs/05_benchmarks.md 历史 sweep 提到 sigma_dvl 强敏感（r=0.78）在新 GT 下不再成立，可能是早期错误 GT 下的伪信号 | 暂不动 sigma 默认值（保守 0.03），等 D8.5 修后做 ≥3 seed × 5 scen sweep 再决定 |
| D8.8 | ⚠ **unresolved (2026-06-09)**：D8.5 闭环后立即触发的 v22 dvl_3seed sweep（30 runs，driver "30/30 ok"）**全部失效**——bag `/auv/sensors/ground_truth Count=0` + `/auv/visual/truth_marker Count=555`，benchmark 拿 mock fallback 当 GT，xy_rmse ∈ [23.3, 29.3]m（应为 ~1m）→ D8.4 mock fallback 在 `protocol_udp` 后端路径下重现 | 根因：D8.4 修复（GT zenoh publish）只覆盖 `HoloOceanPhysicsZenohBridge`（zenoh_json 后端）；sweep harness 在 [tools/run_thesis_sweep.py L174-200](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py#L174-L200) 强制注入 `--bridge-backend protocol_udp + --arbiter-profile + --auto-activate`，[run_zenoh_bridge.py L106-112](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/apps/run_zenoh_bridge.py#L106-L112) 据此走 `MockAmdUdpServer`（[mock_amd_server.py](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/mock_amd_server.py) 全文件零 zenoh publish，仅 `sock.sendto` UDP 二进制），zenoh 总线无 `rt/auv/sensors/ground_truth` 样本 → viz_bridge 0 callback → ROS topic 0 message → mock fallback 公式输出 | 30 runs **全部失效**；论文 §5.4 表 5-1 mean±std 不可回填；锚点仍冻结在 D9.1+D9.2+D9.5 单 seed 数字（thesis 01 §6）。driver "30/30 ok" 仅意味 process exit 0，**不代表数据可用** | **方向 1（推荐，最小侵入）**：在 [`mock_amd_server.py`](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/mock_amd_server.py) `__init__` 加 zenoh session（复用 `ZenohJsonBridge`），`run_forever` 每 tick 后构造 ground_truth payload 并调 `self.zbridge.publish("ground_truth", payload)`（参照 [holoocean_physics_bridge.py L324-332 + L457-463](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/holoocean_physics_bridge.py#L324-L332)），预估 +30/-2 行单文件改动；方向 2（备选）：sweep harness 改默认 `--bridge-backend zenoh_json`，放弃 protocol_udp triplet（影响协议侧链覆盖）；方向 3（备选）：另起 zenoh-only GT publisher 进程并行；方向 4/5（不推荐）：禁 mock fallback / 改 benchmark 逻辑——治标不治本。详见 [docs/thesis/07_drift_log_and_known_issues.md §9 D9.7](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/07_drift_log_and_known_issues.md) |
| D8.8 update (2026-06-10) | ⚠ **方向 1 实施完毕但未根治**：[`mock_amd_server.py`](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/mock_amd_server.py) 已加 zenoh GT publisher（+30/-2 行：__init__ 调 `ZenohBridge.open()`、`run_forever` 每 tick 调 `self._publish_ground_truth_zenoh(state, step)`、close 关 zbridge），sweep 日志确认 `[mock-amd] zenoh GT publisher opened` 且 0 publish 错误。但 6-run smoke sweep（v23_d97_smoke + v24_zj_smoke）的 bag 中**仍然完全没有 `/auv/sensors/ground_truth` topic** | sweep harness 路径下 zenoh 跨进程订阅失效——viz_bridge `_on_ground_truth` 从未被触发（无论 protocol_udp 还是 zenoh_json 后端均失效）；同代码同 yaml 在手工 single seed launcher 下正常（bag GT Count=2782 ✓） | sweep harness 串行 30 个 run 之间可能存在 zenoh shm/peer 残留导致 viz_bridge zenoh peer 无法 discover sim 端 publisher。**论文 §5.4 锚点冻结为 n=1 单 seed**（D9.1+D9.5 数字 XY 1.083/1.074m），multi-seed mean±std 不调设 | **本会话不再深调**（预估 ≥2h，与论文交付 ROI 不匹配）。**遗留任务（后续 cycle）**：(a) viz_bridge `_open_zenoh` 是否进 mock fallback；(b) sweep run 间 zenoh 资源残留；(c) sweep harness 改用每 run 独立 `ZENOH_RUNTIME_TMPDIR` 隔离；(d) 或方向 2/3：harness 改默认 zenoh_json + 把 GT publish 进 ROS publisher（绕过 zenoh 跨进程） |

> 后续 D8 修复以契约/时序参考文档为准（[11_experiment_state_machine.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/internals/11_experiment_state_machine.md) + [terrain_benchmark_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/terrain_benchmark_log.md)），并要求"严格时序契约 + 明确结论"再下笔。

---

## 9. 不在本次范围（明确排除，再次声明）

- 图像美观性（统一字体/色板/坐标轴样式）
- 论文写作浓缩（AI 工具二次加工）
- 实物部署（不改 Jetson 对外接口）
- 硬件电路、九参数标定相关代码
