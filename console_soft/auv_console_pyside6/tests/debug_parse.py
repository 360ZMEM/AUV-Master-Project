#!/usr/bin/env python3
"""
Debug script to analyze text log format in detail
"""

import re

def debug_text_file(filepath):
    """Debug text file parsing with detailed output"""

    print("="*80)
    print("TEXT FILE FORMAT ANALYSIS")
    print("="*80)

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    lines = content.split('\n')

    # Find first few AUV packets
    auv_count = 0
    ckth_count = 0

    for i, line in enumerate(lines[:50]):  # First 50 lines
        line_stripped = line.strip()

        # Skip empty and timestamp lines
        if not line_stripped:
            continue
        if re.match(r'\d{2}:\d{2}:\d{2}::::', line_stripped):
            print(f"\n[{i}] TIMESTAMP: {line_stripped}")
            continue

        # CKTH packet
        if '$CKTH' in line_stripped:
            ckth_count += 1
            # Extract data part
            ckth_pos = line_stripped.index('$CKTH')
            data_part = line_stripped[ckth_pos + 5:].strip()

            # Remove control characters
            data_clean = ''.join(c for c in data_part if ord(c) >= 32 or c == '\n')

            parts = data_clean.split()
            print(f"\n[{i}] CKTH #{ckth_count}")
            print(f"  Raw length: {len(data_part)} chars")
            print(f"  Clean parts: {len(parts)} fields")
            print(f"  First 10 fields: {parts[:10]}")

            if len(parts) > 5:
                print(f"  Frame char: {repr(parts[0][-1]) if len(parts[0]) > 5 else 'N/A'}")
                print(f"  Address: {parts[2] if len(parts) > 2 else 'N/A'}")
                print(f"  Mode: {parts[4] if len(parts) > 4 else 'N/A'}")

        # AUV packet
        if '$AUV' in line_stripped and '$CKTH' not in line_stripped:
            auv_count += 1

            # Extract data part
            auv_pos = line_stripped.index('$AUV')
            data_part = line_stripped[auv_pos + 4:].strip()

            # Remove control characters
            data_clean = ''.join(c for c in data_part if ord(c) >= 32 or c == '\n')

            parts = data_clean.split()

            print(f"\n[{i}] AUV #{auv_count}")
            print(f"  Raw length: {len(data_part)} chars")
            print(f"  Total fields: {len(parts)}")

            if auv_count <= 5:  # Show first 5 in detail
                print(f"  First 15 fields: {parts[:15]}")

                # Analyze structure
                if len(parts) > 3:
                    print(f"  [0] Length: {parts[0]}")
                    print(f"  [1] Frame: {parts[1]}")
                    print(f"  [2] Address: {parts[2]}")
                    print(f"  [3] Mode: {parts[3]}")

                # Scan for GPS
                gps_found = False
                for idx, part in enumerate(parts):
                    if part.lstrip('-').isdigit():
                        val = int(part)
                        if 70000000 < val < 140000000:  # Longitude
                            print(f"  [{idx}] GPS Longitude: {val} ({val/1000000:.6f}°)")
                            gps_found = True
                        elif 10000000 < val < 55000000:  # Latitude
                            print(f"  [{idx}] GPS Latitude: {val} ({val/1000000:.6f}°)")
                            gps_found = True

                if not gps_found:
                    print(f"  ⚠ No GPS data found in this packet")

            if auv_count >= 10:
                break

    print(f"\n{'='*80}")
    print(f"TOTAL: {ckth_count} CKTH, {auv_count} AUV packets in first 50 lines")
    print(f"{'='*80}")


def test_gps_detection():
    """Test GPS coordinate detection"""
    print("\n" + "="*80)
    print("GPS DETECTION TEST")
    print("="*80)

    test_cases = [
        ("115368621", True, "longitude"),
        ("22754909", True, "latitude"),
        ("0", False, "zero"),
        ("1714", False, "depth"),
        ("180", False, "rudder"),
        ("-180", False, "rudder_negative"),
    ]

    for value, should_match, expected_type in test_cases:
        val = int(value)

        # Check longitude
        is_lon = 70000000 < val < 140000000
        # Check latitude
        is_lat = 10000000 < val < 55000000

        matched = is_lon or is_lat

        status = "✓" if matched == should_match else "✗"
        print(f"{status} {value:>10s}: lon={is_lon}, lat={is_lat}, type={expected_type}")


if __name__ == '__main__':
    debug_text_file('20020101103632.txt')
    test_gps_detection()
