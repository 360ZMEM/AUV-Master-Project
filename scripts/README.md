# scripts 目录说明与阶段性整理记录

日期: 2026-07-12

本文说明 `scripts/` 下脚本的类别、用途、命令契约和阶段性归档结果。整理依据包括:

- 文档引用检索: `docs/**/*.md`、`.trae/documents/**/*.md`、`README.md`
- Git 最近修改记录: `git log -1 -- <script>`
- 当前实物上下文: `docs/real_deployment/debug-pc104-telnet-udp.md`

## 当前 PC104 实物上下文

最新运行记录显示:

- Telnet、UdpLogger、`$AUV` 上行、`$CKTH` 零推力下行已通。
- PySide6 PC104 profile 可完成安全构包和实物解析验证。
- ROS2 `protocol_udp` passive 上行桥接已通。
- ROS2 `protocol_udp` non-passive 零执行器短测已通。
- fan-out 架构已完成本地 dry-run、实物 passive 短测和 180 秒 non-passive 零执行器 soak。
- 未闭合项包括 BUG-4 Bit9 设置/保持、BUG-5/6 自救主推输出保留、DVL 自动化 Telnet probe 稳定性、真实传感器链和带负载执行机构闭环。

因此，PC104/fan-out/Telnet probe 相关脚本属于当前一线工具，不归档。

## 命令契约

### 低端口与权限

PC104 HIL 当前实测使用 `21/udp`:

```bash
sudo -n python3 scripts/sniffer.py --bind-port 21 --count 1 --ascii-format --no-color
```

普通用户通常不能绑定 `21/udp`。如果脚本需要绑定本机 `21/udp`，必须使用 `sudo` 或由 fan-out 作为唯一低端口绑定者。

### fan-out 并发契约

fan-out 模式中:

```text
PC104 <-> scripts/pc104_udp_fanout.py <-> ROS2/PySide6
```

约束:

- fan-out 是唯一绑定 `192.168.0.11:21` 的进程。
- ROS2 使用 `127.0.0.1:52365` 接收上行、向 `127.0.0.1:52364` 下行。
- PySide6 使用 `127.0.0.1:52366` 接收上行、向 `127.0.0.1:52364` 下行。
- 默认只允许零执行器 `$CKTH`，非零主推/侧推/舵角会被拒绝，除非显式启用非零执行器选项。
- Docker Desktop/macOS UDP publish 场景下，容器内可能看到上行源为 Docker 网关；此时保持 `--pc104-remote-host 192.168.0.101`，并额外传
  `--accept-uplink-source 172.18.0.1`。

常用命令:

```bash
scripts/start_pc104_fanout_concurrent.sh --passive
scripts/status_pc104_fanout_concurrent.sh
scripts/stop_pc104_fanout_concurrent.sh --force
scripts/run_pc104_fanout_zero_soak.sh --duration 180 --command-hz 2.0
```

### Telnet probe 契约

VxWorks shell 不可靠支持结构体字段表达式和 float 表达式。Telnet probe 应遵循:

```text
lkup 符号 -> Python 侧计算绝对地址 -> shell 执行短命令
```

BUG-4 只读:

```bash
python3 scripts/vxworks_bug4_runtime_probe.py --host 192.168.0.101
```

BUG-4 运行期注入:

```bash
python3 scripts/vxworks_bug4_runtime_probe.py \
  --host 192.168.0.101 \
  --execute \
  --probe both
```

DVL probe 当前仍以手工 Telnet raw 写入结果为权威，`execute` 自动化需要继续加固。

## 目录分层

### PC104 / VxWorks / fan-out 一线工具

| 脚本 | 用途 | 文档引用/更新判定 |
|---|---|---|
| `log_receiver.py` | 接收 VxWorks UdpLogger 文本日志，默认 `52367/udp` | 多文档引用，保留 |
| `sniffer.py` | `$AUV`/`$CKTH` UDP 抓包和 ASCII 解析 | 多文档引用，2026-07-11 修复，保留 |
| `pc104_udp_fanout.py` | PC104 UDP fan-out 代理 | 当前实物文档引用，保留 |
| `start_pc104_fanout_concurrent.sh` | 启动 fan-out + ROS2 并发栈 | 当前实物文档引用，保留 |
| `stop_pc104_fanout_concurrent.sh` | 停止 fan-out + ROS2 并发栈 | 当前实物文档引用，保留 |
| `status_pc104_fanout_concurrent.sh` | 查看 fan-out 并发栈状态 | 当前实物文档引用，保留 |
| `run_pc104_fanout_zero_soak.sh` | bounded non-passive 零执行器 soak | 当前实物文档引用，保留 |
| `vxworks_bug4_runtime_probe.py` | BUG-4 Telnet 运行期 probe | 当前实物文档引用，保留 |
| `vxworks_dvl_runtime_probe.py` | DVL BUG-5/6 Telnet probe | 当前实物文档引用，继续加固 |
| `vxworks_safety_hil.py` | 早期 VxWorks 深度安全 HIL 总脚本 | 多文档引用，历史与辅助用途，保留 |

### 实物部署五阶段脚本

`scripts/real_deployment/` 是阶段化实物部署脚本目录，全部有文档引用，保留原结构。

| 脚本 | 用途 |
|---|---|
| `00_static_preflight.sh` | 静态预检 |
| `01_link_audit.sh` | 链路审计 |
| `02_static_actuator.sh` | 静态执行器检查 |
| `03_shadow_navigation.sh` | 影子导航阶段 |
| `04_closed_loop_single.sh` | 单项闭环阶段 |
| `05_full_autonomy.sh` | 全自主阶段 |
| `_lib.sh` | 五阶段脚本共享库 |
| `kill_switch.sh` | 实物部署急停/kill switch |

### 仿真与 ROS 启动入口

| 脚本 | 用途 | 判定 |
|---|---|---|
| `start_lin_sim.sh` | Linux 仿真入口，支持 sim/bridge 等模式 | 多文档引用，保留 |
| `start_lin_brain.sh` | Linux brain/ROS2 入口 | 多文档引用，保留 |
| `start_experiment.sh` | 主要实验入口 | 大量文档引用，保留 |
| `start_holoocean_sim.sh` | HoloOcean 仿真启动 | 文档引用，保留 |
| `start_pvs_sim.sh` | PVS 仿真启动 | 文档引用，保留 |
| `start_foxglove_holoocean_ros.sh` | Foxglove + HoloOcean ROS 可视化 | 多文档引用，保留 |
| `start_foxglove_pvs_ros.sh` | Foxglove + PVS ROS 可视化 | 文档引用，保留 |
| `start_foxglove_layout.sh` | Foxglove layout 启动/辅助 | 文档引用，保留 |
| `start_ros_brain.sh` | 旧 ROS brain 启动入口 | 无当前文档引用但可能是兼容入口，暂保留 |
| `start_win_sim.bat` | Windows 仿真入口 | 无当前文档引用但跨平台入口，暂保留 |

### 实验、基准与论文复现

| 脚本 | 用途 | 判定 |
|---|---|---|
| `run_benchmark.sh` | 用户指南中的通用 benchmark | 文档引用，保留 |
| `run_integration_test.sh` | 集成测试入口 | 文档引用，保留 |
| `run_sim_equivalence_check.sh` | 仿真等价性检查 shell 入口 | 文档引用，保留 |
| `compare_sim_equivalence.py` | 仿真等价性比较工具 | 无当前文档引用，但与等价性检查相关，暂保留 |
| `run_terrain_benchmark.sh` | 地形跟随 benchmark | 多文档引用，保留 |
| `run_combined_sweep.sh` | 综合 sweep | 多文档引用，保留 |
| `run_dvl_sweep.sh` | DVL sweep | 多文档引用，保留 |
| `run_mag_sweep.sh` | 磁探测 sweep | 多文档引用，保留 |
| `run_jetson_emulated_bench.sh` | Jetson emulated benchmark | 多文档引用，保留 |
| `run_transparency_level_benchmark.sh` | 透明度等级 benchmark | 文档引用，保留 |
| `record_pvs_60s_dvl_fixed.sh` | PVS 60 秒 DVL fixed 记录脚本 | 无当前文档引用，legacy retained |
| `test_current_robustness.py` | 洋流鲁棒性测试 | 文档引用，保留 |
| `test_wait_mechanism.sh` | wait 机制测试 | 无当前文档引用，legacy retained |
| `visual_throttle.py` | 可视化节流辅助 | 文档引用，保留 |

### 电缆追踪与闭环回放

| 脚本 | 用途 | 判定 |
|---|---|---|
| `run_cable_closedloop_distorted.sh` | 扭曲先验电缆闭环实验 | 多文档引用，保留 |
| `score_cable_closedloop_recovery_runs.sh` | 闭环恢复评分 | 多文档引用，保留 |
| `score_cable_closedloop_runs.sh` | 闭环评分 | 文档引用，保留 |
| `run_cable_replay_e2e.sh` | 电缆 E2E replay | 文档引用，保留 |
| `run_cable_replay_one.sh` | 单次电缆 replay | 文档引用，保留 |
| `run_direction_a_decoupled_cable_sim.sh` | Direction A 解耦电缆仿真 | 文档引用，保留 |
| `run_cable_replay_batch.sh` | 批量电缆 replay | 近期更新，保留 |
| `run_cable_replay_distorted.sh` | 扭曲先验 replay | 近期更新，保留 |
| `run_cable_replay_remaining.sh` | 剩余 replay 批处理 | 近期更新，保留 |

### 文档、布局与维护

| 脚本/文件 | 用途 | 判定 |
|---|---|---|
| `build_docs_pdf.sh` | 构建文档 PDF | 文档引用，保留 |
| `pdf_style.html` | PDF 构建样式资源 | `build_docs_pdf.sh` 配套，保留 |
| `build_foxglove_layout.sh` | 构建/维护 Foxglove layout | 文档引用，保留 |
| `sync_thesis_figures.sh` | 同步论文图件 | 文档引用，保留 |
| `preflight_clean.sh` | 实验前清理 | 多文档引用，保留 |
| `auto_activate_emu.py` | 自动激活 emu/实验状态辅助 | 多文档引用，保留 |
| `attacker_station.py` | 攻击站/安全测试辅助 | 无当前文档引用，legacy retained |
| `start_experiment_old.sh` | 旧实验入口 | 被历史实验日志引用，legacy retained |

## archive

以下脚本已移动到 `scripts/archive/`，原因是文件名和审计结果均表明它们是阶段备份，且无当前文档引用:

| 归档文件 | 原因 |
|---|---|
| `start_pc104_fanout_concurrent_bak_20260711_harden.sh` | fan-out 启动脚本历史备份 |
| `start_pc104_fanout_concurrent_bak_20260711_nonzero_gate.sh` | fan-out 启动脚本历史备份 |
| `start_pc104_fanout_concurrent_bak_20260711_params_file.sh` | fan-out 启动脚本历史备份 |
| `stop_pc104_fanout_concurrent_bak_20260711_harden.sh` | fan-out 停止脚本历史备份 |
| `vxworks_dvl_runtime_probe_bak.py` | DVL probe 历史备份 |
| `vxworks_dvl_runtime_probe_bak_20260711_dvl_task_suspend.py` | DVL probe 历史备份 |

`scripts/__pycache__/` 为 Python 运行生成缓存，已删除，不归档。

## 后续整理规则

1. 新增脚本时优先放入明确子目录，避免继续堆叠在 `scripts/` 根目录。
2. 实物 PC104 相关脚本若会绑定低端口或写 Telnet 内存，必须在文件头和 README 中说明安全边界。
3. 阶段备份不要长期留在根目录，统一移动到 `scripts/archive/`。
4. 如果某个脚本连续无文档引用、无近期 git 更新，且被新入口替代，下一轮整理时应优先归档。
