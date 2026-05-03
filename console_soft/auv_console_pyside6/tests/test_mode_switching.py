#!/usr/bin/env python3
"""
Test online/offline mode switching
"""

import sys
sys.path.insert(0, 'src')

from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow

print("=" * 60)
print("Testing Online/Offline Mode")
print("=" * 60)

app = QApplication(sys.argv)

try:
    print("\nStarting AUV Console...")
    main_window = MainWindow()
    main_window.show()

    print("\n✓ Application started")
    print("\nCurrent configuration:")
    print(f"  - Mode from config: {main_window.mode_manager.get_mode()}")
    print(f"  - Is offline: {main_window.is_offline_mode}")
    print(f"  - Offline packets: {main_window.offline_replay.get_packet_count()}")

    print("\n" + "=" * 60)
    print("Instructions:")
    print("=" * 60)
    print("\n1. Online Mode (在线模式):")
    print("   - Click '在线模式' button")
    print("   - Connects to real AUV at 192.168.0.101:52364")
    print("   - Real-time UDP communication")
    print()
    print("2. Offline Mode (离线模式):")
    print("   - Click '离线模式' button")
    print("   - Replays packets from PCAP file")
    print("   - Configured in config/mode_config.ini")
    print()
    print("3. Configuration File (config/mode_config.ini):")
    print("   - mode = online  or  offline")
    print("   - pcap_file = path to .pcapng file")
    print("   - replay_interval_ms = delay between packets (600)")
    print("   - loop_playback = true  or  false")
    print()
    print("4. To switch modes:")
    print("   - Click '在线模式' or '离线模式' button")
    print("   - Configuration is automatically saved")
    print()
    print("=" * 60)
    print("\nApplication is running. Test the mode switching...")
    print("Press Ctrl+C to exit\n")

    app.exec()

    print("\n✓ Test completed")

except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
