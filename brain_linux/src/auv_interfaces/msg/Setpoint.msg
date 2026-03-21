# Behavior-tree intent setpoint for controller.
std_msgs/Header header

string mode
float32 target_depth_m
float32 target_heading_rad
float32 target_speed_mps

bool track_cable
float32 sine_amplitude
float32 sine_period_s

bool high_priority
string note
