# Structured decision/runtime telemetry for visualization, logging, and bagging.
std_msgs/Header header

string current_behavior
string active_path
string mode

float32 confidence
uint8 leak_level
bool battery_low
float32 total_voltage_v
bool anomaly_detected

float32 depth_m
float32 target_depth_m
float32 depth_error_m

float32 speed_mps
float32 target_speed_mps

bool has_lateral_error
float32 lateral_error_m
bool has_magnetic_magnitude
float32 magnetic_magnitude

float32 seabed_clearance_m
bool seabed_proximity_warning
bool seabed_penetration_warning

bool high_priority
string note