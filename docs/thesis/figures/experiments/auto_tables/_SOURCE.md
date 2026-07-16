# 可复算 LaTeX 数据表片段（27 号文 P2-3：自动 LaTeX 表格）

本目录的 `.tex` 片段由 `tools/build_thesis_data_tables.py` 从实验产物 CSV **确定性复算**，
用于替代第 5 章手写数据表中的\ *手工转录*\ 数字，消除"改产物忘改正文"的漂移风险，
并让答辩时"这张表数字怎么来的"可一键回溯。

## 复算命令

```bash
python3 tools/build_thesis_data_tables.py            # 生成 .tex 到本目录
python3 tools/build_thesis_data_tables.py --verify   # 只校验正文数字未漂移（CI/答辩前体检）
```

## 表↔产物映射

| 片段 | 正文 label | 源产物 CSV |
|---|---|---|
| `mpc_extreme_paths.tex` | `tab:ch05-mpc-extreme-paths` | `control_mpc_xy_yaw_extreme/best_comparison.csv` |
| `eskf_robustness.tex` | `tab:ch05-eskf-robustness` | `results/thesis_sweep_aggregates/20260612_170618_p1_sensor_3seed/summary_by_scenario_mode.csv` |
| `nis_covariance_ab.tex` | `tab:ch05-nis-covariance-ab` | `covariance_ab/covariance_ab_summary.csv` |

## 设计边界（复用优先 / 不过度工程化 / 诚实边界）

- **不强拆**现有手写表：本片段作为\ *可复算 provenance 层*\ 与未来 `\input` 入口；
  是否把正文切换到 `\input{...}` 由人决定，本轮不自动改写正文。
- 生成的列结构、表头、caption/label 与正文一一对应，数字取自产物 CSV，**不新造口径**。
- `--verify` 把关键单元格（如协方差 A/B 基线深度 7.205 / DVL 0.119）与正文现值逐一比对，
  任何漂移即非零退出。当前状态：3 张表关键单元格与正文一致，无漂移。
- 纯离线读表，零随机、幂等；缺产物则该表跳过并显式报告，不编造数字。
