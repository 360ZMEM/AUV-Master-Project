#!/usr/bin/env python3
"""
Test UDP communication with actual network
"""

import sys
import socket
import time
sys.path.insert(0, 'src')

from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow
from src.protocol.packet_builder import PacketBuilder

print("=" * 60)
print("Testing UDP Communication")
print("=" * 60)

# Test 1: Check if UDP port is available
print("\n1. Checking UDP port availability...")
try:
    test_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    test_socket.bind(('192.168.0.11', 21))
    test_socket.close()
    print("   ✓ Port 192.168.0.11:21 is available")
except Exception as e:
    print(f"   ✗ Port binding failed: {e}")

# Test 2: Create packet
print("\n2. Building test packet...")
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

print(f"   ✓ Packet built: {len(packet)} bytes")
print(f"   - Header: {packet[0:5].hex()}")
print(f"   - Checksum: {packet[69]:#x}")
print(f"   - Trailer: {packet[70:72].hex()}")

# Test 3: Send test packet
print("\n3. Sending test packet to AUV...")
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('192.168.0.11', 21))
    sock.settimeout(2.0)

    # Send packet
    sock.sendto(packet, ('192.168.0.101', 52364))
    print(f"   ✓ Packet sent to 192.168.0.101:52364")

    # Try to receive
    try:
        data, addr = sock.recvfrom(2048)
        print(f"   ✓ Received {len(data)} bytes from {addr}")
        if len(data) >= 5:
            print(f"   - Header: {data[0:5].hex()}")
    except socket.timeout:
        print("   - No response (AUV may not be sending data)")

    sock.close()
except Exception as e:
    print(f"   ✗ Communication test failed: {e}")

print("\n" + "=" * 60)
print("Communication test completed")
print("=" * 60)
