#!/usr/bin/env python3
"""
AUV Console Application - Main Entry Point
Python/PySide6 implementation of C# Windows Forms AUV Console
"""

import sys
import os
import argparse

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

from src.ui.main_window import MainWindow
from src.threads.udp_receiver_thread import UDPReceiverThread
from src.protocol.packet_builder import PacketBuilder


def parse_app_args(argv):
    # /**
    #  * @brief 允许实物联调显式选择 console_config.pc104.yaml，默认启动路径保持不变。
    #  * @date 2026-07-11
    #  * @author 清华 AUV 课题组
    #  */
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--config",
        dest="config_file",
        default=None,
        help="Path to console YAML config, e.g. console_config.pc104.yaml",
    )
    parser.add_argument(
        "--theme",
        choices=("system", "light", "dark"),
        default=os.environ.get("AUV_CONSOLE_THEME", "system"),
        help="UI palette for screenshot/debug runs",
    )
    return parser.parse_known_args(argv)


def apply_console_theme(app: QApplication, theme: str) -> None:
    """
    @brief Apply an explicit light or dark Qt palette for repeatable GUI verification.
    @param app QApplication instance.
    @param theme One of system, light, or dark.
    @author 清华 AUV 课题组
    """
    if theme == "system":
        return

    app.setStyle("Fusion")
    palette = QPalette()

    if theme == "dark":
        palette.setColor(QPalette.Window, QColor(37, 39, 43))
        palette.setColor(QPalette.WindowText, QColor(235, 238, 242))
        palette.setColor(QPalette.Base, QColor(28, 30, 34))
        palette.setColor(QPalette.AlternateBase, QColor(45, 48, 54))
        palette.setColor(QPalette.ToolTipBase, QColor(235, 238, 242))
        palette.setColor(QPalette.ToolTipText, QColor(235, 238, 242))
        palette.setColor(QPalette.Text, QColor(235, 238, 242))
        palette.setColor(QPalette.Button, QColor(48, 52, 59))
        palette.setColor(QPalette.ButtonText, QColor(235, 238, 242))
        palette.setColor(QPalette.BrightText, QColor(255, 255, 255))
        palette.setColor(QPalette.Highlight, QColor(36, 113, 194))
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        palette.setColor(QPalette.Link, QColor(77, 163, 255))
    else:
        palette.setColor(QPalette.Window, QColor(245, 247, 250))
        palette.setColor(QPalette.WindowText, QColor(28, 32, 36))
        palette.setColor(QPalette.Base, QColor(255, 255, 255))
        palette.setColor(QPalette.AlternateBase, QColor(235, 239, 245))
        palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
        palette.setColor(QPalette.ToolTipText, QColor(28, 32, 36))
        palette.setColor(QPalette.Text, QColor(28, 32, 36))
        palette.setColor(QPalette.Button, QColor(238, 241, 245))
        palette.setColor(QPalette.ButtonText, QColor(28, 32, 36))
        palette.setColor(QPalette.BrightText, QColor(255, 255, 255))
        palette.setColor(QPalette.Highlight, QColor(21, 101, 192))
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        palette.setColor(QPalette.Link, QColor(21, 101, 192))

    app.setPalette(palette)


def main():
    """Main application entry point"""
    args, qt_args = parse_app_args(sys.argv[1:])
    sys.argv = [sys.argv[0]] + qt_args

    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("AUV Console")
    app.setOrganizationName("AUV Control System")
    apply_console_theme(app, args.theme)

    # Create main window
    main_window = MainWindow(config_file=args.config_file)
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
