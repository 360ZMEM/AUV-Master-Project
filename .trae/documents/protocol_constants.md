# AUV 协议常量速查

## Zenoh 主题路径

### 控制主题
| 常量 | 路径 | 说明 |
|------|------|------|
| `Z_PATH_CMD_VEL` | `rt/auv/control/cmd_vel` | 控制命令（Twist 消息） |
| `Z_PATH_PC_CMD_RAW` | `rt/pc/cmd_raw` | PC 原始控制命令 |

### 遥测主题
| 常量 | 路径 | 说明 |
|------|------|------|
| `Z_PATH_AUV_TELEMETRY` | `rt/auv/telemetry` | AUV 遥测数据 |
| `Z_PATH_AUV_VIZ_INTERNAL` | `rt/auv/viz/internal` | 可视化内部状态 |

### 传感器主题
| 常量 | 路径 | 必需字段 |
|------|------|----------|
| `Z_PATH_GROUND_TRUTH` | `rt/auv/sensors/ground_truth` | position_ned, rpy_ned, cable_closest_ned, cable_distance_m |
| `Z_PATH_IMU` | `rt/auv/sensors/imu` | accel_ned, gyro_ned |
| `Z_PATH_DVL` | `rt/auv/sensors/dvl` | vel_ned |
| `Z_PATH_DEPTH` | `rt/auv/sensors/depth` | depth_m |
| `Z_PATH_MAGNETIC` | `rt/auv/sensors/magnetic` | B_ned, B_norm |
| `Z_PATH_SONAR` | `rt/auv/sensors/sonar` | bins |

### 可视化主题
| 常量 | 路径 | 说明 |
|------|------|------|
| `Z_PATH_SEABED_CLOUD` | `rt/auv/visual/seabed_cloud` | 海床点云 |
| `Z_PATH_CABLE_MARKER` | `rt/auv/visual/cable_marker` | 电缆标记点 |
| `Z_PATH_TRUTH_POSE` | `rt/auv/visual/truth_pose` | 地面真值位姿 |
| `Z_PATH_HISTORY_TRAIL` | `rt/auv/visual/history_trail` | 行进轨迹 |

## 有效负载键名

### 通用元数据
| 键名 | 类型 | 说明 |
|------|------|------|
| `KEY_STEP` | int | 仿真步数 |
| `KEY_SIM_TIME` | float | 仿真时间（秒） |
| `KEY_TS` | float | 系统时间戳（Unix 秒） |

### 位置与姿态（NED 坐标系）
| 键名 | 类型 | 说明 |
|------|------|------|
| `KEY_POSITION_NED` | list[3] | 位置 [x, y, z] (m) |
| `KEY_RPY_NED` | list[3] | 欧拉角 [roll, pitch, yaw] (rad) |
| `KEY_CABLE_CLOSEST_NED` | list[3] | 最近电缆点位置 |
| `KEY_CABLE_DISTANCE_M` | float | 到电缆的距离 (m) |

### IMU 数据
| 键名 | 类型 | 说明 |
|------|------|------|
| `KEY_ACCEL_NED` | list[3] | 加速度 [m/s²] |
| `KEY_GYRO_NED` | list[3] | 角速度 [rad/s] |

### 速度与深度
| 键名 | 类型 | 说明 |
|------|------|------|
| `KEY_VEL_NED` | list[3] | 速度 [m/s] |
| `KEY_DEPTH_M` | float | 深度 (m) |
| `KEY_CONFIDENCE` | float | 置信度 (0-1) |

### 控制命令
| 键名 | 类型 | 说明 |
|------|------|------|
| `KEY_RIGHT` | float | 右舵叶偏角 (°) |
| `KEY_TOP` | float | 上舵叶偏角 (°) |
| `KEY_LEFT` | float | 左舵叶偏角 (°) |
| `KEY_BOTTOM` | float | 下舵叶偏角 (°) |
| `KEY_THRUST` | float | 推力百分比 (-100~100) |

### 二进制协议字段
| 键名 | 类型 | 说明 |
|------|------|------|
| `KEY_FRAME_NUMBER` | int | 数据帧序号 |
| `KEY_CONTROL_MODE_BYTE` | int | 控制模式字节 |
| `KEY_WORK_INSTRUCTION` | int | 工作指令字节 |
| `KEY_MAIN_MOTOR_RPM` | int | 主推进马达转速 |

### 仲裁状态
| 键名 | 类型 | 说明 |
|------|------|------|
| `KEY_ACTIVE_ARBITER` | str | 当前活跃仲裁器 |
| `KEY_AUTO_STATE` | str | 自主控制状态 |
| `KEY_DENY_REASON` | str | 自主被拒原因 |

## 二进制协议框架

### 下行协议 ($CKTH)
- **帧头**: `$CKTH` (5 字节)
- **总长度**: 72 字节
- **校验和位置**: offset 69
- **帧尾**: `0xFF 0xFF`

### 上行协议 ($AUV)
- **帧头**: `$AUV\x91` (5 字节)
- **总长度**: 145 字节
- **校验和位置**: offset 142
- **帧尾**: `0xFF 0xFF`

## 控制向量
```python
CONTROL_KEYS = (KEY_RIGHT, KEY_TOP, KEY_LEFT, KEY_BOTTOM, KEY_THRUST)
```

---

**相关文件**: `common/protocol.py`
