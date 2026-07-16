# 电缆声磁方法图来源链

本目录下两张电缆算法方法图由主仓脚本按主仓事实重绘，不是子仓库原图的直接复制。

## 1. cable_acoustic_magnetic_perception_pipeline.{png,pdf}

- 生成脚本：`tools/render_cable_perception_pipeline_figure.py`
- 论文落点：第 3.3.3 / 3.3.4 节（原始磁场如何进入统一感知状态）
- 磁仓可编辑参考：`AUV-Master-Mag/docs/figure/fig_perception_pipeline.drawio`
- 磁仓统一生成器：`AUV-Master-Mag/docs/figure/generate_drawio_method_figures.py`
- 重绘参考预览：`AUV-Master-Mag/docs/figure/fig_perception_pipeline.png`
  - 子仓库重构起点 commit：`12e1884b59737dbe14e83c825b6cea9bb3c7a4bb`
  - 本轮重构后 Draw.io SHA256：`7cef8896bd892afc37d2ac08a33d2cf0a11bc586e0ef625a16d13041e87dd5c7`
  - 本轮重构后预览 PNG SHA256：`8f0208ef5d141ff8a04c1edbe5812b679483295c46e12bab9441534ee191bb8e`
- 主论文出版物：
  - PNG SHA256：`6b2ca4b500ee83eb44a48918f2d259165bf5133fb24cfd8e4cc2cdced7773420`
  - PDF SHA256：`906cd64ef3ce8525cfb3e68eceabb13c33c4e3eeb888bdaef72a9281e1f34f9c`
- 相对子仓库示意图的修订：
  1. 内层采样从子仓库示意的 200 Hz 改为“按采集配置”，正文示例引用当前 2000 Hz 原始 / 10 Hz 特征步进链；
  2. “滤波/RMS”改为 45/50 Hz DLIA 连续 I/Q 与旋转不变模量；
  3. 明确 `CableTrackingOutput` 与两级估计的上下游边界（载体级 ES-EKF → 电缆几何级在线修正）；
  4. 真值只进入离线评价，不进入在线管线；
  5. 声呐观测标注为“质量分驱动，非无条件可信”。

## 2. cable_active_crossing_observability.{png,pdf}

- 生成脚本：`tools/render_cable_active_crossing_figure.py`
- 论文落点：第 2.3.5 节（FWHM 推导后的几何示意），第 4.3.1 节交叉引用
- 磁仓可编辑参考：`AUV-Master-Mag/docs/figure/fig_zigzag_probe.drawio`
- 磁仓统一生成器：`AUV-Master-Mag/docs/figure/generate_drawio_method_figures.py`
- 重绘参考预览：`AUV-Master-Mag/docs/figure/fig_zigzag_probe.png`
  - 子仓库重构起点 commit：`12e1884b59737dbe14e83c825b6cea9bb3c7a4bb`
  - 本轮重构后 Draw.io SHA256：`67d223c5bcd42e7f0aaac420ca68094510da1e21278eaff39669dfd21c467bbe`
  - 本轮重构后预览 PNG SHA256：`677dc24042bb6acde0671c9bb72343787140f6dd7e4b7b48f49319965e599ac1`
- 主论文出版物：
  - PNG SHA256：`63ad550a3d52adfb79ad9d6e232aa32473921cfceb0294b9dab6298d7c263b6e`
  - PDF SHA256：`216f29abd4993d24b3f0fd99c1661cca41fbb21c2d09c2d133156da813931c26`
- 精简与修订：
  1. 只保留真值电缆、AUV 横切航迹、穿缆峰值观测点、横切角 θ、估计中心线；
  2. 增补 `|B|` 剖面下面板，显式区分两类几何观测：峰值时刻 → 横向中心线 `e=0`；半高全宽 FWHM → 垂直距离 / 埋深 `z`；
  3. 标题明确这是 TRACK / REACQUIRE 阶段的**局部主动探查**，区别于 SEARCH 阶段的大范围覆盖之字形。

## 可编辑事实源边界

- 磁仓 `.drawio` 是磁仓说明图的可编辑事实源。
- 主论文两张出版图由各自 Python 脚本生成；脚本是主论文版本的唯一可编辑事实源，不再另建同名
  Draw.io，以免同一出版图出现双真源。
- 第 4.3.1 节只回指第 2.3.5 节的局部主动横切图，不重复插图，并继续区分 SEARCH 覆盖扫描与
  TRACK / REACQUIRE 局部主动探查。

## 边界声明

两张图描述的是同源电缆探测算法的**原理与机理**，不含主仓端到端、多种子或实物结论；配套的算法级数值边界见第 5.5.11 节与附录 A.9，其证据等级为算法级、单次复现、纯仿真。
