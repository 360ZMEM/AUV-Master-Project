# Rosbag 分析工具链验证日志

**日期**: 2026-06-08  
**验证对象**: `docs/user-guide/04_rosbag_analysis.md` 所列全部分析工具  
**目的**: 验证命令可用性、输出格式，并从论文写作角度评估代码结构和实验内容合理性

---

## 验证矩阵

| 工具 | 命令 | 结果 | 产出格式 |
|------|------|------|----------|
| `analyze_bag.py` | `python3 tools/analyze_bag.py <mcap> --output-dir <dir>` | ✅ 通过 | PDF + CSV + TeX |
| `offline_ekf_benchmark.py` | `python3 tools/offline_ekf_benchmark.py --input <mcap> --output-dir <dir>` | ✅ 通过 | PNG + MD |
| `analyze_turning_convergence.py` | `python3 tools/analyze_turning_convergence.py --input <mcap> --output-dir <dir>` | ✅ 通过 | PNG + MD + JSON |
| `replay_mcap_video.py` | `python3 tools/replay_mcap_video.py <mcap> --output <path> --format gif` | ❌ OOM killed | 无输出 |
| `analyze_mcap_experiments.py` | `python3 tools/analyze_mcap_experiments.py` | ✅ 通过 | 终端输出（扫描报告） |
| `replay_mcap_holoocean.py` | 需要 HoloOcean 环境 | ⚠️ 无法测试 | — |
| `capture_holoocean_video.py` | 需要 HoloOcean 环境 | ⚠️ 无法测试 | — |

---

## Step 1: analyze_bag.py — 通用 Bag 分析

```bash
python3 tools/analyze_bag.py log/experiments/benchmark_120s/rosbag_mcap/rosbag_mcap_0.mcap \
    --output-dir /tmp/analyze_test
```

**结果**: 正常完成。

**实际产出**:
```
/tmp/analyze_test/
├── trajectory_comparison.pdf       # 轨迹对比（真值 vs 估计 vs DR）
├── state_timeline.pdf              # 状态机时间线
├── system_monitoring.pdf           # 系统监控（控制量、功率、诊断）
├── uncertainty_analysis.pdf        # 协方差/不确定性分析
├── magnetic_signature.pdf          # 磁力计签名分析
├── summary_statistics.csv          # 数值统计表
├── summary_statistics_table.tex    # LaTeX booktabs 表格（直接嵌入论文）
├── state_transitions.csv           # 状态转移记录
└── state_durations.csv             # 各状态持续时间
```

**论文写作价值**:
- PDF 矢量图可直接 `\includegraphics` 嵌入 LaTeX
- TeX 表格自带 `\caption`、`\label`，格式完整
- CSV 提供原始数据供进一步处理

**文档偏差**:
- 文档描述输出为 "PNG 图表" → 实际为 **PDF**
- 文档未提及 TeX 输出能力
- `--output-dir` 参数有效且工作正常

---

## Step 2: offline_ekf_benchmark.py — EKF 离线对比

```bash
python3 tools/offline_ekf_benchmark.py \
    --input log/experiments/benchmark_120s/rosbag_mcap/rosbag_mcap_0.mcap \
    --output-dir results/localization/验证运行_20260608
```

**结果**: 正常完成（前次验证）。

**实际产出**:
```
results/localization/验证运行_20260608/
├── benchmark_results.md           # Markdown 报告
├── trajectory_xy.png              # XY 轨迹对比图
├── error_time.png                 # 误差时域变化
├── error_components.png           # XYZ 分量误差
└── innovation_residual.png        # 新息残差
```

**论文写作问题**:
- 输出格式为 **PNG**（位图），与 `analyze_bag.py` 的 PDF 不一致
- PNG 嵌入论文需额外调 DPI（默认 100dpi 可能不够期刊要求的 300dpi）
- 无 LaTeX 表格输出（RMSE 等指标在 Markdown 中，需手动转）

---

## Step 3: replay_mcap_video.py — 轨迹回放动画

```bash
python3 tools/replay_mcap_video.py \
    log/experiments/benchmark_120s/rosbag_mcap/rosbag_mcap_0.mcap \
    --output /tmp/replay_test.gif --format gif --fps 10
```

**结果**: exit code 137 (SIGKILL = OOM)。

**问题分析**:
- MCAP 包含 1155 帧（120s × ~9.6Hz），matplotlib 渲染全部帧后写 GIF
- 每帧包含 seabed_mesh + truth_marker + history_trail 等复杂 marker
- 预估内存需求：1155 帧 × ~5MB/帧 = ~5.8GB → 超出容器限制
- 脚本无 `--max-frames` 或 `--downsample` 参数控制帧数

**文档缺失**: 未提及内存限制和长录制的 OOM 风险。

**规避方法**:
```bash
# 仅适用于短时间录制（<30s / <300帧）
python3 tools/replay_mcap_video.py <short_bag>.mcap --output out.gif --fps 5
```

---

## Step 4: analyze_mcap_experiments.py — 批量扫描

```bash
python3 tools/analyze_mcap_experiments.py
```

**行为**: 扫描 `log/experiments/` 下所有 MCAP 文件，按修改时间排序输出报告。

**注意**:
- 硬编码了 `ROOT_DIR = Path("/home/auv_user/auv_ws/AUV-Master-Project")`
- 不适用于其他部署路径
- 遇到损坏 MCAP 时会报错但不中断

---

## 从论文写作角度的评估

### 当前可用于论文的完整工具链

```
录制 → 转换 → 分析 → 论文素材
sqlite3 bag → ros2 bag convert → analyze_bag.py → PDF图 + TeX表
                                 offline_ekf_benchmark → PNG图 + MD报告
```

### 已存在的问题

#### 1. 输出格式不一致（关键问题）

| 工具 | 图表格式 | 表格格式 | 论文就绪？ |
|------|----------|----------|-----------|
| `analyze_bag.py` | **PDF** | **TeX** | ✅ 直接可用 |
| `offline_ekf_benchmark.py` | PNG | Markdown | ❌ 需转换 |
| `analyze_turning_convergence.py` | PNG | Markdown | ❌ 需转换 |
| `benchmark_bt_vs_fsm.py` | 无图 | 终端文本 | ❌ 需重建 |
| `mpc_test.py` / `control_benchmark_module.py` | PNG | 终端文本 | ❌ 需转换 |

**建议**: 统一为 PDF + TeX 输出（或至少提供 `--format pdf` 选项）。

#### 2. 录制-分析链断裂（阻塞问题）

- `start_experiment.sh` 直接 MCAP 录制 → **必然损坏**
- 分析工具需要完整 MCAP → **无法接受损坏文件**
- 唯一可用路径：sqlite3 录制 + 离线转换

这意味着文档中 "一键录制+分析" 的工作流实际**不可行**。新手按文档执行必然失败。

#### 3. 缺少统一的论文素材生成命令

当前没有一个命令能从 bag 文件生成论文所需全部素材。需要分别运行：
- `analyze_bag.py`（通用图表）
- `offline_ekf_benchmark.py`（定位对比）
- `analyze_turning_convergence.py`（转向分析）

各命令的 DPI、字号、颜色方案不统一。

#### 4. MCAP 话题内容缺乏文档

从已知完好文件（57849 条消息，35 个话题）来看，数据内容丰富：

| 话题类别 | 数量 | 代表话题 | 论文用途 |
|----------|------|----------|----------|
| 传感器原始数据 | 5363条/话题 | `/auv/sensors/{imu,dvl,depth,magnetic}` | 传感器噪声分析 |
| 状态估计 | 2330条 | `/auv/state/filtered`, `/auv/state/covariance` | EKF 性能评估 |
| 控制量 | 2144条 | `/cmd_vel` | 控制器行为分析 |
| 可视化 | 1155条 | `/auv/visual/{seabed_mesh,truth_marker}` | 轨迹重建 |
| 地面真值 | 1155条 | `/auv/visual/truth_marker` | 作为 ground truth |

文档应说明各话题的含义和论文中的典型引用方式。

### 代码结构问题

1. **无统一绘图风格配置**: 各脚本各自设定 figsize、fontsize、colormap，论文图表风格不一致
2. **DPI 硬编码**: `offline_ekf_benchmark.py` 用 100dpi（不足论文要求），`analyze_bag.py` 输出 PDF（矢量，无限 DPI）
3. **地面真值来源不明确**: 部分工具从 `/auv/visual/truth_marker` (Marker 消息) 提取，部分从 `/auv/state/filtered` 回退。应有统一约定。
4. **批量运行无 Makefile/脚本**: 需手动逐一运行 5+ 脚本才能生成全部论文素材

---

## 文档修正建议

### 对 `04_rosbag_analysis.md` 的修正

1. **修正输出格式描述**: "PNG 图表" → "PDF 矢量图 + CSV + LaTeX 表格"
2. **添加 MCAP 获取前置条件**: 明确说明需要从 sqlite3 转换获得可用 MCAP
3. **添加 `replay_mcap_video.py` 的内存警告**: 推荐仅用于 <30s 的短录制
4. **补充话题含义表**: 说明各 `/auv/...` 话题在分析中的角色
5. **添加推荐工作流**: 

```bash
# 完整的"录制→分析→论文素材"工作流
# 1. 录制（sqlite3 格式，抗中断）
bash scripts/start_experiment.sh --sim-backend pvs --bag-storage sqlite3 --duration 120

# 2. 转换为 MCAP
cat > /tmp/convert.yaml << 'EOF'
output_bags:
  - uri: /auv_data/bags/<RUN_ID>/rosbag_mcap
    storage_id: mcap
EOF
ros2 bag convert -i /auv_data/bags/<RUN_ID>/rosbag -o /tmp/convert.yaml

# 3. 通用分析（PDF + TeX）
python3 tools/analyze_bag.py /auv_data/bags/<RUN_ID>/rosbag_mcap/*.mcap \
    --output-dir results/analysis/<RUN_ID>

# 4. EKF 定位对比
python3 tools/offline_ekf_benchmark.py \
    --input /auv_data/bags/<RUN_ID>/rosbag_mcap/*.mcap \
    --output-dir results/localization/<RUN_ID>
```

---

## 新手易踩的坑

| 坑点 | 后果 | 规避方法 |
|------|------|----------|
| 直接用 `--duration` 产生的 MCAP | 文件损坏，所有分析工具报错 | 改用 `--bag-storage sqlite3` + 后转换 |
| `replay_mcap_video.py` 处理长 bag | OOM kill (exit 137) | 仅用于 <30s 录制，或先裁剪 |
| 以为输出是 PNG | 实际为 PDF，用错查看器 | `analyze_bag.py` 输出 PDF，用 PDF 阅读器 |
| 分析工具找不到话题 | 返回空图表 | 确认 MCAP 包含必要话题（用 `mcap info` 检查） |
| 各工具 DPI/格式不统一 | 论文图表风格不一致 | 自行统一或只用 `analyze_bag.py` 的 PDF 输出 |
| `analyze_mcap_experiments.py` 路径硬编码 | 非默认部署路径下失败 | 修改脚本第 21 行 `ROOT_DIR` |
