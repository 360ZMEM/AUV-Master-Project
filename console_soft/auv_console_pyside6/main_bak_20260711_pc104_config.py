#!/usr/bin/env python3
"""
AUV Console Application - Main Entry Point
Python/PySide6 implementation of C# Windows Forms AUV Console
"""

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from src.ui.main_window import MainWindow
from src.threads.udp_receiver_thread import UDPReceiverThread
from src.protocol.packet_builder import PacketBuilder


def main():
    """Main application entry point"""
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("AUV Console")
    app.setOrganizationName("AUV Control System")

    # Create main window
    main_window = MainWindow()
    main_window.show()

    # Start UDP receiver thread
    udp_comm = main_window.comm_manager.get_udp_communicator()
    receiver_thread = UDPReceiverThread(udp_comm)

    # Connect signals
    receiver_thread.data_received.connect(lambda data: on_udp_data_received(data, main_window))

    # Start thread
    receiver_thread.start()

    print("AUV Console started")
    print("Press Ctrl+C to exit")

    # Run application
    result = app.exec()

    # Cleanup
    receiver_thread.stop()

    return result


def on_udp_data_received(data: bytes, main_window: MainWindow):
    """Handle UDP data received from AUV"""
    try:
        # Parse packet
        packet_builder = PacketBuilder()
        telemetry = packet_builder.parse_recv_packet(data)

        # Update UI (thread-safe via Qt signal/slot connection)
        main_window.update_telemetry_display(telemetry)

    except Exception as e:
        print(f"Error processing UDP data: {e}")


if __name__ == '__main__':
    sys.exit(main())
