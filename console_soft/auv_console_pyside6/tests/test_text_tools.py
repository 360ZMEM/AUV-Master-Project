#!/usr/bin/env python3
"""
Quick test script for text replay sender
Tests parsing and packet generation without GUI
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from text_replay_sender import TextPacketReplaySender

# Import unified config
try:
    from config_loader import get_text_log_path
except ImportError:
    def get_text_log_path():
        return '20020101103632.txt'


def test_text_sender():
    """Test text replay sender initialization and loading"""
    print("=" * 70)
    print("Testing Text Replay Sender")
    print("=" * 70)
    print()

    try:
        # Show configured file
        text_file = get_text_log_path()
        print(f"Configured text file: {text_file}")
        print()

        # Initialize sender
        sender = TextPacketReplaySender()
        print("✓ Sender initialized successfully")
        print()

        # Load text file
        print("Loading text file...")
        if sender.load_text_file():
            print(f"✓ Loaded {len(sender.packets)} AUV packets")
            print()

            # Show first packet info
            if len(sender.packets) > 0:
                first_packet = sender.packets[0]
                print(f"First packet:")
                print(f"  Length: {len(first_packet)} bytes")
                print(f"  Header: {first_packet[0:5].hex()}")
                print(f"  Frame number: {first_packet[6]}")
                print(f"  Address: {first_packet[7]}")
                print(f"  Mode: {first_packet[8]}")
                print()

            # Show packet count
            print(f"Total packets: {len(sender.packets)}")
            print()

            return True
        else:
            print("✗ Failed to load text file")
            return False

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_packet_viewer():
    """Test packet viewer initialization"""
    print("=" * 70)
    print("Testing Packet Viewer (Parser)")
    print("=" * 70)
    print()

    try:
        from packet_viewer import PacketFileParser

        # Use configured file
        filepath = get_text_log_path()

        if not os.path.exists(filepath):
            print(f"✗ File not found: {filepath}")
            print(f"  Current directory: {os.getcwd()}")
            print(f"  Expected location: {os.path.abspath(filepath)}")
            return False

        print(f"Using file: {filepath}")
        print()

        # Parse file
        parser = PacketFileParser(filepath)
        if parser.parse():
            print(f"✓ Parsed {len(parser.packets)} packets")
            print()

            # Count by type
            ckth_count = sum(1 for p in parser.packets if p.packet_type == 'CKTH')
            auv_count = sum(1 for p in parser.packets if p.packet_type == 'AUV')

            print(f"Packet breakdown:")
            print(f"  CKTH (Console→AUV): {ckth_count}")
            print(f"  AUV (AUV→Console):  {auv_count}")
            print(f"  Total:               {len(parser.packets)}")
            print()

            # Show first few packets
            print("First 3 packets:")
            for i, p in enumerate(parser.packets[:3]):
                print(f"  {i+1}. [{p.timestamp}] {p.packet_type} - Frame {p.raw_data.get('frame', 0)}")
            print()

            return True
        else:
            print("✗ Failed to parse file")
            return False

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print()
    print("AUV Text Tools - Quick Test")
    print("=" * 70)
    print()

    results = []

    # Test 1: Text sender
    results.append(("Text Replay Sender", test_text_sender()))

    # Test 2: Packet viewer
    results.append(("Packet Viewer", test_packet_viewer()))

    # Summary
    print("=" * 70)
    print("Test Summary")
    print("=" * 70)
    print()

    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")

    print()
    all_passed = all(r[1] for r in results)
    if all_passed:
        print("All tests passed!")
    else:
        print("Some tests failed")

    print("=" * 70)

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
