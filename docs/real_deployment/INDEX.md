# 实物部署 — 五阶段路线图（详尽 SOP 体系）

> 本目录是 **实物部署** 的"详尽路线图"，与 [user-guide/08_real_hardware_sop.md](../user-guide/08_real_hardware_sop.md)（"6 步速记表"）互补。当你**真正要把 Jetson 接入 AUV 内部网**时，从本 INDEX 开始照单执行。

---

## 文档结构

| # | 文件 | 你在做什么时读它 |
|---|------|------------------|
| 0 | [00_principles.md](00_principles.md) | 上电之前 — 理解三大战术 + 三大架构智慧 + 本仓库的三条铁律 |
| 1 | [01_stage1_link_audit.md](01_stage1_link_audit.md) | **S1 通信审计**（不插电机电缆） |
| 2 | [02_stage2_static_actuator.md](02_stage2_static_actuator.md) | **S2 静态执行器自检**（上架不入水） |
| 3 | [03_stage3_shadow_navigation.md](03_stage3_shadow_navigation.md) | **S3 影子导航**（入水但 Jetson 不接管） |
| 4 | [04_stage4_closed_loop_single.md](04_stage4_closed_loop_single.md) | **S4 单回路闭环**（恒定 setpoint 验证） |
| 5 | [05_stage5_full_autonomy.md](05_stage5_full_autonomy.md) | **S5 全自主巡检**（行为树 + ros2 bag） |
| 6 | [06_kill_switch.md](06_kill_switch.md) | 任何时候 — 急停操作与"双保险"分工 |
| 7 | [07_param_diff_sim_vs_real.md](07_param_diff_sim_vs_real.md) | 阶段切换 — 参数差异速查（仿真 vs 真机） |
| 8 | [08_cable_inspection_io_contract.md](08_cable_inspection_io_contract.md) | 电缆巡检部署时的输入/输出契约与磁外参要求 |
| 9 | [09_dlt1278_digital_twin_outputs.md](09_dlt1278_digital_twin_outputs.md) | DLT1278 风格数字孪生产物、评分字段和导出物 |
| 10 | [10_sim_vs_real_link_and_wrapper_map.md](10_sim_vs_real_link_and_wrapper_map.md) | 仿真 / 真机链路区别、配置分层、fan-out 用法与 wrapper 接入建议 |
| 11 | [11_sensor_wrapper_ip_coordination.md](11_sensor_wrapper_ip_coordination.md) | Jetson 侧多个真实传感器 wrapper 的 IP/网段规划、主仓 override 规则与故障定位顺序 |

---

## 五阶段串图

```
S0 静态自检 (00_static_preflight.sh)
       │  colcon build + pytest + 协议自检（无网络无硬件）
       ▼
S1 通信审计 (01_link_audit.sh)
       │  $AUV 上行字节序/scale/p95；$CKTH 下行 0xEF 握手
       ▼
S2 静态执行器自检 (02_static_actuator.sh)        ── 上架不入水
       │  5 路通道极性 + 死区；填回 physics_config.yaml
       ▼
S3 影子导航 (03_shadow_navigation.sh)             ── 入水
       │  passive_mode:=true；人驾，Jetson 算但不发；RMSE 阈值
       ▼
S4 单回路闭环 (04_closed_loop_single.sh)          ── Jetson 接管
       │  Setpoint 恒值；超调/稳态误差/响应时间
       ▼
S5 全自主巡检 (05_full_autonomy.sh)               ── 行为树释放
          ros2 bag record -a；DLT+1278 巡检剖面对接
```

每阶段的 `passed.flag` 落于 `log/real_deployment/{ts}_{stage}_{target}/passed.flag`，下阶段会软警告检查。

---

## 三种 target

| target | 用途 | 所需硬件 | 额外开关 |
|--------|------|----------|----------|
| `mock` | 默认；本机回环 + sim_holoocean 假 AMD | 无 | — |
| `vxsim` | VxWorks 仿真器（本机另一进程） | 无 | 需要先在另一终端拉起 [csd_vx6.8_vxsim](../../csd_vx6.8_vxsim/) 中的 vxsim |
| `real` | 真实 AUV PC104 | 有 | **必须**追加 `--i-have-physical-auv` |

通用参数：`--target {mock,vxsim,real}` `--duration N` `--dry-run` `--i-have-physical-auv`。

---

## 最小启动命令（mock，零硬件）

```bash
cd /home/auv_user/auv_ws/AUV-Master-Project

# 0. 静态自检
bash scripts/real_deployment/00_static_preflight.sh

# 1..5. 走完完整五阶段（每阶段 mock + 30s）
for stage in 01_link_audit 02_static_actuator 03_shadow_navigation \
             04_closed_loop_single 05_full_autonomy; do
  bash scripts/real_deployment/${stage}.sh --target mock --duration 30
done

# 任何时候按 Ctrl+C 或并行启动急停
bash scripts/real_deployment/kill_switch.sh --target mock
```

干跑（不真起 mock AMD）：把 `--target mock` 换成 `--target mock --dry-run`。

---

## 与既有文档的关系

- **明线速记**: [user-guide/08_real_hardware_sop.md](../user-guide/08_real_hardware_sop.md) — 6 步表格，5 分钟读完
- **本目录（详尽路线图）**: 9 篇 SOP，每篇 < 200 行，逐阶段照单执行
- **过程日志**: [docs/experiment/real_deployment/](../experiment/real_deployment/) — 每次跑出来的命令实录与发现
- **配置参数地图**: [user-guide/09_config_reference.md](../user-guide/09_config_reference.md)

---

## 三条铁律（本会话固化）

1. **完全向后兼容**：所有新 shell/工具/文档都不动主线 launch/yaml/start_*.sh，仅新增正交。
2. **静态验证优先**：每个 shell 都支持 `--dry-run`；提交前先全 mock dry-run 一遍。
3. **mock AMD 默认**：`--target` 默认 `mock`；`real` 必须加 `--i-have-physical-auv` 才能跑。

---

## 标准依据

- [自主式水下航行器设计方案 2021.5.28](../../标准文档/自主式水下航行器设计方案2021.5.28.md) — AUV 物理 spec
- [软件通信协议](../../标准文档/软件通信协议.md) — `$CKTH` 72B 下行 / `$AUV` 145B 上行
- [VxWorks 最新协议](../../标准文档/VxWorks最新协议.md) — PC104 端解析约束
- DLT+1278—2025 海底电力电缆运行规程 — 在 `标准文档/` PDF（巡检任务工程依据）
