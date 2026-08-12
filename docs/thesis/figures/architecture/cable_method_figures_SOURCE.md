# 电缆声磁方法图（重绘自 AUV-Master-Mag 子仓库）

本目录下两张电缆算法方法图由主仓脚本按主仓事实重绘，不是子仓库原图的直接复制。

## 1. cable_acoustic_magnetic_perception_pipeline.{png,pdf}

- 生成脚本：`tools/render_cable_perception_pipeline_figure.py`
- 论文落点：第 3.3.3 / 3.3.4 节（原始磁场如何进入统一感知状态）
- 重绘参考（非复制）：`AUV-Master-Mag/docs/figure/fig_perception_pipeline.png`
  - 子仓库审计基线 commit：`12e1884b59737dbe14e83c825b6cea9bb3c7a4bb`
  - 参考图 SHA256（前 16 位）：`c6e061e0adb219ab`
- 相对子仓库示意图的修订：
  1. 内层采样从子仓库示意的 200 Hz 改为“按采集配置”，正文示例引用当前 2000 Hz 原始 / 10 Hz 特征步进链；
  2. “滤波/RMS”改为 45/50 Hz DLIA 连续 I/Q 与旋转不变模量；
  3. 明确 `CableTrackingOutput` 与两级估计的上下游边界（载体级 ES-EKF → 电缆几何级在线修正）；
  4. 真值只进入离线评价，不进入在线管线；
  5. 声呐观测标注为“质量分驱动，非无条件可信”。

## 2. cable_active_crossing_observability.{png,pdf}

- 生成脚本：`tools/render_cable_active_crossing_figure.py`
- 论文落点：第 2.3.5 节（FWHM 推导后的几何示意），第 4.3.1 节交叉引用
- 重绘参考（非复制）：`AUV-Master-Mag/docs/figure/fig_zigzag_probe.png`
  - 参考图 SHA256（前 16 位）：`4e0661beda984017`
- 精简与修订：
  1. 只保留真值电缆、AUV 横切航迹、穿缆峰值观测点、横切角 θ、估计中心线；
  2. 增补 `|B|` 剖面下面板，显式区分两类几何观测：峰值时刻 → 横向中心线 `e=0`；半高全宽 FWHM → 垂直距离 / 埋深 `z`；
  3. 标题明确这是 TRACK / REACQUIRE 阶段的**局部主动探查**，区别于 SEARCH 阶段的大范围覆盖之字形。

## 边界声明

两张图描述的是同源电缆探测算法的**原理与机理**，不含主仓端到端、多种子或实物结论；配套的算法级数值边界见第 5.5.11 节与附录 A.9，其证据等级为算法级、单次复现、纯仿真。
