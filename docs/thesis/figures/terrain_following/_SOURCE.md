# 地形跟随图像来源

- 生成脚本：`tools/plot_terrain_following_figures.py`
- 图像与数据说明详见 `docs/thesis/09_terrain_following_figures.md`。

## 论文压缩降级记录（2026-08-18，L2 表-图去重）

- 正文保留：`terrain_tz_tracking_pid_mpc.pdf`（`fig:ch05-terrain-tracking`），用于展示 PID/MPC 地形跟随的离底高度动态过程。
- 已归档不在正文展开：
  - `terrain_clearance_safety_margin.pdf`
  - `terrain_clearance_rmse_pid_mpc.pdf`
  - `terrain_benchmark_command_contract.pdf`
  - `pid_terrain_low_mid_high_ablation.pdf`（原 `fig:ch05-terrain-pid-ablation`）
- 降级理由：安全裕度、RMSE 对比和三档 PID 消融的数值结论已经由 `tab:ch05-terrain-main` 与 `tab:ch05-terrain-ablation` 给出；除主动态过程图外，其余图作为同源支撑材料归档。

## 3D 图提升入正文 + 地形口径修正（2026-08-20，27 号文 P2-1a）

- `terrain_3d_pid_terrain_trajectory.png` / `.pdf`（**已提升入正文** `fig:ch05-terrain-3d`，§5.5.2）：
  由 L2 归档材料提升为正文图，与 `fig:ch05-terrain-tracking`（时间维度）互补，提供近底跟随的**空间直觉**。
- **地形曲面口径修正（关键）**：早先脚本在 bag 存在 `/auv/visual/seabed_cloud` 时优先绘制该点云，
  但离线核验发现该点云是**围绕原点的静态显示帧快照**（仅覆盖 x∈[−25,25]，而 AUV 轨迹 x∈[15.8,62]），
  其 (x,y) 与世界系轨迹**去相关**（corr≈−0.04），叠加世界系轨迹会造成``轨迹悬空''的误导。
  现统一改为**确定性地形重建**：公式与仿真 `sim_holoocean/interfaces/synthetic_sensors.py::_terrain_height`
  完全一致（seed=42、octaves=4、scale=6、amplitude=2.0、slope=3°），对全轨迹均有定义，忠实于本次运行。
- **诚实验证锚**：图中叠加 AUV 沿程 DVL 实测海底高度（`clearance_source=real_altitude`）散点，
  重建曲面与实测沿程 **r≈0.91、偏差≈−0.06 m、RMS≈0.34 m**，量化标注地形可信度。
- 生成脚本：`tools/plot_terrain_following_figures.py::plot_3d_terrain_trajectory`（走 setup_style，中文字体 / 300 dpi）。
- **数据来源（复用，不重跑）**：`results/control/terrain_following_20260619_222639/pid_terrain`
  （轨迹 `/auv/state/filtered`）+ 运行同源配置 `config/bridge_params.protocol_udp.pvs.terrain.yaml`。
- **诚实边界**：单次运行（n=1），仅作空间直觉与地形可信度佐证；近底安全稳健结论仍以 `tab:ch05-terrain-ablation` 三档多种子消融为准。
- 复算命令：`python3 tools/plot_terrain_following_figures.py`。
