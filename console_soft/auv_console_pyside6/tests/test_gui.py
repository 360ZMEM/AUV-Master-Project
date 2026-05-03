#!/usr/bin/env python3
"""
Test GUI with waypoint selection and extended window
"""

import sys
sys.path.insert(0, 'src')

from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow
import time

print("=" * 60)
print("Testing GUI Features")
print("=" * 60)

app = QApplication(sys.argv)

try:
    main_window = MainWindow()
    main_window.show()

    print("\n✓ Main window created")
    print("\nTesting features:")
    print("1. Extended control window will open in 2 seconds...")
    app.processEvents()

    time.sleep(2)

    # Open extended control window
    main_window.open_extended_control()
    print("   ✓ Extended control window opened")

    time.sleep(2)

    # Test waypoint selection
    print("\n2. Testing waypoint selection...")
    main_window.start_waypoint_selection()
    print("   ✓ Waypoint selection mode activated")

    # Add a test waypoint (simulate map click)
    main_window.add_waypoint_from_map(110.123, 31.034)
    print("   ✓ Test waypoint added at 110.123, 31.034")

    main_window.add_waypoint_from_map(110.124, 31.035)
    print("   ✓ Test waypoint added at 110.124, 31.035")

    main_window.end_waypoint_selection()
    print("   ✓ Waypoint selection ended")

    time.sleep(2)

    print("\n" + "=" * 60)
    print("✓ All GUI features tested successfully!")
    print("=" * 60)
    print("\nApplication is running with:")
    print("  - Main window visible")
    print("  - Extended control window visible (independent)")
    print("  - 2 test waypoints loaded")
    print("\nClosing in 3 seconds...")

    time.sleep(3)

    # Cleanup
    if main_window.extend_form:
        main_window.extend_form.close()

    main_window.close()
    app.quit()

    print("\n✓ GUI test completed successfully!")

except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
