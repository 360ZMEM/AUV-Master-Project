#!/usr/bin/env python3
"""
PCAP UDP Replay Script
Replays AUV packets from PCAP file to local network for testing
Compatible with both C# and Python AUV Console applications

Usage:
    python pcap_replay_sender.py

Configuration: config/tools_config.ini (pcap_file) and config/pcap_replay_config.ini
"""

import sys
import os
import time
import socket
import threading
from scapy.all import rdpcap, UDP, Raw
from configobj import ConfigObj

# Import unified configuration
try:
    from config_loader import load_config
except ImportError:
    # Fallback
    def load_config():
        return None


class PcapReplaySender:
    """
    Replays AUV packets from PCAP file via UDP
    Acts as a virtual AUV sending telemetry data
    """

    def __init__(self, config_path: str = None):
        """Initialize replay sender with configuration"""
        if config_path is None:
            # Get project root
            current_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(current_dir, "config", "pcap_replay_config.ini")

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
                self.pcap_file = unified_config.get_pcap_path()
                default_interval = unified_config.get_replay_interval()
                default_loop = unified_config.get_replay_loop()
                self.local_ip = unified_config.get_local_ip()
                self.local_port = unified_config.get_auv_port()
                self.target_ip = unified_config.get_local_ip()
                self.target_port = unified_config.get_console_port()
            else:
                # Fallback to hardcoded defaults
                self.pcap_file = 'capture.pcapng'
                default_interval = 600
                default_loop = True
                self.local_ip = '127.0.0.1'
                self.local_port = 52364
                self.target_ip = '127.0.0.1'
                self.target_port = 21

            # Load legacy pcap_replay_config.ini for backward compatibility
            # This can override unified config settings
            if os.path.exists(self.config_path):
                self.config = ConfigObj(self.config_path)

                # Override with legacy config if specified
                sender = self.config.get('sender', {})
                if 'pcap_file' in sender:
                    self.pcap_file = sender['pcap_file']

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
            print(f"  PCAP file: {self.pcap_file}")
            print(f"  Replay interval: {self.replay_interval_ms}ms")
            print(f"  Loop playback: {self.loop_playback}")
            print(f"  Target: {self.target_ip}:{self.target_port}")
            print(f"  Local bind: {self.local_ip}:{self.local_port}")

        except Exception as e:
            print(f"Error loading configuration: {e}")
            raise

    def load_pcap(self) -> bool:
        """Load and filter AUV packets from PCAP file"""
        # Resolve PCAP file path
        pcap_path = os.path.join(os.path.dirname(__file__), self.pcap_file)

        if not os.path.exists(pcap_path):
            print(f"Error: PCAP file not found: {pcap_path}")
            return False

        try:
            print(f"Loading PCAP file: {pcap_path}")
            packets_data = rdpcap(pcap_path)

            # Filter UDP packets with AUV protocol header
            self.packets = []
            for packet in packets_data:
                if packet.haslayer(UDP):
                    udp = packet[UDP]
                    payload = bytes(udp.payload)

                    # Check for AUV packet header: 0x24 0x41 0x55 0x56 0x91
                    if len(payload) >= 5 and payload[0:5] == b'\x24\x41\x55\x56\x91':
                        self.packets.append(payload)

            print(f"Loaded {len(self.packets)} AUV packets from PCAP")
            return len(self.packets) > 0

        except Exception as e:
            print(f"Error loading PCAP file: {e}")
            return False

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
                print(f"Sent packet {progress[0]}/{progress[1]} "
                      f"({packet[0]:02x} {packet[1]:02x} {packet[2]:02x} {packet[3]:02x} {packet[4]:02x})...")

            self.current_index += 1

            # Wait before next packet
            if self.replay_interval_ms > 0:
                time.sleep(self.replay_interval_ms / 1000.0)

        print("Replay thread stopped")

    def start(self):
        """Start replay in background thread"""
        if self.running:
            print("Replay already running")
            return

        # Load packets
        if not self.load_pcap():
            print("Failed to load PCAP file")
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
    print("=" * 60)
    print("AUV PCAP UDP Replay Sender")
    print("=" * 60)
    print()

    # Check if scapy is available
    try:
        from scapy.all import rdpcap
    except ImportError:
        print("Error: scapy is not installed")
        print("Install with: pip install scapy")
        sys.exit(1)

    # Create replay sender
    try:
        sender = PcapReplaySender()
    except Exception as e:
        print(f"Failed to initialize sender: {e}")
        sys.exit(1)

    # Start replay
    if not sender.start():
        print("Failed to start replay")
        sys.exit(1)

    print()
    print("-" * 60)
    print("Replay is running. Press Ctrl+C to stop.")
    print("-" * 60)
    print()

    # Keep running until interrupted
    try:
        while sender.running:
            time.sleep(1)

            # Print status every 5 seconds
            status = sender.get_status()
            if status['running'] and status['packets_count'] > 0:
                current, total = status['progress']
                if current % 10 == 0:  # Print every 10 packets
                    print(f"Progress: {current}/{total} packets sent")

    except KeyboardInterrupt:
        print("\nReceived interrupt signal")

    # Stop replay
    sender.stop()

    print()
    print("=" * 60)
    print("Replay stopped")
    print("=" * 60)


if __name__ == "__main__":
    main()
