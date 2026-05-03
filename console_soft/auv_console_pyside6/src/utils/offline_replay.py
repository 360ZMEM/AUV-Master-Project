"""
Offline pcap replay module for debugging
Reads Wireshark pcap files and replays UDP packets
"""

from scapy.all import rdpcap, UDP, Raw
from PySide6.QtCore import QObject, Signal, QThread, QTimer
import os
import time
from typing import List


class PcapReplayWorker(QThread):
    """
    Worker thread for replaying pcap packets
    """

    packet_received = Signal(bytes)  # Signal when packet is replayed
    playback_finished = Signal()  # Signal when playback is complete

    def __init__(self, pcap_path: str, interval_ms: int = 600):
        super().__init__()
        self.pcap_path = pcap_path
        self.interval_ms = interval_ms
        self.running = True
        self.loop = False

        # Load packets
        self.packets = self._load_pcap()
        self.current_index = 0

    def _load_pcap(self) -> List[bytes]:
        """Load UDP packets from pcap file"""
        packets = []

        if not os.path.exists(self.pcap_path):
            print(f"Warning: PCAP file not found: {self.pcap_path}")
            return packets

        try:
            print(f"Loading PCAP file: {self.pcap_path}")
            packets_data = rdpcap(self.pcap_path)

            # Filter UDP packets and extract payload
            for packet in packets_data:
                if packet.haslayer(UDP):
                    udp = packet[UDP]
                    # Get UDP payload
                    payload = bytes(udp.payload)

                    # Check if it's AUV packet (starts with 0x24 0x41 0x55 0x56 0x91)
                    if len(payload) >= 5 and payload[0:5] == b'\x24\x41\x55\x56\x91':
                        packets.append(payload)

            print(f"Loaded {len(packets)} AUV packets from PCAP")
            return packets

        except Exception as e:
            print(f"Error loading PCAP file: {e}")
            return packets

    def run(self):
        """Replay packets"""
        print(f"Starting PCAP replay: {len(self.packets)} packets")

        while self.running:
            if self.current_index >= len(self.packets):
                if self.loop and len(self.packets) > 0:
                    print("Looping PCAP replay")
                    self.current_index = 0
                    time.sleep(1)  # Pause before looping
                else:
                    print("PCAP replay finished")
                    self.playback_finished.emit()
                    break

            # Send current packet
            packet = self.packets[self.current_index]
            self.packet_received.emit(packet)

            self.current_index += 1

            # Wait before next packet
            if self.interval_ms > 0:
                self.msleep(self.interval_ms)

    def stop(self):
        """Stop replay"""
        self.running = False
        self.wait()

    def get_packet_count(self) -> int:
        """Get total number of packets"""
        return len(self.packets)

    def get_progress(self) -> tuple:
        """Get replay progress (current, total)"""
        return (self.current_index, len(self.packets))


class OfflineReplayManager(QObject):
    """
    Manager for offline pcap replay
    """

    packet_received = Signal(bytes)
    status_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.worker = None
        self.pcap_path = ""
        self.interval_ms = 600
        self.loop = False
        self.is_replaying = False

    def load_pcap(self, pcap_path: str) -> bool:
        """Load pcap file"""
        self.pcap_path = pcap_path

        # Create temporary worker to test loading
        test_worker = PcapReplayWorker(pcap_path, 0)
        packet_count = test_worker.get_packet_count()

        if packet_count > 0:
            self.status_changed.emit(f"Loaded {packet_count} packets from {os.path.basename(pcap_path)}")
            return True
        else:
            self.status_changed.emit(f"No packets found in {pcap_path}")
            return False

    def start_replay(self, interval_ms: int = 600, loop: bool = False):
        """Start packet replay"""
        if self.is_replaying:
            self.stop_replay()

        self.interval_ms = interval_ms
        self.loop = loop

        self.worker = PcapReplayWorker(self.pcap_path, interval_ms)
        self.worker.loop = loop
        self.worker.packet_received.connect(self._on_packet_received)
        self.worker.playback_finished.connect(self._on_playback_finished)

        self.worker.start()
        self.is_replaying = True
        self.status_changed.emit(f"Replay started: {self.worker.get_packet_count()} packets")

    def stop_replay(self):
        """Stop packet replay"""
        if self.worker:
            self.worker.stop()
            self.worker = None
            self.is_replaying = False
            self.status_changed.emit("Replay stopped")

    def _on_packet_received(self, packet: bytes):
        """Handle received packet from replay"""
        # Emit signal for main window
        self.packet_received.emit(packet)

        # Update status
        if self.worker:
            current, total = self.worker.get_progress()
            self.status_changed.emit(f"Replaying: {current}/{total} packets")

    def _on_playback_finished(self):
        """Handle playback finished"""
        self.is_replaying = False
        self.worker = None
        self.status_changed.emit("Replay finished")

    def get_packet_count(self) -> int:
        """Get packet count"""
        if self.worker:
            return self.worker.get_packet_count()
        return 0
