# UA-MPC P-2 / H4 独立对照与归因记录

- 日期：2026-08-07
- 范围：P-2 `max_iter` 独立对照；H4 有横向机动场景的 lateral RMSE 归因
- 数据层级：P-2 为 PVS + Mock AMD 闭环、3 场景 × 3 seed；H4 为确定性解耦运动学单次基准
- 数据保真：均非真机/海试结论；H4 不替代 PVS 六自由度闭环

## 1. P-2：max_iter 是否是高 fallback 的主因

### 1.1 设计

保持 A1 默认 UA 参数、场景、seed、时长与 forward-sonar 能力链不变，仅扫描 IPOPT `max_iter={100,200,400}`：

- 场景：baseline、dvl_dropout_60、combined_stress
- seed：0/1/2
- 时长：60 s
- 总计：27 run，27/27 `status=ok`
- `controller_type=MPC`，无 H6 能力门控污染
- 默认配置未修改；实验 override 默认仍为 100

为支持独立对照，优化器新增最小参数透传：

- `algorithm/auv_mpc_controller.py`：构造参数 `max_iter=100`
- `brain_linux/src/auv_controller/auv_controller/mpc_controller.py`：从实验 override 取 `max_iter`

### 1.2 结果

| max_iter | debug frames | fallback_rate | Solve_Succeeded | 成功帧 solve mean(ms) | 初始 fallback-setpoint 当前失败 wall(ms) | xy_rmse(m) | safety violation |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 1027 | 0.699 | 0.301 | 13.49 | 88.41 | 1.538 | 0 |
| 200 | 1024 | 0.685 | 0.315 | 15.00 | 192.21 | 1.532 | 0 |
| 400 | 761 | 0.594 | 0.406 | 17.04 | 372.20 | 1.552 | 0 |

各档 fallback reason 均为 IPOPT `Maximum_Iterations_Exceeded`。按场景看，200 档不保证单调改善：combined_stress 的 fallback 从 0.657 上升到 0.736。400 档才在三场景下降至约 0.57–0.61，但失败 wall time 约 372 ms，远超 50 ms 预算；有效 debug/control 帧由 1027 降至 761（约少 26%），表明求解阻塞已吞噬控制更新。

### 1.3 归因

1. `max_iter=100` 偏紧是次要因素，不是高 fallback 的主因。
2. 100→200 仅改善 1.4 个百分点，却使失败时间翻倍；400 仍有 59.4% fallback，并破坏控制更新频率。
3. 不修改默认 `max_iter=100`。后续应优先检查初值/热启动连续性、约束可行性或容差结构。
4. `FALLBACK_LAST_OUTPUT` 当前复用上一成功 `ControlOutput`，其 `solve_time_ms` 是陈旧值。普通全帧 solve mean 会低估失败耗时；本记录只用成功帧 IPOPT 时间和 `FALLBACK_SETPOINT` 当前失败 wall time。
5. 400 档采样帧减少本身是阻塞效应，但也使其 fallback 比例与 100/200 档不是完全等采样率比较，不作统计显著性声称。

### 1.4 证据

- `log/thesis_sweep/20260807_101744_p2_maxiter_ablation_3seed/`
- `results/control_aggregates/20260807_101744_p2_maxiter_ablation_3seed/`
- smoke：`log/thesis_sweep/20260807_101512_p2_maxiter200_smoke/`

## 2. H4：有横向机动时的机制精度归因

### 2.1 设计

此前 P-1/P-2 的参考近直线，lateral RMSE 为毫米级且全回退时反而更小，不能用于精度归因。新增 `tools/mpc_uampc_maneuver_ablation.py`，复用已有公平参考、运动学 plant 与 LOS fallback 契约：

- 路径：可跟踪长波 S 弯、180° hairpin
- `confidence=0.3`
- `max_iter=100`
- 变体：A0 baseline、A1 UA default、A2 w/o sigmoid、A3 alpha=1.0
- 求解失败时显式计 fallback 并使用 LOS；不将 fallback 伪装成 MPC 成功

### 2.2 结果

| 场景 / 指标 | A0 baseline | A1 UA default | A2 w/o sigmoid | A3 alpha=1.0 |
|---|---:|---:|---:|---:|
| S 长波 lateral RMSE (m) | 0.0852 | **0.0754** | 0.0852 | **0.0740** |
| S 长波固定时长进度 | 76.5% | 85.8% | 76.5% | 86.6% |
| Hairpin 有效路径段 RMSE (m) | 0.102 | 0.100 | 0.102 | **0.097** |
| Hairpin 末端越界 RMSE (m) | 7.480 | 7.484 | 7.480 | 7.563 |
| solve success（两场景） | 100% | 100% | 100% | 100% |

Hairpin 全时段 RMSE 约 3.21–3.26 m。轨迹检查证明主要原因是约 52 s 完成路径后仍继续航行，而不是 180° 转弯段跟踪失败。因此指标拆为首次到达 99% 路径前的 active-path RMSE 与完成后的 terminal overshoot。

### 2.3 归因

1. **sigmoid 控制代价降权是精度侧主贡献。** S 长波中，A1 相对 A0 改善约 11.6%，固定时长进度增加 9.3 个百分点；关闭 sigmoid 的 A2 几乎逐位退化回 A0。
2. **alpha=1.0 只有边际增益。** A3 相对 A1 在 S 长波再改善约 1.9%，hairpin 有效段约 3%，但 terminal overshoot 略恶化。
3. **默认 `confidence_alpha=1.5` 保持不变。** 当前边际收益不足以支持修改默认参数，尤其 H4 只是确定性单次运动学基准。
4. **大曲率 hairpin 上 UA 机制没有显著拉开。** 四者有效路径段均约 0.10 m，主要限制来自共同参考/运动学与终端任务设计。
5. H4 全部 solve success，只回答有横向激励时的精度贡献，不能解释或替代 PVS 中的 `Maximum_Iterations_Exceeded`。

### 2.4 证据

- `results/control/uampc_maneuver_ablation/20260807_110001/metrics.csv`
- `results/control/uampc_maneuver_ablation/20260807_110001/report.md`
- `results/control/uampc_maneuver_ablation/20260807_110001/s_turn_long_wave_trajectories.png`
- `results/control/uampc_maneuver_ablation/20260807_110001/hairpin_180deg_trajectories.png`

## 3. 正文与 rating 回填契约

正文应写：

- P-2 证明单纯放宽 max_iter 不是工程修复，默认维持 100。
- P-1 + H4 共同证明 sigmoid 控制代价降权既是可解性主贡献，也是可跟踪 S 弯中的精度主贡献。
- alpha=1.0 的收益为边际，暂不修改默认值。
- Hairpin 全时段大 RMSE 是 terminal stop 缺失，不是转弯段横向跟踪失败。

正文不得写：

- “max_iter=400 优化了实时性能”。
- “H4 证明 PVS 六自由度或真机 lateral 精度提升”。
- “alpha=1.0 已被确定为新默认最优值”。
- 将 `FALLBACK_LAST_OUTPUT.solve_time_ms` 当作当前失败帧耗时。

当前 `05_experiments_and_discussion.md`、`05new_experiments_and_discussion.md` 与 `rating.md` 正由另一写作流程同步生成。本记录作为冲突期间的权威实验事实源；待写作流程稳定后，将本节内容回填至新正文与 rating，避免抢写覆盖。

## 4. 验证

- P-2 结果完整性：27 行、27/27 ok
- H4 结果完整性：2 场景 × 4 变体 = 8 行
- `auv_controller` 安装态 override 检查：`max_iter=200` 生效
- 控制器包测试：3 passed
- Python 编译：优化器、wrapper、H4 工具均通过
- 已知旧测试边界：`tests/test_mpc_solver.py` 有 5 个既有失败，原因是测试使用 `z=-5`，与当前 `min_z_cmd=0` NED 约束冲突；另 32 项通过，失败与本次 max_iter 透传无关
