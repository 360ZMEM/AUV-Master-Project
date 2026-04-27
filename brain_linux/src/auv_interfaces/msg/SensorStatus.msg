# AUV 决策输入状态消息
# 说明：
# 1) 该消息用于决策层输入，优先保持字段稳定；
# 2) 其中 confidence 与 leak_level 是本轮需求的强制字段；
# 3) 其余字段是最小可用补充，用于让行为树具备可解释的决策输入。

# 置信度（0.0~1.0），由传感融合/识别算法给出。
float32 confidence

# 漏水等级（按严重程度编码）
# 0: 无漏水
# 1: 内部漏水
# 2: 外部漏水
# 3: 内外同时漏水
uint8 leak_level
uint8 LEAK_NONE=0
uint8 LEAK_INTERNAL=1
uint8 LEAK_EXTERNAL=2
uint8 LEAK_BOTH=3

# 电池低电告警（由上层估算或直接输入）
bool battery_low

# 当前总电压（V）
float32 total_voltage_v

# 异常检测标志（如磁异常/姿态异常/执行器异常）
bool anomaly_detected

# 当前深度（米）
float32 depth_m

# 当前航速（米/秒）
float32 speed_mps

# 海底参考深度（米）
float32 seabed_depth_m

# 到海底的剩余净空（米），小于等于 0 表示已穿底
float32 seabed_clearance_m

# 接近海底告警（保留提前减速语义）
bool seabed_proximity_warning

# 穿过海底告警（保留紧急上浮语义）
bool seabed_penetration_warning

# 当前航向（弧度，NED 坐标系）
float32 heading_rad

# Mock AMD 时钟时间戳（Unix 微秒），用于解析轨迹模式时间同步
int64 mock_amd_timestamp_us

# 算法透明度级别（0:AUTO, 1:HOLD, 2:PATH, 3:FULL）
uint8 debug_level
uint8 DEBUG_AUTO=0
uint8 DEBUG_HOLD=1
uint8 DEBUG_PATH=2
uint8 DEBUG_FULL=3
