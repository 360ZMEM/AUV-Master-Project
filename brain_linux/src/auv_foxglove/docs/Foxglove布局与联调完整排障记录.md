# Foxglove 布局与联调完整排障记录

> 项目：AUV ROS2 模拟发布 + Foxglove 实时可视化  
> 记录时间：2026-03-19  
> 适用目录：`ros2_ws/foxglove_layout_project`

---

## 1. 背景与目标

本次调试目标分为两部分：

1. 修复 Foxglove 布局导入失败（`Incompatible layout` / `Unknown panel type`）
2. 修复常驻后台运行脚本错误：
   - `AMENT_TRACE_SETUP_FILES: unbound variable`

最终目标：

- 布局可正常导入 Foxglove
- 3D / Plot / Raw Messages 正常显示
- 发布器与 `foxglove_bridge` 可后台长期稳定运行

---

## 2. 环境与组件

- ROS 2: Humble
- 数据发布节点：`my_auv_talker/auv_data_publisher`
- 桥接节点：`foxglove_bridge`
- 布局生成器：
  - `generator/layout_builder.py`
  - `generator/build_layout.py`
- 常驻脚本：
  - `examples/start_persistent_runtime.sh`

核心话题（/auv/*）：

- `/auv/pose`
- `/auv/depth`
- `/auv/temperature`
- `/auv/pressure`
- `/auv/gps`
- `/auv/imu`
- `/auv/status`
- `/auv/twist`

---

## 3. 问题演进与根因分析

### 3.1 第一阶段：布局不被识别

现象：

- `This file is not recognized as a Foxglove layout`
- `Incompatible layout`

阶段性根因：

- 输出 JSON 结构与 Foxglove Desktop 的“导入布局（opaque layout）”格式不一致。
- 一度使用了 notebook 风格 `version/content`，但 Desktop 的导入菜单并不总是接受这类结构。

---

### 3.2 第二阶段：能导入但出现 Unknown panel type

现象：

- `Unknown panel type: GPS / 深度 / 压力 / 状态 / IMU / 温度 / 速度`

关键根因：

- 布局树叶子节点写成了普通字符串（如 `GPS`、`Depth`），
  但 Desktop opaque layout 需要使用 `PanelType!id` 形式，例如：
  - `3D!auv3d`
  - `Plot!depth`
  - `RawMessages!gps`

如果仅写 `GPS`，导入器会把它当成 panel type 并报 `Unknown panel type: GPS`。

---

### 3.3 第三阶段：脚本后台启动失败

现象：

- 运行 `examples/start_persistent_runtime.sh` 报错：
  - `/opt/ros/humble/setup.bash: line 8: AMENT_TRACE_SETUP_FILES: unbound variable`

根因：

- 脚本启用了 `set -u`（nounset）
- ROS setup 脚本内部会读取某些在当前 shell 未定义的变量
- 在 `nounset` 严格模式下会直接触发 `unbound variable`

---

## 4. 关键修复动作

### 4.1 布局生成器结构修复

文件：

- `generator/layout_builder.py`
- `generator/build_layout.py`

修复策略：

1. 改为输出 Desktop opaque layout 结构：
   - `configById`
   - `globalVariables`
   - `userNodes`
   - `playbackConfig`
   - `layout`
2. 布局树叶子统一为 `PanelType!id` 引用
3. `configById` 里按 key 提供对应 panel config
4. 通过 `--no-map` 保留无地图版本，降低兼容风险

### 4.2.1 新一轮布局修复记录（2026-03-27）

这次联调中，曾出现两个新的界面问题：

1. 图表没有标题
2. RawMessages 面板显示 `No message path entered`

进一步对比当前工程的 README、历史可导入布局以及 Console 工作区的生成器后，确认问题更接近于生成器输出结构偏离了当前仓库约定，而不是话题本身丢失：

- `AUV_Master_Project/foxglove_layout_project/README.md` 明确要求使用 `configById + layout`
- 旧版可用输出也是 `configById` 根结构，而不是 `panels + savedProps`
- `configById` 的叶子必须与 `layout` 中的 `PanelType!slug` 保持一致

修复动作：

1. 将生成器从 `panels + savedProps` 回退到 `configById + layout`
2. 将叶子引用恢复为 `3D!auv3d`、`Plot!depth`、`RawMessages!imu` 这类形式
3. 保留现有 topic 配置与 mock topic 链路，只修正布局导出 schema

修复后的导出结果已重新生成到：

- `foxglove_layout_project/output/auv_layout.generated.1774575691.json`

当前结论：

- `Unknown panel type`、图表无标题、`No message path entered` 这一组现象，本质上都属于布局导出结构不稳定引起的面板绑定问题
- 对 AUV 这条链路，当前应以 `configById + layout` 作为唯一基线，不再沿用 `panels + savedProps`

---

### 4.2 后台脚本 `set -u` 兼容修复

文件：

- `examples/start_persistent_runtime.sh`

修复前：

```bash
set -euo pipefail
source "/opt/ros/humble/setup.bash"
source "/home/zmem063/auv_console_python/ros2_ws/install/setup.bash"
```

修复后：

```bash
set -euo pipefail

# 兼容 ROS setup 在 nounset 场景读取未定义变量
set +u
source "/opt/ros/humble/setup.bash"
source "/home/zmem063/auv_console_python/ros2_ws/install/setup.bash"
set -u
```

该方式保证：

- 绝大部分脚本仍保持 `-u` 严格模式
- 仅在 `source` ROS 环境脚本时临时放宽

---

## 5. 验证结果

### 5.1 脚本验证

- `bash -n examples/start_persistent_runtime.sh` 通过
- 在 `set -euo pipefail` 环境下，执行：
  - `set +u; source /opt/ros/humble/setup.bash; set -u` 通过
  - `set +u; source /opt/ros/humble/setup.bash; source ros2_ws/install/setup.bash; set -u` 通过

### 5.2 布局文件结构验证

生成文件：

- `output/auv_layout.generated.json`

关键检查点：

- 顶层包含 `configById/layout` 等 opaque layout 字段
- `configById` key 为 `3D!.../Plot!.../RawMessages!...` 形式
- `layout` 叶子引用与 `configById` key 一致

---

## 6. 经验总结（避免复发）

1. **Foxglove Desktop 导入 JSON** 优先使用“Desktop 导出的同构结构”
2. `Unknown panel type` 首先检查：
   - 布局叶子是否是 `PanelType!id`
   - `configById` 是否存在对应 key
3. 对 ROS setup 脚本：
   - 若外层脚本启用 `set -u`，需对 `source` 阶段做兼容处理
4. 导入时只选布局 JSON：
   - 不要导入 `*.meta.json`

---

## 7. 现行推荐操作流程

1. 生成布局（建议先无地图）：

```bash
cd /home/zmem063/auv_console_python/ros2_ws/foxglove_layout_project
python generator/build_layout.py --no-map --pretty
```

2. 启动常驻后台：

```bash
bash /home/zmem063/auv_console_python/ros2_ws/foxglove_layout_project/examples/start_persistent_runtime.sh
```

3. Foxglove 导入：

- 导入：`output/auv_layout.generated.json`
- 不导入：`output/auv_layout.generated.meta.json`

4. 若异常：

- 查看 `/tmp/auv_data_publisher.log`
- 查看 `/tmp/foxglove_bridge.log`

---

## 8. 本次最终状态

- ✅ 显示功能已正常
- ✅ 布局导入链路已修正
- ✅ 后台常驻脚本 `AMENT_TRACE_SETUP_FILES` 报错已修复

