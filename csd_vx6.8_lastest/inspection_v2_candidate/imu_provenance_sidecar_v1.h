#ifndef INSPECTION_V2_IMU_PROVENANCE_SIDECAR_V1_H
#define INSPECTION_V2_IMU_PROVENANCE_SIDECAR_V1_H

#include "gx3_cf_guard.h"

#define IMU_PROVENANCE_V1_WIRE_SIZE 48u

bool imu_provenance_v1_encode(const Gx3CfSample *sample,
                              uint16_t original_frame_checksum,
                              uint32_t sample_sequence,
                              uint32_t pc104_receive_uptime_ms,
                              uint8_t output[IMU_PROVENANCE_V1_WIRE_SIZE]);

#endif
