# AUV_Master_Project

统一后的 AUV 项目根目录，目标是将仿真侧与 Linux ROS2 决策侧组织为一个可演进仓库。

## 当前目录
- common: 双端共享协议、枚举、物理常量
- algorithm: 与环境无关的控制/导引算法
- config: 仿真与桥接配置
- sim_holoocean: HoloOcean 仿真与 Zenoh 桥接
- brain_linux: ROS2 Humble 工作区（逐步迁入）
- msgs: 中间件无关消息映射说明
- scripts: 一键启动脚本
- docs: 原理说明与开发进度
- docs/字段真值表.md: topic 与字段的一览表
- docs/联调调试记录_2026-03-21.md: 系统 Python 全栈联调记录
- docs/联调验收摘要_2026-03-21.md: 联调验收结论与检查项
- docs/protocol_udp联调复现与模式切换_2026-04-01.md: 新旧桥接模式切换与复现步骤
- docs/控制回路问题定位与修复建议_2026-04-01.md: 当前控制问题、关联参数与修复方向
- docs/foxglove/布局生成器调试上下文_2026-03-25.md: Foxglove 布局 schema 排障记录
- foxglove_layout_project: Foxglove 布局生成器、topic 配置与导入产物

## 仿真侧快速启动（Linux）
```bash
cd scripts
bash start_lin_sim.sh sim
```

## 仿真 + 桥接并发启动（Linux）
```bash
cd scripts
bash start_lin_sim.sh both
```

## Phase 2.5：新旧仿真等价性检查
```bash
cd scripts
bash run_sim_equivalence_check.sh --dry-run
# 正式运行（耗时，建议在 holoocean 环境）
bash run_sim_equivalence_check.sh
```

## 仿真侧快速启动（Windows）
```bat
cd scripts
start_win_sim.bat sim
```

## 桥接快速启动（Windows）
```bat
cd scripts
start_win_sim.bat bridge
```

## 兼容原入口方式
```bash
cd sim_holoocean/apps
python main.py --config ../../config/sim_params.yaml
python run_zenoh_bridge.py --config ../../config/bridge_params.yaml
```

## brain_linux 启动（Phase 3）
```bash
cd scripts
bash start_lin_brain.sh bootstrap
bash start_lin_brain.sh decision
bash start_lin_brain.sh example
bash start_lin_brain.sh foxglove
bash start_lin_brain.sh stack
bash start_lin_brain.sh stack --backend protocol_udp --protocol-control-mode-byte 238
```

## Linux 端新桥接链路（进行中）
- `auv_bridge`: Zenoh JSON <-> ROS2 适配
- `auv_localization`: ES-EKF 过滤节点
- `auv_controller`: Setpoint + FilteredState -> /cmd_vel
- `auv_decision_ros`: 行为树发布 `/auv/control/setpoint`

## Foxglove 布局生成
```bash
cd foxglove_layout_project
/usr/bin/python3 -m foxglove_layout_project.generator.build_layout --pretty
```

如果要同时生成 mock topic 快照，使用：

```bash
/usr/bin/python3 -m foxglove_layout_project.generator.build_layout --with-mock-topics --pretty
```

一键联动启动：
```bash
cd scripts
bash start_foxglove_holoocean_ros.sh
bash start_foxglove_holoocean_ros.sh --bridge-backend protocol_udp --protocol-control-mode-byte 238
```

独立脚本：
- `scripts/start_foxglove_layout.sh`：只生成 Foxglove 布局
- `scripts/start_holoocean_sim.sh`：只启动 HoloOcean / Zenoh
- `scripts/start_ros_brain.sh`：只启动 ROS2 脑端

生成结果默认输出到：
- `foxglove_layout_project/output/auv_layout.generated.<unix>.json`
- `foxglove_layout_project/output/auv_layout.generated.<unix>.meta.json`
