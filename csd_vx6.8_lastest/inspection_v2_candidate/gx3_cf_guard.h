#ifndef INSPECTION_V2_GX3_CF_GUARD_H
#define INSPECTION_V2_GX3_CF_GUARD_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define GX3_CF_FRAME_SIZE 31u
#define GX3_CF_TIMER_TICKS_PER_SECOND 62500u

typedef struct {
    float roll_rad;
    float pitch_rad;
    float yaw_rad;
    float angular_rate_x_rps;
    float angular_rate_y_rps;
    float angular_rate_z_rps;
    uint32_t sensor_timer_ticks;
    uint64_t unwrapped_timer_ticks;
} Gx3CfSample;

typedef struct {
    uint8_t buffer[GX3_CF_FRAME_SIZE];
    size_t buffered;
    bool have_timer;
    uint64_t last_unwrapped_timer_ticks;
    uint32_t max_gap_ticks;
    uint32_t accepted_frames;
    uint32_t rejected_frames;
} Gx3CfParser;

void gx3_cf_parser_init(Gx3CfParser *parser, uint32_t max_gap_ticks);
bool gx3_cf_decode_frame(const uint8_t *frame, size_t length, Gx3CfSample *sample);
size_t gx3_cf_feed(Gx3CfParser *parser, const uint8_t *bytes, size_t length,
                   Gx3CfSample *latest_sample);

#endif
