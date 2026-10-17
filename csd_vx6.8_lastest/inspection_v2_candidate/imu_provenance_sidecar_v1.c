/* Fixed-size companion record. It is not sent by current PC104 firmware. */
#include "imu_provenance_sidecar_v1.h"

#include <math.h>
#include <string.h>

static void put_u16_be(uint8_t *destination, uint16_t value)
{
    destination[0] = (uint8_t)(value >> 8);
    destination[1] = (uint8_t)value;
}

static void put_u32_be(uint8_t *destination, uint32_t value)
{
    destination[0] = (uint8_t)(value >> 24);
    destination[1] = (uint8_t)(value >> 16);
    destination[2] = (uint8_t)(value >> 8);
    destination[3] = (uint8_t)value;
}

static void put_float_be(uint8_t *destination, float value)
{
    uint32_t bits;
    memcpy(&bits, &value, sizeof(bits));
    put_u32_be(destination, bits);
}

static uint32_t crc32_ieee(const uint8_t *bytes, size_t length)
{
    uint32_t result = 0xFFFFFFFFu;
    size_t index;
    for (index = 0u; index < length; ++index) {
        unsigned bit;
        result ^= bytes[index];
        for (bit = 0u; bit < 8u; ++bit) {
            result = (result >> 1) ^ ((result & 1u) != 0u ? 0xEDB88320u : 0u);
        }
    }
    return ~result;
}

bool imu_provenance_v1_encode(const Gx3CfSample *sample,
                              uint16_t original_frame_checksum,
                              uint32_t sample_sequence,
                              uint32_t pc104_receive_uptime_ms,
                              uint8_t output[IMU_PROVENANCE_V1_WIRE_SIZE])
{
    const float *values[6];
    size_t index;
    if (sample == NULL || output == NULL || sizeof(float) != 4u) {
        return false;
    }
    values[0] = &sample->roll_rad;
    values[1] = &sample->pitch_rad;
    values[2] = &sample->yaw_rad;
    values[3] = &sample->angular_rate_x_rps;
    values[4] = &sample->angular_rate_y_rps;
    values[5] = &sample->angular_rate_z_rps;
    for (index = 0u; index < 6u; ++index) {
        if (!isfinite(*values[index])) {
            return false;
        }
    }
    memset(output, 0, IMU_PROVENANCE_V1_WIRE_SIZE);
    output[0] = 'I';
    output[1] = 'M';
    output[2] = 'V';
    output[3] = '1';
    output[4] = 1u;
    output[5] = 1u;  /* Complete 0xCF frame validated by the UART parser. */
    put_u16_be(output + 6u, original_frame_checksum);
    put_u32_be(output + 8u, sample_sequence);
    put_u32_be(output + 12u, sample->sensor_timer_ticks);
    put_u32_be(output + 16u, pc104_receive_uptime_ms);
    for (index = 0u; index < 6u; ++index) {
        put_float_be(output + 20u + index * 4u, *values[index]);
    }
    put_u32_be(output + 44u, crc32_ieee(output, 44u));
    return true;
}
