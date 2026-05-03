#!/usr/bin/env python3
"""
Test receiving and parsing AUV data
"""

import sys
import socket
import time
sys.path.insert(0, 'src')

from src.protocol.packet_builder import PacketBuilder

print("=" * 60)
print("Testing AUV Data Reception and Parsing")
print("=" * 60)

builder = PacketBuilder()
from src.data_structures import Preferences

prefs = Preferences()
prefs.obj_address = 2
prefs.work_mode = 2

packet = builder.build_send_packet(
    preferences=prefs,
    work_instruct=0x01,
    motor_speeds=(0, 0),
    rudder_angles=(0, 0, 0, 0),
    orientation=0,
    parameters=(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
)

print("\n1. Sending command packet and listening for response...")
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('192.168.0.11', 21))
    sock.settimeout(5.0)

    # Send multiple packets to ensure we get responses
    for i in range(3):
        sock.sendto(packet, ('192.168.0.101', 52364))
        print(f"   - Packet {i+1} sent")

    # Receive and parse responses
    responses_received = 0
    start_time = time.time()

    while time.time() - start_time < 3:
        try:
            data, addr = sock.recvfrom(2048)
            responses_received += 1

            print(f"\n   Response {responses_received}:")
            print(f"   - Length: {len(data)} bytes")
            print(f"   - From: {addr}")
            print(f"   - Header: {data[0:5].hex()}")

            # Try to parse
            try:
                telemetry = builder.parse_recv_packet(data)
                print(f"   - ✓ Packet parsed successfully!")
                print(f"   - Frame: {telemetry.frame_number}")
                print(f"   - AUV: {telemetry.auv_address}")
                print(f"   - Mode: {telemetry.work_mode}")
                print(f"   - GPS: {telemetry.gps_lon:.6f}, {telemetry.gps_lat:.6f}")
                print(f"   - Depth: {telemetry.depth:.1f}m")
                print(f"   - Heading: {telemetry.compass_heading:.1f}°")
                print(f"   - Voltage: {telemetry.total_voltage:.1f}V")
                print(f"   - Current: {telemetry.total_current:.1f}A")
                print(f"   - SOC: {telemetry.soc}%")
            except Exception as e:
                print(f"   - ✗ Parse error: {e}")

        except socket.timeout:
            break

    sock.close()

    print(f"\n   Total responses received: {responses_received}")

except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Test completed")
print("=" * 60)
