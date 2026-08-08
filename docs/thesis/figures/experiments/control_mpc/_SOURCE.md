# 数据来源

- 源 run: `results/control/mpc_test/20260610_170426`
- 同步时间: 2026-06-20 15:04:15
- 来源根: `/auv_data`（不随仓库同步，仅本地存在）

## 图内中文化重跑（2026-08-06）

- 脚本 `tools/mpc_test.py` 已完成图内统一中文（文泉驿正黑，`axes.unicode_minus=False`，字体块在 rcParams 后注入）。
- 纯仿真复现型（内部 `test_mpc_*` 生成数据，不依赖历史 bag），无参数，重跑命令 `python3 tools/mpc_test.py`，输出至 `/auv_data/results/control/mpc_test/<时间戳>/figures`，再 `cp` 迁入本目录。
- 本轮源 run: `results/control/mpc_test/20260806_191823`。
