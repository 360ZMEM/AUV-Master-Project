# Mock AMD 使用指南

## 目录

1. [快速开始](#快速开始)
2. [配置说明](#配置说明)
3. [启动方式](#启动方式)
4. [常用操作](#常用操作)
5. [使用场景](#使用场景)
6. [故障排查](#故障排查)
7. [最佳实践](#最佳实践)

## 快速开始

### 最小化启动

最简单的方式是使用 `start_lin_sim.sh` 脚本启动 Mock AMD：

```bash
cd ~/AUV_Master_Project/scripts
bash start_lin_sim.sh both --backend protocol_udp
```

这将：
1. 启动 HoloOcean 仿真
2. 启动 Mock AMD UDP 服务器
3. 输出单行格式的协议日志

### 验证运行

在另一个终端中验证 Mock AMD 是否正常工作：

```bash
# 使用 sniffer 检查报文
/usr/bin/python3 scripts/sniffer.py --bind-port 52364 --count 5
```

你应该看到类似这样的输出：

```
[sniffer][CKTH][127.0.0.1:xxxxx] frame=0 obj=1 mode=0xEE cmd=(0.0,0.0,0.0,0.0,0.0)
[sniffer][CKTH][127.0.0.1:xxxxx] frame=1 obj=1 mode=0xEE cmd=(0.0,0.0,0.0,0.0,0.0)
...
```

## 配置说明

Mock AMD 的配置文件位于 `config/bridge_params.protocol_udp.yaml`。

### 核心配置项

#### 网络配置

```yaml
protocol_udp:
  # Mock AMD 绑定的地址和端口（接收下行命令）
  bind_host: 0.0.0.0        # 0.0.0.0 表示监听所有接口
  bind_port: 52364          # 默认端口

  # 远程客户端（ROS2 bridge）的地址和端口
  remote_host: 127.0.0.1    # 本地测试
  remote_port: 52365        # ROS2 bridge 的端口

  # Socket 参数
  socket_timeout_s: 0.01    # UDP 接收超时（秒）
  recv_buffer_size: 2048    # 接收缓冲区大小（字节）
```

#### 协议参数

```yaml
protocol_udp:
  # AUV 地址
  auv_address: 1                    # AUV 设备地址

  # 控制模式
  default_control_mode_byte: 238    # 0xEE = 自主模式

  # 电机参数
  main_motor_rpm_scale: 15.0        # 推力百分比到 RPM 的转换系数
  side_motor_rpm: 0                 # 侧推电机 RPM
```

**电机 RPM 计算**:

```
main_motor_rpm = thrust_percent * main_motor_rpm_scale
```

例如：`thrust_percent = 50.0` → `main_motor_rpm = 50 * 15 = 750 RPM`

#### 遥测参数

```yaml
protocol_udp:
  # 模拟的电源状态
  telemetry_total_voltage_v: 48.0    # 总电压（伏特）
  telemetry_total_current_a: 12.0    # 总电流（安培）
  telemetry_soc: 100                 # 荷电状态（%）
  telemetry_soh: 100                 # 健康状态（%）
```

#### 日志配置

```yaml
protocol_udp:
  # 日志开关
  log_packets: true                  # 是否记录报文
  log_raw_format: false              # 原始十六进制格式
  log_ascii_format: false            # ASCII 详细格式
  log_packet_hex: false              # 单行格式包含十六进制
  log_hex_bytes: 48                  # 十六进制显示字节数
  log_every_n: 1                     # 每 N 个报文记录一次
```

#### Sniffer 镜像

```yaml
protocol_udp:
  # 数据镜像到 sniffer
  sniffer_mirror_host: 127.0.0.1
  sniffer_mirror_port: 52366         # sniffer 监听端口
```

### 配置模板

#### 开发调试配置

```yaml
protocol_udp:
  # 启用详细日志
  log_ascii_format: true
  log_packets: true
  log_every_n: 1

  # 降低频率便于观察
  bridge:
    rate_hz: 10.0  # 10 Hz 而不是 50 Hz
```

#### 性能测试配置

```yaml
protocol_udp:
  # 禁用详细日志
  log_ascii_format: false
  log_packets: true
  log_every_n: 100  # 每 100 个报文记录一次

  # 正常运行频率
  bridge:
    rate_hz: 50.0  # 50 Hz
```

#### 协议验证配置

```yaml
protocol_udp:
  # 启用十六进制输出
  log_packet_hex: true
  log_hex_bytes: 72  # 显示完整下行报文
  log_packets: true
  log_every_n: 1
```

## 启动方式

### 方式 1: 使用启动脚本（推荐）

```bash
cd ~/AUV_Master_Project/scripts

# 启动仿真 + Mock AMD
bash start_lin_sim.sh both --backend protocol_udp

# 指定配置文件
bash start_lin_sim.sh both --backend protocol_udp --config path/to/config.yaml
```

**优点**:
- 自动处理环境变量
- 统一的启动流程
- 便于脚本化管理

### 方式 2: 直接运行 Python

```bash
cd ~/AUV_Master_Project

# 设置 Python 路径
export PYTHONPATH="${PYTHONPATH}:$(pwd):$(pwd)/common:$(pwd)/sim_holoocean/interfaces"

# 运行 Mock AMD
/usr/bin/python3 sim_holoocean/apps/run_zenoh_bridge.py \
  --config config/bridge_params.protocol_udp.yaml
```

**优点**:
- 更灵活的控制
- 便于 IDE 调试
- 可以附加 Python 调试器

### 方式 3: 使用 systemd 服务（生产环境）

创建服务文件 `/etc/systemd/system/auv-mock-amd.service`:

```ini
[Unit]
Description=AUV Mock AMD Server
After=network.target

[Service]
Type=simple
User=auv
WorkingDirectory=/home/auv/AUV_Master_Project
Environment="PYTHONPATH=/home/auv/AUV_Master_Project:/home/auv/AUV_Master_Project/common"
ExecStart=/usr/bin/python3 sim_holoocean/apps/run_zenoh_bridge.py \
    --config config/bridge_params.protocol_udp.yaml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable auv-mock-amd
sudo systemctl start auv-mock-amd
```

### 方式 4: 后台运行

```bash
# 后台运行并记录日志
nohup /usr/bin/python3 sim_holoocean/apps/run_zenoh_bridge.py \
  --config config/bridge_params.protocol_udp.yaml \
  > logs/mock_amd_$(date +%Y%m%d_%H%M%S).log 2>&1 &

# 查看进程
ps aux | grep mock_amd

# 停止进程
kill $(ps aux | grep 'mock_amd' | grep -v grep | awk '{print $2}')
```

## 常用操作

### 查看 Mock AMD 状态

```bash
# 检查进程
ps aux | grep mock_amd

# 检查端口监听
sudo netstat -tulpn | grep 52364
# 或
sudo ss -tulpn | grep 52364

# 检查日志
tail -f launcher.log
```

### 实时监控协议报文

```bash
# 启动 sniffer
/usr/bin/python3 scripts/sniffer.py --bind-port 52364 --ascii-format

# 或监听镜像端口
/usr/bin/python3 scripts/sniffer.py --bind-port 52366 --ascii-format
```

### 修改配置并重启

```bash
# 1. 编辑配置
vim config/bridge_params.protocol_udp.yaml

# 2. 停止 Mock AMD
# Ctrl+C 或 kill 进程

# 3. 重新启动
bash scripts/start_lin_sim.sh both --backend protocol_udp
```

### 记录测试数据

```bash
# 带时间戳记录日志
LOG_FILE="logs/mock_amd_test_$(date +%Y%m%d_%H%M%S).log"
mkdir -p logs

bash scripts/start_lin_sim.sh both --backend protocol_udp 2>&1 | tee "$LOG_FILE"

# 或使用 sniffer 记录
/usr/bin/python3 scripts/sniffer.py --ascii-format --no-color > logs/sniffer_$(date +%Y%m%d_%H%M%S).log
```

### 性能监控

```bash
# 监控 CPU 使用
top -p $(pgrep -f mock_amd)

# 监控内存使用
watch -n 1 'ps aux | grep mock_amd'

# 监控网络流量
iftop -i lo -f "port 52364"
```

## 使用场景

### 场景 1: 协议开发与验证

**目标**: 验证 `$CKTH/$AUV` 协议实现的正确性。

**步骤**:

1. 启用 ASCII 格式日志

```yaml
# config/bridge_params.protocol_udp.yaml
protocol_udp:
  log_ascii_format: true
  log_packet_hex: true
  log_every_n: 1
```

2. 启动 Mock AMD 和 ROS2 bridge

```bash
# 终端 1: Mock AMD
bash scripts/start_lin_sim.sh both --backend protocol_udp

# 终端 2: ROS2 bridge
cd scripts
bash start_lin_brain.sh stack --backend protocol_udp
```

3. 验证协议字段

```bash
# 检查下行报文格式
grep "DOWNLINK" launcher.log | head -5

# 检查上行报文格式
grep "UPLINK" launcher.log | head -5

# 验证校验和
grep "Checksum:" launcher.log | grep -v "OK"
# 应该没有输出（所有校验和都正确）
```

### 场景 2: 控制算法测试

**目标**: 测试控制器在闭环环境下的表现。

**步骤**:

1. 配置合理的控制频率

```yaml
# config/bridge_params.protocol_udp.yaml
bridge:
  rate_hz: 50.0  # 50 Hz
```

2. 启动完整系统

```bash
# 终端 1: 仿真 + Mock AMD
bash scripts/start_lin_sim.sh both --backend protocol_udp

# 终端 2: ROS2 决策栈
bash scripts/start_lin_brain.sh stack --backend protocol_udp
```

3. 监控控制效果

```bash
# 查看深度控制
ros2 topic echo /auv/state/filtered --once | grep depth

# 查看航向控制
ros2 topic echo /auv/state/filtered --once | grep orientation

# 查看控制指令
ros2 topic echo /cmd_vel
```

4. 记录测试数据

```bash
# 记录 ROS2 bag
ros2 bag record -a -o test_control

# 记录 Mock AMD 日志
bash scripts/start_lin_sim.sh both --backend protocol_udp 2>&1 | tee control_test.log
```

### 场景 3: 长时间稳定性测试

**目标**: 测试系统长时间运行的稳定性。

**步骤**:

1. 降低日志频率

```yaml
# config/bridge_params.protocol_udp.yaml
protocol_udp:
  log_ascii_format: false  # 使用单行格式
  log_every_n: 100         # 每 100 个报文记录一次
```

2. 后台运行

```bash
# 启动 Mock AMD
nohup bash scripts/start_lin_sim.sh both --backend protocol_udp > long_run.log 2>&1 &

# 记录进程 ID
echo $! > mock_amd.pid
```

3. 监控运行状态

```bash
# 实时查看日志
tail -f long_run.log | grep -E "(ERROR|FAILED|WARN)"

# 定期检查进程
watch -n 60 'ps aux | grep mock_amd'

# 统计报文数量
watch -n 60 'grep "frame=" long_run.log | wc -l'
```

4. 测试完成后分析

```bash
# 统计总报文数
echo "总下行报文: $(grep "DOWNLINK" long_run.log | wc -l)"
echo "总上行报文: $(grep "UPLINK" long_run.log | wc -l)"

# 查找错误
grep -E "(ERROR|FAILED|WARN)" long_run.log

# 分析帧率
grep "frame=" long_run.log | awk '{print $NF}' | sort -n | uniq -c
```

### 场景 4: 多机通信测试

**目标**: 测试跨机器通信。

**步骤**:

1. 配置远程地址

```yaml
# config/bridge_params.protocol_udp.yaml
protocol_udp:
  bind_host: 0.0.0.0              # 监听所有接口
  bind_port: 52364
  remote_host: 192.168.1.100      # ROS2 bridge 所在机器
  remote_port: 52365
```

2. 配置防火墙

```bash
# 允许 UDP 端口
sudo ufw allow 52364/udp
sudo ufw allow 52365/udp
```

3. 启动测试

```bash
# 在 AUV 机器上
bash scripts/start_lin_sim.sh both --backend protocol_udp

# 在 ROS2 机器上
bash scripts/start_lin_brain.sh stack --backend protocol_udp
```

4. 验证通信

```bash
# 使用 sniffer 验证
/usr/bin/python3 scripts/sniffer.py --bind-host 0.0.0.0 --bind-port 52364
```

### 场景 5: 故障注入测试

**目标**: 测试系统对各种故障的响应。

#### 测试 1: 通信超时

```bash
# 启动系统后，停止 ROS2 bridge
kill $(pgrep -f bridge_node)

# 观察 Mock AMD 的超时处理
tail -f launcher.log
# 应该看到使用默认命令
```

#### 测试 2: 错误报文

使用测试脚本发送错误报文：

```python
#!/usr/bin/python3
import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# 发送错误格式的报文
sock.sendto(b'\x00\x00\x00\x00', ('127.0.0.1', 52364))
```

观察 Mock AMD 的错误处理。

#### 测试 3: 边界值测试

```yaml
# 修改配置发送极端值
test_commands:
  - [100, 100, 100, 100, 100]    # 全部最大
  - [-100, -100, -100, -100, -100]  # 全部最小
  - [0, 0, 0, 0, 0]               # 全部为零
```

## 故障排查

### 问题 1: Mock AMD 无法启动

**症状**: 执行启动脚本后立即退出。

**排查步骤**:

```bash
# 1. 检查 Python 环境
/usr/bin/python3 --version
which python3

# 2. 检查依赖
/usr/bin/python3 -c "import yaml; import numpy; import socket"

# 3. 检查配置文件
yamllint config/bridge_params.protocol_udp.yaml
# 或
/usr/bin/python3 -c "import yaml; yaml.safe_load(open('config/bridge_params.protocol_udp.yaml'))"

# 4. 检查端口占用
sudo netstat -tulpn | grep 52364
sudo lsof -i :52364

# 5. 查看详细错误
/usr/bin/python3 sim_holoocean/apps/run_zenoh_bridge.py --config config/bridge_params.protocol_udp.yaml
```

**常见原因**:
- 端口被占用 → 修改配置或关闭占用进程
- 配置文件语法错误 → 检查 YAML 格式
- Python 依赖缺失 → 安装缺失的包
- HoloOcean 未安装 → 安装 HoloOcean

### 问题 2: 没有收到下行命令

**症状**: Mock AMD 启动正常，但看不到 RX 日志。

**排查步骤**:

```bash
# 1. 确认 ROS2 bridge 正在运行
ps aux | grep bridge_node

# 2. 使用 sniffer 检查报文
/usr/bin/python3 scripts/sniffer.py --bind-port 52364

# 3. 检查 ROS2 bridge 配置
ros2 param get /bridge_node backend
ros2 param get /bridge_node protocol_udp.remote_host
ros2 param get /bridge_node protocol_udp.remote_port

# 4. 测试网络连通性
ping 127.0.0.1
telnet 127.0.0.1 52364

# 5. 检查防火墙
sudo ufw status
```

**常见原因**:
- ROS2 bridge 未启动 → 启动 bridge
- 端口配置不匹配 → 检查配置文件
- 防火墙阻止 → 允许端口
- ROS2 bridge 后端错误 → 确认使用 protocol_udp

### 问题 3: 上行报文未发送

**症状**: RX 正常，但没有 TX 日志。

**排查步骤**:

```bash
# 1. 检查仿真状态
# 查看 Mock AMD 日志是否有仿真错误

# 2. 检查日志配置
grep "log_packets" config/bridge_params.protocol_udp.yaml

# 3. 使用 sniffer 确认
/usr/bin/python3 scripts/sniffer.py --bind-port 52365

# 4. 检查客户端地址
# Mock AMD 会发送到最后一次接收下行命令的地址
```

**常见原因**:
- 日志被禁用 → 启用日志
- 仿真步进失败 → 检查 HoloOcean 状态
- 没有收到下行命令 → 先解决问题 2

### 问题 4: 日志格式不正确

**症状**: 日志格式混乱或缺少字段。

**排查步骤**:

```bash
# 1. 检查配置
grep -A 10 "protocol_udp:" config/bridge_params.protocol_udp.yaml

# 2. 确认配置文件被加载
# 启动时应该看到配置路径

# 3. 检查 protocol_debug 模块
/usr/bin/python3 -c "from common.protocol_debug import format_protocol_packet; print('OK')"
```

**常见原因**:
- 配置修改未生效 → 重启 Mock AMD
- protocol_debug 模块问题 → 检查 common/ 目录
- 终端不支持颜色 → 使用 `--no-color`

### 问题 5: 性能问题

**症状**: CPU 占用高或控制频率不稳定。

**排查步骤**:

```bash
# 1. 监控 CPU
top -p $(pgrep -f mock_amd)

# 2. 检查控制频率
grep "frame=" launcher.log | awk '{print $1}' | uniq -c

# 3. 检查日志频率
grep "log_every_n" config/bridge_params.protocol_udp.yaml

# 4. 降低频率测试
# 修改 rate_hz 为 10 或 20
```

**优化方案**:
- 降低日志频率 → `log_every_n: 10` 或更大
- 使用单行格式 → `log_ascii_format: false`
- 降低控制频率 → `rate_hz: 20`（仅用于测试）

## 最佳实践

### 1. 配置管理

**使用不同的配置文件**:

```bash
# 开发配置
config/bridge_params.protocol_udp.dev.yaml

# 测试配置
config/bridge_params.protocol_udp.test.yaml

# 生产配置
config/bridge_params.protocol_udp.prod.yaml
```

**管理配置差异**:

```bash
# 比较配置
diff config/bridge_params.protocol_udp.dev.yaml \
     config/bridge_params.protocol_udp.prod.yaml

# 使用版本控制
git add config/bridge_params.protocol_udp.*.yaml
```

### 2. 日志管理

**自动日志轮转**:

```bash
#!/bin/bash
# scripts/start_mock_amd_with_log.sh

LOG_DIR="logs/mock_amd"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/mock_amd_$TIMESTAMP.log"

# 启动并记录
bash scripts/start_lin_sim.sh both --backend protocol_udp 2>&1 | tee "$LOG_FILE"

# 压缩旧日志
find "$LOG_DIR" -name "mock_amd_*.log" -mtime +7 -exec gzip {} \;
```

### 3. 监控与告警

**简单的监控脚本**:

```bash
#!/bin/bash
# scripts/monitor_mock_amd.sh

while true; do
    if ! pgrep -f "mock_amd" > /dev/null; then
        echo "WARNING: Mock AMD not running!"
        # 可以添加通知逻辑
    fi

    # 检查最新日志
    LATEST_LOG=$(ls -t logs/mock_amd/*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_LOG" ]; then
        ERROR_COUNT=$(grep -c "ERROR" "$LATEST_LOG" 2>/dev/null || echo 0)
        if [ "$ERROR_COUNT" -gt 10 ]; then
            echo "WARNING: Too many errors in log!"
        fi
    fi

    sleep 60
done
```

### 4. 测试自动化

**协议验证测试**:

```bash
#!/bin/bash
# scripts/test_protocol.sh

echo "Starting Mock AMD protocol test..."

# 启动 Mock AMD
bash scripts/start_lin_sim.sh both --backend protocol_udp &
MOCK_PID=$!

# 等待启动
sleep 5

# 运行测试
/usr/bin/python3 scripts/sniffer.py --count 100 > test_results.log

# 分析结果
PACKET_COUNT=$(grep "frame=" test_results.log | wc -l)
echo "Received $PACKET_COUNT packets"

# 清理
kill $MOCK_PID

if [ "$PACKET_COUNT" -ge 100 ]; then
    echo "Test PASSED"
    exit 0
else
    echo "Test FAILED"
    exit 1
fi
```

### 5. 开发工作流

**推荐的开发流程**:

```
1. 开发阶段
   - 使用 ASCII 格式日志
   - 低频率运行（10 Hz）
   - 详细调试信息

2. 单元测试
   - 测试协议编解码
   - 测试边界条件
   - 测试错误处理

3. 集成测试
   - 正常频率运行（50 Hz）
   - 单行格式日志
   - 端到端测试

4. 稳定性测试
   - 长时间运行
   - 最低日志频率
   - 自动化监控
```

## 相关文档

- [Mock AMD 技术详解](../03_core_concepts/04_mock_amd.md) - 深入技术细节
- [Mock AMD 协议通信详解](09_mock_amd_protocol.md) - 协议层面说明
- [协议日志使用示例](06_protocol_logging_examples.md) - 日志使用技巧
- [控制调试指南](02_control_debugging.md) - 控制问题排查
