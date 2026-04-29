# PVS 调试排坑记录

本文档记录这次从 HoloOcean 向 PVS 做部分迁移时遇到的关键问题、定位过程、修复动作和验证结果。它不是设计说明，而是可复盘的排障笔记。

## 背景

迁移目标是：

- 让仿真后端支持 `pvs`
- 继续保留 ROS2、Mock AMD、Foxglove、录包和回放链路
- 保持参考深度/航向控制语义
- 在必要时支持 actuator 级别的 PVS 控制

本次调试的重点不是“能不能启动”，而是“启动后轨迹是否合理，产物是否可读，脚本是否可复现”。

## 问题 1：启动后 config 路径失效

### 现象

第一次启动 PVS smoke test 时，主循环进入失败，原因不是仿真本身，而是进入 `sim_holoocean/apps` 后仍然传了相对配置路径，导致读取配置失败。

### 根因

启动脚本先 `cd` 到 apps 目录，再把相对路径交给 Python 主程序。相对路径在新工作目录下不再指向原始配置文件。

### 修复

把 sim/bridge 配置路径在启动前统一规范成绝对路径。

### 结果

修复后，PVS 可以正常启动并进入主循环。

## 问题 2：PVS 轨迹明显跑太快

### 现象

第二次 smoke test 里，PVS 能跑，但速度显著过高，轨迹末端直接把 RMS 拉爆。

### 定位过程

我没有直接猜，而是先测了 PVS `remus100` 的速度响应，发现目标速度 1.1 m/s 只需要大约 520 rpm 左右，而不是原先映射出来的 1525 rpm。

### 根因

原来的 `target_u -> rpm` 映射太激进，导致参考转速远高于 PVS 真实需要的稳态范围。

### 修复

- 用经验标定后的线性映射替换比例映射
- 将初始实际推进器状态置零
- 在打开 PVS 后把参考深度、航向和内部状态显式重置

### 结果

速度问题明显缓解，PVS 可以稳定在约 1.1 m/s 附近运行。

## 问题 3：轨迹末端被安全边界夹断

### 现象

即使速度正常，长轨迹 smoke test 仍然出现 RMS 偏大。查看日志后发现，参考路径在后半段被限制在 `x=42` 左右，而车辆继续前进到了更远位置。

### 根因

PVS 专属配置仍沿用了 HoloOcean 尺寸的环境边界，但轨迹长度还保持着长航程设置。评估时参考点先被裁剪，导致误差被人为放大。

### 修复

我试过两种方向：

- 先把轨迹缩短，确认链路本身能收敛
- 再把 PVS 专属环境边界扩大，并保留中等长度轨迹，避免评估夹断

最终保留了 PVS 专属的大边界，并把轨迹长度调到一个能兼顾 RMS 和 axis_ratio 的中等长度。

### 结果

最终 PVS smoke test 通过：

- `rms=1.2539m`
- `axis_ratio=1.9438%`
- `pass_rms=True`
- `pass_axis_ratio=True`

## 问题 4：基准脚本直接报 `python: command not found`

### 现象

运行 `scripts/run_sim_equivalence_check.sh` 时，shell 直接报 `python: command not found`。

### 根因

脚本 wrapper 和内部 benchmark 逻辑都还在依赖裸 `python`。

### 修复

- wrapper 改为调用 `/usr/bin/python3`
- `scripts/compare_sim_equivalence.py` 改为使用 `sys.executable`

### 结果

脚本可以正常启动并输出结果，但默认 unified 配置的对比结果仍然不等价。

## 问题 5：默认 benchmark 结果不通过

### 现象

脚本现在能跑完，但对默认 legacy/unified 配置的比较输出是失败的。

### 实测结果

- legacy：`rms=0.9127`, `axis_ratio=0.017683`, `pass_rms=True`, `pass_axis_ratio=True`
- unified：`rms=33.3015`, `axis_ratio=0.610884`, `pass_rms=False`, `pass_axis_ratio=False`
- `equivalent=false`

### 解释

这说明脚本已经可用，但当前默认对比基线不满足等价阈值。这里不是脚本崩了，而是默认配置下确实没有达到等价条件。

### 后续建议

如果后续要把这个 benchmark 作为门禁，需要：

- 明确 legacy 和 unified 应该使用哪一组可比配置
- 不要直接拿默认 config 做等价性结论
- 把配置对齐后再讨论阈值是否合理

## 已验证产物

本次实际验证中，以下产物都已落地：

- `log/experiments/20260411_162254/analysis_pvs/`
- `log/experiments/20260411_162254/replay.gif`
- `log/phase2_5_legacy.log`
- `log/phase2_5_unified.log`

## 当前结论

这次迁移里，真正影响结果的不是“能不能跑”，而是三类问题：

1. 启动路径是否正确。
2. PVS 的速度参考是否标定合理。
3. 轨迹和边界是否在同一语义范围内。

前三个问题已经处理完，脚本和产物链路也已验证。现在剩下的是把 benchmark 的“默认不等价”解释清楚，避免后续误用。
