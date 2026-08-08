# 数据来源

- 源 run: `results/control/pid_pvs_tuning/20260610_142323`
- 同步时间: 2026-06-20 15:04:15
- 来源根: `/auv_data`（不随仓库同步，仅本地存在）

## 图内中文化重跑（2026-08-06）

- 脚本 `tools/pid_pvs_tracking_plots.py` 已完成图内统一中文（文泉驿正黑，`axes.unicode_minus=False`）。
- 该脚本为纯仿真复现型（内部跑 PVS remus100 自驾，不依赖历史 bag），重跑命令：
  `python3 tools/pid_pvs_tracking_plots.py --output-root <tmp> && cp <tmp>/*/figures/*.png .`
- profile 内部名（`pvs_default_baseline`/`step_tuned_v2`/`sine_tuned_v2`）为溯源标识，保留英文不译。
