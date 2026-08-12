# Time-aligned calibrated magnetic waveform block for coherent processing.
std_msgs/Header header

float64 sample_rate_hz
uint32 sample_count

# Seconds relative to header.stamp. Arrays must all have sample_count entries.
float64[] time_offset_s
float64[] x_nt
float64[] y_nt
float64[] z_nt

float64 clipping_ratio
float64 data_completeness
uint64 dropped_sample_count
bool calibration_valid
string calibration_id
bool sample_clock_verified
string status
