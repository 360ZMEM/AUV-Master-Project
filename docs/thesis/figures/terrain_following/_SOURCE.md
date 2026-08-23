# 地形跟随图像来源

- 生成脚本：`tools/plot_terrain_following_figures.py`
- 正文两图复算命令：
  ```bash
  source /opt/ros/humble/setup.bash
  source brain_linux/install/setup.bash
  python3 tools/render_thesis_figures.py \
    --id ch05_terrain_tz \
    --id ch05_terrain_3d \
    --render linux
  ```
- 正式四相结果：`results/control/terrain_following_20260823_215036/`
- Linux 原始 MCAP（SHA256 同步记录于 `thesis_figure_manifest.json`）：
  - PID terrain：`/auv_data/bags/20260823_215151/rosbag/rosbag_0.mcap`，`0ea51e9f49a7b4675e176c3c11ab197f6e1443480a652043a34fb56d6da1f407`
  - MPC terrain：`/auv_data/bags/20260823_215416/rosbag/rosbag_0.mcap`，`e465d0b9cf80b54e77693b5654d6ef9f4dbeea1021603404206793b4e65a5014`
- PVS 内环 sidecar：
  - PID terrain：`pvs_control_trace.csv`，`51989db27eb0c1ad3788c452aaf6ccb50f62bdf2e1acf70dc6a138698af5fe42`
  - MPC terrain：`pvs_control_trace.csv`，`d8d8689858d4d1cfe2a72aa109462400d5d50d61874e0d9e36da4980778b2cdb`
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
  重建曲面与实测沿程 **r≈1.00、偏差≈0.00 m、RMS≈0.03 m**，量化标注地形可信度。
- 生成脚本：`tools/plot_terrain_following_figures.py::plot_3d_terrain_trajectory`（走 `thesis_plot_style`，中文字体、STIX 数学字体、PDF + 600 dpi PNG）。
- **数据来源（2026-08-23 原生 PVS 重跑）**：`results/control/terrain_following_20260823_215036/pid_terrain`
  （轨迹 `/auv/sensors/ground_truth`）+ 运行同源配置 `config/bridge_params.protocol_udp.pvs.terrain.yaml`。
- **诚实边界**：单次运行（n=1），仅作空间直觉与地形可信度佐证；近底安全稳健结论仍以 `tab:ch05-terrain-ablation` 三档多种子消融为准。
- 复算入口只重绘两幅正文图，不改写同目录归档图；渲染前由总入口校验原始 MCAP SHA256。

## 全量图片统一审计（2026-08-23，Linux）

- `terrain_tz_tracking_pid_mpc`：6.8 inch 通栏、两子图共享图例、统一 `(a)/(b)` 标识；移除重复总标题，图例置于数据区外。
- `terrain_3d_pid_terrain_trajectory`：6.8 inch 通栏、`cividis` 海底深度色标、统一语义色；移除图内长来源说明，完整来源与边界保留在本文件和论文 caption。
- 2026-08-23 执行链审计后，时序图明确分离几何净空目标、`/auv/control/mpc_cmd` 实际命令、PVS 可行参考 \(z_d\) 与 AUV 真值深度；legend 使用不透明白底和 0.8 线宽灰边框。
- 3D 图由滤波位姿改为同一录包的 PVS 真值轨迹，消除了 EKF 近常量平移偏置对地形一致性校核的污染；未对真值轨迹做平滑。
