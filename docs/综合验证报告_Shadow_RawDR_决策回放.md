# 综合验证报告 — Shadow / Raw-DR / 决策回放

> 本文档记录「第二阶段」功能的落地验证过程与结果，涵盖 ROS2 编译验证、PVS shadow 模式、raw dead-reckoning 基准、决策回放路径修正。

## 1. 验证范围

| # | 功能 | 验证方式 | 状态 |
| --- | --- | --- | --- |
| 1 | ROS2 全包编译 | `colcon build` | ✅ 通过 |
| 2 | ROS2 单元测试 | `colcon test` + `test-result` | ✅ 通过（21 tests, 0 failures） |
| 3 | `auv_common` 共享包 | 安装到 overlay 后 `import common` | ✅ 修复通过 |
| 4 | PVS 启动脚本语法 | `bash -n` smoke check | ✅ 通过 |
| 5 | 仿真后端切换 `--sim-backend pvs` | 脚本参数传递验证 | ✅ 通过 |
| 6 | Foxglove/HoloOcean 联调脚本修复 | 移除 stray 示例行 | ✅ 修复通过 |
| 7 | 决策回放默认日志路径 | 路径自动探测 + launch 默认值 | ✅ 修正并验证 |
| 8 | Shadow 模式 / raw DR 文档 | PVS runbook + 速查文档更新 | ✅ 完成 |
| 9 | `auv_control` README | 重写为匹配实际仓库布局 | ✅ 完成 |

---

## 2. ROS2 编译验证

### 2.1 构建命令

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/brain_linux
source /opt/ros/humble/setup.bash
colcon build --packages-select \
  auv_common auv_interfaces auv_bridge auv_localization \
  auv_controller auv_decision_ros auv_decision_core auv_viz_bridge
```

**结果：** 编译成功，无错误。

### 2.2 测试命令

```bash
colcon test --packages-select \
  auv_common auv_interfaces auv_bridge auv_localization \
  auv_controller auv_decision_ros auv_decision_core auv_viz_bridge

colcon test-result --all --verbose
```

**结果：** 21 tests, 0 errors, 0 failures, 0 skipped。

### 2.3 `auv_common` 包修复

**问题：** `auv_controller` 测试在 install 空间中无法 `import common`，因为 `common/` 仅存在于 workspace root，未被安装到 ROS2 overlay。

**修复：** 新建 `brain_linux/src/auv_common/` 包，通过 `setup.py` 将 workspace root 的 `common` 包安装到 ROS2 install 空间。依赖方（`auv_bridge`、`auv_controller`、`auv_localization`、`auv_viz_bridge`）的 `package.xml` 中添加了 `<exec_depend>auv_common</exec_depend>`。

---

## 3. PVS 脚本与文档验证

### 3.1 启动脚本语法检查

```bash
bash -n scripts/start_pvs_sim.sh
bash -n scripts/start_foxglove_pvs_ros.sh
bash -n scripts/start_lin_sim.sh
bash -n scripts/start_foxglove_holoocean_ros.sh
```

**结果：** 全部通过。

### 3.2 Foxglove 联调脚本修复

**问题：** `start_foxglove_holoocean_ros.sh` 中有一行未注释的示例命令，导致 PVS wrapper 路径执行时报 shell 错误。

**修复：** 将该行注释掉。

### 3.3 PVS 全链路入口

```bash
# 纯仿真
bash scripts/start_pvs_sim.sh sim

# PVS + Foxglove + ROS2
bash scripts/start_foxglove_pvs_ros.sh

# protocol_udp + arbiter
bash scripts/start_lin_brain.sh stack --arbiter-profile
```

---

## 4. 决策回放路径修正

### 4.1 问题

- `decision_replay.launch.py` 默认路径指向 `/home/zmem063/.../20020101103632.txt`（不存在）。
- `mock_sensor_input.py` 的候选路径与实际仓库布局不匹配。
- `auv_control/README.md` 中引用的路径和命令都已过时。

### 4.2 仓库实际结构

```
/home/gwxie/master_work-tmp/
├── AUV_Master_Project/          ← ROS2 脑端 + 仿真 + 文档
└── Console上位机软件/
    └── auv_console_python/
        └── 20020101103632.txt  ← 样例日志（真实存在）
```

### 4.3 修复内容

| 文件 | 修改 |
| --- | --- |
| `mock_sensor_input.py` | 重写 `_guess_default_log_file()`，覆盖仓库并列结构 |
| `decision_replay.launch.py` | 默认路径改为 `/home/gwxie/master_work-tmp/Console上位机软件/auv_console_python/20020101103632.txt` |
| `auv_control/README.md` | 完整重写，匹配实际路径、参数、Topic |

---

## 5. Shadow 模式与 Raw Dead-Reckoning

### 5.1 Shadow 模式

bridge 的 `passive_mode` 参数为 `true` 时：
- 不下发给仿真/实物
- 在 `/auv/bridge/shadow_cmd` 和 `/auv/bridge/shadow_telemetry` 发布影子快照
- arbiter 状态照常发布

```bash
ros2 launch auv_stack auv_stack.launch.py passive_mode:=true
```

### 5.2 Raw Dead-Reckoning

localization 额外发布 `/auv/state/raw_dr`，controller 根据参数选择状态源：

```bash
# 启用 raw DR 发布
ros2 launch auv_stack auv_stack.launch.py publish_raw_state:=true

# controller 直接使用 raw DR（绕过 EKF）
ros2 launch auv_stack auv_stack.launch.py publish_raw_state:=true bypass_ekf:=true
```

### 5.3 运行时参数热更新

bridge 支持通过 ROS2 parameter callback 在运行时更新：
- `cmd_rate_hz`
- `cmd_timeout_s`
- `protocol_motor_rpm_scale`
- `guard_voltage_threshold`
- `guard_confidence_threshold`
- `guard_uplink_timeout_s`

---

## 6. 文档更新清单

| 文档 | 更新内容 |
| --- | --- |
| `docs/PVS全流程runbook.md` | 新增 Shadow 模式、Raw DR 基准、决策回放三个章节 |
| `docs/PVS与protocol_udp联调速查.md` | 新增 §7 Shadow/DR/Replay 速查入口，更新 §8 交叉引用 |
| `brain_linux/src/auv_control/README.md` | 完整重写：路径、参数表、Topic 表、验证步骤 |
| `brain_linux/src/auv_control/launch/decision_replay.launch.py` | 默认路径和用法示例修正 |
| `brain_linux/src/auv_control/auv_decision_ros/mock_sensor_input.py` | 默认路径探测逻辑重写 |

---

## 7. 后续工作

- [ ] 实际运行 shadow 模式 + raw DR，产出对照数据
- [ ] 用 `analyze_bag.py` 对 shadow 产物做定量比对
- [ ] 将 bypass-EKF 的控制精度回归结果写入 runbook
- [ ] 考虑将 `mock_sensor_input.py` 的默认路径做成 workspace-relative 的 ROS2 parameter（避免硬编码用户名）
