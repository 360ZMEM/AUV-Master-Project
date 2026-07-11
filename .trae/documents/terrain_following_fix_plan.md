# 地形跟随（Terrain Following）仿真链路完整闭合修复计划

## 摘要

地形跟随的**算法层**已完整实现（`terrain_engine.py` + `terrain_perception.py`），但仿真的**感知层**存在4个断点导致无法在仿真中端到端验证。本计划旨在修复这4个断点，使"恒深控制 vs 自适应地形跟随"对比实验可在现有基准测试框架内直接运行产出数据。

---

## 当前状态分析

### 已完整实现的部分
| 模块 | 文件 | 状态 |
|------|------|------|
| 地形跟随核心算法 | `brain_linux/.../terrain_engine.py` | 完整（前瞻+LPF+安全仲裁） |
| 地形感知适配层 | `brain_linux/.../terrain_perception.py` | 完整（DVL失效补偿） |
| 控制器集成 | `brain_linux/.../auv_controller_node.py:395-414` | 完整（条件分支+防撞底） |
| feature_flags支持 | `brain_linux/config/feature_flags.yaml` | `depth_mode: 'TERRAIN_FOLLOWING'` 已定义 |
| 诊断消息字段 | `AuvDiagnostic.msg` | `seabed_clearance_m` + warning flags |
| 分析工具 | `tools/analyze_bag.py` | 已解析 seabed_clearance 系列指标 |

### 4个断点
1. **mock_amd_server altitude用平坦常量** — 第489/556行用 `seabed_z_m` 固定值
2. **VirtualSonarWrapper为纯占位** — `predict_slope()` 恒返回0.0
3. **HoloOcean Zenoh直连路径无altitude** — DVL包中只有速度，无离底高度
4. **无端到端集成测试/实验脚本** — 无法一键验证

---

## 修复方案

### 修复 1：mock_amd_server 接入动态地形

**文件**: `sim_holoocean/interfaces/mock_amd_server.py`

**原因**: 第489行 `seabed_depth_m = float(self.config.get('digital_twin', {}).get('seabed_z_m', 15.0))` 使用配置中的固定标量，完全忽略AUV当前XY位置对应的真实Perlin噪声地形。

**修改内容**:

1. 新增 import:
   ```python
   from synthetic_sensors import VirtualEnvironment
   ```

2. 在 `__init__` 中实例化 `VirtualEnvironment`（与 `holoocean_physics_bridge.py` 第146行做法一致）:
   ```python
   digital_twin_cfg = self.config.get("digital_twin", {})
   self._virtual_env = VirtualEnvironment(digital_twin_cfg)
   ```

3. 修改第489/556行的 altitude 计算（此时 `tf["position_ned"]` 已可用）:
   ```python
   # 原代码（第489行）:
   # seabed_depth_m = float(self.config.get('digital_twin', {}).get('seabed_z_m', 15.0))
   
   # 新代码：
   pos_ned = tf["position_ned"]
   seabed_depth_m = self._virtual_env.terrain_height_at(pos_ned[0], pos_ned[1])
   ```

4. 在 `VirtualEnvironment` 中暴露公共方法（避免外部调用下划线方法）:
   
   **文件**: `sim_holoocean/interfaces/synthetic_sensors.py`，在 `_terrain_height` 方法之后新增:
   ```python
   def terrain_height_at(self, x: float, y: float) -> float:
       """公共接口：查询给定 (x, y) NED位置的海底深度(Z坐标，正向下)。"""
       return self._terrain_height(x, y)
   ```

**向后兼容**: `holoocean_physics_bridge.py` 中可视化部分仍直接调用 `_terrain_height`（内部调用），无需改动。

**验证**: 运行 `protocol_udp` 后端实验，检查 `/auv/sensors/altitude` 话题是否随AUV移动呈现地形起伏变化（不再是平滑的直线）。

---

### 修复 2：Zenoh 直连路径注入 altitude

**文件**: `sim_holoocean/interfaces/holoocean_physics_bridge.py`

**原因**: `_build_sensor_packet()` 构造的 `packets["dvl"]` 只包含 `KEY_VEL_NED`，无altitude字段。而真实DVL（如Nortek DVL1000）同时输出速度和 bottom-track range（离底高度），因此将 altitude 附加到 DVL 包中是物理合理的。

**修改内容**:

1. 在步骤5（打包）中、DVL包构造处（第341-347行），计算并注入altitude:
   ```python
   # 在 dvl_noisy is not None 分支内:
   terrain_z = self.virtual_env.terrain_height_at(pos_ned[0], pos_ned[1])
   altitude_m = max(0.0, terrain_z - pos_ned[2])  # NED: terrain_z > pos_ned[2] 表示AUV在海底上方
   # 注入到DVL包中
   packets["dvl"] = {
       **base,
       KEY_VEL_NED: dvl_noisy.tolist(),
       "altitude_m": altitude_m,  # 新增字段
       "vel_water_ned": vel_water_ned,
       "current_magnitude": current_magnitude,
   }
   ```

2. 同时新增独立的 altitude 包（确保即使DVL降采样期间altitude仍有数据）:
   ```python
   # 在 packets["depth"] 之后:
   terrain_z = self.virtual_env.terrain_height_at(pos_ned[0], pos_ned[1])
   altitude_m = max(0.0, terrain_z - pos_ned[2])
   packets["altitude"] = {
       **base,
       "altitude_m": altitude_m,
   }
   ```

3. **ROS2 Bridge 侧**: 修改 `bridge_node.py` 的 `handle_json_sensor_payload()` 方法，增加对 altitude 数据的解析和发布:

   **文件**: `brain_linux/src/auv_bridge/auv_bridge/bridge_node.py`
   
   在 `handle_json_sensor_payload()` 的 dvl 分支或新增 altitude 分支中:
   ```python
   # 如果 dvl 包中含 altitude_m:
   alt = data.get("altitude_m")
   if alt is not None:
       altitude_msg = Float32()
       altitude_msg.data = float(alt)
       self.altitude_pub.publish(altitude_msg)
   ```
   
   或者新增独立的 altitude topic 处理（推荐后者，更清晰）。

4. **配置**: 在 `config/bridge_params.yaml` 的 `uplink_keys` 节中注册新 topic:
   ```yaml
   altitude: rt/auv/sensors/altitude
   ```

5. **TopicBridgeBackend**: 在 `bridge_backends.py` 的 `open()` 方法中新增 altitude topic 订阅。

**向后兼容**: 下游控制器已订阅 `/auv/sensors/altitude`（`auv_controller_node.py` 第196行），无需修改。新字段对旧的 `TopicBridgeBackend` 来说如果无法识别会被忽略（JSON格式的天然向后兼容性）。

**验证**: 启动 `zenoh_json` 后端实验，`ros2 topic echo /auv/sensors/altitude` 应能看到随AUV位置变化的非零值。

---

### 修复 3：实现前视声呐仿真

**文件**: `brain_linux/src/auv_controller/auv_controller/virtual_sonar_wrapper.py`

**原因**: terrain_engine 的前瞻预测分支需要 `abs(sonar_slope) > 1e-3` 才启用，当前占位实现始终返回0.0导致前瞻功能完全失效。

**设计**: 利用仿真侧已有的 `VirtualEnvironment._terrain_height()` 能力，在仿真侧计算前向地形斜率并通过新 Zenoh/ROS2 话题透传给控制器。

**修改内容**:

#### 3a. 仿真侧：计算前向地形斜率

**文件**: `sim_holoocean/interfaces/holoocean_physics_bridge.py`

在 `_build_sensor_packet()` 的 altitude 计算之后，添加前向斜率计算:
```python
# 前视声呐仿真：查询AUV前方的地形斜率
heading_rad = tf["rpy_ned"][2]  # 偏航角
lookahead_m = 5.0  # 前视距离
x_fwd = pos_ned[0] + lookahead_m * math.cos(heading_rad)
y_fwd = pos_ned[1] + lookahead_m * math.sin(heading_rad)
terrain_z_fwd = self.virtual_env.terrain_height_at(x_fwd, y_fwd)
terrain_z_here = self.virtual_env.terrain_height_at(pos_ned[0], pos_ned[1])
forward_terrain_slope = (terrain_z_fwd - terrain_z_here) / lookahead_m  # tan(alpha)

packets["forward_sonar"] = {
    **base,
    "slope": forward_terrain_slope,
    "lookahead_m": lookahead_m,
}
```

同样在 `mock_amd_server.py` 中类似添加（如果走 protocol_udp 路径，可通过spare字段或新话题透传）。

#### 3b. ROS2 Bridge 侧：转发前向斜率

**文件**: `brain_linux/src/auv_bridge/auv_bridge/bridge_node.py`

新增对 `forward_sonar` 话题的订阅和转发，发布到 `/auv/sensors/forward_sonar_slope`（Float32类型）。

#### 3c. 控制器侧：VirtualSonarWrapper 改为 ROS2 话题订阅

**文件**: `brain_linux/src/auv_controller/auv_controller/virtual_sonar_wrapper.py`

将占位实现改为接收外部灌入的斜率数据:
```python
class VirtualSonarWrapper:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._slope = 0.0
            cls._instance._logger = logging.getLogger("VirtualSonarWrapper")
        return cls._instance

    def update_slope(self, slope: float) -> None:
        """由外部（ROS2回调）灌入最新的前向地形斜率。"""
        self._slope = slope

    def predict_slope(self) -> float:
        """返回最新的前向地形斜率 tan(alpha)。"""
        return self._slope
```

**文件**: `brain_linux/src/auv_controller/auv_controller/auv_controller_node.py`

在控制器节点中新增订阅:
```python
self.create_subscription(Float32, '/auv/sensors/forward_sonar_slope', self._on_forward_sonar, 10)
```

回调中调用:
```python
def _on_forward_sonar(self, msg):
    self._sonar_wrapper.update_slope(msg.data)
```

**向后兼容**: 如果仿真侧不发布此话题（如旧版本仿真），`_slope` 保持默认0.0，terrain_engine 自动回退到历史斜率——完全向后兼容。

**验证**: 在倾斜地形（`terrain_slope_deg: 5.0`）上运行TERRAIN_FOLLOWING，检查 `terrain_debug` JSON中 `slope_source` 是否从 `"history"` 切换为 `"sonar"`。

---

### 修复 4：端到端集成验证（基准测试契约对齐）

**目标**: 在现有基准框架内新增地形跟踪实验，遵循 `start_experiment.sh` + `analyze_bag.py` 的流程契约。

#### 4a. 新增 feature_flags preset

**文件**: `brain_linux/config/feature_flags_terrain.yaml`（新建）
```yaml
# Terrain Following 基准实验配置
depth_mode: 'TERRAIN_FOLLOWING'
heading_mode: 'CONSTANT'
constant_depth_m: 3.0          # 目标离底高度 3m (作为 target_altitude 使用)
constant_heading_rad: 0.0
bypass_zero_effort: false
enable_behavior_tree: true
bypass_to_manual_setpoint: false
passive_mode: false
```

#### 4b. 新增地形配置 preset（起伏地形）

**文件**: `config/bridge_params_terrain.yaml`（新建，继承 `bridge_params.yaml`，仅覆盖地形参数）
```yaml
# 起伏地形场景配置 - 用于地形跟随基准测试
digital_twin:
  seabed_z_m: 15.0
  terrain_noise_amplitude_m: 2.0     # 增大到 ±2m 起伏
  terrain_noise_scale_m: 6.0         # 缩短波长到 6m（更剧烈变化）
  terrain_noise_octaves: 4           # 4层噪声
  terrain_seed: 42                   # 不同种子产生不同地形
  terrain_slope_deg: 3.0             # 3度线性斜坡
```

#### 4c. 基准实验运行脚本

**文件**: `scripts/run_terrain_benchmark.sh`（新建）
```bash
#!/usr/bin/env bash
# 地形跟随基准测试 - 对比 CONSTANT vs TERRAIN_FOLLOWING
set -euo pipefail

DURATION=${1:-120}
OUTPUT_BASE="results/control/terrain_following_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTPUT_BASE"

echo "=== Phase 1: Baseline (CONSTANT depth) ==="
# 使用默认 feature_flags (depth_mode: CONSTANT)
bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --duration "$DURATION" \
  --record-bag \
  --output-dir "$OUTPUT_BASE/baseline"

echo "=== Phase 2: Terrain Following ==="
# 切换 feature_flags 到 terrain following
bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --duration "$DURATION" \
  --record-bag \
  --feature-flags config/feature_flags_terrain.yaml \
  --output-dir "$OUTPUT_BASE/terrain_following"

echo "=== Phase 3: Analysis ==="
python tools/analyze_bag.py "$OUTPUT_BASE/baseline/rosbag/" \
  --output-dir "$OUTPUT_BASE/baseline/analysis"
python tools/analyze_bag.py "$OUTPUT_BASE/terrain_following/rosbag/" \
  --output-dir "$OUTPUT_BASE/terrain_following/analysis"

echo "Results saved to: $OUTPUT_BASE"
```

#### 4d. 分析工具扩展（最小改动）

**文件**: `tools/analyze_bag.py`

在现有的 `compute_summary_metric_rows()` 函数中，`seabed_clearance_min_m` 和 `seabed_clearance_mean_m` 已经是标准输出指标，无需新增。地形跟随实验的核心KPI直接从现有字段导出:

| KPI | 来源 | 说明 |
|-----|------|------|
| seabed_clearance_mean_m | AuvDiagnostic.seabed_clearance_m | 平均离底高度（越接近目标越好） |
| seabed_clearance_min_m | 同上 | 最小离底高度（安全性指标） |
| depth_error_rmse_m | AuvDiagnostic.depth_error_m | 深度跟踪精度 |
| seabed_proximity_ratio | 告警计数/总帧数 | 安全违规率 |

**可选扩展**（优先级低，不影响主流程）:
- 在绘图函数中新增"目标altitude vs 实际altitude"曲线
- 解析 `/auv/controller/terrain_debug` JSON话题中的 `slope_source` 统计

#### 4e. 现有 `start_experiment.sh` 兼容性

检查 `start_experiment.sh` 是否已支持 `--feature-flags` 参数。如不支持，需要添加一个参数将自定义 feature_flags 文件的路径传递给 ROS2 launch（通过 `ros2 param load` 或 launch argument）。

**如果不支持**，最简方案是在实验前临时 symlink:
```bash
cp brain_linux/config/feature_flags_terrain.yaml brain_linux/config/feature_flags.yaml
```
实验完成后恢复原文件。

---

## 依赖关系与执行顺序

```
修复1 (mock_amd altitude) ─┐
                            ├─→ 修复4 (端到端验证)
修复2 (Zenoh altitude) ────┘         │
                                     │
修复3 (前视声呐) ───────────────────→ (可选增强，不阻塞修复4)
```

- **修复1和修复2互相独立**，可并行开发
- **修复4依赖修复1或修复2**（至少一个路径的altitude数据正确）
- **修复3是增强项**，不阻塞基本的地形跟随验证（terrain_engine在无声呐数据时自动回退到历史斜率推算）

**推荐执行顺序**: 1 → 2 → 4 → 3

---

## 假设与决策

1. **地形一致性**: mock_amd_server 和 holoocean_physics_bridge 使用**相同的** `VirtualEnvironment` 实例化参数（来自同一份 `digital_twin` 配置），确保两个路径看到的地形完全相同。

2. **altitude 语义**: altitude = `terrain_z - auv_z`（NED坐标系，terrain_z > auv_z 表示AUV在海底上方），与 mock_amd_server 现有的 `max(0.0, seabed_depth - depth)` 语义一致。

3. **不修改 AuvDiagnostic.msg**: 现有字段已足够，无需新增消息字段。

4. **不修改 terrain_engine.py**: 核心算法已完整，本计划仅修复感知数据源。

5. **前视声呐的lookahead距离**: 使用固定5m（可配置化留给后续），这与 terrain_engine 的 `lookahead_time_s=2.0` × 典型航速 `1.5 m/s` ≈ 3m 在同一量级。

6. **PVS后端兼容**: PVS后端使用 `MockAmdUdpServer`（修复1自动覆盖），或直接走独立main.py（不经过ROS2栈，不影响）。

---

## 验证步骤

### 单元验证
1. 修改 `terrain_slope_deg: 5.0` 后启动 `protocol_udp` 仿真 → `ros2 topic echo /auv/sensors/altitude` 应看到值随X位置线性变化
2. 切换到 `zenoh_json` 后端重复上述测试 → 同样的结果
3. 设置 `depth_mode: 'TERRAIN_FOLLOWING'` → `terrain_debug` JSON中 `slope_source` 在斜坡区段应为 `"sonar"`（修复3后）

### 集成验证
4. 运行 `run_terrain_benchmark.sh` 生成对比数据
5. 检查 baseline 的 `seabed_clearance` 波动大于 terrain_following 的波动
6. 检查 terrain_following 的 `seabed_clearance_mean_m` 接近目标 altitude（3.0m）

### 回归验证
7. 保持默认 `feature_flags.yaml`（`depth_mode: 'CONSTANT'`）运行现有实验 → 行为与修复前完全一致
8. `analyze_bag.py` 对旧 rosbag 的解析结果不变

---

## 涉及文件清单

| 文件 | 操作 | 修复编号 |
|------|------|----------|
| `sim_holoocean/interfaces/synthetic_sensors.py` | 新增 `terrain_height_at()` 公共方法 | 1,2,3 |
| `sim_holoocean/interfaces/mock_amd_server.py` | import VirtualEnvironment + 修改altitude计算 | 1 |
| `sim_holoocean/interfaces/holoocean_physics_bridge.py` | 新增altitude包 + forward_sonar包 | 2,3 |
| `brain_linux/src/auv_bridge/auv_bridge/bridge_node.py` | 新增altitude/forward_sonar话题处理 | 2,3 |
| `brain_linux/src/auv_bridge/auv_bridge/bridge_backends.py` | TopicBridgeBackend订阅altitude topic | 2 |
| `brain_linux/src/auv_controller/auv_controller/virtual_sonar_wrapper.py` | 改为数据驱动实现 | 3 |
| `brain_linux/src/auv_controller/auv_controller/auv_controller_node.py` | 新增forward_sonar订阅回调 | 3 |
| `config/bridge_params.yaml` | uplink_keys新增altitude和forward_sonar | 2,3 |
| `brain_linux/config/feature_flags_terrain.yaml` | 新建：TF实验preset | 4 |
| `config/bridge_params_terrain.yaml` | 新建：起伏地形场景参数 | 4 |
| `scripts/run_terrain_benchmark.sh` | 新建：对比实验脚本 | 4 |
