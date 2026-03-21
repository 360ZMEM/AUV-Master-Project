# Foxglove AUV 联调操作清单（Checklist）

> 目标：快速定位问题并在最短时间内完成 Foxglove 可视化联调。

---

## 1. 必备环境 & 预检查

- [ ] ROS2 Humble 已安装，且 `/opt/ros/humble/setup.bash` 可用
- [ ] 已构建工作空间：
  - `cd /home/zmem063/auv_console_python/ros2_ws`
  - `colcon build --packages-select my_auv_talker`
- [ ] `foxglove_bridge` 已安装（`ros2 run foxglove_bridge foxglove_bridge_launch` 能启动）
- [ ] 确认当前机器或虚拟机 IP：`hostname -I | awk '{print $1}'`

---

## 2. 生成最新布局文件（强烈推荐）

1. 进入布局目录：

```bash
cd /home/zmem063/auv_console_python/ros2_ws/foxglove_layout_project
```

2. 生成布局（默认包含 3D 内置地图层；如需兼容降级可禁用地图层）：

```bash
python generator/build_layout.py --pretty
```

3. 确认文件存在：

```bash
ls -l output/auv_layout.generated.json
```

4. 注意：不要导入 `*.meta.json`，它仅用于版本记录。

---

## 3. 启动常驻后台（推荐）

执行：

```bash
bash examples/start_persistent_runtime.sh
```

检查输出是否包含：

- `AUV 发布器 PID:`
- `Foxglove Bridge PID:`
- `Foxglove 地址: ws://<IP>:8765`

如果出现 `AMENT_TRACE_SETUP_FILES: unbound variable`，说明脚本未更新为带 `set +u` 段。

---

## 4. 验证基础连通性

### 4.1 进程存在

```bash
ps -ef | grep -E "auv_data_publisher|foxglove_bridge" | grep -v grep
```

### 4.2 8765 监听正常

```bash
ss -ltnp | grep ':8765'
```

### 4.3 ROS 话题存在

```bash
source /opt/ros/humble/setup.bash
source /home/zmem063/auv_console_python/ros2_ws/install/setup.bash
ros2 topic list | grep '^/auv/'
```

### 4.4 数据能正常输出（任选一条）

```bash
ros2 topic echo /auv/depth --once
```

---

## 5. Foxglove 客户端连接与布局

### 5.1 连接 Foxglove Bridge

1. 打开 Foxglove Desktop/Web
2. 选择 “Live connection” → “Foxglove Bridge”
3. 填写地址：
   - 本机：`ws://127.0.0.1:8765`
   - 远程：`ws://<机器IP>:8765`
4. 点击连接

### 5.2 导入布局

1. 菜单 → Layouts → Import from file...
2. 选择：
   - `ros2_ws/foxglove_layout_project/output/auv_layout.generated.json`
3. 确认无 `Incompatible layout` 错误

---

## 6. 常见问题 + 快速排查（Checklist）

### 6.1 导入失败：`Incompatible layout`

- [ ] 确认导入的是 `output/auv_layout.generated.json`（不是 `.meta.json`）
- [ ] 重新生成布局：`python generator/build_layout.py --no-map --pretty`
- [ ] 确认文件头部结构是否含 `configById` + `layout`（Opaque Layout）

### 6.2 导入成功但出现 `Unknown panel type: ...`

- [ ] 确认布局 `layout` 节点里使用的是 `PanelType!id` 格式（例如 `Plot!depth`）
- [ ] 确认 `configById` 里存在对应 key
- [ ] 若使用 `--no-map`，确认布局中没有 3D 内置地图层（`layers.map`）

### 6.3 只看到 GPS 流量、其他面板不动

- [ ] Foxglove 连接是否为 Live Connection（不是 Replay/Playback）
- [ ] 看 Foxglove 左侧 Topics 面板，是否列出了 `/auv/depth` `/auv/temperature` 等
- [ ] 如果没有，说明布局未订阅对应 topic 或数据未真实发布

### 6.4 后台脚本启动失败（`AMENT_TRACE_SETUP_FILES`）

- [ ] 确认 `examples/start_persistent_runtime.sh` 已包含：
  - `set +u` / `source ...` / `set -u`
- [ ] 如果仍失败，可手动执行：

```bash
set +u
source /opt/ros/humble/setup.bash
source /home/zmem063/auv_console_python/ros2_ws/install/setup.bash
set -u
```

---

## 7. 停止/清理

直接停止后台进程：

```bash
pkill -f "ros2 run my_auv_talker auv_data_publisher"
pkill -f "foxglove_bridge_launch.xml"
pkill -f "foxglove_bridge"
```

若需要彻底重启：

```bash
bash examples/start_persistent_runtime.sh
```

---

## 8. 备注

- 若后续需要“地图层”功能，请优先使用 3D 内置地图层；不要再回退到独立 `Map` 面板。
- 若需要扩展布局（新增 panel/标签/分屏），请先在 Foxglove 中生成一个样板布局并导出，然后对比 `configById/layout` 结构。
