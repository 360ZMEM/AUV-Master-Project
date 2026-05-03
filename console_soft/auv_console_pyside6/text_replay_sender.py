#!/usr/bin/env python3
"""
AUV Text Replay Sender
Replays AUV packets from text log file via UDP (compatible with C#/Python consoles)

This is an alternative to pcap_replay_sender.py that reads from text format logs
instead of PCAP files. Useful for replaying sea trial logs.

Usage:
    python text_replay_sender.py

Configuration: config/tools_config.ini (text_log_file) and config/text_replay_config.ini
"""

import sys
import os
import time
import socket
import threading
import re
from configobj import ConfigObj

# Import unified configuration
try:
    from config_loader import load_config
except ImportError:
    # Fallback
    def load_config():
        return None


class TextPacketReplaySender:
    """
    Replays AUV packets from text log file via UDP
    Compatible with both C# and Python AUV Console applications
    """

    def __init__(self, config_path: str = None):
        """Initialize replay sender with configuration"""
        if config_path is None:
            # Get project root
            current_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(current_dir, "config", "text_replay_config.ini")

        self.config_path = config_path
        self.config = None

        # Runtime state
        self.running = False
        self.thread = None
        self.socket = None
        self.packets = []
        self.current_index = 0

        # Load configuration
        self.load_config()

    def load_config(self):
        """Load configuration from INI files"""
        try:
            # Load unified configuration for file paths
            unified_config = load_config()
            if unified_config:
                self.text_file = unified_config.get_text_log_path()
                default_interval = unified_config.get_replay_interval()
                default_loop = unified_config.get_replay_loop()
                self.local_ip = unified_config.get_local_ip()
                self.local_port = unified_config.get_auv_port()
                self.target_ip = unified_config.get_local_ip()
                self.target_port = unified_config.get_console_port()
            else:
                # Fallback to hardcoded defaults
                self.text_file = '20020101103632.txt'
                default_interval = 600
                default_loop = True
                self.local_ip = '127.0.0.1'
                self.local_port = 52364
                self.target_ip = '127.0.0.1'
                self.target_port = 21

            # Load legacy text_replay_config.ini for backward compatibility
            # This can override unified config settings
            if os.path.exists(self.config_path):
                self.config = ConfigObj(self.config_path)

                # Override with legacy config if specified
                sender = self.config.get('sender', {})
                if 'text_file' in sender:
                    self.text_file = sender['text_file']

                # Replay settings
                self.replay_interval_ms = int(sender.get('replay_interval_ms', default_interval))
                self.loop_playback = sender.get('loop_playback', str(default_loop)).lower() == 'true'

                # Network settings (legacy overrides)
                network = self.config.get('network', {})
                if 'local_ip' in network:
                    self.local_ip = network['local_ip']
                if 'local_port' in network:
                    self.local_port = int(network['local_port'])
                if 'target_ip' in network:
                    self.target_ip = network['target_ip']
                if 'target_port' in network:
                    self.target_port = int(network['target_port'])
            else:
                # Use unified config values (already set above)
                self.replay_interval_ms = default_interval
                self.loop_playback = default_loop

            # Display configuration
            config_source = self.config_path if os.path.exists(self.config_path) else "tools_config.ini"
            print(f"Configuration loaded from {config_source}")
            print(f"  Text file: {self.text_file}")
            print(f"  Replay interval: {self.replay_interval_ms}ms")
            print(f"  Loop playback: {self.loop_playback}")
            print(f"  Target: {self.target_ip}:{self.target_port}")
            print(f"  Local bind: {self.local_ip}:{self.local_port}")

        except Exception as e:
            print(f"Error loading configuration: {e}")
            raise

    def load_text_file(self) -> bool:
        """Load and parse AUV packets from text log file"""
        # Resolve text file path
        text_path = os.path.join(os.path.dirname(__file__), self.text_file)

        if not os.path.exists(text_path):
            print(f"Error: Text file not found: {text_path}")
            return False

        try:
            print(f"Loading text file: {text_path}")

            self.packets = []
            current_timestamp = ""

            with open(text_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            i = 0
            while i < len(lines):
                line = lines[i].strip()

                # Check for timestamp line
                if re.match(r'\d{2}:\d{2}:\d{2}::::', line):
                    time_parts = line.split(':')[0:3]
                    current_timestamp = ':'.join(time_parts)
                    i += 1
                    continue

                # Check for AUV packet (data on SAME line after $AUV marker)
                if '$AUV' in line and '$CKTH' not in line:
                    # Extract data part from the same line
                    auv_pos = line.index('$AUV')
                    data_line = line[auv_pos + 4:].strip()

                    # Remove control characters
                    data_line = ''.join(c for c in data_line if ord(c) >= 32)

                    if data_line:
                        packet_bytes = self._parse_auv_to_bytes(data_line)
                        if packet_bytes:
                            self.packets.append(packet_bytes)

                i += 1

            print(f"Loaded {len(self.packets)} AUV packets from text file")
            return len(self.packets) > 0

        except Exception as e:
            print(f"Error loading text file: {e}")
            return False

    def _parse_auv_to_bytes(self, line: str) -> bytes:
        """
        Parse AUV text data line and convert to binary packet
        Returns 145-byte packet in binary format

        Text format: 145 frame addr mode ... GPS_long GPS_lat ... checksum
        Binary format per protocol: 145 bytes at specific offsets
        """
        try:
            parts = line.split()
            if len(parts) < 4:
                return None

            # Create 145-byte packet
            packet = bytearray(145)

            # Frame header (bytes 0-4): $AUV + 0x91
            packet[0:5] = b'\x24\x41\x55\x56\x91'

            # Parse basic fields (fixed positions at start)
            idx = 0

            # Data length (byte 5): should be 145
            if idx < len(parts) and parts[idx].isdigit():
                packet[5] = int(parts[idx]) & 0xFF
            idx += 1

            # Frame number (byte 6)
            if idx < len(parts) and parts[idx].isdigit():
                packet[6] = int(parts[idx]) & 0xFF
            idx += 1

            # Address (byte 7)
            if idx < len(parts) and parts[idx].isdigit():
                packet[7] = int(parts[idx]) & 0xFF
            idx += 1

            # Work mode (byte 8)
            if idx < len(parts) and parts[idx].isdigit():
                packet[8] = int(parts[idx]) & 0xFF
            idx += 1

            # Scan through remaining fields for key data
            while idx < len(parts):
                part = parts[idx]

                if not part.lstrip('-').isdigit():
                    idx += 1
                    continue

                val = int(part)

                # GPS Longitude (bytes 94-97): 70-140°E range
                if 70000000 < val < 140000000:
                    packet[94:98] = val.to_bytes(4, byteorder='big', signed=True)

                # GPS Latitude (bytes 98-101): 10-55°N range
                elif 10000000 < val < 55000000:
                    packet[98:102] = val.to_bytes(4, byteorder='big', signed=True)

                # Depth (bytes 38-39): 0-50000 cm range
                elif 0 <= val <= 50000 and packet[38:40] == b'\x00\x00':
                    packet[38:40] = val.to_bytes(2, byteorder='big', signed=False)

                # Pressure (bytes 35-36): 0-100000 range (MPa×1000)
                elif 0 <= val <= 100000 and packet[35:37] == b'\x00\x00':
                    packet[35:37] = val.to_bytes(2, byteorder='big', signed=False)

                # Rudder angles (bytes 27-34): -1800 to 1800 range
                elif -1800 <= val <= 1800:
                    # Find next empty rudder slot
                    if packet[27:29] == b'\x00\x00':
                        packet[27:29] = val.to_bytes(2, byteorder='big', signed=True)
                    elif packet[29:31] == b'\x00\x00':
                        packet[29:31] = val.to_bytes(2, byteorder='big', signed=True)
                    elif packet[31:33] == b'\x00\x00':
                        packet[31:33] = val.to_bytes(2, byteorder='big', signed=True)
                    elif packet[33:35] == b'\x00\x00':
                        packet[33:35] = val.to_bytes(2, byteorder='big', signed=True)

                idx += 1

            # Calculate checksum (byte 142): sum of bytes 0-141
            checksum = sum(packet[0:142]) & 0xFF
            packet[142] = checksum

            # Frame trailer (bytes 143-144)
            packet[143:145] = b'\xFF\xFF'

            return bytes(packet)

        except Exception as e:
            print(f"Error parsing AUV line: {e}")
            return None

    def create_socket(self) -> bool:
        """Create and bind UDP socket"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Bind to local address (simulates AUV's local endpoint)
            self.socket.bind((self.local_ip, self.local_port))

            print(f"UDP socket bound to {self.local_ip}:{self.local_port}")
            return True

        except Exception as e:
            print(f"Error creating socket: {e}")
            return False

    def send_packet(self, packet: bytes) -> bool:
        """Send single packet to target"""
        try:
            self.socket.sendto(packet, (self.target_ip, self.target_port))
            return True
        except Exception as e:
            print(f"Error sending packet: {e}")
            return False

    def replay_loop(self):
        """Main replay loop (runs in background thread)"""
        print(f"Starting replay: {len(self.packets)} packets")

        while self.running:
            if self.current_index >= len(self.packets):
                if self.loop_playback:
                    print("Looping replay...")
                    self.current_index = 0
                    time.sleep(1)  # Pause before looping
                else:
                    print("Replay finished")
                    break

            # Send current packet
            packet = self.packets[self.current_index]
            success = self.send_packet(packet)

            if success:
                progress = (self.current_index + 1, len(self.packets))
                header = packet[0:5].hex()
                print(f"Sent packet {progress[0]}/{progress[1]} "
                      f"(header: {header})...")

            self.current_index += 1

            # Wait before next packet
            if self.replay_interval_ms > 0:
                time.sleep(self.replay_interval_ms / 1000.0)

        print("Replay thread stopped")

    def start(self):
        """Start replay in background thread"""
        if self.running:
            print("Replay already running")
            return False

        # Load packets from text file
        if not self.load_text_file():
            print("Failed to load text file")
            return False

        # Create socket
        if not self.create_socket():
            print("Failed to create socket")
            return False

        # Start replay thread
        self.running = True
        self.current_index = 0
        self.thread = threading.Thread(target=self.replay_loop, daemon=True)
        self.thread.start()

        print("Replay started")
        return True

    def stop(self):
        """Stop replay"""
        if not self.running:
            print("Replay not running")
            return

        print("Stopping replay...")
        self.running = False

        # Wait for thread to finish
        if self.thread:
            self.thread.join(timeout=5)
            self.thread = None

        # Close socket
        if self.socket:
            self.socket.close()
            self.socket = None

        print("Replay stopped")

    def get_status(self):
        """Get current replay status"""
        return {
            'running': self.running,
            'progress': (self.current_index, len(self.packets)),
            'packets_count': len(self.packets)
        }


def main():
    """Main entry point"""
    print("=" * 70)
    print("AUV Text Replay Sender - 海试报文回放")
    print("=" * 70)
    print()

    # Create replay sender
    try:
        sender = TextPacketReplaySender()
    except Exception as e:
        print(f"Failed to initialize sender: {e}")
        sys.exit(1)

    # Start replay
    if not sender.start():
        print("Failed to start replay")
        sys.exit(1)

    print()
    print("-" * 70)
    print("Replay is running. Press Ctrl+C to stop.")
    print("-" * 70)
    print()

    # Keep running until interrupted
    try:
        while sender.running:
            time.sleep(1)

            # Print status every 10 packets
            status = sender.get_status()
            if status['running'] and status['packets_count'] > 0:
                current, total = status['progress']
                if current % 10 == 0:
                    print(f"Progress: {current}/{total} packets sent")

    except KeyboardInterrupt:
        print("\nReceived interrupt signal")

    # Stop replay
    sender.stop()

    print()
    print("=" * 70)
    print("Replay stopped")
    print("=" * 70)


if __name__ == "__main__":
    main()
