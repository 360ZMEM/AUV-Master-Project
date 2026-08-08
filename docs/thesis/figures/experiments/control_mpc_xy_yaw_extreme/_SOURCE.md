# 数据来源

- 源 run: `results/control/mpc_xy_yaw_extreme/20260620_011831`
- 同步时间: 2026-06-20 15:04:15
- 来源根: `/auv_data`（不随仓库同步，仅本地存在）

## 图内中文化重跑（2026-08-06）

- 脚本 `tools/mpc_xy_yaw_extreme_benchmark.py` 已完成图内统一中文（文泉驿正黑，`axes.unicode_minus=False`）。
- 纯仿真复现型（离线制导 MPC 基准，不依赖历史 bag），无参数，重跑命令 `python3 tools/mpc_xy_yaw_extreme_benchmark.py`，输出至 `/auv_data/results/control/mpc_xy_yaw_extreme/<时间戳>/figures`，再 `cp` 迁入本目录。
- **scenario/variant 内部名（`chicane_90deg`/`s_turn_short_wave`/`xy_v1_balanced` 等）保留英文**——是诚实边界证据（chicane 场景 PID-LOS 优于 MPC），译名会破坏溯源。
- 本轮源 run: `results/control/mpc_xy_yaw_extreme/20260806_192034`。
