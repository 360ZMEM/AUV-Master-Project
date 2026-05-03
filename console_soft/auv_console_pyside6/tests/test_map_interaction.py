#!/usr/bin/env python3
"""
Test map interaction features - pan, zoom, distance measurement
"""

import sys
sys.path.insert(0, 'src')

from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QMouseEvent
import time

print("=" * 60)
print("Testing Map Interaction Features")
print("=" * 60)

app = QApplication(sys.argv)

try:
    main_window = MainWindow()
    main_window.show()

    print("\n✓ Main window created")
    print("\nMap Interaction Tests:")
    print("  The application will run for 10 seconds")
    print("  Please test the following manually:\n")
    print("  1. Map Pan (Left/Middle Click + Drag)")
    print("     - Click and drag to pan the map")
    print("     - Cursor should change to OpenHand/ClosedHand")
    print()
    print("  2. Distance Measurement (Right Click + Drag)")
    print("     - Right click and drag to measure distance")
    print("     - Yellow line with distance text should appear")
    print("     - Line should follow mouse cursor accurately")
    print()
    print("  3. Map Zoom (Mouse Wheel)")
    print("     - Scroll up to zoom in")
    print("     - Scroll down to zoom out")
    print()
    print("  4. Waypoint Selection")
    print("     - Click '开始选点' button")
    print("     - Left click on map to add waypoints")
    print("     - Cursor should be PointingHandCursor")

    print("\n" + "=" * 60)
    print("Application is running...")
    print("=" * 60)

    # Auto-close timer
    def close_app():
        print("\nTest completed. Closing...")
        if main_window.extend_form:
            main_window.extend_form.close()
        main_window.close()
        app.quit()

    QTimer.singleShot(10000, close_app)

    app.exec()

    print("\n✓ Map interaction test completed!")
    print("\nManual Verification Checklist:")
    print("  ☐ Map pan works with left/mouse drag")
    print("  ☐ Cursor changes correctly (OpenHand → ClosedHand)")
    print("  ☐ Distance measurement line follows mouse accurately")
    print("  ☐ Distance text shows correct values")
    print("  ☐ Map zoom works with mouse wheel")
    print("  ☐ Waypoint selection adds points correctly")

except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
