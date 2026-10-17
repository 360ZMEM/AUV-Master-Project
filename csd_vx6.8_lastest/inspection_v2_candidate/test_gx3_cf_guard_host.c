/* Host fault injection for the isolated VxWorks-portable parser candidate. */
#include "gx3_cf_guard.h"

#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static void put_u32_be(uint8_t *destination, uint32_t value)
{
    destination[0] = (uint8_t)(value >> 24);
    destination[1] = (uint8_t)(value >> 16);
    destination[2] = (uint8_t)(value >> 8);
    destination[3] = (uint8_t)value;
}

static void make_frame(uint8_t frame[GX3_CF_FRAME_SIZE], uint32_t timer)
{
    const float values[6] = {0.1f, -0.2f, 0.3f, 1.0f, 2.0f, 3.0f};
    uint32_t sum = 0u;
    size_t index;
    memset(frame, 0, GX3_CF_FRAME_SIZE);
    frame[0] = 0xCFu;
    for (index = 0u; index < 6u; ++index) {
        uint32_t bits;
        memcpy(&bits, &values[index], sizeof(bits));
        put_u32_be(frame + 1u + index * 4u, bits);
    }
    put_u32_be(frame + 25u, timer);
    for (index = 0u; index < GX3_CF_FRAME_SIZE - 2u; ++index) {
        sum += frame[index];
    }
    frame[29] = (uint8_t)(sum >> 8);
    frame[30] = (uint8_t)sum;
}

int main(void)
{
    Gx3CfParser parser;
    Gx3CfSample sample;
    uint8_t first[GX3_CF_FRAME_SIZE];
    uint8_t second[GX3_CF_FRAME_SIZE];
    uint8_t corrupt[GX3_CF_FRAME_SIZE];
    uint8_t input[2u * GX3_CF_FRAME_SIZE + 2u];
    const uint8_t noise[2] = {0x00u, 0x12u};

    assert(GX3_CF_FRAME_SIZE == 31u);
    make_frame(first, 100000u);
    gx3_cf_parser_init(&parser, 5u * GX3_CF_TIMER_TICKS_PER_SECOND);
    assert(!gx3_cf_decode_frame(first, 25u, &sample));
    assert(gx3_cf_feed(&parser, noise, sizeof(noise), &sample) == 0u);
    assert(gx3_cf_feed(&parser, first, 12u, &sample) == 0u);
    assert(gx3_cf_feed(&parser, first + 12u, GX3_CF_FRAME_SIZE - 12u, &sample) == 1u);
    assert(sample.sensor_timer_ticks == 100000u);
    assert(fabsf(sample.yaw_rad - 0.3f) < 1e-6f);
    assert(parser.accepted_frames == 1u);

    /* A valid-looking header is insufficient; checksum failure must not refresh. */
    memcpy(corrupt, first, sizeof(corrupt));
    corrupt[10] ^= 1u;
    assert(gx3_cf_feed(&parser, corrupt, sizeof(corrupt), &sample) == 0u);
    assert(parser.rejected_frames >= 1u);
    assert(parser.last_unwrapped_timer_ticks == 100000u);

    /* Repeated and reset sensor timer do not become fresh PC104 samples. */
    make_frame(second, 100000u);
    assert(gx3_cf_feed(&parser, second, sizeof(second), &sample) == 0u);
    make_frame(second, 90000u);
    assert(gx3_cf_feed(&parser, second, sizeof(second), &sample) == 0u);
    make_frame(second, 100000u + GX3_CF_TIMER_TICKS_PER_SECOND);
    assert(gx3_cf_feed(&parser, second, sizeof(second), &sample) == 1u);
    assert(sample.unwrapped_timer_ticks == 162500u);

    /* Garbage and a bad frame followed by a valid frame resynchronize. */
    make_frame(first, 200000u);
    memcpy(corrupt, first, sizeof(corrupt));
    corrupt[5] ^= 1u;
    input[0] = 0xFFu;
    input[1] = 0x01u;
    memcpy(input + 2u, corrupt, GX3_CF_FRAME_SIZE);
    memcpy(input + 2u + GX3_CF_FRAME_SIZE, first, GX3_CF_FRAME_SIZE);
    assert(gx3_cf_feed(&parser, input, sizeof(input), &sample) == 1u);
    assert(sample.sensor_timer_ticks == 200000u);

    /* The only accepted decrease is a bounded 32-bit rollover. */
    gx3_cf_parser_init(&parser, 5u * GX3_CF_TIMER_TICKS_PER_SECOND);
    make_frame(first, UINT32_MAX - 31249u);
    make_frame(second, 31250u);
    assert(gx3_cf_feed(&parser, first, sizeof(first), &sample) == 1u);
    assert(gx3_cf_feed(&parser, second, sizeof(second), &sample) == 1u);
    assert(sample.unwrapped_timer_ticks == (uint64_t)UINT32_MAX + 1u + 31250u);

    /* A frame with a NaN and a correct checksum is still rejected. */
    make_frame(first, 40000u);
    put_u32_be(first + 1u, 0x7FC00000u);
    {
        uint32_t sum = 0u;
        size_t index;
        for (index = 0u; index < GX3_CF_FRAME_SIZE - 2u; ++index) {
            sum += first[index];
        }
        first[29] = (uint8_t)(sum >> 8);
        first[30] = (uint8_t)sum;
    }
    assert(!gx3_cf_decode_frame(first, sizeof(first), &sample));

    puts("GX3 CF host parser fault injection passed");
    return 0;
}
