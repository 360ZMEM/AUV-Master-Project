/* Print one C-encoded golden record for the Python decoder cross-check. */
#include "imu_provenance_sidecar_v1.h"

#include <assert.h>
#include <stdio.h>

int main(void)
{
    Gx3CfSample sample = {0};
    uint8_t wire[IMU_PROVENANCE_V1_WIRE_SIZE];
    size_t index;
    sample.roll_rad = 0.1f;
    sample.pitch_rad = -0.2f;
    sample.yaw_rad = 0.3f;
    sample.angular_rate_x_rps = 1.0f;
    sample.angular_rate_y_rps = 2.0f;
    sample.angular_rate_z_rps = 3.0f;
    sample.sensor_timer_ticks = 125000u;
    assert(imu_provenance_v1_encode(&sample, 0x127fu, 23u, 4390u, wire));
    for (index = 0u; index < sizeof(wire); ++index) {
        printf("%02x", wire[index]);
    }
    putchar('\n');
    return 0;
}
