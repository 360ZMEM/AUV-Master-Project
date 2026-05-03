#!/usr/bin/env python3
"""
Test application startup without blocking
"""

import sys
sys.path.insert(0, 'src')

from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow
from src.communication.comm_manager import CommunicationManager

print("=" * 60)
print("Testing AUV Console Application Startup")
print("=" * 60)

# Create application
app = QApplication(sys.argv)
app.setApplicationName("AUV Console Test")

try:
    # Create main window
    print("\n1. Creating main window...")
    main_window = MainWindow()
    print("   ✓ Main window created successfully")

    # Check configuration loaded
    print("\n2. Checking configuration...")
    print(f"   - Preferences: address={main_window.preferences.obj_address}, mode={main_window.preferences.work_mode}")
    print(f"   - Communication mode: {main_window.comm_manager.comm_mode}")

    # Check UI components
    print("\n3. Checking UI components...")
    print(f"   - Map widget: {type(main_window.map_widget).__name__}")
    print(f"   - Waypoint table: {main_window.waypoint_table.rowCount()} rows")
    print(f"   - Timer active: {main_window.tx_timer.isActive()}")

    print("\n" + "=" * 60)
    print("✓ ALL CHECKS PASSED - Application is ready!")
    print("=" * 60)
    print("\nClosing test window in 2 seconds...")

    # Show window briefly
    main_window.show()
    app.processEvents()

    import time
    time.sleep(2)

    print("\nTest completed successfully!")
    sys.exit(0)

except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
