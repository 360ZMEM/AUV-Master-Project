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
