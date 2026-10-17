#include "dvl_bi_guard.h"

#include <string.h>

static bool ascii_space(char ch)
{
    return ch == ' ' || ch == '\t';
}

static void skip_space(const char **cursor, const char *end)
{
    while (*cursor < end && ascii_space(**cursor)) {
        ++(*cursor);
    }
}

static bool signed_decimal_field(const char **cursor, const char *end,
                                 int16_t *value)
{
    int sign = 1;
    int32_t magnitude = 0;
    bool has_digit = false;
    skip_space(cursor, end);
    if (*cursor < end && (**cursor == '+' || **cursor == '-')) {
        if (**cursor == '-') sign = -1;
        ++(*cursor);
    }
    while (*cursor < end && **cursor >= '0' && **cursor <= '9') {
        int32_t digit = **cursor - '0';
        has_digit = true;
        if (magnitude > (32767 - digit) / 10) return false;
        magnitude = magnitude * 10 + digit;
        ++(*cursor);
    }
    if (!has_digit) return false;
    skip_space(cursor, end);
    if (*cursor >= end || **cursor != ',') return false;
    ++(*cursor);
    *value = (int16_t)(sign * magnitude);
    return true;
}

static bool parse_bi_line(const char *line, size_t length,
                          dvl_bi_guard_sample_t *sample)
{
    const char *cursor;
    const char *end = line + length;
    int16_t quality;
    if (length < 4u || memcmp(line, ":BI,", 4u) != 0) return false;
    cursor = line + 4;
    if (!signed_decimal_field(&cursor, end, &sample->body_x_mmps) ||
        !signed_decimal_field(&cursor, end, &sample->body_y_mmps) ||
        !signed_decimal_field(&cursor, end, &sample->body_z_mmps) ||
        !signed_decimal_field(&cursor, end, &quality)) return false;
    (void)quality; /* Keep the documented field, but do not infer quality from it. */
    skip_space(&cursor, end);
    if (cursor >= end || *cursor != 'A') return false;
    ++cursor;
    skip_space(&cursor, end);
    return cursor == end;
}

void dvl_bi_guard_reset(dvl_bi_guard_t *guard)
{
    if (guard != NULL) memset(guard, 0, sizeof(*guard));
}

bool dvl_bi_guard_feed(dvl_bi_guard_t *guard, const uint8_t *bytes,
                       size_t count, uint32_t complete_receive_uptime_ms,
                       dvl_bi_guard_sample_t *latest)
{
    size_t i;
    bool emitted = false;
    if (guard == NULL || latest == NULL || (bytes == NULL && count != 0u)) {
        return false;
    }
    for (i = 0; i < count; ++i) {
        unsigned char ch = bytes[i];
        if (ch == ':') {
            if (guard->line_length >= 3u &&
                memcmp(guard->line, ":BI", 3u) == 0) ++guard->rejected_bi_lines;
            guard->line[0] = ':';
            guard->line_length = 1u;
            continue;
        }
        if (guard->line_length == 0u) continue;
        if (ch == '\r' || ch == '\n') {
            dvl_bi_guard_sample_t candidate;
            if (guard->line_length >= 3u &&
                memcmp(guard->line, ":BI", 3u) == 0) {
                if (parse_bi_line(guard->line, guard->line_length, &candidate)) {
                    candidate.sample_sequence = ++guard->sample_sequence;
                    candidate.pc104_complete_receive_uptime_ms =
                        complete_receive_uptime_ms;
                    *latest = candidate;
                    ++guard->accepted_lines;
                    emitted = true;
                } else {
                    ++guard->rejected_bi_lines;
                }
            }
            guard->line_length = 0u;
            continue;
        }
        if (ch < 32u || ch > 126u ||
            guard->line_length >= DVL_BI_GUARD_LINE_CAPACITY - 1u) {
            if (guard->line_length >= 3u &&
                memcmp(guard->line, ":BI", 3u) == 0) ++guard->rejected_bi_lines;
            guard->line_length = 0u;
            continue;
        }
        guard->line[guard->line_length++] = (char)ch;
    }
    return emitted;
}
