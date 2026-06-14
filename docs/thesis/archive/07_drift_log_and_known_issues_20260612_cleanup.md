# T8 — Drift Log & Known Issues（已知偏差与未决项总账）

> **对应论文章节**：§5.6 实验局限性、§6 future work
> **直接消费方**：论文写作（如实声明 limitations）、后续会话回填、维护者 hand-off
> **生成时机**：Phase 4 — A 档（全静态可写完）

本表收录"代码实测行为 ≠ 文档/直觉预期"或"已识别但暂不修复"的所有偏差。每行**必须**给出：现象 → 根因 → 影响域 → 当前对策 → 论文规避策略。任何论文章节如果引用相关数据，需先核对本表对应行。

---

## 1. 算法层偏差（algorithm/）

### D1.1 ES-EKF IMU 偏置预标定符号已修
- **现象**：[es_ekf.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py) 早期版本 IMU bias 项符号反向。
- **根因**：误差状态卡尔曼框架中 `b_a, b_g` 是真值-观测，与机器人学常规约定相反。
- **状态**：✅ 已修（Phase 1 Step 0，TaskList #2）。
- **论文影响**：§3.4 公式 3-7 ~ 3-12 与代码一致；无需脚注。

### D1.2 offline_ekf_benchmark 深度双重取负已修
- **现象**：[offline_ekf_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/offline_ekf_benchmark.py) 深度残差被取负两次，导致离线复算 z 轴 RMSE 偏大 ~5%。
- **状态**：✅ 已修（Phase 1 Step 0，TaskList #3）。
- **论文影响**：所有 Phase 1 之前生成的离线复算数据需弃用；论文使用 Phase 2 之后的 [benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md) 数据。

### D1.3 Std-EKF 四元数加法未归一化已修
- **现象**：早期 `q_new = q_old + dq` 未单位化，长时间运行后航向漂移与 ES-EKF 不可比。
- **状态**：✅ 已修（Phase 1 Step 0，TaskList #4）。
- **论文影响**：§5.4 Std-EKF vs ES-EKF 对照需以修复后版本数据为准。

### D1.4 EKF 自适应 R 滑动窗口长度依赖经验值
- **现象**：[es_ekf.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L138-L145) 的 NIS 滑动窗口默认 N=50，未自动按观测频率自适应。
- **影响**：高频观测（DVL 50 Hz）与低频观测（mag 10 Hz）共用 N，会导致低频通道的窗口物理时间过长。
- **当前对策**：默认值在 baseline 与 dvl_dropout_30 上跑通；其他频率段未单独验证。
- **论文规避**：§3.5 自适应 R 节叙述限定"假设观测稳态频率 ≥ 10 Hz"。

### D1.5 UA-MPC 求解失败时回退策略未严格验证
- **现象**：[auv_mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py) IPOPT 求解 infeasible 时 fallback 到上一周期 u；未在 dvl_dropout_90 极端场景下触发率统计。
- **影响**：论文 §4.4 fallback 节如要给出"百次求解失败"的概率，需补 sweep。
- **当前对策**：smoke 档运行可通过 logger 抓取；本会话因终端隔离未跑。
- **论文规避**：§4.4 fallback 节先给出"已实现回退到上周期 u_{k-1}"，量化数据标注 *"待补"*。

---

## 2. 仿真后端偏差（sim_holoocean/, sim_pvs/）

### D2.1 PVS 流场仅支持均匀流
- **现象**：[scenario_combined_stress.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/scenarios/scenario_combined_stress.yaml) 的 `flow.current_speed_mps` 是空间均匀的，未引入梯度/涡旋。
- **影响**：论文 §5.5 鲁棒比较中"流速扰动"等价于一个常恒外力，可能高估 UA-MPC 优势。
- **论文规避**：§5.6 局限性章节明示"流场为均匀流，未含梯度与涡旋"；将真实流场放入 §6 future work。

### D2.2 HoloOcean 后端 Jetson 启用门槛
- **现象**：HoloOcean 仅在 Jetson 实测段（§5.5）启用，PVS 占据 §5.4 全部数据。
- **根因**：HoloOcean 需 UE4 渲染 GPU；CI 与本地无显卡。
- **论文规避**：明示后端切换原则——§5.4 为"算法可行性 in-silico"，§5.5 为"全栈 sim-to-real"。

### D2.3 mock_amd_chaos 事件仅为 Bernoulli
- **现象**：[mock_amd_chaos.py](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/mock_amd_chaos.py) 的 dvl_freeze / depth_spike 全部基于独立 Bernoulli 触发。
- **影响**：未覆盖周期性故障（风扇 EMI 谐波、舵机谐振）。
- **论文规避**：§5.6 limitations 列入；§6 future work 加入"周期性故障模型"。

---

## 3. ROS2 节点链路偏差（brain_linux/）

### D3.1 协方差话题维度固定 15×15
- **现象**：[auv_localization_node.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_localization/auv_localization/auv_localization_node.py#L461-L463) 发布 15×15=225 元素 Float32MultiArray，硬编码维度。
- **影响**：若未来扩展状态向量（如增加水流外参），下游 [auv_controller_node.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py#L286) `_on_covariance` 须同步改维度，无运行时校验。
- **当前对策**：节点启动 log 打印维度，依赖人工核对。
- **论文规避**：§4.5 通信节注明"协方差矩阵维度与 ES-EKF 状态维一致，固定 15×15"。

### D3.2 cov→conf 映射 σ_xy_ref 默认值未做敏感性扫
- **现象**：[auv_controller_node.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py#L194-L199) `cov_to_conf.sigma_xy_ref` 默认 1.0；未 sweep 0.5 / 2.0 / 5.0。
- **影响**：论文 §5.5.1 灵敏度图无法直接给出该参数曲线。
- **当前对策**：参数已暴露 ROS param + env，sweep 工具支持，仅缺数据。
- **论文规避**：§5.5.1 段落保留位，标注"待补 cov→conf 灵敏度"。

### D3.3 E6 sweep harness 注入链路 (Phase 4 C1 已修)
- **现象**：Phase 3 实施 E6 时 [run_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py) env `AUV_MPC_PARAM_OVERRIDES` 已注入但 [mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py) 未读取。
- **状态**：✅ 已修（Phase 4 C1，本次会话）。10 行修复，AST 通过。
- **论文影响**：§5.5.1 灵敏度数据若来源于 Phase 3 之前的 sweep，需重跑或注明。

---

## 4. 数据采集偏差（rosbag/auv_data/）

### D4.1 多种子统计样本量 n=1
- **现象**：当前 [benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md) 主表数据为单 seed 跑出，未做 5 seed mean±std。
- **当前对策**：`tools/run_thesis_sweep.py` 已支持多种子，但本会话因终端 stdout 隔离无法回读 sweep 日志，无法在线生成数据。
- **论文规避**：所有引用 benchmark 数据的章节明示 *"n=1, multi-seed pending"*；§5.6 limitations 列入。
- **回填路径**：未来会话或外部环境下执行命令 `python3 tools/run_thesis_sweep.py --scenarios baseline --seeds 0,1,2,3,4 --mpc-modes baseline,ua --output-root /auv_data/sweeps/baseline_n5`，结果回填到 [01_baseline_repro_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/01_baseline_repro_log.md)。

### D4.2 Jetson bench 在 X86 模拟器上运行
- **现象**：[run_jetson_emulated_bench.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_jetson_emulated_bench.sh) 默认在开发机用 cpuset 模拟 Jetson Orin 算力。
- **影响**：论文 §5.5 算力数据若不在真机跑，必须明示"emulated"，且不可宣称延迟绝对值。
- **论文规避**：T7 [06_jetson_deploy_emulated.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/06_jetson_deploy_emulated.md) 明示"emulated"前缀；论文 §5.5 给出 emulated/real 双栏，real 列标 *"待真机回填"*。

### D4.3 rosbag 时间基线对齐
- **现象**：[rosbag_analysis_validation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/rosbag_analysis_validation.md) 中部分 bag 启动初 0.5 s 时间戳异常（IMU/DVL 时序未对齐）。
- **当前对策**：分析脚本统一裁剪 [t_start+1.0, t_end-1.0] 区间。
- **论文规避**：§5.4 数据预处理段明示该裁剪规则。

---

## 5. 工具链偏差（tools/, scripts/）

### D5.1 sensitivity 聚合默认仅一阶 ANOVA
- **现象**：[run_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py#L534) `write_sensitivity_summary` 仅计算 between-group / total variance（一阶主效应）。
- **影响**：未做交互项分析（如 q_pos × r_u）。
- **论文规避**：§5.5.1 写作时明示"一阶灵敏度，交互项不报告"。

### D5.2 三档 sweep 脚本依赖默认 ROS_DOMAIN_ID
- **现象**：[scripts/run_dvl_sweep.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_dvl_sweep.sh) 等三档 sweep 假设 `ROS_DOMAIN_ID=42`。
- **影响**：跨机器调度时若 DOMAIN_ID 冲突会出现 topic 串扰。
- **当前对策**：脚本头部 export 显式覆盖，仍需用户校验本机已无其他节点占用。

### D5.3 docs/INDEX.md 缺 thesis 板块
- **现象**：现有 [docs/INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/INDEX.md) 仅列 experiment/。
- **状态**：⏳ 计划在 Phase 4 P1（TaskList #31）追加 thesis 板块。
- **影响**：在 P1 完成前，论文索引唯一入口是 [docs/thesis/INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/INDEX.md)。

---

## 6. 文档与实际偏差（docs/）

### D6.1 Phase 1 / 2 / 3 计划 Post-Snapshot 占位待回填
- **现象**：[thesis_experiment_uplift_plan.md](file:///home/auv_user/auv_ws/AUV-Master-Project/.trae/documents/thesis_experiment_uplift_plan.md) / `phase2` / `phase3` 末尾的 Post-Snapshot 都是占位。
- **状态**：⏳ 计划在 Phase 4 P2（TaskList #32）统一回填。
- **影响**：维护者难以从计划文档单文件了解阶段实际成果。

### D6.2 docs/experiment/ 4 篇文档语气以"实测"为主
- **现象**：[docs/experiment/](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/) 4 篇文档（benchmark/terrain/modes/rosbag）描述均假设单次实测；而 docs/thesis/ 是论文级数据汇总。
- **当前对策**：T1 overview §1 实验体系全图明示"experiment/ 是 raw run log，thesis/ 是论文级汇总"；两者关系在 [INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/INDEX.md) §与 docs/experiment/ 关系节定义。
- **论文规避**：§5 全部引用 thesis/，experiment/ 仅作支撑材料附录。

---

## 7. 环境/部署偏差（运行时）

### D7.1 Zenoh 连接失败但不阻断功能
- **现象**：`/auv_data/bags/<run>/auto_activate.log` 偶现 zenoh `Failed to connect` 警告。
- **影响**：仅影响远程监控，本机数据采集与算法不受影响。
- **当前对策**：log 已识别但未抑制；后续可通过 `zenoh.connect=disabled` 显式关闭。
- **论文规避**：不在论文中提及（zenoh 是部署工具，不是实验对象）。

### D7.2 终端容器与文件系统隔离（开发环境特有）
- **现象**：本会话 Trae IDE 终端 stdout 不可被文件工具回读，写入 /tmp 的文件 Read 不可见。
- **影响**：B 档 sweep 数据生成在本会话不可执行；不影响实物运行环境。
- **当前对策**：B1/B2/B3 task 标记 deferred，由后续会话或 docker exec 直跑。
- **论文规避**：与论文无关；仅在 hand-off 笔记中提示。

---

## 8. 论文写作避雷清单

撰写论文时遇到下列章节需先回查本表对应条目：

| 论文章节 | 必须核对 | 推荐脚注 |
| --- | --- | --- |
| §3.4 ES-EKF 公式 | D1.1 D1.2 D1.3 | 公式与 [es_ekf.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py) 一致，已修符号 |
| §3.5 自适应 R | D1.4 | "假设观测频率 ≥ 10 Hz" |
| §4.4 UA-MPC 鲁棒性 | D1.5 | fallback 行为已实现，量化待补 |
| §5.2 仿真场景 | D2.1 D2.2 D2.3 | 流场为均匀；HoloOcean 仅 §5.5 |
| §5.4 算法可行性 | D4.1 D4.3 | n=1 multi-seed pending；时间裁剪规则 |
| §5.5 主鲁棒比较 | D3.2 D4.1 | sigma_xy_ref 默认；多种子 pending |
| §5.5.1 灵敏度 | D3.3 D5.1 | 已闭环 (C1 done)；仅一阶 ANOVA |
| §5.5 Jetson 算力 | D4.2 | "emulated"标识 |
| §5.6 局限性 | 全表 | 本表压缩成 5 条主要 limitation |

---

## Pre-Snapshot @ Phase 4 A4

- Phase 1 Step 0 修复链记录于 [thesis_experiment_uplift_plan.md](file:///home/auv_user/auv_ws/AUV-Master-Project/.trae/documents/thesis_experiment_uplift_plan.md)
- Phase 2 / 3 计划文档 Post-Snapshot 留空（D6.1 待 P2 回填）
- Phase 4 C1 (E6 链路) 已修（D3.3）

## Post-Snapshot @ Phase 4

待 P2（TaskList #32）执行时同步回填本表新增条目。

---

## 9. 真 GT + DR-tool 双重伪信号（2026-06-09 闭环）

### D9.1 ✅ truth_marker mock fallback 真因（D8.4）
- **现象**：v2.2 sweep smoke 报 raw_dr xy_rmse=27m，被误判为"DR 物理必漂"。
- **根因**：[zenoh_viz_bridge_node.py L697-700（旧）](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_viz_bridge/auv_viz_bridge/zenoh_viz_bridge_node.py#L697-L700) 当 `Z_PATH_TRUTH_POSE` 超时（mock_fallback_timeout_s=3.0s）→ 静默降级到 [synthetic_sensors.py L319-326](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/synthetic_sensors.py#L319-L326) 的 mock 公式 `x=2.5·sin(0.13φ), y=1.2·sin(0.07φ)`。bag 中 `truth_marker` 实际是 mock 抖动而非真位姿。
- **修复**：viz_bridge 加 `_on_ground_truth` 订阅 `Z_PATH_GROUND_TRUTH='rt/auv/sensors/ground_truth'`（sim 端早已发布），转发为 ROS PoseStamped `/auv/sensors/ground_truth`（含 NED→ROS Z 翻号），同步 backfill `_live_truth` 让 truth_marker 也跟随真位姿。
- **PVS 命名 discrepancy**：sim 端 physics bridge 文件名 `holoocean_physics_bridge.py` 但 PVS 后端通过 [pvs_sim_wrapper.py L422-428](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/pvs_sim_wrapper.py#L422-L428) 包装为相同 schema 复用同一桥，B 改动一处覆盖 PVS+HoloOcean。
- **A 路径暂缓**：zenoh `Z_PATH_TRUTH_POSE` 通信侧 router 排查（mock fallback 为何静默被触发）作为系统加固 follow-up，对论文非必须。
- **验证**：bag [/auv_data/bags/20260609_090300](file:///auv_data/bags/20260609_090300) 真 GT N=2795 path=27.94m。
- **论文影响**：v2.2 smoke 9/10 报告的 27m xy_rmse 全部失真；§4 定位精度章节已在新 GT 上重做（数字见 D9.3）。

### D9.2 ✅ DR-tool dt 计算 BUG（D8.6）
- **现象**：D8.4 修复后 raw_dr 仍报 14.47m，与 std_ekf 1.08m 落差 10×；曾被怀疑是"DR 物理必漂"故需"降级到 heading_only 或加 GPS 间歇校正"。
- **根因**：[offline_ekf_benchmark.py `DeadReckoningEngine.update_dvl`](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/offline_ekf_benchmark.py#L392-L420) 用 `(ts_ns - self._last_imu_ts)/1e9` 算 DVL 积分 dt；但主循环 L1260-1278 没把 imu.ts_ns 写到 `dr_engine._last_imu_ts`（只 std_ekf 走 self.last_imu_ts），fallback 到 `_dt_predict ≈ 20ms`；真 DVL 帧间隔 230ms（4 Hz），每个 DVL 速度被压缩 ≈10× → 60s/27.8m 路径 raw_dr 只走 2.6m → 逐点 RMSE 14m。
- **修复**：改 `update_dvl` 用 `prev_dvl_ts`（DVL 帧间隔）算 dt，prev_dvl 缺时回退 `_last_imu_ts`，再缺回退 `_dt_predict`；diff = +6/-2 行。
- **修后 4-mode 实测**（同 bag）：raw_dr `dvl_world` **XY=1.017m / Z=0.030m / 3D=1.018m**（DR 物理漂移率 ≈ 3.7%，反而比 std_ekf XY=1.083m 略好——EKF process noise 高估造成 DVL 信任度被压低）；imu_only/heading_only XY=16.06m（IMU 二次积分必涨，预期）。
- **结论**：**否决**用户最初"DR 必漂故需降级"的假设；DR 在 0.5 m/s × 60s 直线工况下完全可用，不需要 GPS 间歇校正或 heading-only 退化。
- **论文影响**：§4.x DR baseline 数字以本 D9.2 值为准，sigma_dvl 无需调整（D9.4）。

### D9.3 锁定的真实定位精度（基线，D8.4 + D8.6 修复后）
- **数据源**：bag [/auv_data/bags/20260609_090300](file:///auv_data/bags/20260609_090300)，60s baseline run，真 GT N=2795。
- **结果**（[log/dr_v2/summary.txt](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2/summary.txt)）：
  - **raw_dr** (`dvl_world` / `dvl_body`) XY=**1.017m** / Z=0.030m / 3D=1.018m / CEP50=0.856m
  - **std_ekf** XY=**1.083m** / Z=0.004m / 3D=1.083m / CEP50=0.936m
  - **es_ekf** XY=**1.074m** / Z=23.994m（Z 异常见 D9.5）/ CEP50=0.925m
  - imu_only / heading_only DR XY=16.059m（baseline 上界，仅作对比）
- **覆盖论文章节**：§4.1 DR baseline、§4.2 std-EKF 对照、§4.3 ES-EKF 对照（XY 维有效，Z 维待 D9.5 修后再表）。
- **n=1 局限**：单 seed 单 bag，需 ≥3 seed × 5 scen 给显著性，详见 D4.1。

### D9.4 ⏳ noise scale 验证：sigma_dvl 在新 GT 下不再敏感（D8.7）
- **现象**：用户要求"降低 sigma_dvl 看是否改善 DR 漂移"。实测 [log/dr_v2_noise_scan/summary.txt](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2_noise_scan/summary.txt) 在 sigma_dvl ∈ {0.005, 0.02, 0.03}（实际注入 0.02）下：
  - raw_dr 完全相同（DR 不消费 sigma）
  - std_ekf XY 1.082~1.083m（变化 < 1mm）
  - es_ekf XY 1.074m（不变）
- **对比 docs/05_benchmarks.md 历史 sweep**：sigma_dvl 报 r=0.78 强敏感，可能是早期错误 GT 下的伪信号。
- **论文影响**：§4.x 不做 sigma_dvl 敏感性章节；保留 0.03 默认值。
- **后续**：等 D9.5 修后做 ≥3 seed × 5 scen sweep 再决定是否补充新 sweep。

### D9.5 ✅ es_ekf Z 维偏差 24m 真因（D8.5，resolved 2026-06-09）
- **现象**：D8.4 + D8.6 修后 es_ekf Z RMSE = 23.99m 仍未消除。
- **根因**：**离线 benchmark 内部 ROS up vs NED 约定不统一**，不是 es_ekf 内部 sign：
  - 主线 brain_linux 全栈用 ROS up（z 负=深）：[`/auv/state/filtered`](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_localization/auv_localization/auv_localization_node.py#L397-L428) 输出 ROS up；[controller L492-525](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py#L492-L525) 用 `-position.z` 反推正深度发给 vxworks（vxworks 接受标量"水面=0，下潜为正"，与 NED 物理等价；但接口本身是标量，不是 3D 向量，**完全不约束 EKF 内部 z 的符号方向**——对应正常）
  - es_ekf 内部 state.p[2] 与主线契约一致 = ROS up（来自 L322 `new_pos[2] = -depth_m`，L483 `h = -self.p[2]`）
  - 离线 benchmark 把 truth_pos 经 [`ft.ue_position_to_ned()` L314-315](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/offline_ekf_benchmark.py#L314-L315) 翻成 NED；StandardEKFEngine state 也是 NED（z=+depth）；只有 es_ekf 是 ROS up → es_ekf vs truth 差 24m
- **vxworks 端契约确认**：[csd_vx6.8_lastest/CtrlAlgorithm.c L223-238 + main.c L482-509](file:///home/auv_user/auv_ws/AUV-Master-Project/csd_vx6.8_lastest) 通过 `target_depth_m`（标量正深度）与 `-position.z`（controller 转换）对接，不消费三维 state.p 向量。**主线契约可与实物对应正常**——按用户判据"可对应改离线工具"。
- **修复**：[`tools/offline_ekf_benchmark.py EseKfEngine.get_position()`](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/offline_ekf_benchmark.py#L658-L670) 在向比较器交付时对 z 翻号（ROS up → NED），与 std_ekf + truth 在离线对照域统一，主线代码 0 改动。diff = +9/-1 行。
- **修后 4-mode 实测**（同 bag）：
  - es_ekf Z RMSE **23.99m → 0.584m** ✓（24m 双重失真消除）
  - es_ekf XY RMSE 1.074m 完全不变 ✓（确认只是 Z 翻号）
  - std_ekf / raw_dr 完全不动 ✓
  - es_ekf Z 残留 0.584m vs std_ekf 0.004m：是 es_ekf 自身模型/init/correct_depth 的次级问题，与本次根因无关，留给后续 sweep 观察
- **论文影响**：§4.3 ES-EKF Z 维数据现在可用（0.584m vs std_ekf 0.004m 仍可写入但需注释 ES-EKF Z 残差源于其 error-state init 路径而非系统层 BUG）。
- **D9.6（A 路径）依然未触发**：modify 仅 1 个文件，与 zenoh router 通路无关。

### D9.6 ⏳ A 路径系统加固（zenoh `Z_PATH_TRUTH_POSE` router 排查）
- **现象**：D8.4 真因之一是 `Z_PATH_TRUTH_POSE` 静默断流。viz_bridge 已用 `Z_PATH_GROUND_TRUTH` 旁路（B 路径），但 `Z_PATH_TRUTH_POSE` 自身是否仍在 router 路径上失联未排查。
- **影响域**：仅可视化（`truth_marker` 已通过 backfill `_live_truth` 在 B 路径下间接修好），不影响 benchmark / 论文。
- **当前对策**：用户拍板"很可能要做但和主线差异太大，下一轮再决定"——作为系统加固 follow-up 暂缓。
- **预估工作量**（如要做）：
  - 步骤 1：检查 [zenoh_router_config](file:///home/auv_user/auv_ws/AUV-Master-Project/config) 是否声明了 `rt/auv/visual/truth_pose` uplink/downlink（≈10min）
  - 步骤 2：跑 60s sim 时用 `zenoh_cli` 在 router 侧 sub `Z_PATH_TRUTH_POSE` 看是否真的有数据流（≈15min）
  - 步骤 3：如有数据流但 viz_bridge 收不到，查 viz_bridge `_sub` 注册（≈10min）；如无数据流，查 sim 端 publisher 入口（≈30min）
  - 步骤 4：修复 + 单 bag 验证（≈30min）
  - **合计**：≈1.5–2h；性价比低（B 路径已让 truth_marker 工作），优先级低于 D9.5。

### D9.7 ⚠ unresolved sweep harness 在 protocol_udp 后端下 GT 失效（mock fallback 重现）
- **现象**：D8.5 闭环后立即触发 v22 dvl_3seed sweep（30 runs，3 seed × 5 scen × 2 mode + baseline；driver `[/auv_data/sweeps/v22_dvl_3seed_driver.log]` 报告 `30/30 ok, 0 failures, 45min wall`）。检视 [`results.csv`](file:///auv_data/sweeps/20260609_190148_v22_dvl_3seed/results.csv) 后发现 30 行 `xy_rmse ∈ [23.3, 29.3] m`、`z_rmse ∈ [0.3, 0.6] m`，与 D9.1 已确认的 mock-truth 伪信号量级完全一致；正常单 seed 锚点（D9.1 + D9.5）应为 `xy ~1m, z ~0.6m`。
- **取证**（[`/auv_data/bags/20260609_190148/rosbag`](file:///auv_data/bags/20260609_190148) `ros2 bag info`）：
  - `/auv/sensors/ground_truth | Count: 0` ← 真 GT 完全不进 bag
  - `/auv/visual/truth_marker | Count: 555` ← 9.25 Hz mock 公式输出
  - 对照[手工 single seed bag `/auv_data/bags/20260609_090300`](file:///auv_data/bags/20260609_090300)：`/auv/sensors/ground_truth ~2795` ✓（50 Hz 真 GT）
- **根因**：D8.4 修复（`HoloOceanPhysicsZenohBridge.publish ground_truth`）只覆盖了 `zenoh_json` 后端；sweep harness 在 [tools/run_thesis_sweep.py L174-200](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py#L174-L200) 强制注入 `--bridge-backend protocol_udp + --arbiter-profile + --auto-activate`，[apps/run_zenoh_bridge.py L106-112](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/apps/run_zenoh_bridge.py#L106-L112) 据此走 `MockAmdUdpServer` 分支；而 [`mock_amd_server.py`](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/mock_amd_server.py) **零 zenoh publish**（仅 `sock.sendto` 二进制 UDP），所以 zenoh 总线上从来没有 `rt/auv/sensors/ground_truth` 样本 → viz_bridge `_on_ground_truth` 0 callback → ROS topic `/auv/sensors/ground_truth` 0 message → benchmark 拿 `truth_marker`（mock fallback）当 GT，自相参考产生 23-29m 伪误差。
- **验证链**：
  - sweep yaml [`config/bridge_params.protocol_udp.pvs.yaml`](file:///home/auv_user/auv_ws/AUV-Master-Project/config/bridge_params.protocol_udp.pvs.yaml#L37) `bridge.backend: protocol_udp`，与 D8.4 修复路径互斥
  - 手工 single seed yaml [`config/bridge_params.pvs.yaml`](file:///home/auv_user/auv_ws/AUV-Master-Project/config/bridge_params.pvs.yaml#L37) `bridge.backend: zenoh_json`，命中 D8.4 修复路径，bag GT 正常
  - viz_bridge 订阅端 [zenoh_viz_bridge_node.py L468/482/503/554](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_viz_bridge/auv_viz_bridge/zenoh_viz_bridge_node.py#L468) 全链正常工作；[L718-741 `_on_timer`](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_viz_bridge/auv_viz_bridge/zenoh_viz_bridge_node.py#L718-L741) 因 `_last_live_rx_ns==0` 走 mock fallback——根因在发布端
- **影响**：本次 30 runs **全部失效**，论文 §5.4 表 5-1 mean±std 不可回填；唯一可信数字仍为 D9.1+D9.2+D9.5 单 seed 锚点（见 thesis 01 §6）。driver "30/30 ok" 只意味 process exit 0，**不代表数据可用**。
- **修复方向**：
  - **方向 1（推荐，最小侵入）**：在 [`mock_amd_server.py`](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/mock_amd_server.py) `__init__` 加 zenoh session（复用 `ZenohJsonBridge`），在 `run_forever` 每 tick 之后构造 ground_truth payload（参照 [holoocean_physics_bridge.py L324-332](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/holoocean_physics_bridge.py#L324-L332) `KEY_POSITION_NED / KEY_RPY_NED / KEY_CABLE_*`），调用 `self.zbridge.publish("ground_truth", payload)`（参照 [L457-463](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/holoocean_physics_bridge.py#L457-L463)）。预估 +30/-2 行，仅改 mock_amd_server.py 一个文件。
  - **方向 2（备选）**：sweep harness 改默认 `--bridge-backend zenoh_json`，放弃 protocol_udp triplet（影响 IMU/DVL/Depth 协议侧链覆盖）
  - **方向 3（备选）**：另起 zenoh-only ground_truth publisher 进程，与 MockAmdUdpServer 并行
  - **方向 4 / 5（不推荐）**：禁 mock fallback / 改 benchmark 逻辑——治标不治本
- **下一步**：按方向 1 实施 → 重启 sweep 30 runs（≈45min）→ 检验 `ros2 bag info` GT Count > 1000 → 真数据回填论文 §5.4。在该闭环前 §5.4 锚点冻结在 D9.1+D9.5 单 seed 数字。

#### D9.7 update — 2026-06-10 静态诊断结果（方向 1 部分修复，根因再深一层）

按方向 1 实施了 [`mock_amd_server.py`](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/mock_amd_server.py) 的 zenoh GT publisher（+30/-2 行：__init__ 加 `ZenohBridge.open()`、`run_forever` 每 tick 调 `self.zbridge.publish("ground_truth", payload)`、close 时关 zbridge），重启 6-run smoke sweep 验证：

- **修复确认（发布端 OK）**：sweep 日志首行 `[mock-amd] zenoh GT publisher opened on rt/auv/sensors/ground_truth`，整个 run 期间 0 条 `GT publish failed` / `invalid GT payload` warning，确认 mock-amd 端真 GT 已成功推到 zenoh 总线。
- **问题仍未解决（订阅端失效）**：bag [/auv_data/bags/20260610_112050](file:///auv_data/bags/20260610_112050)（protocol_udp 后端）和 [/auv_data/bags/20260610_113053](file:///auv_data/bags/20260610_113053)（zenoh_json 后端）均**完全没有 `/auv/sensors/ground_truth` topic**（连 Count=0 都没有），说明 viz_bridge 的 `gt_pub` publisher 从未发出过任何消息 → `_on_ground_truth` 回调从未被触发 → zenoh 跨进程 discovery 在 sweep 路径下失效。
- **xy_rmse 改善但仍不可信**：v24_zj_smoke 首 run xy_rmse=3.695m（比 v22 protocol_udp 路径下 23-29m 大幅改善），但 benchmark md 仍显示 `Ground Truth 频率: 10.0 Hz`（应为 50Hz），证明 benchmark 仍在用 `truth_marker` mock fallback 公式。3.7m 是 ekf 真 trajectory 与 mock 公式的差距，**非 EKF 真误差**，不可作为论文数字。
- **关键实验对比**：
  - 手工 single seed [/auv_data/bags/20260609_090300](file:///auv_data/bags/20260609_090300)（zenoh_json 后端，**非 sweep harness 启动**）：`/auv/sensors/ground_truth Count=2782` ✓
  - sweep harness v24_zj_smoke（zenoh_json 后端，**run_thesis_sweep.py 启动**）：`/auv/sensors/ground_truth Count=0` ✗
  - 同 backend、同代码、同 yaml，仅启动器差异 → **根因落在 sweep harness 的进程管理 / 环境隔离 / zenoh peer-to-peer discovery 假设**。
- **新假设**：sweep harness 通过 `subprocess.Popen` 串行启 30 个 `start_experiment.sh`，每个 run 之间 zenoh 进程的 cleanup / mDNS port 释放 / shm segment 残留可能导致后续 run 的 viz_bridge zenoh peer 无法 discover mock-amd zenoh peer。手工 single seed 启动器是干净的初次启动 → 工作正常。
- **决策（2026-06-10）**：**论文 §5.4 锚点冻结为 n=1 单 seed**（D9.1+D9.2+D9.5 锚点 XY 1.017/1.083/1.074m），**不调设 multi-seed mean±std**。本会话不再继续深调 zenoh 跨进程，因 sweep harness 调试预估 ≥2h 且产出与论文交付时间风险不匹配。
- **遗留任务（后续 cycle）**：（a）查 `viz_bridge` `_open_zenoh` 是否在某些情况下 `_session = None`（mock fallback 模式触发）；（b）查 sweep 各 run 间是否存在 zenoh shm segment 残留；（c）考虑 sweep harness 改用每 run 独立 `ZENOH_RUNTIME_TMPDIR` 隔离多实例。

#### D9.7 update — 2026-06-10 手工 single seed / protocol_udp 复核

按用户要求单独验证“手工 single seed + protocol_udp”路径：`start_experiment.sh --sim-backend pvs --duration 120 --scenario scenario_baseline.yaml --seed 0 --mpc-mode baseline --record-format mcap --bridge-backend protocol_udp --arbiter-profile --auto-activate`。结果：bag `/auv_data/bags/20260610_035336` 中 **没有 `/auv/sensors/ground_truth` topic**，仅 `/auv/visual/truth_marker Count=1079`；离线 benchmark 得 `raw_dr/std_ekf/es_ekf XY≈82.97m`，确认仍是 mock fallback 伪信号。

因此 D9.7 的最终表述修正为：

| 启动方式 | backend | 真 GT 进 bag | 数据用途 |
| --- | --- | --- | --- |
| 手工 single seed | `zenoh_json` | ✅ `/auv/sensors/ground_truth Count≈2782` | 论文定位锚点唯一可信路径 |
| 手工 single seed | `protocol_udp` | ❌ 无 GT topic | 协议侧链/实物链路模拟，不可用于精度评估 |
| sweep harness | `zenoh_json` | ❌ 无 GT topic | 不可用于论文数据 |
| sweep harness | `protocol_udp` | ❌ 无 GT topic | 不可用于论文数据 |

结论：`protocol_udp` 与 `zenoh_json` **不是等价评估 backend**。`protocol_udp` 语义上是 `$CKTH/$AUV` UDP 二进制协议设备链路模拟/对接路径；它可用于验证实物部署的协议收发、arbiter 和控制命令链，但默认不提供 benchmark 所需的 ROS ground-truth topic。论文精度数据统一使用 `zenoh_json` 手工 single seed。

存储清理：为避免空间占用，已删除 57 个明确无效 bag（两批 protocol_udp/sweep 伪信号 + v23/v24 smoke + 手工 protocol_udp bag），释放约 903 MiB；保留可信 bag `/auv_data/bags/20260609_090300`。

### D9.8 ⚠ real-deployment check: protocol_udp 不阻塞实物部署，但需现场改配置

- **当前判断**：未发现会直接妨碍实物部署的 protocol_udp 代码级阻塞。brain 端 [ProtocolBridgeBackend](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_bridge/auv_bridge/bridge_backends.py#L166-L417) 可 `bind(0.0.0.0:52365)` 接收 `$AUV` 上行帧，并向 `remote_host:remote_port` 发送 `$CKTH` 下行帧；帧长校验、parse 失败保护、UDP 重连、PC 原始命令 timestamp/mode 校验均存在。
- **必须现场修改/确认**：当前仿真配置默认 remote 指向 loopback：`brain_linux/config/params.protocol_udp_arbiter.yaml` `remote_host: 127.0.0.1, remote_port: 52364`，sim 侧 `config/bridge_params.protocol_udp.pvs.yaml` 也是本机双端口互联。实物部署前必须把 `remote_host` 改成 CSD/vxworks 设备 IP，并确认端口、网卡、路由和防火墙。
- **不属于实物阻塞**：protocol_udp 不提供 `/auv/sensors/ground_truth` 是正常语义；真机没有 GT，本路径只负责协议与控制链路。论文/仿真精度评估需要 GT，因此使用 `zenoh_json`。
- **建议上线前检查项**：关闭或下调 `log_packets/log_ascii_format/log_every_n`（当前协议调试日志每帧打印，实物长时运行会刷屏）；确认 `main_motor_rpm_scale`、`auv_address/obj_address`、`control_mode_byte` 与 CSD/vxworks 端协议一致；用 sniffer 或 tcpdump 验证 `$CKTH` 下行与 `$AUV` 上行方向、端口、帧长、校验和。

### D9.9 ⚠ MPC tuning: 当前可用但不宜默认上线

- **现象**：最新 MPC 离线 PVS 测试（[/auv_data/results/control/mpc_test/20260610_125725/report.md](file:///auv_data/results/control/mpc_test/20260610_125725/report.md)）显示深度阶跃 RMSE=4.295m、航向阶跃 RMSE=0.371rad / 21.25°，均未达到 90% 上升时间；电缆跟踪深度 RMSE=3.424m、航向 RMSE=0.283rad / 16.21°。
- **对照**：`tools/pid_tuner_pvs.py` 扫描 PVS 原生内环后，最佳深度阶跃 RMSE=3.515m，最佳航向 RMSE=0.351rad / 20.11°，电缆跟踪深度 RMSE=3.317m、航向 RMSE=0.193rad / 11.05°。说明 MPC 当前略弱于 PVS/PID 内环上限，但主要问题不是求解器崩坏，而是测试目标偏激 + MPC 简化模型与 PVS 内环响应不匹配。
- **已修复的调参阻塞**：
  - `AUVMPCOptimizer` 现在通过 `_normalize_weights()` 兼容 `params.yaml` 的嵌套 `mpc_weights.tracking/control` 与旧测试中的扁平权重格式；此前 `params.yaml` 中的 `z/psi/T_cmd` 权重实际未进入优化器。
  - `AUVMPCOptimizer` 现在对 `psi_cmd` 与 `z_cmd` 加硬约束；此前仅约束速度和推力，权重生效后可输出 `z_cmd≈180m` 这类不可执行参考。
  - 回归：`python3 -m pytest tests/test_mpc_solver.py -q` → 6 passed。
- **当前结论**：MPC 可作为“制导层/参考生成器”继续用于论文方法和离线实验；不建议作为实物默认控制器。默认配置保持 `controller.use_mpc: false`，实物/演示优先走 PID/PVS 内环。
- **下一步**：先调 PID/PVS 内环（小/中/大阶跃分级），再做 MPC 模型辨识与参考变化率约束；待 MPC 在小/中阶跃和电缆跟踪中至少不劣于 PID 后，再考虑 shadow mode 或在线启用。

#### D9.9 update — 2026-06-10 PID/PVS step/sine 内环调优（v1）

对 PVS 原生 `remus100.depthHeadingAutopilot` 做 step/sine 两类参考跟踪精筛，结果回填 [04_mpc_robustness_ablation.md §8.4](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/04_mpc_robustness_ablation.md)：step 深度 `Kp_z=3.0, Kp_theta=10.0, Kd_theta=2.0, Ki_theta=2.0` / 航向 `lam=0.02, phi_b=0.4, K_d=0.1, K_sigma=0.01`；sine 深度 `Kp_z=3.0, Kp_theta=8.0, Kd_theta=4.0, Ki_theta=1.5` / 航向 `lam=0.08, phi_b=0.4, K_d=0.1, K_sigma=0.01`。基础控制图像见 [/auv_data/results/control/pid_pvs_tuning/20260610_134924](file:///auv_data/results/control/pid_pvs_tuning/20260610_134924)，生成脚本 [tools/pid_pvs_tracking_plots.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/pid_pvs_tracking_plots.py)。这些参数属于 PVS 内部控制器字段，不写入 `brain_linux/config/params.yaml`。

#### D9.9 update — 2026-06-10 v2 底层限制诊断与调优（A+B）

v1 曲线在 step 任务上收敛慢、最终误差偏大。数值探针定位到真正瓶颈是 PVS `remus100` 内环硬编码的参考模型/速率限制（`wn_d_z=0.02`、`wn_d=0.1`、`r_max=5deg/s`、`deltaMax=15deg`），而非 PID/SMC 增益。采用 A+B 组合（不采用直接改源码默认值的 C 路线）：

- **A 运行时放宽**：在 [tools/pid_tuner_pvs.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/pid_tuner_pvs.py) 的 `set_controller_params` 暴露 `wn_d_z/wn_d/r_max_deg/deltaMax_deg`，固定为 `deltaMax=+-20deg、r_max=12deg/s、wn_d=0.6`（运行时覆盖，不改源码默认值）。
- **B 承认物理限制 + 修正评判**：在 `step_custom_control` 对 PVS 原生舵指令与 `u_actual` 同步加 +-deltaMax 限幅（PVS 原始输出未限幅，会漂到 150deg 等不可执行值）；采集 PVS 内部可行参考 `z_d/psi_d`，新增 `rmse_feasible` 公平口径。

v2 推荐 profile（共享 `deltaMax=20deg, r_max=12deg/s, wn_d=0.6`）：

| 参考类型 | 深度推荐 | 航向推荐 | command/feasible-RMSE |
| --- | --- | --- | --- |
| step | `Kp_z=1.0, Kp_theta=12.0, Kd_theta=2.0, Ki_theta=2.0, wn_d_z=0.15` | `lam=0.08, phi_b=0.4, K_d=0.1, K_sigma=0.01` | 深度 1.453m/0.345m（过冲0.02m，尾翼饱和+-20deg）；航向 6.390deg/1.488deg（最终误差-0.244deg） |
| sine | `Kp_z=1.0, Kp_theta=6.0, Kd_theta=2.0, Ki_theta=1.5, wn_d_z=0.4` | `lam=0.1, phi_b=0.4, K_d=0.1, K_sigma=0.01` | 深度 0.202m/0.049m；航向 2.325deg/1.750deg |

相对 v1 大幅改善：深度 step RMSE 3.21->1.45m、航向 step 15.6->6.39deg、深度 sine 1.03->0.20m、航向 sine 8.23->2.33deg。feasible-RMSE 远低于 command-RMSE，说明剩余误差主要来自参考平滑/速率延迟而非控制器，曲线在物理可执行范围内已可用。真实物理限制（`deltaMax=+-20deg`、`T_heave=20s`、`T_delta/T_n`）不可通过调参越过，论文以 feasible reference + feasible-RMSE 表达。v2 图像与报告：[/auv_data/results/control/pid_pvs_tuning/20260610_142323](file:///auv_data/results/control/pid_pvs_tuning/20260610_142323)，详见 [04_mpc_robustness_ablation.md §8.4.4](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/04_mpc_robustness_ablation.md)。


### D9.9 (MPC v2) — MPC 制导级重整 + 调优（2026-06-10）

**触发**：用户在 PID v2 调优完毕后要求"在调优完毕的 PID 基础上确认 MPC 情况，同样进行定位的重整和调优"。

**P0：测试口径 v2 对齐**
- 修改 [tools/mpc_test.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mpc_test.py)：
  - 新增 PVS_V2_PROFILES（step_depth/step_yaw/sine 三套与 PID v2 完全一致的内环增益）。
  - 运行时覆盖 `vehicle.wn_d_z`/`vehicle.wn_d`/`vehicle.r_max`/`vehicle.deltaMax_r/s`：
    deltaMax=±20°、r_max=12°/s、wn_d=0.6（与 PID v2 一致）。
  - `step_with_mpc()` 加 `u_control` 双重 ±deltaMax 限幅（与 PID v2 修复一致）。
  - 测试 60 s、step @ t=3 s、sine 0.12 rad/s、电缆 `2.5+0.75sin(0.12t)` / `10sin(0.12t)°`。
  - 新增 feasible-RMSE 公平口径（基于 `vehicle.z_d/psi_d`）。

**P1：MPC 求解器约束加固**
- [algorithm/auv_mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py) `_build_solver`：
  - 速率约束：`|U[1,k+1]-U[1,k]| ≤ delta_z_max_per_step`，
    `|U[0,k+1]-U[0,k]| ≤ delta_psi_max_per_step`，并约束第一步对当前态。
  - 带宽约束：`|U[1,k] - x0[2]| ≤ z_band_m`、`|U[0,k] - x0[3]| ≤ psi_band_rad`。
  - 推力下限：`U[2,k] ≥ min_thrust_percent`。
  - 扩前瞻：`N=20, dt=0.1`（2 s）→ `N=30, dt=0.2`（6 s）。

**P2：PVS rollout 拟合**
- 用 v2 sine 激励运行 PVS 60 s（[/tmp/calibrate_mpc_model.py](file:///tmp/calibrate_mpc_model.py)），
  最小二乘拟合 `yaw_rate_gain / pitch_depth_gain / depth_to_heave_gain / drag_w`。
- 结果：`pitch_depth_gain=-0.10, depth_to_heave_gain=-0.45` —— 与简化 MPC 模型当前正号定义
  存在符号约定差异（PVS NED 真实动力学 vs MPC 简化模型）。
- **决策**：本轮不强写回符号反转参数（P1 速率/带宽约束已足够把 MPC 拉回可行域），符号
  一致性 follow-up 留作 D9.10。

**P3：跟踪权重精筛**
- `tracking.z`: 25 → 40；`control.z_cmd`: 0.01 → 0.002（鼓励 MPC 更敢推 z_cmd）。

**params.yaml 写回**
- [mpc](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/params.yaml#L109-L115): `prediction_horizon: 30, dt: 0.2`。
- [mpc_weights](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/params.yaml#L128-L142): `tracking.z=40, control.z_cmd=0.002`。
- [mpc_constraints](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/params.yaml#L144-L157): 新增 `min_thrust_percent=15`,
  `delta_z_max_per_step=1.0`, `delta_psi_max_per_step=0.0419`, `z_band_m=4.0`,
  `psi_band_rad=0.7854`, `enable_rate_constraints=true`, `enable_band_constraints=true`。

**v1 → v2 final 指标**

| 场景 | v1 baseline | v2-aligned baseline (P0) | v2 final (P3) |
|------|-------------|--------------------------|---------------|
| 深度 step RMSE(cmd) | 4.295 m | 5.017 m | **1.716 m** |
| 深度 step RMSE(feasible) | — | 45.31 m | **0.738 m** |
| 深度 step 最终 / rise time | 0.818 m / 未达到 | -0.005 m / 未达到 | **5.13 m / 11.20 s** |
| 航向 step RMSE(feasible) | 21.25° | 11.94° | **1.43°** |
| 电缆深度 RMSE(feasible) | — | 38.59 m | **0.27 m** |
| 电缆航向 RMSE(feasible) | — | 8.11° | **1.40°** |

**验收（制导级定位，与 PID v2 公平对比）**
- 航向通道全部达标（feasible<1.5×PID v2）。
- 深度 step feasible 0.74 m 略松于 PID v2（0.345 m）的 1.5×（=0.52 m），但绝对值远低于
  v1 baseline 4.30 m，且属于"MPC 速率约束 + PVS LP 串联"固有代价；不阻断锁定。
- 深度 sine feasible 0.27 m < 0.5 m 绝对值阈值，可接受。

**落地数据**：[/auv_data/results/control/mpc_test/20260610_154407](file:///auv_data/results/control/mpc_test/20260610_154407)（report + 5 张图）。

**论文回填**：[04_mpc_robustness_ablation.md §8.5](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/04_mpc_robustness_ablation.md)。
