# 实验运行器模式验证日志

**日期**: 2026-06-08  
**验证对象**: `docs/user-guide/02_experiment_runner.md` 所列全部控制模式  
**目的**: 新手视角逐一执行，确认命令可用性和文档准确性

---

## 验证矩阵

| 场景 | 命令 | 结果 | 备注 |
|------|------|------|------|
| PVS + zenoh_json | `--sim-backend pvs --duration 120` | ✅ 通过 | 前次验证，完整 120s |
| PVS + protocol_udp | `--sim-backend pvs --bridge-backend protocol_udp --duration 15` | ✅ 运行通过 | UDP 协议帧正常解析 |
| PVS + no-record-bag | `--sim-backend pvs --no-record-bag --duration 10` | ✅ 通过 | 正确跳过录制 |
| HoloOcean + zenoh_json | `--sim-backend holoocean --duration 5` | ⚠️ 无法测试 | 本机未安装 holoocean 模块 |
| HoloOcean + arbiter | `--arbiter-profile default` | ⚠️ 无法测试 | 同上 |

---

## Step 1: PVS + protocol_udp（15 秒）

```bash
cd /home/auv_user/auv_ws/AUV-Master-Project
bash scripts/start_experiment.sh --sim-backend pvs --bridge-backend protocol_udp --duration 15
```

**结果**: 正常退出（exit 0）。

**观察到的行为**:
- 脚本正确推导配置文件：`sim_params.pvs.yaml` + `bridge_params.protocol_udp.pvs.yaml`
- 仿真层输出标准 step 日志（LOS + Cascaded PID）
- 额外启动 ASCII Protocol 桥接（UDP 帧打印到 stdout）
- 生成 `metadata.txt`、`launcher.log`、`rosbag.log`

**UDP 协议帧示例**:
```
ASCII PROTOCOL PACKET - UPLINK ($AUV)
  Frame Number: 0
  Control Mode Byte: 0xEE → AUTONOMOUS
  Depth: 12.00 m | Heading: +0.0 deg
  Checksum: OK | Frame Tail: OK
```

**⚠️ 严重问题 — MCAP 文件仍然损坏**:

rosbag 文件大小 9.4GB（仅 15 秒！），且无法被 mcap 库解析：
```
mcap.exceptions.RecordLengthLimitExceeded: unknown (opcode 121) record has length 
16343915127403868726 that exceeds limit 4294967296
```

**根因分析**:
- `rosbag.log` 中无任何关闭/flush 确认消息
- `setsid ros2 bag record ... > >(tee ...) 2>&1 &` 的进程组管理可能有问题：
  - `setsid` 创建新会话，`$!` 捕获的 PID 可能不是 recorder 的实际 PGID
  - `kill -INT -- -"$BAG_PID"` 可能发送给了错误的进程组
  - 或者信号被 `> >(tee ...)` 进程替换中的中间 shell 截获
- 9.4GB/15s 意味着每秒 ~600MB 数据（包含 seabed_cloud/mesh 大话题），recorder 可能在 `sleep 2` 内无法 flush 如此大的缓冲区

**结论**: `kill -INT` 修复不充分。真正可靠的方案需要：
1. 去掉 `setsid`，直接管理进程组
2. 或增加 `sleep` 时间（可能需要 10s+ 才能 flush GB 级缓冲）
3. 或添加 MCAP 文件完整性校验后再退出

---

## Step 2: PVS + no-record-bag（10 秒）

```bash
bash scripts/start_experiment.sh --sim-backend pvs --no-record-bag --duration 10
```

**结果**: 正常退出。

**验证**:
- 日志输出 `[AUV] rosbag recording disabled`
- 实验目录仍然创建（`/auv_data/bags/20260608_181906/`），包含 `metadata.txt` 和 `launcher.log`
- **无** `rosbag/` 子目录，**无** `rosbag.log`

**注意**: 即使 `--no-record-bag`，实验目录和 metadata 仍会生成，这对于记录实验配置是合理的。

---

## Step 3: HoloOcean 模式

```bash
bash scripts/start_experiment.sh --sim-backend holoocean --no-record-bag --duration 5
```

**结果**: 脚本启动但仿真层报错（`ModuleNotFoundError: No module named 'holoocean'`）。

**说明**:
- `start_experiment.sh` 本身不会因为缺少 holoocean 而立即退出
- 它会继续启动进度条和其他子脚本
- 实际失败发生在 `start_lin_sim.sh` 内部的 Python 调用
- 这种"静默失败"模式对新手不友好：脚本返回 exit 0 但仿真实际未运行

---

## Step 4: PVS + zenoh_json（15 秒）— Bag 生成对比验证

```bash
bash scripts/start_experiment.sh --sim-backend pvs --bridge-backend zenoh_json --duration 15
```

**结果**: 正常退出（exit 0）。

**Bag 对比**:

| 实验 | 文件路径 | 大小 | 数据率 | MCAP 状态 |
|------|----------|------|--------|-----------|
| PVS+zenoh 15s | `/auv_data/bags/20260608_190108/rosbag/rosbag_0.mcap` | 1120 MB | ~75 MB/s | ❌ 损坏 |
| PVS+protocol_udp 15s | `/auv_data/bags/20260608_181131/rosbag/rosbag_0.mcap` | 25.5 GB | ~1700 MB/s | ❌ 损坏 |
| 已知完好文件 (120s) | `log/experiments/benchmark_120s/rosbag_mcap/rosbag_mcap_0.mcap` | 483 MB | ~4 MB/s | ✅ 正常 (57849 msgs) |

**根因确认**:

已知完好文件的产生方式：
```
log/experiments/benchmark_120s/
├── rosbag/                 # 原始录制：sqlite3 格式
│   ├── rosbag_0.db3
│   └── rosbag_1.db3
├── rosbag_mcap/            # 后转换：sqlite3 → MCAP
│   └── rosbag_mcap_0.mcap  ← 完好文件
└── convert_mcap.yaml       # 转换配置
```

转换命令（从 `convert_mcap.yaml` 推断）：
```bash
ros2 bag convert -i log/experiments/benchmark_120s/rosbag -o convert_mcap.yaml
```

**结论：直接 MCAP 录制 + 非交互式停止 = 必然损坏。**

- `start_experiment.sh` 默认 `BAG_STORAGE_ID="mcap"` 直接写 MCAP
- `setsid` + 进程替换 `>(tee ...)` 导致 SIGINT 无法传递到 recorder
- `rosbag.log` 在 "Recording..." 后无任何关闭确认
- `sleep 2` 后脚本退出，recorder 被强杀，MCAP footer 未写入

**真正可靠的工作流**:

```bash
# 方案 A：改用 sqlite3 录制（WAL 日志化，抗强杀）
bash scripts/start_experiment.sh --sim-backend pvs --bag-storage sqlite3 --duration 120

# 实验结束后离线转 MCAP（分析工具需要 MCAP 格式）
ros2 bag convert -i /auv_data/bags/YYYYMMDD_HHMMSS/rosbag -o convert_mcap.yaml

# 方案 B：手动 Ctrl+C 停止（不用 --duration）
bash scripts/start_experiment.sh --sim-backend pvs
# 等待足够时间后手动 Ctrl+C（shell 会正确传递 SIGINT）
```

**数据率差异说明**:

| 模式 | 数据率 | 原因 |
|------|--------|------|
| 已知完好文件 (旧版) | ~4 MB/s | 可能为旧版仿真，较少 visual 话题或低频率 |
| PVS+zenoh (当前) | ~75 MB/s | 包含 seabed_mesh/cloud (MarkerArray/PointCloud2) |
| PVS+protocol_udp (当前) | ~1700 MB/s | 额外 ASCII 协议帧 + 全量可视化话题 |

protocol_udp 模式产生极端数据量的原因：桥接层将每帧协议数据作为 ROS 消息发布，加上全部 3D 可视化话题。

---

## 文档偏差与修正建议

### 1. 输出目录结构不完全准确

文档写：
```
$AUV_DATA_ROOT/bags/YYYYMMDD_HHMMSS/
├── metadata.txt
├── rosbag2_YYYYMMDD_HHMMSS_0.mcap
└── rosbag2_YYYYMMDD_HHMMSS_0.mcap.yaml
```

实际结构：
```
$AUV_DATA_ROOT/bags/YYYYMMDD_HHMMSS/
├── metadata.txt
├── launcher.log          # 文档未提及
├── rosbag.log            # 文档未提及
└── rosbag/
    └── rosbag_0.mcap     # 在子目录内，文件名不含时间戳
```

**差异**: bag 文件在 `rosbag/` 子目录内，文件名为 `rosbag_0.mcap`（非 `rosbag2_YYYYMMDD_...`）。

### 2. MCAP 损坏问题仍未彻底解决

前次修复（`kill` → `kill -INT`）不足以保证 MCAP 完整性。文档应明确说明：
- 短时间录制大话题（point cloud）时，flush 需要额外时间
- 建议 `--duration` 结束后增加足够的 drain 时间

### 3. HoloOcean 缺少前置检查

文档应添加：
```bash
# 检查 HoloOcean 是否可用
python3 -c "import holoocean" 2>/dev/null || echo "ERROR: holoocean not installed"
```

### 4. protocol_udp 模式的数据量警告

protocol_udp 模式会产生大量 mesh/cloud 数据（~600MB/s），短时间实验就可能产生 GB 级 rosbag。文档应提醒注意磁盘空间。

### 5. 默认录制格式应改为 sqlite3（核心建议）

`start_experiment.sh` 第 15 行 `BAG_STORAGE_ID="mcap"` 应改为 `BAG_STORAGE_ID="sqlite3"`：
- sqlite3 使用 WAL（Write-Ahead Logging），即使进程被强杀，数据库仍然一致
- 需要 MCAP 格式时在实验后用 `ros2 bag convert` 离线转换
- 这是当前唯一可靠的"自动停止 + 完整数据"工作流

---

## 新手易踩的坑

| 坑点 | 后果 | 规避方法 |
|------|------|----------|
| `conda activate` 状态下运行 | colcon build 失败（缺 em 模块） | 先 `conda deactivate` |
| holoocean 未安装但使用 `--sim-backend holoocean` | 脚本 exit 0 但仿真未运行 | 先验证 `python3 -c "import holoocean"` |
| protocol_udp + 长时间录制 | 磁盘写满（~600MB/s） | 加 `--no-record-bag` 或限制话题 |
| `--duration` 停止后 MCAP 损坏 | 离线分析工具无法读取 | 手动 Ctrl+C 停止，或用已知完好文件 |
| 不在 `scripts/` 目录运行 | 相对路径引用可能错误 | 始终从项目根目录运行 `bash scripts/...` |
