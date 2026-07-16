# 控制实验图像来源

## R13-v2 分源置信正式矩阵

- 源结果目录：`results/control_aggregates/20260810_r13_v2_full/r13_v2_thesis_audit/`
- 生成脚本：`tools/plot_r13_v2_formal_audit.py`
- 正文保留：
  - `r13_v2_control_rate_paired.png`
  - `r13_v2_authority_modes_ua.png`
  - `r13_v2_p_track_boxplot_ua.png`
- 论文压缩降级记录（2026-08-18，L2 表-图去重）：
  - `r13_v2_rmse_paired.png`（原 `fig:ch05-r13-v2-rmse-boundary`）：从正文降级归档，图片文件保留本目录不删。理由：该图仅以柱状图重复表 `tab:ch05-r13-v2-main-results` 中六类场景的固定权重/保守 UA 成对 RMSE 与 RMSE 变化列；“控制平滑不等于精度改善”的边界已经由表格和 `tab:ch05-negative-results` 汇总表直接给出。
  - 数值权威源：`tab:ch05-r13-v2-main-results` 与 Artifact `CONTROL-R13-V2-SOURCE-CONFIDENCE`。
