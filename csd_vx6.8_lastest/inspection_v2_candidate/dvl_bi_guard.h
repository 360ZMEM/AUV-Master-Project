#ifndef INSPECTION_V2_DVL_BI_GUARD_H
#define INSPECTION_V2_DVL_BI_GUARD_H

/* Isolated C99 candidate: not part of the current VxWorks project build. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define DVL_BI_GUARD_LINE_CAPACITY 96u

typedef struct {
    int16_t body_x_mmps;
    int16_t body_y_mmps;
    int16_t body_z_mmps;
    uint32_t sample_sequence;
    uint32_t pc104_complete_receive_uptime_ms;
} dvl_bi_guard_sample_t;

typedef struct {
    char line[DVL_BI_GUARD_LINE_CAPACITY];
    size_t line_length;
    uint32_t sample_sequence;
    uint32_t accepted_lines;
    uint32_t rejected_bi_lines;
} dvl_bi_guard_t;

void dvl_bi_guard_reset(dvl_bi_guard_t *guard);

/* Feed arbitrarily split serial bytes. Returns the most recent complete valid
 * :BI line, if any; never changes the output for incomplete/invalid input.
 * The caller must publish x/y/z/time from this one returned struct atomically.
 */
bool dvl_bi_guard_feed(dvl_bi_guard_t *guard, const uint8_t *bytes,
                       size_t count, uint32_t complete_receive_uptime_ms,
                       dvl_bi_guard_sample_t *latest);

#endif
