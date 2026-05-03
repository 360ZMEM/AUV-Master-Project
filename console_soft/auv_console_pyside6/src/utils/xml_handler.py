"""
XML waypoint file handler
C# Reference: Form1.cs XML handling (lines 2201-2250)
"""

import os
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import List
from ..data_structures import AutoFixedPoint


class XMLHandler:
    """
    Handle XML waypoint file import/export
    C# Reference: Form1.cs Point_File.xml handling
    """

    def __init__(self, filepath: str = None):
        """
        Initialize XML handler

        Args:
            filepath: Path to Point_File.xml
                     If None, uses default location
        """
        if filepath is None:
            app_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            filepath = os.path.join(app_path, "config", "Point_File.xml")

        self.filepath = filepath

    def load_waypoints(self) -> List[AutoFixedPoint]:
        """
        Load waypoints from Point_File.xml
        C# Reference: Form1.cs XML loading logic

        Returns:
            List of AutoFixedPoint objects
        """
        waypoints = []

        try:
            if not os.path.exists(self.filepath):
                print(f"Waypoint file not found: {self.filepath}")
                return waypoints

            tree = ET.parse(self.filepath)
            root = tree.getroot()

            # Find all Points elements
            for point_elem in root.findall('Points'):
                wp = AutoFixedPoint()

                # Parse longitude
                lon_elem = point_elem.find('Longitude')
                if lon_elem is not None and lon_elem.text:
                    wp.longitude = float(lon_elem.text)

                # Parse latitude
                lat_elem = point_elem.find('Latitude')
                if lat_elem is not None and lat_elem.text:
                    wp.latitude = float(lat_elem.text)

                # Parse control strategy
                strategy_elem = point_elem.find('strategy')
                if strategy_elem is not None and strategy_elem.text:
                    wp.control_strategy = int(strategy_elem.text)

                # Parse control parameter
                param_elem = point_elem.find('Parameter')
                if param_elem is not None and param_elem.text:
                    wp.control_param = float(param_elem.text)

                # Parse motor speed
                motor_elem = point_elem.find('MotorSetSpeed')
                if motor_elem is not None and motor_elem.text:
                    wp.motor_speed = int(motor_elem.text)

                # Parse device control (binary string)
                device_elem = point_elem.find('Device')
                if device_elem is not None and device_elem.text:
                    try:
                        wp.device_control = int(device_elem.text, 2)
                    except ValueError:
                        wp.device_control = 0

                waypoints.append(wp)

            print(f"Loaded {len(waypoints)} waypoints from {self.filepath}")

        except Exception as e:
            print(f"Error loading waypoints: {e}")

        return waypoints

    def save_waypoints(self, waypoints: List[AutoFixedPoint]):
        """
        Save waypoints to Point_File.xml
        C# Reference: Form1.cs button14_Click (generate XML)

        Args:
            waypoints: List of AutoFixedPoint objects
        """
        try:
            # Create root element
            root = ET.Element('AutoPloitPoint')
            root.set('TaskNumber', '')
            root.set('TotalTimeout', '')
            root.set('TotalNumber', str(len(waypoints)))

            # Add each waypoint
            for i, wp in enumerate(waypoints):
                point_elem = ET.SubElement(root, 'Points')
                point_elem.set('Name', f'Point{i+1}')

                # Track point number
                track_point = ET.SubElement(point_elem, 'TrackPoint')
                track_point.text = str(i + 1)

                # Longitude (6 decimal places)
                longitude = ET.SubElement(point_elem, 'Longitude')
                longitude.text = f"{wp.longitude:.6f}"

                # Latitude (6 decimal places)
                latitude = ET.SubElement(point_elem, 'Latitude')
                latitude.text = f"{wp.latitude:.6f}"

                # Control strategy
                strategy = ET.SubElement(point_elem, 'strategy')
                strategy.text = str(wp.control_strategy)

                # Control parameter
                param = ET.SubElement(point_elem, 'Parameter')
                param.text = str(wp.control_param)

                # Motor speed
                motor = ET.SubElement(point_elem, 'MotorSetSpeed')
                motor.text = str(wp.motor_speed)

                # Device control (8-bit binary string)
                device = ET.SubElement(point_elem, 'Device')
                device.text = f"{wp.device_control:08b}"

            # Pretty print XML
            xml_str = ET.tostring(root, encoding='unicode')
            dom = minidom.parseString(xml_str)
            pretty_xml = dom.toprettyxml(indent="  ")

            # Remove extra blank lines
            lines = [line for line in pretty_xml.split('\n') if line.strip()]
            pretty_xml = '\n'.join(lines)

            # Write to file
            with open(self.filepath, 'w', encoding='utf-8') as f:
                f.write(pretty_xml)

            print(f"Saved {len(waypoints)} waypoints to {self.filepath}")

        except Exception as e:
            print(f"Error saving waypoints: {e}")
            raise
