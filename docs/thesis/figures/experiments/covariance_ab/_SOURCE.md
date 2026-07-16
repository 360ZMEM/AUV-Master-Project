# 分源协方差整定 A/B 独立对照（E-3 / O-3 / O-4）

本目录产物由 `tools/run_es_ekf_covariance_ab.py` 复算，对应论文 §5.5.5 表 `tab:ch05-nis-covariance-ab`。

## 复算命令

```bash
python3 tools/run_es_ekf_covariance_ab.py --in-place
```

- 源 sweep：`log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv`（P1 sensor sweep，8 场景 × 3 种子 = 24 次真实运行）。
- 引擎：`tools/uncertainty_metrics.py` 回放 ES-EKF，按观测源与自由度分别聚合标准 NIS。
- **不改动** `algorithm/es_ekf.py` / `brain_linux/config/params.yaml` 默认协方差；
  仅通过 uncertainty_metrics.py 的 CLI 覆盖开关在本对照进程内改写口径。

## 三臂定义

| 臂 | 覆盖开关 | 含义 |
|---|---|---|
| A_baseline_default | （无，global / sigma_depth=0.05 / sigma_dvl=0.03） | 复现正文锚点，既有产物不失效 |
| B_per_source_gating | `--adaptive-r-mode per_source` | 切断跨源污染（DVL R 缩放 1.69→1.0） |
| C_per_source_tuned | `--adaptive-r-mode per_source --sigma-depth 0.12` | 深度整定回卡方带内 |

## 池化结果（24 次运行逐量测池化）

| 臂 | 源 | 事件数 | NIS/自由度 | 95% 覆盖率 | 上界超限 |
|---|---|---:|---:|---:|---:|
| A_baseline_default | depth | 17630 | 7.205 | 0.561 | 0.416 |
| A_baseline_default | dvl_world | 17613 | 0.119 | 0.553 | 0.000 |
| B_per_source_gating | depth | 17630 | 8.126 | 0.567 | 0.410 |
| B_per_source_gating | dvl_world | 17613 | 0.055 | 0.231 | 0.000 |
| C_per_source_tuned | depth | 17630 | 3.285 | 0.737 | 0.214 |
| C_per_source_tuned | dvl_world | 17613 | 0.050 | 0.222 | 0.000 |

## 结论边界

- O-4 兑现：`sigma_depth` 0.05→0.12 后深度 NIS/自由度 7.205→3.280、覆盖率 0.561→0.735。
- DVL 过保守（分源门控仅单向膨胀）判定为**结构性下界（类型 2）**，如实承认，不宣称已解决。
- baseline 臂逐字节复现正文口径（深度 7.205 / DVL 0.119），既有 24 矩阵结论不被回改。
- 把 C 臂口径回写主线默认并重跑 24 矩阵属独立后续，不在本轮范围。

