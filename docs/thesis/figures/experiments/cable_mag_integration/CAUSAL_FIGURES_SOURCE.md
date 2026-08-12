# 电缆声磁第 5.5.11 节因果图（重绘自 AUV-Master-Mag 子仓库）

本目录下三张 §5.5.11 算法级因果图由主仓脚本
`tools/render_cable_mag_causal_figures.py` 按主仓中文排版约定（WenQuanYi CJK）
重绘 / 重算，不是子仓库原图 PNG 的直接复制。三图共同构成
“失效现象 → 机制解耦 → 运维价值” 的算法级证据链。

子仓库审计基线 commit：`12e1884b59737dbe14e83c825b6cea9bb3c7a4bb`。
证据等级统一为：算法级、单次确定性复现、纯仿真、`n=1`，不构成主仓端到端或实测。

## 1. pure_magnetic_failure_timeseries.{png,pdf}

- 论文落点：第 5.5.11 节“失效边界”，图 `fig:ch05-mag-failure-timeseries`
- 数据来源：重跑子仓库确定性仿真
  （`case_maze_sonar_dropout_prior_heavy` 基线 vs 关闭
  `nominal_route_prior_observation_correction_enabled` 的消融）
- 重绘参考（非复制）：`AUV-Master-Mag/docs/figure/fig_b1_failure_timeseries.pdf`
  - 参考图 SHA256（前 16 位）：`dafdb0f8c514bd83`
- 关键复现数值：消融支路约 2119 s 处 +57.5 m 跨车道单步跳变，横偏漂移至 30--40 m；
  与正文摘要表“纯磁失效时序”一行一致。

## 2. prior_alignment_decoupling.{png,pdf}

- 论文落点：第 5.5.11 节“机制解耦”，图 `fig:ch05-mag-prior-decoupling`
- 数据来源：
  - `AUV-Master-Mag/results/20260705_lane_shortcut/lane_shortcut_prior_alignment_70.csv`
  - `AUV-Master-Mag/results/20260705_lane_shortcut/lane_shortcut_prior_alignment_50.csv`
- 重绘参考（非复制）：`AUV-Master-Mag/docs/figure/fig_d4_prior_alignment_decoupling.pdf`
  - 参考图 SHA256（前 16 位）：`5d40d2a75c292dd2`
- 核心机制：关闭在线先验修正时全局路由跳变 686.4/724.1 m 但地图系投影跳变仅约 0.2 m；
  基线累计约 7.53 m 平移与约 −3.18° 旋转把错位地图拉回真实电缆。

## 3. zigzag_burial_tradeoff.{png,pdf}

- 论文落点：第 5.5.11 节“运维价值”，图 `fig:ch05-mag-zigzag-tradeoff`
- 数据来源（合并三份调优扫描，取 `lat_2p0` 基础覆盖变体，得到 20--36° 完整包络）：
  - `results/20260705_zigzag_burial/zigzag_burial_tuning_focused.csv`
  - `results/20260705_zigzag_burial/zigzag_burial_tuning_shallow_mid.csv`
  - `results/20260705_zigzag_burial/zigzag_burial_tuning_depth2.csv`
- 相对子仓库当前 `fig_zigzag_burial_tradeoff`（0--20° 第一轮未达标）的修订：
  1. 覆盖区间扩到 20--36°，纳入调优后达标结果；
  2. 圈标三个当前最优工作点：1.0 m@36°=0.124 m、1.5 m@32°=0.079 m、2.0 m@25°=0.123 m；
  3. 增补右面板“埋深精度增益 vs TRACK 横偏 / 完成度代价”权衡；
  4. 标注 0.15 m 行业参考目标线。

## 边界声明

三张图描述同源电缆探测算法在专用磁探测仓库中被扫描出的**机理与边界**，
均为确定性单次纯仿真（`n=1`），不等同于主仓 ROS/PVS 端到端、多种子或实物结论；
配套证据契约见附录 A.9 与 Artifact `MAG-CABLE-ALGORITHM-BOUNDARY`（M3 固化）。
