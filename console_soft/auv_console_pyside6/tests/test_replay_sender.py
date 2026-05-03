#!/usr/bin/env python3
"""
Integration test for PCAP Replay Sender and AUV Console
Tests that the console can receive packets from the replay sender
"""

import sys
import os
import time
import subprocess
import shutil
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread, Signal

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.ui.main_window import MainWindow


class TestRunner(QThread):
    """Thread to run replay sender and test reception"""

    progress = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.replay_process = None
        self.running = False

    def run(self):
        """Run integration test"""
        try:
            self.progress.emit("Starting integration test...")

            # Backup current port_set.txt
            config_dir = os.path.join(os.path.dirname(__file__), 'config')
            port_set_backup = os.path.join(config_dir, 'port_set_backup.txt')

            if os.path.exists(os.path.join(config_dir, 'port_set.txt')):
                shutil.copy(
                    os.path.join(config_dir, 'port_set.txt'),
                    port_set_backup
                )

            # Use local configuration
            shutil.copy(
                os.path.join(config_dir, 'port_set_local.txt'),
                os.path.join(config_dir, 'port_set.txt')
            )

            self.progress.emit("✓ Using local network configuration (127.0.0.1)")

            # Start replay sender
            self.progress.emit("Starting PCAP replay sender...")
            self.replay_process = subprocess.Popen(
                [sys.executable, 'pcap_replay_sender.py'],
                cwd=os.path.dirname(__file__),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Wait for sender to start
            time.sleep(2)

            if self.replay_process.poll() is not None:
                stdout, stderr = self.replay_process.communicate()
                self.finished.emit(False, f"Replay sender failed to start:\n{stderr.decode()}")
                return

            self.progress.emit("✓ Replay sender started")

            # Wait for packets to be received
            self.progress.emit("Waiting for packets (10 seconds)...")
            timeout = 10
            start_time = time.time()

            packet_count = 0
            last_packet_count = 0

            while time.time() - start_time < timeout:
                time.sleep(1)

                # Check if we received packets (via frame counter)
                if hasattr(self.main_window, 'frame'):
                    if self.main_window.frame != last_packet_count:
                        packet_count = self.main_window.frame
                        last_packet_count = packet_count
                        self.progress.emit(f"✓ Received packet #{packet_count}")

                # Check if replay sender is still running
                if self.replay_process.poll() is not None:
                    self.progress.emit("⚠ Replay sender stopped unexpectedly")
                    break

            # Stop replay sender
            self.progress.emit("Stopping replay sender...")
            self.replay_process.terminate()
            self.replay_process.wait(timeout=5)

            # Restore original configuration
            if os.path.exists(port_set_backup):
                shutil.copy(
                    port_set_backup,
                    os.path.join(config_dir, 'port_set.txt')
                )
                os.remove(port_set_backup)

            # Check results
            if packet_count > 0:
                self.finished.emit(
                    True,
                    f"✓ SUCCESS: Received {packet_count} packets from replay sender\n"
                    f"✓ Network replay is working correctly!"
                )
            else:
                self.finished.emit(
                    False,
                    "✗ FAILED: No packets received. Check:\n"
                    "  1. Is replay sender running?\n"
                    "  2. Are ports 21 and 52364 available?\n"
                    "  3. Is firewall blocking UDP?"
                )

        except Exception as e:
            self.finished.emit(False, f"✗ Test error: {e}")

        finally:
            # Cleanup
            if self.replay_process:
                try:
                    self.replay_process.terminate()
                    self.replay_process.wait(timeout=2)
                except:
                    self.replay_process.kill()


def main():
    """Main test entry point"""
    print("=" * 70)
    print("PCAP Replay Sender Integration Test")
    print("=" * 70)
    print()

    # Create Qt application
    app = QApplication(sys.argv)

    # Create main window
    print("Creating AUV Console...")
    main_window = MainWindow()
    main_window.show()

    # Start in online mode (important!)
    print("Starting in ONLINE mode...")
    main_window.switch_to_online_mode()

    print("✓ Console ready, listening on 127.0.0.1:21")
    print()

    # Create test runner
    test_runner = TestRunner(main_window)

    # Connect signals
    test_runner.progress.connect(lambda msg: print(f"  {msg}"))
    test_runner.finished.connect(lambda success, msg: print(f"\n{msg}"))

    # Start test
    test_runner.start()

    # Run application
    print("-" * 70)
    print("Test running... Close the console window to exit.")
    print("-" * 70)
    print()

    app.exec()

    # Wait for test to finish
    test_runner.wait()

    print()
    print("=" * 70)
    print("Test completed")
    print("=" * 70)


if __name__ == "__main__":
    main()
