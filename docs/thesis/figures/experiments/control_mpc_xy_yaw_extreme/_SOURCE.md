# 数据来源

- 源 run: `results/control/mpc_xy_yaw_extreme/20260620_011831`
- 同步时间: 2026-06-20 15:04:15
- 来源根: `/auv_data`（不随仓库同步，仅本地存在）

## 图内中文化重跑（2026-08-06）

- 脚本 `tools/mpc_xy_yaw_extreme_benchmark.py` 已完成图内统一中文（文泉驿正黑，`axes.unicode_minus=False`）。
- 纯仿真复现型（离线制导 MPC 基准，不依赖历史 bag），无参数，重跑命令 `python3 tools/mpc_xy_yaw_extreme_benchmark.py`，输出至 `/auv_data/results/control/mpc_xy_yaw_extreme/<时间戳>/figures`，再 `cp` 迁入本目录。
- **scenario/variant 内部名（`chicane_90deg`/`s_turn_short_wave`/`xy_v1_balanced` 等）保留英文**——是诚实边界证据（chicane 场景 PID-LOS 优于 MPC），译名会破坏溯源。
- 本轮源 run: `results/control/mpc_xy_yaw_extreme/20260806_192034`。

## 多种子统计层（E-1，2026-08-13）

- 目的：把原 `n=1` 支线升级为可作主结论的统计（对应 24 号文档 §8.1 ①、正文 chap05 `tab:ch05-mpc-extreme-paths`）。
- 方法学修复：原脚本 plant 完全确定性、无随机扰动，直接重跑 3 次只是复制 n=1。本轮在 `plant_step` 注入**受控扰动**（恒定横流 ≤0.15 m/s、初始横向偏移 ≤0.8 m、逐步艏向白噪声 ≤1.5°），以 seed 固定。同一 seed 下 PID/LOS/MPC **共享同一扰动实现与同一噪声流**，保证公平；MPC 变体**冻结**为确定性通道选出的 best（防逐 seed 樱桃摘取）。
- 向后兼容：不传 `--seeds` 时 plant 逐字节复现旧 n=1（PID/LOS 列与归档完全一致，MPC 列仅 IPOPT ~1e-6 浮点噪声，三位小数不变），归档图与 Manifest 无需更新。
- 重跑命令：`python3 tools/mpc_xy_yaw_extreme_benchmark.py --seeds 0,1,2,3,4`（输出 `multiseed_summary.csv` + `multiseed_raw.csv`，含逐 seed 扰动参数）。
- 本轮源 run：`.auv_data_e1/results/control/mpc_xy_yaw_extreme/20260813_151303`（AUV_DATA_ROOT 隔离目录，不随仓库同步）。
- 结论（n=5 lateral RMSE mean±std, m）：长波 S 弯 MPC 0.133±0.034 vs LOS 1.146±0.148（不重叠，全胜）；发卡 MPC 2.363±0.234 vs LOS 4.246±0.459（不重叠，全胜）；短波 S 弯 MPC 1.824±0.190 与 LOS 1.672±0.043 持平、均优于仅航向 PID 2.725±0.315；直角折弯 LOS 1.003±0.513 最优（诚实边界保留）。n=1 论断在扰动统计下全部成立。

## 论文压缩降级记录（2026-08-18，L2 表-图去重）

- `s_turn_long_wave_xy_v4_short_realtime.png`（原 `fig:ch05-mpc-long-s`）：从正文降级归档，图片文件保留本目录不删。理由：长波 S 弯的 \(n=1\) 横向 RMSE 优势已由 `tab:ch05-mpc-extreme-paths` 给出，五种子统计层已由 `multiseed_summary.csv` 和正文段落支撑；单次轨迹图只提供直观展示，不再占正文版面。
- `s_turn_short_wave_xy_v3_speed_flexible.png`、`hairpin_180deg_xy_v3_speed_flexible.png`、`chicane_90deg_xy_v1_balanced.png` 继续作为同组归档图保存。

## 图表统一美化重跑（2026-08-20，P1-4）

- 脚本 `tools/mpc_xy_yaw_extreme_benchmark.py` 由内联 `_apply_zh_style()` 迁移到统一样式层 `tools/thesis_plot_style.py`：中文字体（文泉驿正黑）/ 300 dpi / 黑白可辨（线型 + marker 双通道，去色仍可分 PID 与 MPC）。
- 输出由单一 180 dpi PNG 升级为 300 dpi PNG + 矢量 PDF 双份（`save_figure`）。
- 数值不变：deterministic 通道逐字节复现，best 变体选择与文件名不变（`s_turn_long_wave→v4`、`s_turn_short_wave→v3`、`hairpin_180deg→v3`、`chicane_90deg→v1`）；本轮仅换样式、不改结论。
- 本轮源 run：`/auv_data/results/control/mpc_xy_yaw_extreme/20260820_193105`。重跑命令 `python3 tools/mpc_xy_yaw_extreme_benchmark.py`（无参数）。
