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
            # 文本日志是字段值列表，不是原始字节流。仅恢复可由 VxWorks
            # ToUI12 顺序和样本日志共同定界的字段，未知字段保持为 0。
            parts = [int(x) for x in re.findall(r'-?\d+', line)]
            if len(parts) < 22:
                return None

            # Create 145-byte packet
            packet = bytearray(145)

            # Frame header (bytes 0-4): $AUV + 0x91
            packet[0:5] = b'\x24\x41\x55\x56\x91'

            def put_u8(offset, value):
                packet[offset] = value & 0xFF

            def put_i8(offset, value):
                packet[offset] = value & 0xFF

            def put_u16(offset, value):
                packet[offset:offset + 2] = int(value).to_bytes(2, byteorder='big', signed=False)

            def put_i16(offset, value):
                packet[offset:offset + 2] = int(value).to_bytes(2, byteorder='big', signed=True)

            def put_i32(offset, value):
                packet[offset:offset + 4] = int(value).to_bytes(4, byteorder='big', signed=True)

            # txt[0] 是二进制 header 的第 5 字节 0x91；frame/address/mode 从 txt[1:4] 开始。
            put_u8(4, parts[0])
            put_u8(5, parts[1])
            put_u8(6, parts[2])
            put_u8(7, parts[3])

            fixed_u16 = [(8, 4), (10, 5), (12, 6), (14, 7), (16, 8)]
            for offset, pos in fixed_u16:
                if pos < len(parts):
                    put_u16(offset, max(0, min(parts[pos], 0xFFFF)))

            if len(parts) > 9:
                put_u8(22, parts[9])
            if len(parts) > 10:
                put_i16(23, parts[10])
            if len(parts) > 11:
                put_i16(25, parts[11])

            for offset, pos in [(27, 12), (29, 13), (31, 14), (33, 15)]:
                if pos < len(parts):
                    put_i16(offset, parts[pos])

            # 样本日志中 txt[19:22] 与 VxWorks offset 35/37/38 的 Pres/Temp/Depth 对齐。
            if len(parts) > 19:
                put_i16(35, parts[19])
            if len(parts) > 20:
                put_i8(37, parts[20])
            if len(parts) > 21:
                put_u16(38, max(0, min(parts[21], 0xFFFF)))

            # GPS 样经纬度只能按数值范围恢复；无法从文本日志区分所有位置字段。
            for val in parts:
                if 70000000 < val < 140000000 and packet[94:98] == b'\x00\x00\x00\x00':
                    put_i32(94, val)
                elif 10000000 < val < 55000000 and packet[98:102] == b'\x00\x00\x00\x00':
                    put_i32(98, val)

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
