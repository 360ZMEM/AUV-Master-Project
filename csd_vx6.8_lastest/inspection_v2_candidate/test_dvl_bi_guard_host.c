#include "dvl_bi_guard.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static bool feed_text(dvl_bi_guard_t *guard, const char *text, uint32_t uptime,
                      dvl_bi_guard_sample_t *sample)
{
    return dvl_bi_guard_feed(guard, (const uint8_t *)text, strlen(text),
                             uptime, sample);
}

int main(void)
{
    dvl_bi_guard_t guard;
    dvl_bi_guard_sample_t sample = {111, 222, 333, 444, 555};
    uint32_t state = 0x12345678u;
    size_t i;
    dvl_bi_guard_reset(&guard);

    assert(!feed_text(&guard, "noise:BI, +300, -5,", 1000u, &sample));
    assert(sample.body_x_mmps == 111 && sample.sample_sequence == 444u);
    assert(feed_text(&guard, " +20, +00,A\r\n", 1010u, &sample));
    assert(sample.body_x_mmps == 300 && sample.body_y_mmps == -5);
    assert(sample.body_z_mmps == 20 && sample.sample_sequence == 1u);
    assert(sample.pc104_complete_receive_uptime_ms == 1010u);

    assert(!feed_text(&guard, ":BI, +300\r", 1020u, &sample));
    assert(!feed_text(&guard, ":BI, +300, +0, +0, +00,V\n", 1030u, &sample));
    assert(!feed_text(&guard, ":BI, +999999999999999999999999, +0, +0, +00,A\n",
                      1040u, &sample));
    assert(!feed_text(&guard, ":BI, +300, +0, +0, +00,Agarbage\n", 1050u, &sample));
    assert(!feed_text(&guard, ":WI, +300, +0, +0, +00,A\n", 1060u, &sample));
    assert(sample.sample_sequence == 1u && sample.pc104_complete_receive_uptime_ms == 1010u);
    assert(guard.accepted_lines == 1u && guard.rejected_bi_lines == 4u);

    assert(feed_text(&guard, ":BI, -250, +10, 0, +00,A\n", 1070u, &sample));
    assert(sample.sample_sequence == 2u && sample.body_x_mmps == -250);
    assert(sample.pc104_complete_receive_uptime_ms == 1070u);

    /* Arbitrary serial garbage, including embedded NUL and truncated BI
     * records, may not crash or create an unchecked velocity sample. */
    for (i = 0; i < 200000u; ++i) {
        uint8_t data[7];
        size_t j;
        for (j = 0; j < sizeof(data); ++j) {
            state = state * 1664525u + 1013904223u;
            data[j] = (uint8_t)(state >> 24);
        }
        (void)dvl_bi_guard_feed(&guard, data, sizeof(data),
                                1080u + (uint32_t)i, &sample);
    }
    printf("dvl_bi_guard_host: accepted=%u rejected_bi=%u\n",
           guard.accepted_lines, guard.rejected_bi_lines);
    return 0;
}
