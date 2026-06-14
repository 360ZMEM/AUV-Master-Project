# T4 — 不确定性量化（论文 §3.5 / §4.4 关键创新点）

> **对应论文章节**：§3.5 感知不确定性量化；§4.4 UA-MPC 中协方差→置信度耦合
> **直接消费方**：论文 §3.5 自适应 R 算法图 / §4.4 协方差注入路径 / §5.4 NIS 验证表
> **生成时机**：Phase 4 — A 档骨架 + 多场景数据待补

本表覆盖论文中"如何把 EKF 内部协方差变成 MPC 可用置信度"的完整链路：从滤波器内部 NIS、到 ROS topic 发布、到 MPC 节点 sigmoid 映射、到 UA-MPC 权重缩放。

---

## 1. 不确定性来源链路

```
IMU/DVL/Mag 原始量测
  ├── perception_engine.py 加噪声 (sonar_noise_scale, mag_saturation)
  └─→ ES-EKF (es_ekf.py)
        ├── predict() 推进 P(15×15)
        ├── correct_*() 累加 NIS_window
        ├── _adapt_R(): NIS > χ² ⇒ scale R 上调
        └─→ /auv/state/covariance (Float32MultiArray, 225 元素)
              └─→ auv_controller_node._on_covariance
                    └── _confidence_from_cov: conf = exp(-trace_xy / σ_xy_ref)
                          └─→ /auv/control/confidence (Float32) + env AUV_MPC_CONFIDENCE
                                └─→ auv_mpc_controller (sigmoid + (1-conf)^α)
                                      └── 跟踪权重 / 输入权重 / low_conf_scale
```

每一段对应代码位置：

| 段 | 文件 | 关键符号 |
| --- | --- | --- |
| 滤波器协方差 | [es_ekf.py L329](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L329) | `self.P` (15×15) |
| NIS 滑窗 | [es_ekf.py L417](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L417) | `get_nis_stats()` |
| 自适应 R | [es_ekf.py L138-L145, L376-L415](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py) | `_adapt_R` |
| 协方差发布 | [auv_localization_node.py L461-L463](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_localization/auv_localization/auv_localization_node.py#L461-L463) | `Float32MultiArray` 225 元素 |
| 协方差订阅 | [auv_controller_node.py L286](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py#L286) | `_on_covariance` |
| cov→conf 映射 | [auv_controller_node.py L298](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py#L298) | `_confidence_from_cov` |
| ROS 参数 | [auv_controller_node.py L194-L199, L548](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py#L194-L199) | `cov_to_conf.{enabled,sigma_xy_ref,...}` |
| MPC 消费 | [auv_mpc_controller.py L162-L164, L218, L249](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py) | `low_conf_scale`, sigmoid, `(1-conf)^α` |

---

## 2. 关键公式

### 2.1 NIS（归一化新息平方）

每个观测周期：
```
ν = z - h(x̂)         # 新息
S = H P H^T + R      # 新息协方差
NIS = ν^T S^-1 ν     # 标量
```
窗口长度 N=50，统计 `mean(NIS)`、`95% CI`，与 χ²(dim_obs) 阈值比较。

### 2.2 自适应 R

```
NIS_avg > χ²_upper ⇒ R ← min(R_max, R · k_up)
NIS_avg < χ²_lower ⇒ R ← max(R_min, R · k_dn)
```
其中 `k_up=1.5, k_dn=0.95`（见 [es_ekf.py L138](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L138) 默认值）。论文 §3.5 公式 3-21 ~ 3-22 与此一致。

### 2.3 协方差 → 置信度

```python
trace_xy = P[0,0] + P[1,1]                  # XY 位置不确定性
conf_raw = exp(-trace_xy / sigma_xy_ref²)
conf = sigmoid(α · (conf_raw - β))          # 平滑过渡
```

参数：
- `sigma_xy_ref` 默认 1.0 m（[auv_controller_node.py L194-L199](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py#L194-L199)）
- `α` 默认 6.0（sigmoid 陡度）
- `β` 默认 0.5（中点）

### 2.4 UA-MPC 权重缩放

[auv_mpc_controller.py L157, L227-L230](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py)：
```
W_track ← W_track · (1 - low_conf_scale · (1 - conf)^α_w)
W_input ← W_input · (1 + low_conf_scale · (1 - conf)^α_w)
```
低置信时跟踪权重下调、输入正则上调，使 MPC 倾向"保守平滑"。

---

## 3. 验证矩阵

| 实验 | 目的 | 期望产物 | 状态 |
| --- | --- | --- | --- |
| **NIS 时序图** | 验证滑窗统计正确 | `innovation_residual.png` | ✅ baseline 1 张（[benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md)） |
| **dvl_dropout 系列** | 验证 R 自适应触发 | NIS 时序 + R 上调记录 | ⏳ pending（多 seed） |
| **mag_distortion** | 磁通道触发自适应 R 的频率 | mag NIS + 触发率 | ⏳ pending |
| **cov→conf 阶跃响应** | 验证 sigmoid 平滑性 | `conf` 时序图 vs `trace_xy` | ⏳ pending |
| **σ_xy_ref 灵敏度** | 论文 §5.5.1 灵敏度图 | 5 档参数 sweep | ⏳ pending（D3.2） |
| **mpc_mode=baseline 对照** | 关闭协方差耦合的对照组 | 同场景两条 RMSE 曲线 | ⏳ pending |

---

## 4. 复现命令

### 4.1 NIS / 自适应 R 复算（baseline）

```bash
python3 tools/offline_ekf_benchmark.py \
  --input log/experiments/benchmark_120s/rosbag_mcap/rosbag_mcap_0.mcap \
  --output-dir results/localization/uncertainty_baseline \
  --verbose
```
输出：`innovation_residual.png` 含 NIS 时序 + χ² 阈值带。

### 4.2 协方差→置信度链路在线观测

```bash
# 第一终端：实验
bash scripts/start_experiment.sh \
  --scenario scenarios/scenario_dvl_dropout_60.yaml --seed 0 --duration 120

# 第二终端：观测话题
ros2 topic echo /auv/state/covariance --once
ros2 topic echo /auv/control/confidence
```
预期：DVL 冻结期 `/auv/state/covariance` 的对角 [0,0] [1,1] 元素膨胀，`/auv/control/confidence` 下降至 < 0.5。

### 4.3 σ_xy_ref 灵敏度（pending）

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios dvl_dropout_60 \
  --seeds 0,1,2 \
  --mpc-modes ua \
  --param-grid '{"cov_to_conf.sigma_xy_ref":[0.5,1.0,2.0,5.0]}' \
  --output-root /auv_data/sweeps/cov_conf_sensitivity
```

> ⚠️ 当前 [run_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py) 的 `--param-grid` 通过 env `AUV_MPC_PARAM_OVERRIDES` 注入到 [mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py)（Phase 4 C1 已闭环）；如要把 ROS 参数 `cov_to_conf.sigma_xy_ref` 也从 sweep 注入，需扩展 sweep harness 解析路径，列入 future work。

---

## 5. 论文 §3.5 / §4.4 引用对照

| 论文位置 | 本表 §  | 来源代码 / 数据 |
| --- | --- | --- |
| §3.5 NIS 公式 | §2.1 | [es_ekf.py get_nis_stats](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L417) |
| §3.5 自适应 R 公式 | §2.2 | [es_ekf.py _adapt_R](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L138) |
| §4.4 cov→conf 映射 | §2.3 | [auv_controller_node.py _confidence_from_cov](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py#L298) |
| §4.4 UA-MPC 权重 | §2.4 | [auv_mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py#L157) |
| §5.4 NIS 验证表 | §3 + §4.1 | `innovation_residual.png` |
| §5.5 鲁棒比较 | [04_mpc_robustness_ablation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/04_mpc_robustness_ablation.md) | sweep 数据 |
| §5.5.1 灵敏度 | §4.3 | param-grid sweep |

---

## 6. 已知限制（呼应 [07_drift_log_and_known_issues.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/07_drift_log_and_known_issues.md)）

- D1.4：NIS 滑窗长度未按观测频率自适应
- D3.2：σ_xy_ref 灵敏度数据待补
- D3.3：sweep harness param-grid 注入路径已修但仍仅覆盖 MPC weights，未覆盖 ROS 参数
- D5.1：sensitivity 仅一阶 ANOVA

---

## Pre-Snapshot @ Phase 4 A7

- ES-EKF NIS + 自适应 R 实现完整（Phase 2 E2）
- 协方差话题发布 + 控制端订阅就位（Phase 3 E4）
- UA-MPC sigmoid + (1-conf)^α 实现完整（Phase 2 E3）
- E6 sweep harness param-grid 链路闭合（Phase 4 C1）

## Post-Snapshot @ Phase 4

待 P2（TaskList #32）补全多场景多种子 NIS 时序与 σ_xy_ref 灵敏度数据。
