# AUV 决策输出目标消息
# 说明：
# 该消息承载行为树输出的目标运动状态，供控制层执行。

# 行为模式名称（如 EMERGENCY_SURFACE / PARALLEL_TRACKING / ZIGZAG_SEARCH）
string mode

# 桥接后端选择（如 zenoh_json / protocol_udp）
string bridge_backend

# 协议控制模式字节（protocol_udp 模式下用于 Ctrl_Mode）
uint8 control_mode_byte

# 目标深度（米）
float32 target_depth_m

# 目标速度（米/秒）
float32 target_speed_mps

# 正弦扰动参数（用于并行巡检等轨迹控制）
float32 sine_amplitude
float32 sine_period_s

# 是否高优先级（紧急上浮等）
bool high_priority

# 备注信息（调试/可视化）
string note
