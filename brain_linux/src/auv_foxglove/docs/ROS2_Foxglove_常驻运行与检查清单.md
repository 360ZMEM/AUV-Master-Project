# ROS2 + Foxglove 常驻运行与检查清单

> 适用对象：`ros2_ws` 中的 AUV 模拟发布器 + `foxglove_bridge` + Foxglove 客户端
>
> 目标：保证数据持续发布、Foxglove 持久在线连接、布局可复现导入

---

## 1. 你要先明白的结论

- Foxglove 本身不负责“发送数据”，它只是一个实时可视化客户端。
- 真正持续发送的是：
  - `ros2 run my_auv_talker auv_data_publisher`
  - `ros2 launch foxglove_bridge foxglove_bridge_launch.xml`
- 只要这两个进程一直运行，Foxglove 连接就能保持实时刷新。

---

## 2. 推荐的常驻启动方式

### 方式 A：使用后台常驻脚本（推荐）

文件：`ros2_ws/foxglove_layout_project/examples/start_persistent_runtime.sh`

执行：

```bash
bash /home/zmem063/auv_console_python/ros2_ws/foxglove_layout_project/examples/start_persistent_runtime.sh
```

启动后会输出：
- AUV 发布器 PID
- Foxglove Bridge PID
- 日志路径
- Foxglove 连接地址

### 方式 B：手工后台启动

终端 1：

```bash
source /opt/ros/humble/setup.bash
source /home/zmem063/auv_console_python/ros2_ws/install/setup.bash
nohup ros2 run my_auv_talker auv_data_publisher >/tmp/auv_data_publisher.log 2>&1 < /dev/null &
```

终端 2：

```bash
source /opt/ros/humble/setup.bash
source /home/zmem063/auv_console_python/ros2_ws/install/setup.bash
nohup ros2 launch foxglove_bridge foxglove_bridge_launch.xml >/tmp/foxglove_bridge.log 2>&1 < /dev/null &
```

---

## 3. Foxglove 客户端连接步骤

1. 打开 Foxglove Desktop 或 Foxglove Web
2. 选择 **Live connection** / **Foxglove Bridge**
3. 填写地址：
   - 本机：`ws://127.0.0.1:8765`
   - 虚拟机/远程：`ws://<运行ROS2机器IP>:8765`
4. 连接成功后，导入布局文件：
   - `ros2_ws/foxglove_layout_project/output/auv_layout.generated.json`
  - 不要导入 `*.meta.json`
5. 观察面板是否实时刷新

---

## 4. 常驻运行检查清单

### 4.1 启动前检查

- [ ] `/opt/ros/humble/setup.bash` 存在
- [ ] `ros2_ws/install/setup.bash` 存在
- [ ] 已编译工作空间：`colcon build --packages-select my_auv_talker`
- [ ] `foxglove_bridge` 已安装
- [ ] 你知道当前机器 IP：`hostname -I`

### 4.2 发布器检查

- [ ] 进程存在：`ps -ef | grep auv_data_publisher`
- [ ] 话题存在：`ros2 topic list | grep '^/auv/'`
- [ ] 深度数据持续变化：`ros2 topic echo /auv/depth --once`
- [ ] 状态数据持续变化：`ros2 topic echo /auv/status --once`

### 4.3 Bridge 检查

- [ ] 8765 端口监听：`ss -ltnp | grep ':8765'`
- [ ] 日志中出现：`Server listening on port 8765`
- [ ] 日志中出现 `/auv/pose`、`/auv/gps` 等 topic 广播
- [ ] Foxglove 连接后，桥日志出现 subscribe / connection graph 信息

### 4.4 Foxglove 客户端检查

- [ ] 数据源选择的是 **Live connection**
- [ ] 地址写的是 `ws://<IP>:8765`
- [ ] 连接后没有红色报错
- [ ] 布局已导入 `auv_layout.generated.json`
- [ ] 3D 面板能看到 `/auv/pose`
- [ ] Plot 面板能看到 `/auv/depth`、`/auv/temperature`、`/auv/pressure`
- [ ] Raw Messages 面板能看到 `/auv/gps`、`/auv/imu`、`/auv/status`、`/auv/twist`

---

## 5. 运行时问题排查

### 5.0 只看到 GPS 有实时消息

优先判断下面两类原因：

1. **导入了旧布局**
  - 现象：面板里出现 `Unknown panel type: GPS/Depth/Pressure/...`
  - 处理：改为导入 `ros2_ws/foxglove_layout_project/output/auv_layout.generated.json`

2. **只订阅了 GPS topic**
  - 现象：左侧 Topics 里只有 `/auv/gps` 显示频率，其他 topic 只有名字没有活跃统计
  - 处理：确认布局中的 Plot / Raw Messages / 3D 面板已经正常加载并订阅对应 topic

### 5.1 Foxglove 连不上

先检查：

```bash
ss -ltnp | grep ':8765'
```

若没有监听：
- 重新启动 bridge
- 检查 `foxglove_bridge.log`
- 确认网络和防火墙

### 5.2 话题有但图不动

可能原因：
- 连的是静态文件，不是 Live connection
- 面板 topic 绑定错误
- 数据字段路径写错，例如：
  - `std_msgs/Float32` -> `data`
  - `sensor_msgs/Temperature` -> `temperature`
  - `sensor_msgs/FluidPressure` -> `fluid_pressure`

### 5.3 进程退出

查看日志：

```bash
tail -n 50 /tmp/auv_data_publisher.log
tail -n 50 /tmp/foxglove_bridge.log
```

若需要重启，先杀旧进程，再重新执行常驻脚本。

### 5.4 版本或兼容性问题

- 如果 Foxglove 顶部提示版本过旧，建议先升级到最新版本。
- 如果布局导入后仍然出现未知面板类型，优先用当前生成器产物重新导入，不要混用旧 JSON。

---

## 6. 停止命令

停止发布器与 bridge：

```bash
pkill -f "ros2 run my_auv_talker auv_data_publisher"
pkill -f "foxglove_bridge_launch.xml"
pkill -f "foxglove_bridge"
```

---

## 7. 建议的日常联调顺序

1. 启动常驻脚本
2. 等待 2~3 秒确认 8765 端口监听
3. 打开 Foxglove
4. 连接 `ws://<IP>:8765`
5. 导入布局 JSON
6. 检查 3D、Plot、Raw Messages 是否都有数据
7. 若异常，先看 `/tmp/auv_data_publisher.log` 和 `/tmp/foxglove_bridge.log`

---

## 8. 最简可复制命令

### 启动常驻

```bash
bash /home/zmem063/auv_console_python/ros2_ws/foxglove_layout_project/examples/start_persistent_runtime.sh
```

### 查看话题

```bash
source /opt/ros/humble/setup.bash
source /home/zmem063/auv_console_python/ros2_ws/install/setup.bash
ros2 topic list | grep '^/auv/'
```

### 查看桥监听

```bash
ss -ltnp | grep ':8765'
```

### 查看日志

```bash
tail -f /tmp/foxglove_bridge.log
```
