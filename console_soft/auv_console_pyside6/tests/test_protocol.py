"""
Test protocol encoding/decoding
"""

import sys
sys.path.insert(0, '../src')

from src.data_structures import Preferences
from src.protocol.packet_builder import PacketBuilder
from src.protocol.constants import FRAME_HEADER_SEND, FRAME_TRAILER


def test_send_packet():
    """Test 72-byte send packet construction"""
    print("Testing send packet construction...")

    builder = PacketBuilder()
    prefs = Preferences()

    packet = builder.build_send_packet(
        preferences=prefs,
        work_instruct=0x01,
        motor_speeds=(0, 0),
        rudder_angles=(0, 0, 0, 0),
        orientation=0,
        parameters=(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    )

    assert len(packet) == 72, f"Packet length {len(packet)}, expected 72"
    assert packet[0:5] == FRAME_HEADER_SEND, "Invalid frame header"
    assert packet[70:72] == FRAME_TRAILER, "Invalid frame trailer"

    # Verify checksum
    checksum = sum(packet[0:69]) & 0xFF
    assert packet[69] == checksum, f"Checksum mismatch: {packet[69]} != {checksum}"

    print("✓ Send packet construction test PASSED")
    print(f"  Packet length: {len(packet)} bytes")
    print(f"  Frame header: {packet[0:5].hex()}")
    print(f"  Checksum: {checksum:#x}")
    print(f"  Frame trailer: {packet[70:72].hex()}")


def test_beidou_packet():
    """Test 34-byte Beidou packet construction"""
    print("\nTesting Beidou packet construction...")

    builder = PacketBuilder()
    prefs = Preferences()

    packet = builder.build_beidou_packet(prefs, 0x01)

    assert len(packet) == 34, f"Packet length {len(packet)}, expected 34"
    assert packet[0:5] == bytes([0x24, 0x43, 0x4B, 0x54, 0x22]), "Invalid Beidou frame header"
    assert packet[32:34] == FRAME_TRAILER, "Invalid frame trailer"

    # Verify checksum
    checksum = sum(packet[0:31]) & 0xFF
    assert packet[31] == checksum, f"Checksum mismatch: {packet[31]} != {checksum}"

    print("✓ Beidou packet construction test PASSED")
    print(f"  Packet length: {len(packet)} bytes")
    print(f"  Checksum: {checksum:#x}")


if __name__ == '__main__':
    test_send_packet()
    test_beidou_packet()
    print("\n✓ All protocol tests PASSED!")
