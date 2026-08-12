# Calibrated, source-specific perception quality.
std_msgs/Header header

uint8 VALIDITY_INVALID=0
uint8 VALIDITY_DEGRADED=1
uint8 VALIDITY_VALID=2

string source
uint8 validity
string[] reason_codes

# Raw evidence remains meaningful when no probability calibration is loaded.
float64 detection_score
float64 p_detect
float64 p_track
bool detection_probability_calibrated
bool track_probability_calibrated

# Cable-relative estimate: cross-track [m], heading [rad], burial depth [m].
# Unobserved components and covariance entries are NaN.
float64[3] estimate
float64[9] covariance

float64 age_s
uint32 sample_count
float64 data_completeness
string calibration_id
