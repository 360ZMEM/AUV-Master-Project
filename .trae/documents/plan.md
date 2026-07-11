# AUV-Master-Project 实施计划：无扰动切换与存储架构重构

## 1. 摘要 (Summary)
本计划旨在 AUV 决策控制栈中实现“无扰动切换（Bumpless Transfer）”以确保手动到自主模式的平滑过渡，并在行为树中引入待命（Standby）模式。同时，将进行存储架构重构，引入 `common/env_utils.py` 全局路径契约，适配 OverlayFS（只读系统盘 + 独立数据盘），并将所有数据分析和基准测试的输出路径统一迁移至独立数据盘，实现代码区与数据区的完全脱钩。最后，增加对 Jetson 系统负载和数据盘空间的心跳自检。

## 2. 现状分析 (Current State Analysis)
- **存储架构**：当前代码库中的录包脚本（如 `start_experiment.sh`）、数据分析工具（如 `analyze_bag.py`, `mpc_test.py` 等）均使用相对路径或直接在工作区（如 `log/`, `tools/`, `verify_results_original/` 等）写入文件。这与 OverlayFS 的只读系统盘设计冲突。
- **控制器状态**：`auv_controller_node.py` 目前没有监听仲裁器状态（`ArbiterStatus`），在从遥控切换到自主模式时，PID 积分器未重置，且目标点未与当前实际位姿对齐，容易导致“暴力接管”（舵机瞬间打到底）。
- **行为树决策**：当前行为树在启动后如果满足条件即会直接进入任务状态，缺少等待手动授权（Wait For Arbiter Authorization）的挂起逻辑。
- **系统自检**：`bridge_node.py` 当前未监控 CPU/内存负载和磁盘空间，存在数据盘写满导致系统崩溃的风险。

## 3. 拟议变更 (Proposed Changes)

### 3.1 存储分区化重构 (Infrastructure Layer)

1. **新建 `common/env_utils.py`**：
   - `get_data_root() -> Path`：首先尝试读取环境变量 `AUV_DATA_ROOT`，其次读取 `brain_linux/config/params.yaml` 中的 `auv_data_root`，若均无则回退到 `/tmp/auv_data`。
   - `get_output_dir(sub_name: str) -> Path`：获取带时间戳的子目录。例如：返回 `{data_root}/{datetime_str}/{sub_name}` 或 `{data_root}/{sub_name}/{datetime_str}`（根据调用统一）。
   - `load_config_with_overrides(base_path: str) -> dict`：读取基础 yaml 后，检查 `{data_root}/config_overrides/params.yaml`，若存在则进行字典深度合并。

2. **脚本与工具路径脱钩**：
   - **`scripts/start_experiment.sh`**：调用 `env_utils.py` 获取数据根目录，将 `LOG_ROOT` 设为 `{data_root}/bags`。
   - **配置合并**：在 `auv_controller_node.py`, `bridge_node.py` 等手动加载 `params.yaml` 的地方，改为调用 `load_config_with_overrides`。

3. **基准测试与分析脚本的输出路径变更方案**：
   以下脚本的写入操作将统一使用 `env_utils.get_output_dir("results/<module_name>")` 或 `plots`：
   - `tools/analyze_bag.py`：输出 PDF/CSV 统一使用 `env_utils`。
   - `tools/mpc_test.py` & `tools/pid_ros2_test.py` & `tools/control_benchmark_module.py`：测试报告和图表路径迁移。
   - `tools/offline_ekf_benchmark.py` & `tools/es_ekf_comprehensive_tuner.py` & `tools/enhanced_benchmark_analysis.py`：将默认 `output_dir` 指向数据盘 `results/ekf_benchmark` 等子文件夹。
   - `tests/benchmark_bt_vs_fsm.py`：图表和报告路径迁移。
   - `tools/verify_init_pos_alignment.py`：不再向工作区 `verify_results_original` 写入 `root_cause_summary.json`，改写至数据盘。

### 3.2 控制器“无扰动切换” (`auv_controller_node.py`)
- **订阅仲裁状态**：增加对 `/auv/arbiter/status` (类型: `ArbiterStatus`) 的订阅，缓存 `msg.active_arbiter`。
- **积分重置与状态跟随**：
  在 `_on_timer` 中增加逻辑：若 `self._active_arbiter != 'AUTONOMOUS'`：
  1. 调用 `self._active_controller.reset()`（该方法在 `PIDController` 中会清空所有积分）。
  2. 强制将 `sp.target_depth_m` 设为 `actual_depth` (`-st.pose.pose.position.z`)。
  3. 强制将 `sp.target_heading_rad` 设为 `actual_heading` (`yaw`)。

### 3.3 行为树“待命”模式 (`decision_node.py` & `auv_decision_core`)
- **模型扩展**：在 `models.py` 的 `SensorStatusData` 中新增 `auto_state: str = 'LOCKED'` 字段。
- **状态注入**：在 `decision_node.py` 的 `_on_arbiter_status` 中，将 `msg.auto_state` 赋给 `SensorStatusData.auto_state`。
- **新增节点**：在 `behaviors.py` 中实现 `WaitForArbiterAuthorization`：当 `auto_state == 'ACTIVE'` 时返回 SUCCESS，否则发布 `mode='IDLE', note='Standby: Waiting for manual authorization'` 并返回 RUNNING。
- **树结构修改**：在 `bt_engine.py` 的 `_build_tree` 中，使用一个 Sequence 节点将 `WaitForArbiterAuthorization` 置于主控制流（`debug_cascade_selector`）的最前面（确保优先级低于 Emergency 紧急序列，但拦截所有的业务执行）。

### 3.4 增强型心跳自检 (`auv_bridge/bridge_node.py`)
- **指标收集**：使用 `psutil` 库获取 `cpu_percent()`, `virtual_memory().percent`, 以及 `get_data_root()` 的 `disk_usage().percent`。
- **遥测上报**：在 `handle_protocol_telemetry` 中将上述三个字段注入 `bridge_payload`，以便上位机和后端获取。
- **空间熔断**：在 `_on_stats_timer` (周期 2.0s) 中检查数据盘剩余空间，若低于 10%，调用 `self.autonomy_guard.lock(deny_reason=DenyReason.LOW_CONFIDENCE)`。

## 4. 假设与决策 (Assumptions & Decisions)
- **数据根目录契约**：为了兼顾多次运行的隔离，`get_output_dir(sub_name)` 将创建 `{data_root}/{sub_name}/{datetime_str}` 的层级结构（或类似清晰结构），保证代码修改的复用性。
- **只读保证**：假定通过全局搜索确认的文件写入均在上述列表内。实施时，将严格排查并替换 `open()`, `savefig()`, `to_csv()` 等调用的路径参数。
- **Python 环境依赖**：假定目标 Jetson 环境中已安装 `psutil`，若未安装，代码将使用 `try...except` 进行优雅降级，防止桥接节点崩溃。

## 5. 验收与验证 (Verification Steps)
1. **只读工作区验证**：实施完成后，对整个代码库执行 `chmod -R 555 .`，然后运行仿真与控制节点，确认没有任何 Permission Denied 报错，所有输出均落在 `/tmp/auv_data` 或指定目录下。
2. **Kick Test 暴力接管测试**：
   - 运行仿真或实车。
   - 手动模式下将 AUV 压至 5 米，而目标设定为 2 米。
   - 停留 10 秒后点击“自主授权”。
   - 观察 `/cmd_vel` 或 `MpcCmd` 输出，确认在切换瞬间舵机/推力指令不发生剧烈跳变（积分重置且目标瞬间跟随）。
3. **日志一致性检查**：确认 AI Agent 已经记录上述延迟和误差跳变测试，并在文档 `docs/AUV_系统鲁棒性压测记录.md` 中进行补充或确认（如文档不存在，可选择新建或跳过，以符合指令要求）。