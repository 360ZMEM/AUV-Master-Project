# 常见问题

这里收集了新手最常遇到的问题和解决方案。

## 环境配置问题

### Q1: "ModuleNotFoundError: No module named 'zenoh'"

**症状**:
```
ModuleNotFoundError: No module named 'zenoh'
```

**原因**:
- 使用了错误的 Python 环境（如 conda）
- **正确的包名是 `eclipse-zenoh`，不是 `zenoh`**

**解决方案**:
```bash
# 1. 确认退出 conda 环境
conda deactivate
conda deactivate

# 2. 确认使用系统 Python
which python3  # 应该输出 /usr/bin/python3

# 3. 重新安装 eclipse-zenoh（全局安装，不要 --user）
/usr/bin/python3 -m pip install eclipse-zenoh py-trees pyyaml
```

**导入说明**:
- 虽然安装包名是 `eclipse-zenoh`，但导入时仍然使用 `import zenoh`
- 代码中已经正确配置了这一点，无需修改任何代码！

### Q2: ROS2 命令找不到

**症状**:
```
ros2: command not found
```

**原因**: ROS2 环境未正确加载

**解决方案**:
```bash
# Source ROS2 环境
source /opt/ros/humble/setup.bash

# Source 工作区环境
source ~/AUV_Master_Project/brain_linux/install/setup.bash

# 将上面两行添加到 ~/.bashrc 以永久生效
```

### Q3: 构建失败，提示找不到 Python

**症状**:
```
Could not find Python
```

**解决方案**:
```bash
# 清理构建
cd ~/AUV_Master_Project/brain_linux
rm -rf build install log

# 使用明确的 Python 路径重新构建
cd ~/AUV_Master_Project/scripts
bash start_lin_brain.sh bootstrap
```

## 运行问题

### Q4: 仿真启动失败

**症状**: HoloOcean 无法启动或崩溃

**可能原因**:
1. 图形驱动问题
2. HoloOcean 未正确安装
3. 配置文件路径错误

**解决方案**:
```bash
# 检查 OpenGL 支持
glxinfo | grep "OpenGL version"

# 检查 HoloOcean 安装
/usr/bin/python3 -c "import holoocean; print(holoocean.__version__)"

# 查看详细错误日志
cd ~/AUV_Master_Project/scripts
bash start_lin_sim.sh sim 2>&1 | tee sim_error.log
```

### Q5: ROS2 节点无法启动

**症状**: 节点启动后立即退出或报错

**检查步骤**:
```bash
# 1. 检查话题是否创建
ros2 topic list

# 2. 查看节点状态
ros2 node list

# 3. 查看详细日志
ros2 run auv_bridge bridge_node --ros-args --log-level debug
```

### Q6: 没有传感器数据

**症状**: `/auv/sensors/*` 话题没有数据

**排查步骤**:
1. 确认仿真侧正在运行
2. 确认桥接节点已启动
3. 检查网络连接

```bash
# 检查 Zenoh 连接
ros2 topic echo /auv/sensors/imu --once

# 检查桥接节点日志
# 在桥接节点运行的终端查看输出
```

## 控制问题

### Q7: AUV 不动或控制无效

**症状**: 控制指令发送但 AUV 没有响应

**可能原因**:
1. 控制模式不正确
2. 参数配置问题
3. 通信链路问题

**排查步骤**:
```bash
# 1. 检查控制指令
ros2 topic echo /cmd_vel --once

# 2. 检查控制模式
ros2 topic echo /auv/control/setpoint --once

# 3. 查看控制器调试信息
ros2 topic echo /auv/controller/debug --once

# 4. 检查仿真侧是否收到命令
# 在仿真终端查看日志输出
```

### Q8: 深度控制不稳定

**症状**: 深度振荡或无法到达目标深度

**参考**: [控制调试指南](../05_operations/02_control_debugging.md)

**快速检查**:
```bash
# 查看深度误差
ros2 topic echo /auv/diagnostics --once | grep depth_error

# 查看舵面输出
ros2 topic echo /cmd_vel --once
```

## 性能问题

### Q9: 系统运行卡顿

**症状**: 仿真帧率低，响应延迟大

**检查项**:
```bash
# 1. 检查 CPU 使用率
htop

# 2. 检查 ROS2 节点频率
ros2 topic hz /auv/sensors/imu

# 3. 查看延迟日志
# 在桥接节点日志中查找 "latency" 关键字
```

### Q10: 内存占用过高

**解决方案**:
```bash
# 1. 减少仿真步数（编辑 config/sim_params.yaml）
# 2. 降低传感器采样频率
# 3. 减少日志记录
```

## 开发问题

### Q11: 修改代码后没有生效

**解决方案**:
```bash
# 1. 清理并重新构建
cd ~/AUV_Master_Project/brain_linux
rm -rf build install log
cd ~/AUV_Master_Project/scripts
bash start_lin_brain.sh bootstrap

# 2. 如果是 common/ 或算法修改，确保没有旧的 .pyc 文件
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} +
```

### Q12: 如何调试单个节点？

```bash
# 独立运行桥接节点
ros2 run auv_bridge zenoh_json_bridge_node \
  --ros-args \
  -p params_file:=~/AUV_Master_Project/brain_linux/config/params.yaml

# 独立运行控制器
ros2 run auv_controller controller_node \
  --ros-args \
  -p params_file:=~/AUV_Master_Project/brain_linux/config/params.yaml
```

## 模式切换问题

### Q13: 如何在 zenoh_json 和 protocol_udp 之间切换？

参考: [运行模式切换](../05_operations/01_mode_switching.md)

**快速命令**:
```bash
# zenoh_json 模式
bash start_lin_sim.sh both --backend zenoh_json
bash start_lin_brain.sh stack --backend zenoh_json

# protocol_udp 模式
bash start_lin_sim.sh both --backend protocol_udp
bash start_lin_brain.sh stack --backend protocol_udp --protocol-control-mode-byte 238
```

## 获取更多帮助

如果以上都没有解决你的问题：

1. **查看详细日志**
   ```bash
   # 保存完整日志
   your_command 2>&1 | tee debug.log
   ```

2. **查看相关文档**
   - [日志解读指南](../05_operations/03_log_analysis.md)
   - [控制调试指南](../05_operations/02_control_debugging.md)

3. **检查系统状态**
   ```bash
   # ROS2 节点图
   ros2 run rqt_graph rqt_graph

   # Topic 信息
   ros2 topic info /topic_name
   ```

## 常用调试命令速查

```bash
# 列出所有话题
ros2 topic list

# 查看话题类型
ros2 topic info /auv/sensors/imu

# 实时查看话题数据
ros2 topic echo /auv/sensors/imu

# 查看话题发布频率
ros2 topic hz /auv/sensors/imu

# 列出所有节点
ros2 node list

# 查看节点信息
ros2 node info /bridge_node

# 检查系统资源
htop
```

需要添加更多问题？请提交 issue 或 PR。
