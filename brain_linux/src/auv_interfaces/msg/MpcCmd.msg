# Jetson MPC output command consumed by the bridge arbiter.
# Header timestamp is the producer timestamp for freshness checks.
std_msgs/Header header

# Source tag, typically JETSON_MPC.
string source

# Whether this command should be accepted by downstream consumers.
bool valid

# Optional producer-side health bit.
bool healthy

# Fin commands in degrees, aligned with the shared $CKTH sign convention.
float32 right_fin_deg
float32 top_fin_deg
float32 left_fin_deg
float32 bottom_fin_deg

# Main thrust command in percent.
float32 thrust_percent

# Free-form note for observability.
string note