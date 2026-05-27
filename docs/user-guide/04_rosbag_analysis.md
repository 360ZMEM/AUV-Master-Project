# MCAP 数据分析工具链

本文档说明如何对实验产出的 rosbag（.mcap）数据进行离线分析。

## 数据来源

`start_experiment.sh` 在每次实验启动时会自动录制 rosbag 数据，存储路径为：

```
$AUV_DATA_ROOT/bags/YYYYMMDD_HHMMSS/*.mcap
```

其中 `YYYYMMDD_HHMMSS` 为实验启动时的时间戳。每次实验结束后可在该目录下找到对应的 `.mcap` 文件。

## 核心分析工具

| 工具 | 功能 | 命令 |
|------|------|------|
| tools/analyze_bag.py | 通用 MCAP 分析（轨迹/误差/磁场） | `python tools/analyze_bag.py /path/to/bag.mcap --output-dir ./figures` |
| tools/analyze_mcap_experiments.py | 实验异常检测 | `python tools/analyze_mcap_experiments.py` |
| tools/enhanced_benchmark_analysis.py | 增强定位诊断（坐标系镜像检测等） | `python tools/enhanced_benchmark_analysis.py --input bag.mcap --output-dir ./results` |
| tools/offline_ekf_benchmark.py | 离线 EKF 基准对比（Raw DR/StdEKF/ES-EKF） | `python tools/offline_ekf_benchmark.py --input bag.mcap --output-dir ./results` |
| tools/analyze_turning_convergence.py | 转向段收敛分析 | `python tools/analyze_turning_convergence.py --input bag.mcap --output-dir ./turning_analysis` |

### 使用示例

```bash
# 通用分析：生成轨迹对比图、误差曲线、磁场数据
python tools/analyze_bag.py $AUV_DATA_ROOT/bags/20260101_120000/recording.mcap --output-dir ./figures

# 实验异常检测：扫描所有已录制的bag文件
python tools/analyze_mcap_experiments.py

# 增强定位诊断：检测坐标系镜像等问题
python tools/enhanced_benchmark_analysis.py --input bag.mcap --output-dir ./results

# 离线EKF对比：Raw DR / StdEKF / ES-EKF 三算法基准
python tools/offline_ekf_benchmark.py --input bag.mcap --output-dir ./results

# 转向段收敛分析
python tools/analyze_turning_convergence.py --input bag.mcap --output-dir ./turning_analysis
```

## 输出解读

### 轨迹对比图

分析工具会生成轨迹对比图，包含以下三条曲线：

- **ground_truth**（绿色）：仿真器提供的真值位姿
- **filtered**（蓝色）：EKF 融合后的状态估计
- **raw_dr**（红色）：纯航位推算（Dead Reckoning），仅靠 IMU+DVL 积分

三者对比可以直观看出 EKF 融合相对于纯推算的改善程度，以及与真值之间的偏差。

### RMSE / CEP 指标

- **RMSE（Root Mean Square Error）**：各时刻位置误差的均方根，单位为米。值越小说明整体精度越高。
- **CEP（Circular Error Probable）**：50% 概率误差圆半径。即 50% 的位置估计落在以真值为圆心、CEP 为半径的圆内。

### 控制量曲线

控制量曲线展示 `cmd_vel` 话题的输出：

- **linear.x**：纵向推力指令（前进/后退）
- **linear.z**：垂向推力指令（上浮/下潜）
- **angular.z**：偏航力矩指令（转向舵角）

可用于判断控制器是否饱和、是否存在震荡等问题。

### 误差时域分量图

独立显示 X、Y、Z 三轴误差随时间的演化：

- **X 误差**：纵向（前进方向）位置偏差
- **Y 误差**：横向位置偏差
- **Z 误差**：深度偏差

可用于定位特定轴向的漂移或突变问题。

## 视频生成工具

| 工具 | 功能 | 命令 |
|------|------|------|
| tools/replay_mcap_video.py | 离线轨迹动画（无需 HoloOcean） | `python tools/replay_mcap_video.py bag.mcap --output replay.gif --fps 24` |
| tools/replay_mcap_holoocean.py | HoloOcean 内回放+录制 | `python tools/replay_mcap_holoocean.py bag.mcap --output replay.mp4` |
| tools/capture_holoocean_video.py | 实时 HoloOcean 录制 | `python tools/capture_holoocean_video.py --format gif` |

### 使用说明

```bash
# 离线轨迹动画：不需要启动HoloOcean，纯数据驱动生成GIF/MP4
python tools/replay_mcap_video.py bag.mcap --output replay.gif --fps 24

# HoloOcean回放：在仿真环境中重现录制的轨迹并录制视频
python tools/replay_mcap_holoocean.py bag.mcap --output replay.mp4

# 实时录制：在HoloOcean运行期间捕获画面
python tools/capture_holoocean_video.py --format gif
```

## PVS 全流程产物阅读顺序建议

完成一次 PVS（Plan-Verify-Summarize）实验后，建议按以下顺序查阅产出物：

1. **实验日志** — 确认实验是否正常结束、有无异常退出
2. **轨迹对比图** — 快速判断整体定位质量（ground_truth vs filtered vs raw_dr）
3. **RMSE/CEP 指标** — 量化定位精度
4. **误差时域分量图** — 定位各轴偏差来源
5. **控制量曲线** — 检查控制器表现（饱和/震荡/稳态）
6. **转向段收敛分析** — 确认航向变化时 EKF 的收敛速度
7. **异常检测报告** — 排查传感器丢失、数值跳变等问题
8. **视频回放** — 直观确认 AUV 运动行为
