# 06 - 现场调试命令行工具箱 (Field Debugging Toolkit)

> 本文件汇总一套**不需要 GUI** 即可快速排障的 `ros2 cli` 命令集。  
> 在海上作业环境中，显示器和网络通常不可靠，开发者必须能够通过 SSH 在纯终端环境下完成所有调试操作。

---

## 1. 快速状态总览

### 1.1 一键诊断脚本

```bash
# 保存为 ~/auv_diagnose.sh，chmod +x
#!/bin/bash
echo "========================================="
echo "  AUV 现场诊断报告 - $(date)"
echo "========================================="

echo ""
echo "--- 1. 活跃节点 ---"
ros2 node list

echo ""
echo "--- 2. 仲裁器状态 ---"
ros2 topic echo /auv/arbiter/status --once 2>/dev/null || echo "  [无仲裁器数据]"

echo ""
echo "--- 3. EKF 滤波位姿 ---"
ros2 topic echo /auv/state/filtered --once 2>/dev/null || echo "  [无 EKF 数据]"

echo ""
echo "--- 4. 传感器状态 ---"
ros2 topic echo /auv/sensors/status --once 2>/dev/null || echo "  [无传感器状态]"

echo ""
echo "--- 5. 电压监控 ---"
ros2 param get /auv_localization_node nominal_voltage_v 2>/dev/null

echo ""
echo "--- 6. 控制模式 ---"
ros2 param get /auv_bridge_node protocol_control_mode_byte 2>/dev/null

echo ""
echo "========================================="
echo "  诊断完成"
echo "========================================="
```

---

## 2. EKF 强制复位

### 2.1 复位方法

EKF 复位有三种级别，从温和到激进：

#### 方法 A：重置 PID 积分项（温和）

```bash
# 重置深度环积分
ros2 param set /auv_bridge_node depth_ki 0.0
sleep 1
ros2 param set /auv_bridge_node depth_ki 0.01

# 重置航向环积分
ros2 param set /auv_bridge_node yaw_ki 0.0
sleep 1
ros2 param set /auv_bridge_node yaw_ki 5.0
```

#### 方法 B：重启 EKF 节点（标准）

```bash
# 方式 1：通过 lifecycle 管理（如果节点支持）
ros2 lifecycle set /auv_localization_node shutdown
ros2 lifecycle set /auv_localization_node configure
ros2 lifecycle set /auv_localization_node activate

# 方式 2：直接 kill 后让 launch 文件自动重启
ros2 node info /auv_localization_node
# 找到 PID 后 kill
kill <auv_localization_node_pid>
```

#### 方法 C：通过协方差重置（激进 — 清除所有记忆）

```bash
# 发布一个协方差重置信号到 /auv/state/covariance
ros2 topic pub /auv/ekf/reset std_msgs/msg/Empty "{}" --once

# 或者修改 init_P_diag 让 EKF 使用新的初始不确定性
ros2 param set /auv_localization_node init_P_diag "[5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 0.5, 0.5, 0.5, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]"
```

### 2.2 验证 EKF 已复位

```bash
# 查看协方差是否重置为大值
ros2 topic echo /auv/state/covariance --once

# 观察位置是否回到初始值附近
ros2 topic echo /auv/state/filtered --once | grep -A3 position

# 观察 DVL 修正是否开始生效（复位后应等待首次 DVL 观测）
ros2 topic echo /auv/sensors/dvl --once
```

---

## 3. 在线修改舵机极性参数

### 3.1 极性翻转

```bash
# 翻转所有舵面极性（安装方向整体相反时）
ros2 param set /auv_bridge_node flip true

# 恢复正向
ros2 param set /auv_bridge_node flip false
```

### 3.2 Trim 中位偏移调整

```bash
# 全局 Trim 调整（所有舵面共同偏移）
ros2 param set /auv_bridge_node center_bias -1.5

# 增大 Trim（修正艇首上仰）
ros2 param set /auv_bridge_node center_bias -3.0

# 减小 Trim（修正艇首下俯）
ros2 param set /auv_bridge_node center_bias 1.0
```

### 3.3 舵面增益调整

```bash
# 降低舵面灵敏度（舵面反应过猛时）
ros2 param set /auv_bridge_node gain 0.7

# 提高舵面灵敏度（舵面反应迟钝时）
ros2 param set /auv_bridge_node gain 1.3
```

### 3.4 舵面极限角度调整

```bash
# 收紧舵面限位（防止舵面卡死）
ros2 param set /auv_bridge_node fin_deg_max 10.0

# 放宽舵面限位（需要更大舵效时）
ros2 param set /auv_bridge_node fin_deg_max 20.0
```

### 3.5 验证舵机响应

```bash
# 发送固定舵角指令，观察实际偏转
ros2 topic pub /auv/control/cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.0}, angular: {x: 0.0, y: 0.1, z: 0.0}}" --once

# 监控下行协议输出（查看编码后的舵角值）
ros2 topic echo /auv/bridge/shadow_cmd --once | grep -E "top|bottom|left|right"
```

---

## 4. 监控上行链路新鲜度 (Freshness)

### 4.1 查看遥测数据时间戳

```bash
# 方法 1：直接查看遥测数据中的时间戳
ros2 topic echo /auv/sensors/status --once | grep -E "ts|mock_amd_timestamp"

# 方法 2：计算数据新鲜度（与系统时间对比）
python3 -c "
import rclpy, time
from auv_interfaces.msg import SensorStatus
rclpy.init()
node = rclpy.create_node('freshness_checker')
msg = None
def cb(m): global msg; msg = m
sub = node.create_subscription(SensorStatus, '/auv/sensors/status', cb, 1)
while msg is None: rclpy.spin_once(node, timeout_sec=0.1)
age_ms = (time.time() - msg.ts) * 1000 if hasattr(msg, 'ts') and msg.ts > 0 else -1
print(f'上行链路新鲜度: {age_ms:.1f} ms')
print(f'阈值: 200 ms (guard_max_uplink_age_ms)')
print(f'状态: {\"正常\" if age_ms < 200 else \"过期!\"} ')
node.destroy_node()
rclpy.shutdown()
"
```

### 4.2 实时监控帧率

```bash
# 查看上行遥测发布频率（正常应 ≥ 10Hz）
ros2 topic hz /auv/sensors/status

# 查看 EKF 滤波输出频率（正常应 = 20Hz）
ros2 topic hz /auv/state/filtered

# 查看控制指令发布频率（正常应 = 10Hz）
ros2 topic hz /auv/control/cmd_vel
```

### 4.3 帧号连续性监控（检测丢帧）

```bash
# 连续输出 50 帧的 frame_number，检查是否有跳号
ros2 topic echo /auv/sensors/status --once 2>/dev/null | grep frame_number
# 或使用专用脚本：
python3 -c "
import rclpy
from std_msgs.msg import UInt32
rclpy.init()
node = rclpy.create_node('frame_monitor')
prev_fn = -1
lost = 0
def cb(msg):
    global prev_fn, lost
    fn = msg.data
    if prev_fn >= 0 and fn != (prev_fn + 1) % 256:
        lost += 1
        print(f'丢帧! 期望 {(prev_fn+1)%256}, 收到 {fn}, 累计丢失 {lost}')
    prev_fn = fn
sub = node.create_subscription(UInt32, '/auv/frame_number', cb, 10)
rclpy.spin(node)
"
```

---

## 5. 控制模式切换

### 5.1 遥控 ↔ 自主切换

```bash
# 切换到自主模式（control_mode_byte = 0xEE = 238）
ros2 param set /auv_bridge_node protocol_control_mode_byte 238

# 切换回遥控模式（control_mode_byte = 0x01 = 1）
ros2 param set /auv_bridge_node protocol_control_mode_byte 1

# 查看当前模式
ros2 param get /auv_bridge_node protocol_control_mode_byte
```

### 5.2 PID ↔ MPC 控制器切换

```bash
# 启用 MPC 控制器
ros2 param set /auv_bridge_node use_mpc true

# 切换回 PID 控制器
ros2 param set /auv_bridge_node use_mpc false

# 查看当前控制器类型
ros2 param get /auv_bridge_node use_mpc
```

### 5.3 绕过 EKF（使用原始传感器数据）

```bash
# 跳过 EKF，直接使用原始传感器（仅用于调试！）
ros2 param set /auv_bridge_node bypass_ekf true

# 恢复 EKF 滤波
ros2 param set /auv_bridge_node bypass_ekf false
```

---

## 6. 传感器原始数据检查

### 6.1 IMU 数据验证

```bash
# 查看 IMU 原始数据
ros2 topic echo /auv/sensors/imu --once

# 验证静止时加速度应接近 [0, 0, -9.81] (NED 系)
# 陀螺仪应接近 [0, 0, 0]

# 持续监控 IMU 噪声水平
ros2 topic echo /auv/sensors/imu 2>/dev/null | \
  grep -E "x:|y:|z:" | head -20
```

### 6.2 DVL 数据验证

```bash
# 查看 DVL 速度
ros2 topic echo /auv/sensors/dvl --once

# 验证：静止时速度应接近 0
# 前进时 vel_ned[0] 应为正值

# 检查 DVL 更新频率
ros2 topic hz /auv/sensors/dvl
```

### 6.3 深度数据验证

```bash
# 查看深度
ros2 topic echo /auv/sensors/depth --once

# 验证：海面深度 ≈ 0，下潜后深度为正
```

---

## 7. 推进器与舵面诊断

### 7.1 推力死区测试

```bash
# 从 0 开始逐步增加推力，观察何时开始运动
for pct in 1 2 3 4 5 6 7 8 9 10; do
  echo "推力 $pct%"
  ros2 param set /auv_bridge_node thrust_command $pct
  sleep 3
done
```

### 7.2 推力死区参数在线调整

```bash
# 增大死区（螺旋桨启动需要更大推力时）
ros2 param set /auv_bridge_node deadzone_percent 8.0

# 减小死区（低推力控制需要更精细时）
ros2 param set /auv_bridge_node deadzone_percent 3.0
```

### 7.3 电压补偿验证

```bash
# 查看电压补偿是否启用
ros2 param get /auv_bridge_node voltage_compensation

# 查看标称电压
ros2 param get /auv_bridge_node voltage_nominal

# 禁用电压补偿（调试推力问题时）
ros2 param set /auv_bridge_node voltage_compensation false
```

---

## 8. FSM 状态机诊断

### 8.1 查看当前状态

```bash
# 查看 FSM 当前状态（通过传感器状态推断）
ros2 topic echo /auv/sensors/status --once | grep -E "confidence|depth|speed"

# 查看决策节点输出
ros2 topic echo /auv/decision/goal --once 2>/dev/null || echo "  [无决策数据]"
```

### 8.2 手动触发调试模式

```bash
# debug_level=1 → 触发 STABILIZE_HOLD（定深定航保持）
ros2 param set /auv_bridge_node debug_level 1

# debug_level=2 → 触发 ANALYTICAL_PATH（解析轨迹跟踪）
ros2 param set /auv_bridge_node debug_level 2

# debug_level=0 → 恢复自动决策
ros2 param set /auv_bridge_node debug_level 0
```

---

## 9. 通信链路诊断

### 9.1 Zenoh 主题健康检查

```bash
# 列出所有活跃的 Zenoh 主题
ros2 topic list

# 检查关键主题是否有数据
for topic in /auv/state/filtered /auv/sensors/status /auv/control/cmd_vel /auv/arbiter/status; do
  count=$(ros2 topic echo $topic --once --spin-time 2 2>/dev/null | wc -l)
  if [ $count -gt 0 ]; then
    echo "[OK] $topic"
  else
    echo "[FAIL] $topic"
  fi
done
```

### 9.2 UDP 协议层诊断

```bash
# 检查 UDP 端口是否活跃
netstat -ulnp | grep -E "52364|52365"

# 查看 UDP 桥接参数
ros2 param get /auv_bridge_node local_port
ros2 param get /auv_bridge_node remote_port

# 修改远程主机地址（切换通信目标）
ros2 param set /auv_bridge_node remote_host "192.168.1.100"
```

---

## 10. 常用参数快速参考

### 10.1 关键参数一键查询

```bash
# 所有控制参数
ros2 param list | grep -E "depth_|pitch_|yaw_|speed_"

# 所有守卫参数
ros2 param list | grep -E "guard_|timeout_"

# 所有 EKF 噪声参数
ros2 param list | grep -E "sigma_"

# 所有 HAL 参数
ros2 param list | grep -E "rpm_scale|deadzone|center_bias|gain|flip"
```

### 10.2 参数批量导出/导入

```bash
# 导出当前所有参数
ros2 param dump /auv_bridge_node > ~/params_backup.yaml

# 从文件加载参数
ros2 param load /auv_bridge_node ~/params_backup.yaml
```

---

## 11. 紧急操作手册

### 11.1 紧急上浮

```bash
# 方法 1：通过 FSM 触发（如果可用）
ros2 param set /auv_bridge_node debug_level 1  # STABILIZE_HOLD → 停止下潜

# 方法 2：直接发送零推力 + 仰首舵角
ros2 topic pub /auv/control/cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: -0.5}, angular: {x: 0.0, y: -0.3, z: 0.0}}" --once

# 方法 3：强制切回遥控模式
ros2 param set /auv_bridge_node protocol_control_mode_byte 1
```

### 11.2 紧急停机

```bash
# 所有执行器归零
ros2 topic pub /auv/control/cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}" --once

# 发送任务取消指令（触发仲裁器切换到 REMOTE）
# 这需要将 work_instruction 设置为 TASK_CANCEL (0x02)
```

### 11.3 节点异常恢复

```bash
# 查找所有 AUV 相关进程
ps aux | grep auv | grep -v grep

# 重启整个系统（如果 launch 文件支持 respawn）
# 找到主 launch 进程并 kill，让 systemd 自动重启
sudo systemctl restart auv-system

# 单独重启某个节点
kill $(pgrep -f auv_localization_node)
# launch 文件中的 respawn=true 会自动重启
```

---

## 12. 调试日志级别控制

```bash
# 增加日志输出（查看调试信息）
ros2 run auv_bridge protocol_udp_bridge_node --ros-args --log-level debug

# 减少日志输出（仅显示错误和告警）
ros2 run auv_bridge protocol_udp_bridge_node --ros-args --log-level warn

# 实时修改节点日志级别（不需要重启）
ros2 service call /auv_bridge_node/set_logger_level \
  rcl_interfaces/srv/SetLoggerLevel "{logger_name: 'auv_bridge_node', level: 'DEBUG'}"
```

---

## 13. 离线排查 — 无 ROS2 环境时的应急操作

```bash
# 直接查看 UDP 数据包
tcpdump -i any -nn -X port 52364 or port 52365 | head -50

# 使用 Python 直接解析协议帧
python3 -c "
import socket, struct
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', 52365))
sock.settimeout(5.0)
data, addr = sock.recvfrom(2048)
if data[:5] == b'\$AUV\x91':
    print('收到上行 $AUV 帧')
    depth = struct.unpack('>H', data[38:40])[0] * 0.1
    heading = struct.unpack('>h', data[72:74])[0] * 0.1
    pitch = struct.unpack('>h', data[74:76])[0] * 0.1
    voltage = struct.unpack('>H', data[102:104])[0] * 0.1
    print(f'深度: {depth:.1f}m, 航向: {heading:.1f}°, 俯仰: {pitch:.1f}°, 电压: {voltage:.1f}V')
elif data[:5] == b'\$CKTH':
    print('收到下行 $CKTH 帧')
    rpm = struct.unpack('>h', data[23:25])[0]
    print(f'Main Motor RPM: {rpm}')
else:
    print(f'未知帧头: {data[:5]}')
"
```
