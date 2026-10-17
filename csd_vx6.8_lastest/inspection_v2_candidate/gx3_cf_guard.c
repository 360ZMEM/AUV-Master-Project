/* Isolated C99 candidate. This file is not linked into current VxWorks tasks. */
#include "gx3_cf_guard.h"

#include <math.h>
#include <string.h>

static uint32_t read_u32_be(const uint8_t *data)
{
    return ((uint32_t)data[0] << 24) | ((uint32_t)data[1] << 16)
           | ((uint32_t)data[2] << 8) | (uint32_t)data[3];
}

static float read_float_be(const uint8_t *data)
{
    const uint32_t bits = read_u32_be(data);
    float value = 0.0f;
    memcpy(&value, &bits, sizeof(value));
    return value;
}

void gx3_cf_parser_init(Gx3CfParser *parser, uint32_t max_gap_ticks)
{
    if (parser == NULL) {
        return;
    }
    memset(parser, 0, sizeof(*parser));
    parser->max_gap_ticks = max_gap_ticks;
}

bool gx3_cf_decode_frame(const uint8_t *frame, size_t length, Gx3CfSample *sample)
{
    uint32_t checksum = 0u;
    uint16_t reported;
    float values[6];
    size_t index;

    if (frame == NULL || sample == NULL || length != GX3_CF_FRAME_SIZE
            || frame[0] != 0xCFu || sizeof(float) != 4u) {
        return false;
    }
    for (index = 0u; index < GX3_CF_FRAME_SIZE - 2u; ++index) {
        checksum += frame[index];
    }
    reported = (uint16_t)(((uint16_t)frame[29] << 8) | frame[30]);
    if ((uint16_t)checksum != reported) {
        return false;
    }
    for (index = 0u; index < 6u; ++index) {
        values[index] = read_float_be(frame + 1u + index * 4u);
        if (!isfinite(values[index])) {
            return false;
        }
    }
    sample->roll_rad = values[0];
    sample->pitch_rad = values[1];
    sample->yaw_rad = values[2];
    sample->angular_rate_x_rps = values[3];
    sample->angular_rate_y_rps = values[4];
    sample->angular_rate_z_rps = values[5];
    sample->sensor_timer_ticks = read_u32_be(frame + 25u);
    sample->unwrapped_timer_ticks = 0u;
    return true;
}

static bool advance_timer(Gx3CfParser *parser, Gx3CfSample *sample)
{
    uint64_t candidate;
    const uint64_t modulus = (uint64_t)1u << 32;

    if (parser->max_gap_ticks == 0u) {
        return false;
    }
    if (!parser->have_timer) {
        sample->unwrapped_timer_ticks = sample->sensor_timer_ticks;
        return true;
    }
    candidate = (parser->last_unwrapped_timer_ticks / modulus) * modulus
                + sample->sensor_timer_ticks;
    if (candidate <= parser->last_unwrapped_timer_ticks) {
        candidate += modulus;
    }
    if (candidate - parser->last_unwrapped_timer_ticks > parser->max_gap_ticks) {
        return false;
    }
    sample->unwrapped_timer_ticks = candidate;
    return true;
}

static void resynchronize_after_bad_frame(Gx3CfParser *parser)
{
    size_t offset;
    for (offset = 1u; offset < GX3_CF_FRAME_SIZE; ++offset) {
        if (parser->buffer[offset] == 0xCFu) {
            const size_t remaining = GX3_CF_FRAME_SIZE - offset;
            memmove(parser->buffer, parser->buffer + offset, remaining);
            parser->buffered = remaining;
            return;
        }
    }
    parser->buffered = 0u;
}

size_t gx3_cf_feed(Gx3CfParser *parser, const uint8_t *bytes, size_t length,
                   Gx3CfSample *latest_sample)
{
    size_t index;
    size_t accepted = 0u;
    Gx3CfSample sample;

    if (parser == NULL || bytes == NULL || latest_sample == NULL) {
        return 0u;
    }
    for (index = 0u; index < length; ++index) {
        if (parser->buffered == 0u && bytes[index] != 0xCFu) {
            continue;
        }
        parser->buffer[parser->buffered++] = bytes[index];
        if (parser->buffered != GX3_CF_FRAME_SIZE) {
            continue;
        }
        if (!gx3_cf_decode_frame(parser->buffer, GX3_CF_FRAME_SIZE, &sample)) {
            ++parser->rejected_frames;
            resynchronize_after_bad_frame(parser);
            continue;
        }
        parser->buffered = 0u;
        if (!advance_timer(parser, &sample)) {
            ++parser->rejected_frames;
            continue;
        }
        parser->have_timer = true;
        parser->last_unwrapped_timer_ticks = sample.unwrapped_timer_ticks;
        ++parser->accepted_frames;
        ++accepted;
        *latest_sample = sample;
    }
    return accepted;
}
