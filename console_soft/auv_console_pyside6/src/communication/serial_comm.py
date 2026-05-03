"""
Serial port communication handler for Radio and Beidou
C# Reference: Form1.cs SerialPort usage
"""

import serial
import serial.tools.list_ports
from PySide6.QtCore import QObject, Signal


class SerialCommunicator(QObject):
    """
    Handle serial port communication (Radio or Beidou)
    C# Reference: Form1.cs serialPort_Radio, serialPort_BD
    """

    data_received = Signal(bytes)  # Signal emitted when data received

    def __init__(self, port_name: str, baudrate: int = 115200):
        super().__init__()
        self.port_name = port_name
        self.baudrate = baudrate
        self.serial_port = None
        self.is_running = False

    def open(self):
        """
        Open serial port
        C# Reference: Form1.cs serialPort.Open()
        """
        try:
            self.serial_port = serial.Serial(
                port=self.port_name,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1  # Non-blocking read timeout
            )
            self.is_running = True
            print(f"Serial port {self.port_name} opened at {self.baudrate} baud")
            return True
        except serial.SerialException as e:
            print(f"Failed to open {self.port_name}: {e}")
            return False

    def write(self, data: bytes):
        """
        Write data to serial port
        C# Reference: Form1.cs line 1482 serialPort_Radio.Write()
        """
        if self.serial_port and self.serial_port.is_open and self.is_running:
            try:
                self.serial_port.write(data)
                return True
            except Exception as e:
                print(f"Serial write error: {e}")
                return False
        return False

    def read(self) -> bytes:
        """
        Read available data from serial port
        C# Reference: Form1.cs serialPort_DataReceived events
        """
        if self.serial_port and self.serial_port.is_open and self.is_running:
            try:
                if self.serial_port.in_waiting > 0:
                    return self.serial_port.read(self.serial_port.in_waiting)
            except Exception as e:
                print(f"Serial read error: {e}")
        return None

    def close(self):
        """Close serial port"""
        self.is_running = False
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.close()
                print(f"Serial port {self.port_name} closed")
            except Exception as e:
                print(f"Error closing serial port: {e}")

    @staticmethod
    def list_available_ports():
        """
        List all available serial ports
        Returns: List of port device names
        """
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]
