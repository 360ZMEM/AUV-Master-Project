std_msgs/Header header

uint8 MODE_HOLD=0
uint8 MODE_SEARCH=1
uint8 MODE_TRACK=2

uint8 mode
bool sensor_health_ok
bool detection_authorized
bool tracking_authorized
float64 p_detect
float64 p_track
string[] contributing_sources
string[] reason_codes
string calibration_domain
bool shadow_only
