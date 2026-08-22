# Bridge arbiter status for ROS2-side observability.
std_msgs/Header header

# Effective control owner and its source.
string active_arbiter
string arbiter_source

# Autonomy handshake status and failure reason.
string auto_state
string deny_reason

# Effective bytes that will be sent to the binary protocol.
uint8 effective_control_mode_byte
uint8 effective_work_instruction

# High-level readiness flags.
bool autonomy_allowed
bool mpc_command_valid

# Latest AMD uplink freshness used by the guard.
float32 telemetry_freshness_ms

# PC104 execution-brain fault state decoded from $AUV Sys_Abnorm_Inf.
uint32 pc104_sys_abnorm_info
bool pc104_system_comm_fault
bool pc104_dvl_lost
bool pc104_jetson_timeout

# Free-form note for debugging.
string note
