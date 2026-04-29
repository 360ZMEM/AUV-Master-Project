# 协议日志使用示例

本文档提供 Mock AMD 测试和协议日志的详细使用示例。

## 目录

1. [快速开始](#快速开始)
2. [ASCII 格式日志](#ascii-格式日志)
3. [Sniffer 使用](#sniffer-使用)
4. [日志解读实战](#日志解读实战)
5. [常见场景](#常见场景)

## 快速开始

### 方式 1: 使用默认单行格式

```bash
# 启动仿真（默认单行格式）
cd ~/AUV_Master_Project/scripts
bash start_lin_sim.sh both --backend protocol_udp
```

输出示例：
```
[mock-amd RX][CKTH][127.0.0.1:52364] frame=138 obj=1 mode=0xEE instr=0x00 cmd=(15.0,10.0,-15.0,-10.0,50.0) main_rpm=750 side_rpm=0 heading=87.2deg
[mock-amd TX][AUV][127.0.0.1:52365] frame=138 auv=1 mode=0xEE instr=0x00 depth=7.60m heading=87.2deg gps=(0.000000,0.000000) voltage=48.0V cmd=(15.0,10.0,-15.0,-10.0,750) step=051690
```

### 方式 2: 使用详细 ASCII 格式

编辑配置文件：
```yaml
# config/bridge_params.protocol_udp.yaml
protocol_udp:
  log_ascii_format: true   # 启用 ASCII 格式
  log_packets: true
  log_packet_hex: false
```

然后启动：
```bash
bash start_lin_sim.sh both --backend protocol_udp
```

输出示例：
```
==================================================
ASCII PROTOCOL PACKET - DOWNLINK ($CKTH)
Timestamp: 2026-04-10 23:54:12.123
Source: 127.0.0.1:52364
--------------------------------------------------
HEADER INFO:
  Frame Number: 138
  Object Address: 1
  Control Mode Byte: 0xEE
    → AUTONOMOUS (自主模式)
  Work Instruction: 0x00

CONTROL SURFACES:
  Right Fin:    +15.0 deg
  Top Fin:      +10.0 deg
  Left Fin:     -15.0 deg
  Bottom Fin:   -10.0 deg
  Thrust:       +50.0 %

MOTORS:
  Main Motor:  750 RPM
  Side Motor:    0 RPM

NAVIGATION:
  Target Heading:  +87.2 deg

FRAME INTEGRITY:
  Checksum: OK
    Expected: 0x7A
    Actual:   0x7A
  Frame Tail: OK
    Expected: 0xFFFF
    Actual:   0xFFFF
==================================================

[mock-amd TX] UPLINK
... (上行报文)
```

## ASCII 格式日志

### 配置选项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `log_packets` | bool | true | 是否记录报文 |
| `log_ascii_format` | bool | false | 是否使用 ASCII 格式 |
| `log_packet_hex` | bool | false | 是否包含十六进制 |
| `log_hex_bytes` | int | 48 | 十六进制显示字节数 |
| `log_every_n` | int | 1 | 每 N 个报文记录一次 |

### 启用 ASCII 格式

#### 方法 1: 配置文件（推荐）

```yaml
# config/bridge_params.protocol_udp.yaml
protocol_udp:
  log_ascii_format: true
  log_packets: true
  log_every_n: 1  # 每 1 个报文记录一次（所有报文）
```

#### 方法 2: 临时修改（测试用）

```bash
# 使用 sed 临时启用
sed -i 's/log_ascii_format: false/log_ascii_format: true/' \
  config/bridge_params.protocol_udp.yaml

# 运行测试
bash start_lin_sim.sh both --backend protocol_udp

# 恢复原设置
sed -i 's/log_ascii_format: true/log_ascii_format: false/' \
  config/bridge_params.protocol_udp.yaml
```

### ASCII 格式优势

| 特性 | 单行格式 | ASCII 格式 |
|------|---------|-----------|
| 可读性 | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| 详细程度 | 基础 | 完整 |
| 调试效率 | 一般 | 优秀 |
| 日志大小 | 小 | 大 |
| 性能影响 | 低 | 中 |
| 推荐场景 | 正常运行 | 问题诊断 |

## Sniffer 使用

### 基本用法

```bash
# 默认模式（单行摘要）
/usr/bin/python3 scripts/sniffer.py

# 显示十六进制
/usr/bin/python3 scripts/sniffer.py --show-hex

# ASCII 格式（推荐）
/usr/bin/python3 scripts/sniffer.py --ascii-format
```

### 高级选项

```bash
# 绑定到不同端口
/usr/bin/python3 scripts/sniffer.py --bind-port 52366

# 只捕获 10 个报文
/usr/bin/python3 scripts/sniffer.py --count 10

# ASCII 格式，禁用时间戳
/usr/bin/python3 scripts/sniffer.py --ascii-format --no-timestamp

# ASCII 格式，禁用颜色
/usr/bin/python3 scripts/sniffer.py --ascii-format --no-color > sniffer.log
```

### Sniffer 镜像端口

配置文件中的镜像设置：
```yaml
# config/bridge_params.protocol_udp.yaml
protocol_udp:
  sniffer_mirror_host: 127.0.0.1
  sniffer_mirror_port: 52366
```

这样 Mock AMD 会将所有报文镜像到 52366 端口，sniffer 可以监听该端口而不影响正常通信。

### 组合使用示例

```bash
# 终端 1: 启动仿真和桥接
cd ~/AUV_Master_Project/scripts
bash start_lin_sim.sh both --backend protocol_udp

# 终端 2: 监听主端口
/usr/bin/python3 scripts/sniffer.py --bind-port 52364 --ascii-format

# 终端 3: 监听镜像端口
/usr/bin/python3 scripts/sniffer.py --bind-port 52366 --ascii-format --no-color > mirror.log
```

## 日志解读实战

### 场景 1: 检查控制命令是否到达

**问题**: 控制器在运行，但 AUV 没有响应。

**步骤**:

1. 启动 ASCII 格式日志
2. 查看下行报文中的 `cmd` 字段

```bash
# 查看推力是否非零
grep "Thrust:" launcher.log | grep -v "Thrust:      +0.0 %"
```

3. 检查控制模式字节
```bash
# 确认是自主模式
grep "Control Mode Byte:" launcher.log
# 期望: 0xEE (AUTONOMOUS)
```

### 场景 2: 验证状态反馈

**问题**: 需要确认 AUV 状态是否正确回传。

**步骤**:

1. 查看上行报文中的深度数据
```bash
grep "Depth:" launcher.log | tail -10
```

2. 查看航向数据
```bash
grep "Heading:" launcher.log | tail -10
```

3. 验证校验和
```bash
grep "Checksum:" launcher.log | grep -v "Checksum: OK"
# 应该没有输出（所有校验和都正确）
```

### 场景 3: 跟踪控制模式切换

**问题**: 需要观察从手动到自主的切换过程。

**步骤**:

1. 提取所有控制模式字节
```bash
grep "Control Mode Byte:" launcher.log | awk '{print $1, $NF}'
```

2. 统计各模式出现次数
```bash
grep "Control Mode Byte:" launcher.log | awk '{print $NF}' | sort | uniq -c
```

3. 查找模式切换点
```bash
grep "Control Mode Byte:" launcher.log | grep -A1 -B1 "0xDD"
```

### 场景 4: 性能分析

**问题**: 需要分析通信频率和延迟。

**步骤**:

1. 计算报文频率
```bash
# 下行频率
grep "DOWNLINK" launcher.log | wc -l

# 上行频率
grep "UPLINK" launcher.log | wc -l
```

2. 查看时间戳间隔
```bash
grep "Timestamp:" launcher.log | awk '{print $2}' | uniq -c
```

## 常见场景

### 场景 A: 协议调试

**目标**: 验证协议实现是否正确。

**配置**:
```yaml
log_ascii_format: true
log_packet_hex: true
log_every_n: 1
```

**命令**:
```bash
bash start_lin_sim.sh both --backend protocol_udp 2>&1 | tee debug.log
```

**分析**:
1. 检查校验和是否全部通过
2. 验证帧尾是否正确
3. 确认字段值在合理范围内

### 场景 B: 长时间运行

**目标**: 监控长时间运行的稳定性。

**配置**:
```yaml
log_ascii_format: false  # 单行格式减少日志量
log_every_n: 10          # 每 10 个报文记录一次
```

**命令**:
```bash
bash start_lin_sim.sh both --backend protocol_udp > long_run.log 2>&1 &
```

**监控**:
```bash
# 实时查看错误
tail -f long_run.log | grep -E "(FAILED|MISMATCH|ERROR)"

# 统计报文数量
grep "frame=" long_run.log | wc -l
```

### 场景 C: 问题复现

**目标**: 捕获特定问题的现场。

**步骤**:

1. 启用详细日志
```yaml
log_ascii_format: true
log_every_n: 1
```

2. 重现问题

3. 保存日志
```bash
cp launcher.log problem_$(date +%Y%m%d_%H%M%S).log
```

4. 分析日志
```bash
# 查找错误
grep -E "(FAILED|MISMATCH|ERROR)" problem_*.log

# 查看错误上下文
grep -B5 -A5 "FAILED" problem_*.log
```

### 场景 D: 性能基准

**目标**: 测量通信性能。

**命令**:
```bash
# 记录时间戳
/usr/bin/python3 scripts/sniffer.py --ascii-format --count 1000 > benchmark.log

# 分析时间戳
grep "Timestamp:" benchmark.log | \
  awk 'NR>1 {print $2}' | \
  awk 'NR>1 {print $0-prev; prev=$0}' | \
  awk '{sum+=$1; count++} END {print "平均间隔:", sum/count, "秒"}'
```

## 日志文件管理

### 日志轮转

```bash
# 创建带时间戳的日志
LOG_FILE="logs/protocol_$(date +%Y%m%d_%H%M%S).log"
mkdir -p logs
bash start_lin_sim.sh both --backend protocol_passwd > "$LOG_FILE" 2>&1
```

### 日志压缩

```bash
# 压缩旧日志
gzip logs/protocol_*.log

# 查看压缩日志
zcat logs/protocol_*.log.gz | grep "Timestamp:"
```

### 日志清理

```bash
# 删除 7 天前的日志
find logs/ -name "protocol_*.log.gz" -mtime +7 -delete
```

## 故障排查

### 问题 1: 没有日志输出

**检查**:
```bash
# 确认日志配置
grep "log_ascii_format" config/bridge_params.protocol_udp.yaml

# 确认报文正在传输
/usr/bin/python3 scripts/sniffer.py
```

### 问题 2: ASCII 格式不生效

**原因**: 配置文件修改后需要重启。

**解决**:
```bash
# 停止当前运行
# Ctrl+C

# 重新启动
bash start_lin_sim.sh both --backend protocol_udp
```

### 问题 3: 日志文件过大

**解决**:
```yaml
# 降低日志频率
log_every_n: 10  # 只记录 1/10 的报文

# 或使用单行格式
log_ascii_format: false
```

## 相关文档

- [日志解读指南](05_log_analysis.md) - 详细的日志解读方法
- [协议调试](02_control_debugging.md) - 控制问题排查
- [命令参考](../06_reference/03_command_reference.md) - sniffer 命令

## 快速参考

### 常用命令

```bash
# 启用 ASCII 日志
vim config/bridge_params.protocol_udp.yaml  # 设置 log_ascii_format: true
bash start_lin_sim.sh both --backend protocol_udp

# 使用 sniffer
/usr/bin/python3 scripts/sniffer.py --ascii-format --count 10

# 分析日志
grep "Control Mode Byte:" launcher.log | sort | uniq -c
grep "Checksum:" launcher.log | grep -v "OK"
```

### 配置位置

```
协议配置: config/bridge_params.protocol_udp.yaml
Sniffer:   scripts/sniffer.py
日志:      launcher.log, sniffer.log
```

### 关键端口

```
主端口:     52364
远程端口:   52365
镜像端口:   52366
```
