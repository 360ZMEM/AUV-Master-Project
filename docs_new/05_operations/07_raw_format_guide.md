# 原始格式使用指南

本文档专门介绍协议报文的原始紧凑格式（CSV 输出）。

## 什么是原始格式

原始格式是一种**极简的 CSV 输出格式**，直接以协议标识开头，后面跟随逗号分隔的数值，**没有任何字段名或解释**。

### 输出示例

```
$CKTH,138,1,238,0,15.0,10.0,-15.0,-10.0,50.0,750,0,87.2
$AUV,138,1,238,0,7.60,87.2,0.5,0.0,0.000000,0.000000,48.0,12.0,750,15.0,10.0,-15.0,-10.0
$CKTH,139,1,238,0,20.0,15.0,-20.0,-15.0,60.0,800,0,90.5
$AUV,139,1,238,0,7.65,90.5,0.6,0.1,0.000000,0.000000,48.0,12.5,800,20.0,15.0,-20.0,-15.0
```

### 优势

| 特性 | 说明 |
|------|------|
| **极简输出** | 一行一个报文，无冗余信息 |
| **易于解析** | 标准 CSV 格式，任何编程语言都能处理 |
| **快速浏览** | 密度高，一屏可看更多报文 |
| **脚本友好** | 可直接用 awk/grep/cut 处理 |
| **文件小** | 相比 ASCII 格式节省 90% 空间 |

## 启用原始格式

### 方法 1: 配置文件（Mock AMD）

```yaml
# config/bridge_params.protocol_udp.yaml
protocol_udp:
  log_raw_format: true    # 启用原始格式
  log_packets: true
```

### 方法 2: Sniffer 命令行

```bash
# 使用原始格式
/usr/bin/python3 scripts/sniffer.py --raw-format

# 原始格式 + 保存到文件
/usr/bin/python3 scripts/sniffer.py --raw-format > raw_log.csv

# 原始格式 + 只捕获 100 个报文
/usr/bin/python3 scripts/sniffer.py --raw-format --count 100
```

### 方法 3: 临时切换

```bash
# 快速启用
vim config/bridge_params.protocol_udp.yaml
# 修改: log_raw_format: true

# 运行测试
bash start_lin_sim.sh both --backend protocol_udp

# 测试完成后恢复
vim config/bridge_params.protocol_udp.yaml
# 修改: log_raw_format: false
```

## 字段定义

### 下行报文 ($CKTH)

```
$CKTH,帧号,目标地址,模式字节,指令,右舵,上舵,左舵,下舵,推力,主电机RPM,侧推RPM,航向
```

| 字段 | 类型 | 说明 |
|------|------|------|
| 帧号 | int | 报文序号（递增） |
| 目标地址 | int | 目标设备地址 |
| 模式字节 | int | 控制模式（238=自主，221=手动） |
| 指令 | int | 工作指令 |
| 右舵 | float | 右舵角度（度） |
| 上舵 | float | 上舵角度（度） |
| 左舵 | float | 左舵角度（度） |
| 下舵 | float | 下舵角度（度） |
| 推力 | float | 主推力（百分比） |
| 主电机RPM | int | 主电机转速 |
| 侧推RPM | int | 侧推器转速 |
| 航向 | float | 目标航向（度） |

### 上行报文 ($AUV)

```
$AUV,帧号,AUV地址,模式字节,指令,深度,航向,俯仰,横滚,GPS经度,GPS纬度,电压,电流,主电机RPM,右舵,上舵,左舵,下舵
```

| 字段 | 类型 | 说明 |
|------|------|------|
| 帧号 | int | 报文序号 |
| AUV地址 | int | AUV 设备地址 |
| 模式字节 | int | 控制模式 |
| 指令 | int | 工作指令 |
| 深度 | float | 当前深度（米） |
| 航向 | float | 当前航向（度） |
| 俯仰 | float | 俯仰角（度） |
| 横滚 | float | 横滚角（度） |
| GPS经度 | float | GPS 经度（度） |
| GPS纬度 | float | GPS 纬度（度） |
| 电压 | float | 总电压（伏） |
| 电流 | float | 总电流（安） |
| 主电机RPM | int | 主电机实际转速 |
| 右舵 | float | 右舵实际角度 |
| 上舵 | float | 上舵实际角度 |
| 左舵 | float | 左舵实际角度 |
| 下舵 | float | 下舵实际角度 |

## 脚本处理示例

### Bash 脚本

#### 提取特定字段

```bash
# 提取所有下行报文的推力值
awk -F',' '$1=="$CKTH" {print $10}' raw_log.csv

# 提取所有上行报文的深度值
awk -F',' '$1=="$AUV" {print $6}' raw_log.csv

# 提取帧号和模式字节
awk -F',' '{print $1, $2, $4}' raw_log.csv
```

#### 统计分析

```bash
# 统计报文数量
echo "下行: $(grep -c '^$CKTH' raw_log.csv)"
echo "上行: $(grep -c '^$AUV' raw_log.csv)"

# 统计各模式出现次数
awk -F',' '{print $1, $4}' raw_log.csv | sort | uniq -c

# 查找特定帧号
awk -F',' '$2==138' raw_log.csv

# 计算平均深度
awk -F',' '$1=="$AUV" {sum+=$6; count++} END {print "平均深度:", sum/count, "米"}' raw_log.csv
```

#### 数据验证

```bash
# 检查是否有解析错误
grep 'DECODE_ERROR' raw_log.csv

# 验证帧号是否连续
awk -F',' '{print $2}' raw_log.csv | awk 'NR>1 && $1!=prev+1 {print "不连续:", prev, $1} {prev=$1}'

# 检查深度范围
awk -F',' '$1=="$AUV" && $6>100 || $6<0' raw_log.csv
```

### Python 脚本

#### 读取和解析

```python
import csv

def read_raw_log(filename):
    """读取原始格式日志"""
    downlink_packets = []
    uplink_packets = []

    with open(filename, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            parts = line.split(',')
            if parts[0] == '$CKTH':
                # 解析下行报文
                packet = {
                    'frame': int(parts[1]),
                    'obj': int(parts[2]),
                    'mode': int(parts[3]),
                    'right': float(parts[5]),
                    'top': float(parts[6]),
                    'left': float(parts[7]),
                    'bottom': float(parts[8]),
                    'thrust': float(parts[9]),
                    'rpm': int(parts[10]),
                    'heading': float(parts[12]),
                }
                downlink_packets.append(packet)

            elif parts[0] == '$AUV':
                # 解析上行报文
                packet = {
                    'frame': int(parts[1]),
                    'auv': int(parts[2]),
                    'mode': int(parts[3]),
                    'depth': float(parts[5]),
                    'heading': float(parts[6]),
                    'voltage': float(parts[11]),
                    'current': float(parts[12]),
                    'rpm': int(parts[13]),
                }
                uplink_packets.append(packet)

    return downlink_packets, uplink_packets

# 使用示例
downlink, uplink = read_raw_log('raw_log.csv')

# 分析深度变化
for i in range(len(uplink) - 1):
    depth_change = uplink[i+1]['depth'] - uplink[i]['depth']
    print(f"帧 {uplink[i]['frame']}: 深度变化 {depth_change:.3f}m")
```

#### 数据转换

```python
import csv
import json

def csv_to_json(csv_file, json_file):
    """将 CSV 格式转换为 JSON"""
    data = []

    with open(csv_file, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if row[0] == '$CKTH':
                data.append({
                    'type': 'downlink',
                    'frame': int(row[1]),
                    'mode': int(row[3]),
                    'thrust': float(row[9]),
                })

    with open(json_file, 'w') as f:
        json.dump(data, f, indent=2)

# 使用
csv_to_json('raw_log.csv', 'output.json')
```

### Excel/电子表格

#### 直接导入

1. 打开 Excel
2. 数据 → 从文本/CSV
3. 选择 `raw_log.csv`
4. 设置逗号作为分隔符
5. 完成

#### 数据透视表

导入后可以创建数据透视表：
- 行：帧号
- 列：模式字节
- 值：深度、推力等

## 实用场景

### 场景 1: 快速查找异常

```bash
# 查找推力超过 80% 的报文
awk -F',' '$1=="$CKTH" && $9>80' raw_log.csv

# 查找深度超过 20m 的报文
awk -F',' '$1=="$AUV" && $6>20' raw_log.csv

# 查找模式切换点
awk -F',' '$4!=prev_mode {print "模式变化:", $2, $4} {prev_mode=$4}' raw_log.csv
```

### 场景 2: 性能分析

```bash
# 计算报文频率
total_time=$(tail -1 raw_log.csv | awk -F',' '{print $2}')  # 假设第一列是时间戳
total_packets=$(wc -l < raw_log.csv)
echo "平均频率: $(echo "scale=2; $total_packets / $total_time" | bc) Hz"

# 查找丢帧
awk -F',' '{print $2}' raw_log.csv | awk 'NR>1 && $1!=prev+1 {print "丢帧:", prev, $1} {prev=$1}'
```

### 场景 3: 数据导出

```bash
# 只导出深度和航向数据
awk -F',' '$1=="$AUV" {print $2, $6, $7}' raw_log.csv > depth_heading.csv

# 导出为制表符分隔（适合 Excel）
awk -F',' '$1=="$AUV" {print $2 "\t" $6 "\t" $7}' raw_log.csv > depth_heading.tsv

# 导出特定时间范围
awk -F',' '$2>=100 && $2<=200' raw_log.csv > segment.csv
```

### 场景 4: 实时监控

```bash
# 实时显示深度变化
tail -f raw_log.csv | awk -F',' '$1=="$AUV" {print "深度:", $6, "m"}'

# 实时监控模式变化
tail -f raw_log.csv | awk -F',' '$4!=prev {print "模式变化: 帧号="$2", 新模式="$4} {prev=$4}'

# 实时报警
tail -f raw_log.csv | awk -F',' '$1=="$AUV" && $6>20 {print "警告: 深度超过 20m! 帧号="$2}'
```

## 格式对比

| 特性 | 单行摘要 | ASCII 详细 | 原始紧凑 ⭐ |
|------|---------|-----------|-----------|
| 可读性 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| 信息密度 | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| 脚本处理 | ⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ |
| 文件大小 | 中 | 大 | 小 |
| 调试效率 | 中 | 高 | 中 |
| 正常运行 | ✅ 推荐 | ❌ 冗长 | ✅ 推荐 |
| 问题诊断 | ⚠️ 一般 | ✅ 最好 | ⚠️ 一般 |

## 最佳实践

### 选择建议

- **正常运行监控**: 使用原始格式
- **问题诊断**: 使用 ASCII 详细格式
- **人工查看**: 使用单行摘要格式
- **长期存储**: 使用原始格式（节省空间）

### 组合使用

```bash
# 终端 1: 单行摘要（人工监控）
bash start_lin_sim.sh both --backend protocol_udp

# 终端 2: 原始格式（保存到文件）
/usr/bin/python3 scripts/sniffer.py --raw-format > raw_$(date +%Y%m%d_%H%M%S).csv

# 需要调试时切换到 ASCII 格式
vim config/bridge_params.protocol_udp.yaml
# 设置 log_ascii_format: true
```

### 日志轮转

```bash
# 按时间轮转
while true; do
    /usr/bin/python3 scripts/sniffer.py --raw-format > raw_$(date +%Y%m%d_%H%M%S).csv
    sleep 3600  # 每小时一个文件
done
```

## 相关文档

- [日志解读指南](05_log_analysis.md) - 所有日志格式详解
- [协议日志示例](06_protocol_logging_examples.md) - 使用示例
- [控制调试](02_control_debugging.md) - 控制问题排查
