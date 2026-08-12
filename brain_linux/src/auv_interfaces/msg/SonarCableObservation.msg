# Detector-facing cable observation. Quality is recomputed downstream.
std_msgs/Header header

bool valid
float64 detector_score

# Cable pixels/points expressed in the sonar body frame [m].
float64[] point_x_m
float64[] point_y_m
float64[] point_weight

float64 contrast_to_noise_ratio
float64 visible_length_m
float64 ambiguity_margin
bool field_of_view_truncated
string detector_id
string[] quality_flags
