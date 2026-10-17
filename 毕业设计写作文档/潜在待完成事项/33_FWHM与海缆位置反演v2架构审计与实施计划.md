# FWHM 与海底电缆位置反演 v2：架构审计与实施计划

> 日期：2026-09-18  
> 阶段：第一阶段完成——只审计、定边界和制定计划，尚未重构或实现 v2。  
> 需求基线：[`32_FWHM与海缆位置反演v2任务Prompt.md`](32_FWHM与海缆位置反演v2任务Prompt.md)  
> 主作用域：`AUV-Master-Mag/`；最终验证范围包含主仓 ROS2、PVS/HoloOcean、协议桥和日志链。  
> 总约束：v1 源码、默认配置、入口和既有实验结果保持不变；v2 采用新增目录、入口、配置和结果目录；接口向后兼容。

## 1. 审计结论

当前仓库具备磁场仿真、信号滤波、峰值检测、局部主动探查、状态机、控制和 ROS 部署接口，但论文中描述的 FWHM 主链尚未在代码中闭合。

最关键的四项结论如下。

1. **状态机存在，但真实部署 Search 尚不完整。** `AUV-Master-Mag/src/auv_mag_tracking/mission_manager.py` 已有 `SEARCH_ZIGZAG → LOCK_ALIGN → TRACK_ACTIVE`，并含 `REACQUIRE_REGION` 和 `EMERGENCY_SURFACE`；然而主仓 ROS 节点调用的是轻量 `AuvMagTrackingPipeline`，没有消费该状态机，也没有按先验区域、初始位置不确定度和边界生成覆盖航点。因此“真实任务流程缺少 Search”在 ROS 全链路层面成立。
2. **当前埋深算法不是 FWHM。** `perception/burial_inversion.py` 使用按部署标定的幅值公式 `d_3d = K I_rms / B_track`，经横向门控后反演埋深，再用中位数和 IQR 融合。仓库内没有左右半高交点、空间半高全宽和基于宽度的深度估计器。
3. **已有 zig-zag 能产生激励，但不保证 FWHM 可辨识。** 子模块控制器含角度式局部横切和 probe burst；ROS 侧则按路线里程生成正弦横摆，默认横向幅度 1.5 m、波长 24 m。现有轨迹主要服务跟踪与探查，没有以“完整覆盖左右半高点、横切段近似单调且速度可估”为设计门槛。
4. **论文公式和仿真物理模型必须先做一致性验证。** 论文采用远场偶极包络 `B=C/(x²+z²)`，由此得到 `W=2z`。子模块采用有限直导线 Biot–Savart 模型，幅值随横向距离的函数形状一般不同。v2 不能直接把 `z=W/2` 当成所有模型的通用换算；应先确定剖面模型或标定形状系数，并把模型不一致计入 validity/confidence。

因此，v2 的目标不是替换一条公式，而是闭合下面的可验证任务链：

```text
先验走廊与边界
  → 规则覆盖航点
  → 稳健磁检测与迟滞锁定
  → 局部主动横切
  → B(x) 空间剖面
  → 峰值、左右半高点、FWHM 与有效性
  → 电缆中心/走向/垂直距离估计
  → 稳定跟踪与失锁重捕
```

## 2. 当前架构定位

### 2.1 状态机与主动探查

| 能力 | 现有位置 | 现状 | v2 处理 |
|---|---|---|---|
| 任务状态机 | `AUV-Master-Mag/src/auv_mag_tracking/mission_manager.py` | SEARCH、ALIGN、TRACK、区域重捕、应急；带磁/声迟滞和连续帧门控 | 复用状态语义和迟滞思想；新增独立 v2 状态机，不改 v1 |
| probe burst | `AUV-Master-Mag/src/auv_mag_tracking/probe_burst_manager.py` | IDLE、证据收集、回线、冷却 | 复用阶段语义；由 v2 cross-scan 生成明确的空间扫描段 |
| 子模块控制 | `AUV-Master-Mag/src/auv_mag_tracking/controller.py` | 自适应 zig-zag 角、磁过线腿、区域重捕 | 复用动力学边界与回退思想；不把其内部仿真状态直接耦合进 ROS |
| ROS 部署任务链 | `brain_linux/src/auv_control/auv_decision_ros/cable_tracking_node.py` | 轻量 pipeline + 正弦探查 + 制导限幅；未接内部 MissionManager | 后续新增 v2 ROS 节点/适配器和 launch，保留原节点为默认 v1 |

现有 SEARCH 主要是内部仿真中的行为状态。它没有形成一个可独立测试的接口：

```text
(prior path, initial uncertainty, boundary, width, spacing, speed)
    -> ordered search waypoints
```

这正是 v2 Search 的新增边界。

### 2.2 磁场与传感器模型

| 层 | 现有位置 | 可复用内容 |
|---|---|---|
| 电缆/海床/埋深真值 | `environment.py` | 路由、海床深度、埋深和悬空高度 |
| 磁场核心 | `math_utils.py::finite_wire_field_nT`、`environment.py::cable_field_gain_ned_nt` | 有限线段 Biot–Savart 场及批量计算 |
| 传感器 | `sensor_model.py` | 安装坐标、噪声、偏置漂移、非正交、饱和、脉冲和有色噪声 |
| 信号处理 | `perception/filters.py` | 中值、低通、带通、滑动 RMS |
| 部署磁质量 | `api/deployment_quality.py` | 强度、噪声底、SNR、置信度和幅值埋深接口 |

v2 优先复用这些生成和预处理能力，不另造物理仿真器。FWHM 的模型验证至少需要同时覆盖：

- 论文远场偶极解析剖面；
- 当前有限直导线仿真剖面；
- 带背景、DLIA/RMS、姿态和传感器误差后的处理链剖面；
- 后续台架轨迹与 TMR 数据回放剖面。

### 2.3 检测与峰值

`perception/peaks.py::PeakDetector` 已实现上升—峰区—下降状态、最小强度、迟滞、冷却、连续计数和峰值时空插值。`mission_manager.py` 也有磁强/声呐锁定与释放迟滞。这些可以复用设计思想，但当前尚缺：

- 明确定义的 detection score；
- 滑窗背景/噪声的稳健估计；
- 搜索态虚警率和检测时延统计；
- 检测输出与 Confirm 触发之间的稳定契约；
- 半峰水平、左右交点和 FWHM。

### 2.4 当前埋深反演

当前实现见 `perception/burial_inversion.py` 和 `docs/08_磁法埋深反演.md`：

```text
d_3d = K * I_rms / B_track
burial = sqrt(d_3d^2 - lateral^2) - altitude
```

其优势是实现简单、经过 case1 标定并有门控；限制是依赖电流、按部署常数 `K`、横向位置和处理链标定。`MagneticBurialCycleEstimator` 仍使用同一幅值定律，只是按 zig-zag 周期局部融合，并非 FWHM。

现有 `tools/zigzag_burial_sweep.py` 扫描 zig-zag 角度和埋深，但评价对象仍是幅值反演。它可以复用场景构造、记录和指标框架，不能作为“FWHM 已实现”的证据。

### 2.5 轨迹生成

存在三类相近但用途不同的轨迹：

1. `mission_manager.py` / `controller.py` 中的 SEARCH 与重捕行为；
2. `controller.py` 中按角度和证据状态生成的局部横切；
3. ROS `cable_guidance_limits.py::apply_zigzag_probe` 中按路线里程生成的正弦横向轨迹。

ROS 正弦轨迹的几何为固定幅度和波长，航向偏置由空间正弦的导数计算，并检查最大航向、最小转弯半径和横向速度。它适合连续跟踪扰动，但横向速度在周期内变化，并且默认半幅 1.5 m 可能不足以覆盖较大垂直间距对应的两个半高点。

v2 应明确区分：

- **Search coverage zig-zag**：沿先验走廊作规则覆盖；
- **Confirm cross-scan**：检测后在局部法向上产生单调、可量测的横切段；
- **Track dither**：跟踪时的小幅周期探查；
- **Reacquire scan**：失锁后围绕最后可信位置扩大的局部搜索。

### 2.6 部署接口和 ROS 全链路

`AUV-Master-Mag/src/auv_mag_tracking/api/pipeline.py::AuvMagTrackingPipeline` 是当前稳定部署门面，输入导航、磁测和可选声呐，输出 `CableTrackingOutput`。主仓 `cable_tracking_node.py` 订阅：

- `/auv/state/filtered`；
- `/auv/sensors/magnetic`；
- 任务、仲裁和传感器运行状态。

并发布 `/auv/control/setpoint`、`/auv/cable/tracking`、`/auv/cable/diagnostics` 以及横偏、进度、埋深、置信度等 typed topics。

当前电缆 XY 和横偏主要来自“导航位置投影到先验电缆图”，可由声呐或可选磁比值先验对齐辅助修正。它不是完全独立的磁位置反演。v2 的实验必须分别记录：

- prior projection；
- observation-only center estimate；
- fused cable estimate；
- truth（只用于离线评分）。

否则用先验投影结果评价同一先验会形成循环论证。

## 3. 论文方法与代码的对应关系

ThuThesis 第 2.3.5 节和第 3.3.3 节给出：

```text
B(x) = C / (x^2 + z^2)
W_x = 2z
z = 0.5 * v * |sin(alpha)| * delta_t_FWHM
burial = z - altitude
```

论文也已限定其前提：远场偶极近似、匀速直线横切、单峰和稳定包络；误差来自横切速度、交角、拟合与噪声。第 4.3.1 节进一步区分大范围 SEARCH 覆盖与 TRACK/REACQUIRE 局部主动横切。

v2 将保留这一可解释主线，但采用更稳健的工程实现：

1. 优先利用导航位姿把样本投影为局部法向空间坐标 `x`，直接构建 `B(x)`；时间式 `v sin(alpha) delta_t` 仅作为交叉校验或导航缺失时的降级方案。
2. 半峰以局部背景为基准：`B_half = B_base + 0.5 * (B_peak - B_base)`，避免非零背景导致绝对半峰偏移。
3. 用左右两侧线性插值求交点，不把采样点间距直接当宽度精度。
4. 引入模型形状系数 `z = k_shape W`。论文模型下 `k_shape=0.5`；当前仿真和实测数据必须验证或标定该系数，并报告适用域。
5. 将 FWHM 有效性与深度数值分离：没有完整左右交点、覆盖不足或模型残差过大时，输出无效原因，不给出伪精确埋深。

## 4. v2 目录和接口设计

后续只新增下列目录和文件；具体命名可在实现时微调，但职责不合并回 v1：

```text
AUV-Master-Mag/
├── src/auv_mag_tracking/v2/
│   ├── __init__.py
│   ├── types.py                 # 输入、状态、结果与原因码
│   ├── config.py                # v2 参数模型与校验
│   ├── search.py                # 先验走廊规则覆盖航点
│   ├── detection.py             # 滑窗分数、阈值、迟滞与峰值证据
│   ├── cross_scan.py            # Confirm 主动横切轨迹
│   ├── fwhm.py                  # B(x)、半峰交点、宽度和有效性
│   ├── cable_estimator.py       # 中心、走向、埋深与多次横切融合
│   ├── tracking.py              # 简单稳定的横偏/航向修正
│   ├── state_machine.py         # SEARCH/DETECT/CONFIRM/TRACK/REACQUIRE
│   ├── metrics.py               # v2 指标定义
│   └── pipeline.py              # 与 v1 输入输出兼容的 v2 门面
├── config/v2/default.yaml
├── tests/v2/
├── tools/run_v2_experiments.py
├── docs/v2/README.md
└── docs/v2/V1_V2_DIFFERENCES.md

brain_linux/src/auv_control/auv_decision_ros/
├── cable_tracking_v2_node.py    # 新节点；不改原 cable_tracking_node.py
└── ...新增的 v2 launch/config 适配文件
```

兼容策略：

- v2 pipeline 保持与 `AuvMagTrackingPipeline.step(...)` 相同的核心输入形态；
- 核心输出仍映射为 `CableTrackingOutput`；
- 新增信息先放入 `diagnostics`，包括 detection、scan phase、FWHM、validity、confidence 和失效原因；
- ROS v1 原节点、原 launch 和原 YAML 默认行为不变；
- v2 使用新节点、新参数命名空间和新结果目录显式启动；
- 不覆盖 `results/` 中任何历史产物。

建议新增但不强制旧消费者读取的 diagnostics 字段：

```text
algorithm_version
mission_phase
detection_score
detected
detection_threshold_on/off
cross_scan_id
cross_scan_x_min/max_m
fwhm_left_x_m
fwhm_right_x_m
fwhm_width_m
fwhm_vertical_separation_m
fwhm_burial_depth_m
fwhm_valid
fwhm_validity_score
fwhm_confidence
fwhm_reason_codes
cable_center_observed_xy_m
cable_heading_observed_deg
position_covariance_or_sigma
```

## 5. 模块设计

### 5.1 Prior-guided Search

采用规则的先验走廊覆盖，不引入 A*、采样规划或在线全局优化。

输入：

- 电缆先验折线；
- 初始 AUV 位置及横向不确定度；
- 搜索边界多边形；
- `search_width_m`、`lane_spacing_m`、`velocity_mps`；
- 最小转弯半径和边界裕量。

方法：

1. 沿先验折线构造有界走廊；搜索半宽至少覆盖先验误差和初始位置横向不确定度的配置分位数。
2. 在局部切向/法向坐标生成交替平行航线，并裁剪到搜索边界。
3. 以首航点距离和换向代价确定航线顺序，只做简单确定性排序。
4. lane spacing 由有效检测带宽及重叠裕度约束：`spacing <= lambda * W_eff`；将跟踪误差纳入保证覆盖宽度。
5. 检测成立后立即结束覆盖，输出当前位置和局部切向给 Confirm。

输出除航点外还应包含预计航程、预计时长、覆盖范围和不可行原因。评价采用跨随机种子的 detection probability、首次确认时间和检测前航程，并同时报告 false alarm rate。

### 5.2 Magnetic Detection

检测输入使用经过现有带通/DLIA/RMS 处理后的旋转不变包络，并保留原始时间戳和位置。

首版分数采用可解释的稳健标准化：

```text
baseline = rolling median(background window)
noise = 1.4826 * rolling MAD + epsilon
score = max(0, envelope - baseline) / noise
```

再叠加四个简单机制：

- `threshold_on > threshold_off` 的 Schmitt 迟滞；
- 连续 `N_on/N_off` 样本确认与释放；
- 峰值 prominence/最小宽度证据；
- 饱和、姿态突变、时间戳异常和采样不足门控。

输出 `score`、`detected`、背景、噪声、SNR、峰值证据和原因码。阈值只从训练/调参场景选择一次，再在独立种子上评价，不逐场景追真值调参。

### 5.3 Confirm 与主动横切

Confirm 的目标是取得完整且可解释的单峰 `B(x)`，而不是仅让航迹“看起来像 zig-zag”。

推荐首版使用**局部法向的分段直线三角/往返横切**：从中心一侧进入，以近似恒定横向速度跨过预计中心到另一侧，稳定后反向复核。相比连续正弦，它更容易得到单调空间坐标、稳定横向速度和完整左右半峰点。正弦轨迹保留为对照组。

扫描半幅由预期垂直间距或保守上界驱动：

```text
half_span >= coverage_factor * expected_half_width + navigation_margin
```

若当前默认 1.5 m 无法覆盖预测半高点，则逐级增大半幅，但始终受搜索边界、最小转弯半径、最大横向速度和任务超时约束。推荐档位而非连续优化，例如 `2 m → 4 m → 6 m`；具体数值由仿真可辨识性和载体动力学共同确定。

每条横切腿必须记录：

- 局部切向和法向；
- 每个样本的投影坐标 `x`、时间、包络、SNR、速度和姿态；
- 实际横切角和横向速度；
- 扫描覆盖范围、折返点和 scan id。

### 5.4 Explicit FWHM

首版算法流程：

1. 按 scan id 截取单次横切，按局部法向坐标排序，合并过密或重复位置样本。
2. 用边缘样本的稳健统计估计背景 `B_base`，做轻量中值/低通平滑；原始数据仍保留用于审计。
3. 检测单个主峰，求 prominence、SNR 和峰值位置；必要时用三点抛物线插值改善中心位置。
4. 计算背景修正半峰 `B_half`。
5. 从峰值向左右搜索首次可靠过线区间，并用线性插值得到 `x_left`、`x_right`。
6. 计算 `W=x_right-x_left`、中心 `x_center=(x_left+x_right)/2`。
7. 用已经验证的 `k_shape` 计算垂直间距 `z=k_shape W`，再用同步高度计求埋深。
8. 通过重复横切或 bootstrap/误差传播估算宽度和埋深不确定度。

validity 至少包含以下独立分量：

- 左右交点完整性；
- 峰值 prominence/SNR；
- 峰两侧覆盖裕量；
- 左右形状对称性；
- 单峰性和饱和检查；
- 横切角/横向速度稳定性；
- 导航投影质量；
- 解析剖面或稳健拟合残差；
- 重复横切一致性。

将这些分量映射到 `[0,1]` validity score，并保留逐项原因码。confidence 再结合样本数和估计方差形成，避免把“曲线形状有效”和“数值精度高”混成一个量。

### 5.5 更好的电缆位置反演

单次横切同时产生两个观测：

- 横向中心：优先用半高交点中点 `x_center`，峰值位置作为交叉校验；
- 垂直间距：由验证后的宽度模型得到。

把 `x_center` 从局部坐标变换回 NED/地图坐标，形成 observation-only cable point。多次有效横切点用带权直线或短折线拟合局部走向，权重来自位置方差和 validity。先验只用于确定初始切向、搜索走廊和消除方向二义性，不进入 observation-only 误差评分。

埋深融合采用分级策略：

1. FWHM 有效时，以其作为幅值尺度无关的主估计；
2. 已标定幅值反演保留为独立对照和退化备份；
3. 两者均有效时先做一致性门控，再按各自方差加权；明显冲突时降置信并触发复扫，不盲目平均；
4. 声呐有效时作为独立几何锚点；
5. 任何估计均携带来源、方差和适用条件。

首版不引入深度学习、粒子滤波或高维非线性联合优化。若解析 FWHM 在真实剖面上系统失配，可在后续阶段增加固定形状的稳健一维曲线拟合作为对照，但不能替代可审计的交点结果。

### 5.6 Track

输入为融合后的 signed cable offset、局部电缆切向、置信度和估计方差。输出保持简单：

```text
heading_correction = saturate(-K_heading * offset)
lateral_reference = saturate(-K_lateral * offset)
speed = schedule(confidence, curvature, cross-scan state)
```

复用 ROS `limit_guidance` 的最大航向变化、最大横向速度、最小转弯半径和速率限制。采用低通、死区、限幅和 anti-chatter 迟滞保证稳定。低置信度时减速并触发局部重捕；不得继续消费陈旧 FWHM 结果。

## 6. 分级实施计划与验收门槛

### P0：冻结基线与契约

- 记录 v1 入口、默认配置、现有测试与关键结果路径；
- 明确 `NavigationInput`、`MagneticInput`、`SonarInput`、`CableTrackingOutput` 的兼容表；
- 建立 v2 独立结果 manifest，记录 git commit、配置、seed、环境和产物哈希。

验收：v1 工作树和历史结果没有被 v2 修改；v1 smoke 与现有测试保持原结论。

### P1：解析模型和 FWHM 单元闭环

- 实现纯函数式 `B(x)` FWHM 提取器；
- 用论文解析剖面验证 `W=2z`；
- 注入背景、噪声、非均匀采样、截断、双峰和离群值；
- 给出 validity 和原因码。

验收：无噪声解析剖面误差由插值容差限定；缺任一半峰交点时必须无效；结果对幅值整体缩放保持不变。

### P2：物理模型一致性与形状系数

- 从当前有限线段 Biot–Savart 环境生成空间横截面；
- 扫描垂直间距、线段长度、弯率、传感器姿态和处理链；
- 比较论文模型、直导线模型和仿真剖面的 FWHM 比值；
- 确定 `k_shape` 是固定、分场景标定，还是需模型门控。

验收：形成误差曲线和适用域；未验证区域不输出“无参”高置信深度。

### P3：Search 与 Detection

- 生成先验走廊覆盖航点；
- 实现稳健滑窗检测和迟滞；
- 加入大初始误差、无电缆和干扰源场景；
- 记录检测时间、航程、虚警和漏检。

验收：相同输入和 seed 输出确定；航点全部位于边界内；无目标场景能统计 false alarm；搜索终止条件可解释。

### P4：Confirm cross-scan 与位置估计

- 实现法向分段直线往返横切；
- 自适应扫描幅度只用离散档位和边界约束；
- 输出完整 `B(x)`、FWHM、中心点和走向；
- 与现有正弦/角度 zig-zag 做同条件对照。

验收：有效输出必须覆盖两侧半峰；中心位置误差、宽度误差和有效率分别报告；轨迹满足动力学和边界约束。

### P5：Track 与状态机闭环

- 串联 SEARCH → DETECT → CONFIRM → TRACK → REACQUIRE；
- 实现简单横偏/航向修正和置信度降级；
- 验证失锁、复扫和回线不产生状态颤振。

验收：状态转换均有条件、迟滞、超时和原因码；低质量 FWHM 不进入控制；跟踪 RMSE 和 q95 均报告。

### P6：ROS2 新链路

- 新增 v2 node、配置和 launch；
- 使用现有 topic 和 `CableTrackingOutput` 兼容适配；
- diagnostics 增加搜索、检测、横切和 FWHM 字段；
- bag/replay 验证时序、坐标系和消息陈旧度。

验收：v1 launch 完全不变；v2 可单独启动；缺磁、缺导航、陈旧数据和仲裁 hold 均按明确状态降级。

### P7：PVS/HoloOcean 全链路与论文回填

- PVS/HoloOcean → bridge → ROS2 v2 → setpoint → 日志/报告闭环；
- 固定随机种子执行正式矩阵；
- 只在证据完成后更新 ThuThesis 的“已实现/已验证”表述和实验章。

验收：在线估计不读取真值；原始输入、状态、估计、控制和真值评分可通过时间戳追溯；论文结论严格限定证据等级。

## 7. 实验矩阵

### 7.1 必做四类场景

| Case | 主变量 | 建议水平 | 主要指标 |
|---|---|---|---|
| A 大初始位置误差 | 横向偏差、航向误差、先验平移/旋转误差 | 小/中/大，多个 seed | detection probability/time/distance、越界率 |
| B 不同埋深 | 埋深和离底高度 | 覆盖现有 1.0/1.5/2.0 m，并加适用边界 | FWHM 有效率、bias、MAE、q90、coverage |
| C 不同噪声 | 白噪声、有色噪声、漂移、脉冲、饱和 | 工业级到退化档 | 虚警、漏检、交点丢失率、置信度校准 |
| D 不同搜索间距 | `spacing/W_eff`、跟踪误差 | 含重叠、临界、欠覆盖 | 检测概率、时间、航程、保证覆盖率 |

### 7.2 必要消融

- 空间坐标 FWHM vs 时间换算 FWHM；
- 背景修正半峰 vs 绝对峰值一半；
- 正弦 probe vs 分段直线/三角 cross-scan；
- 固定 1.5 m 幅度 vs 分档扩幅；
- FWHM-only、幅值-only、带一致性门控的融合；
- 仅先验投影、observation-only、融合位置；
- 有/无迟滞、有/无重复横切一致性门控。

### 7.3 指标定义

- `detection_probability`：在搜索边界/时限内完成稳定检测的运行占比；
- `detection_time_s`：从 Search 开始到首次稳定检测的时间，未检测运行按删失样本单独报告；
- `travelled_distance_m`：检测前路径积分；
- `false_alarm_rate`：无目标或干扰场景中的错误确认次数/时间或每公里次数；
- `fwhm_valid_rate`：完成 Confirm 的扫描中有效左右交点占比；
- `fwhm_width_error_m`：估计宽度对当前物理模型真值宽度的误差；
- `vertical/burial_error_m`：模型换算后的 bias、MAE、RMSE、q90；
- `cable_center_error_m`：observation-only 中心点到真值电缆的垂距；
- `heading_error_deg`：多次横切拟合切向与真值走向的误差；
- `tracking_error_m`：TRACK 段横偏 RMSE、mean、q95、max；
- `confidence_calibration`：置信区间覆盖率或按 confidence 分箱的实际误差。

所有均值同时给出样本数、seed 数和离散度；不能只报告成功案例。

## 8. 验证层级

| 层级 | 输入与执行 | 能回答的问题 | 不能外推的结论 |
|---|---|---|---|
| L0 解析单元 | 人工 `B(x)` | 交点、插值、失效门控是否正确 | 真实场适用性 |
| L1 子模块仿真 | `AUV-Master-Mag` 物理/传感器模型 | 搜索、检测、FWHM 和控制的算法闭环 | ROS/协议时序与实机水动力 |
| L2 ROS replay | rosbag/合成 topics | 接口、时戳、坐标、状态和降级 | 实时闭环任务成功率 |
| L3 PVS/HoloOcean 闭环 | 仿真器—桥—ROS—控制回路 | 全链路路径和动力学可行性 | 海试精度 |
| L4 台架/实测 | TMR、电流、高度/位置基准 | 形状系数和实测误差 | 未覆盖海况的泛化能力 |

## 9. 风险与明确边界

1. **物理模型风险**：有限直导线、无限直导线和远场偶极子的 FWHM—深度系数不同。P2 未完成前，FWHM 只能输出宽度和模型条件下的候选深度。
2. **扫描幅度风险**：幅度太小缺半峰点，太大则增加航程、偏离巡检走廊并触发动力学限制。采用分档扩幅和明确失败返回。
3. **背景风险**：总场或残余背景使“峰值一半”产生偏差，必须用背景修正 prominence。
4. **速度/角度风险**：时间域公式对速度和交角误差敏感，优先用导航投影的空间坐标。
5. **先验循环风险**：用先验投影生成估计，再以同一先验评分会夸大性能。必须保留 observation-only 通道。
6. **幅值反演风险**：现有 case1 的低 MAE来自按部署 `K` 标定和横向门控，不能当作跨场景无参证据。
7. **ROS 集成风险**：当前部署 pipeline 与内部仿真 perception/FSM 是两条不同链。v2 必须通过新适配器显式闭合，不能仅在子模块 demo 中宣称全链路完成。
8. **论文证据风险**：当前论文描述的是目标主链，代码尚未实现 FWHM。实现和正式实验完成前，应把相关性能表述限定为方法设计或解析性质。

## 10. 完成定义

v2 只有同时满足以下条件才算完成：

- v1 源码、默认入口和既有结果未被修改；
- Search 能由先验、不确定度和边界生成确定性航点；
- Detection 输出连续分数、二值状态、迟滞和原因码；
- Confirm 输出可审计的 `B(x)` 和受动力学约束的横切轨迹；
- FWHM 显式输出峰、背景半峰、左右交点、宽度、validity、confidence 和失效原因；
- 深度换算的物理模型/形状系数有独立验证，不把 `W/2` 无条件泛化；
- observation-only 电缆中心与先验投影分开记录；
- Track 对低置信度和陈旧估计稳定降级；
- Cases A–D 与必要消融由固定 seed、可追溯配置运行；
- 子模块、ROS replay 和至少一条 PVS/HoloOcean 全链路 smoke 通过；
- README、配置、v1/v2 差异、运行命令和结果 manifest 齐全；
- 论文只引用达到对应证据层级的结论。

## 11. 本阶段未执行事项

按照需求“第一步只分析和计划”，本阶段没有：

- 修改 `AUV-Master-Mag` v1 代码或配置；
- 修改 ROS v1 节点或 launch；
- 创建 v2 源代码骨架；
- 运行或覆盖现有实验；
- 改写 ThuThesis 的算法结论。

下一实施阶段从 P0/P1 开始，并以新增文件方式完成接口契约、解析 FWHM 单元和模型一致性验证。
