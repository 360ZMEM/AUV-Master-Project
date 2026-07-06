# PySide6 上位机操作教程

## 职责划分

- GUI 上位机：操作员授权、手动接管、任务下发和报告查看入口。
- Foxglove：时间序列曲线、3D 场景、电缆跟踪诊断和 DL/T 评分可视化。

## 关键按钮

- `请求自主`：向 bridge/arbiter 请求自主控制权限。
- `手动接管`：把控制权限交还给操作员。
- `下发任务`：通过 Zenoh 侧通道发布 mission JSON。
- `任务开启` / `任务取消`：通过既有协议路径发送任务生命周期命令。
- `紧急切断 ESTOP`：高风险安全动作，自动化脚本默认不得点击。
- `解除急停`：高风险恢复动作，未经明确复核时自动化脚本不得点击。

## 电缆跟踪任务

使用 mission type `CABLE_TRACKING` 或 `CABLE_INSPECTION`。电缆跟踪 ROS2 节点只有在收到已接受的电缆任务，并同时具备有效导航/磁输入后，才会发布 `/auv/control/setpoint`。

## 截图反馈闭环

```bash
python tools/gui_console_loop.py --screenshot-only
```

截图会保存到 `results/visual_feedback/gui/`。第一阶段脚本不会点击危险控制项。
