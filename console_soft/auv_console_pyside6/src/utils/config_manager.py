"""
Configuration file manager
C# Reference: Form1.cs Form1_Load() lines 266-340
"""

import os
import json
from configparser import ConfigParser
from typing import Dict


class ConfigManager:
    """
    Handle configuration file I/O
    C# Reference: Form1.cs port_set.txt and param.txt loading
    """

    def __init__(self, app_path: str = None):
        """
        Initialize configuration manager

        Args:
            app_path: Application path (where config files are located)
                     If None, uses parent of src directory
        """
        if app_path is None:
            # Get the project root (parent of src directory)
            current_dir = os.path.dirname(os.path.abspath(__file__))
            src_dir = os.path.dirname(current_dir)
            app_path = os.path.dirname(src_dir)

        self.app_path = app_path
        self.port_set_file = os.path.join(app_path, "config", "port_set.txt")
        self.param_file = os.path.join(app_path, "config", "param.txt")
        self.side_channel_file = os.path.join(app_path, "config", "zenoh_side_channel.ini")

    def load_port_config(self) -> Dict[str, any]:
        """
        Load port_set.txt (6 lines)
        C# Reference: Form1.cs lines 266-287

        Returns:
            Dictionary with keys:
                - radio_port: str
                - beidou_port: str
                - console_ip: str
                - console_port: int
                - auv_ip: str
                - auv_port: int
        """
        config = {}

        try:
            with open(self.port_set_file, 'r', encoding='utf-8') as f:
                config['radio_port'] = f.readline().strip()
                config['beidou_port'] = f.readline().strip()
                config['console_ip'] = f.readline().strip()
                config['console_port'] = int(f.readline().strip())
                config['auv_ip'] = f.readline().strip()
                config['auv_port'] = int(f.readline().strip())

            print(f"Port configuration loaded from {self.port_set_file}")
            print(f"  Radio: {config['radio_port']}, Beidou: {config['beidou_port']}")
            print(f"  Console: {config['console_ip']}:{config['console_port']}")
            print(f"  AUV: {config['auv_ip']}:{config['auv_port']}")

        except FileNotFoundError:
            print(f"Warning: {self.port_set_file} not found, using defaults")
            config = {
                'radio_port': 'COM3',
                'beidou_port': 'COM4',
                'console_ip': '192.168.0.11',
                'console_port': 21,
                'auv_ip': '192.168.0.101',
                'auv_port': 52364
            }
        except Exception as e:
            print(f"Error loading port configuration: {e}")
            raise

        return config

    def save_port_config(self, config: Dict[str, any]):
        """
        Save port_set.txt (6 lines)
        C# Reference: Form3.cs save button handler

        Args:
            config: Dictionary with same structure as load_port_config() returns
        """
        try:
            with open(self.port_set_file, 'w', encoding='utf-8') as f:
                f.write(config['radio_port'] + '\n')
                f.write(config['beidou_port'] + '\n')
                f.write(config['console_ip'] + '\n')
                f.write(str(config['console_port']) + '\n')
                f.write(config['auv_ip'] + '\n')
                f.write(str(config['auv_port']) + '\n')

            print(f"Port configuration saved to {self.port_set_file}")

        except Exception as e:
            print(f"Error saving port configuration: {e}")
            raise

    def load_parameters(self) -> Dict[str, any]:
        """
        Load param.txt (11 lines)
        C# Reference: Form1.cs lines 293-340

        Returns:
            Dictionary with parameters matching Preferences structure
        """
        params = {}

        try:
            with open(self.param_file, 'r', encoding='utf-8') as f:
                params['obj_address'] = int(f.readline().strip())
                params['work_mode'] = int(f.readline().strip())
                params['depth_proprotect_param1'] = int(f.readline().strip())
                params['depth_proprotect_param2'] = int(f.readline().strip())
                params['bottom_proprotect_param1'] = int(f.readline().strip())
                params['bottom_proprotect_param2'] = int(f.readline().strip())
                params['preset_time'] = int(f.readline().strip())
                params['spare_param1'] = int(f.readline().strip())
                params['spare_param2'] = int(f.readline().strip())
                params['return_longitude'] = int(f.readline().strip())
                params['return_latitude'] = int(f.readline().strip())

            print(f"Parameters loaded from {self.param_file}")
            print(f"  Address: {params['obj_address']}, Mode: {params['work_mode']}")

        except FileNotFoundError:
            print(f"Warning: {self.param_file} not found, using defaults")
            params = {
                'obj_address': 2,
                'work_mode': 2,
                'depth_proprotect_param1': 500,
                'depth_proprotect_param2': 29,
                'bottom_proprotect_param1': 300,
                'bottom_proprotect_param2': 200,
                'preset_time': 10,
                'spare_param1': 0,
                'spare_param2': 0,
                'return_longitude': 0,
                'return_latitude': 0
            }
        except Exception as e:
            print(f"Error loading parameters: {e}")
            raise

        return params

    def save_parameters(self, params: Dict[str, any]):
        """
        Save param.txt (11 lines)
        C# Reference: Form1.cs button1_Click (save preferences)

        Args:
            params: Dictionary with same structure as load_parameters() returns
        """
        try:
            with open(self.param_file, 'w', encoding='utf-8') as f:
                f.write(str(params['obj_address']) + '\n')
                f.write(str(params['work_mode']) + '\n')
                f.write(str(params['depth_proprotect_param1']) + '\n')
                f.write(str(params['depth_proprotect_param2']) + '\n')
                f.write(str(params['bottom_proprotect_param1']) + '\n')
                f.write(str(params['bottom_proprotect_param2']) + '\n')
                f.write(str(params['preset_time']) + '\n')
                f.write(str(params['spare_param1']) + '\n')
                f.write(str(params['spare_param2']) + '\n')
                f.write(str(params['return_longitude']) + '\n')
                f.write(str(params['return_latitude']) + '\n')

            print(f"Parameters saved to {self.param_file}")

        except Exception as e:
            print(f"Error saving parameters: {e}")
            raise

    def load_side_channel_config(self) -> Dict[str, any]:
        """Load optional Zenoh side-channel settings for arbiter integration."""
        defaults = {
            'enabled': False,
            'pc_cmd_raw_key': 'rt/pc/cmd_raw',
            'telemetry_key': 'rt/auv/telemetry',
            'viz_internal_key': 'rt/auv/viz/internal',
            'publish_cmd_raw': True,
            'subscribe_bridge_telemetry': True,
            'subscribe_viz_internal': False,
            'session': {},
        }

        if not os.path.exists(self.side_channel_file):
            print(f"Warning: {self.side_channel_file} not found, side channel disabled by default")
            return defaults

        parser = ConfigParser()
        parser.read(self.side_channel_file, encoding='utf-8')
        if not parser.has_section('zenoh_side_channel'):
            return defaults

        section = parser['zenoh_side_channel']
        session_text = section.get('session_json', '{}')
        try:
            session = json.loads(session_text)
        except Exception:
            session = {}

        return {
            'enabled': section.getboolean('enabled', fallback=defaults['enabled']),
            'pc_cmd_raw_key': section.get('pc_cmd_raw_key', fallback=defaults['pc_cmd_raw_key']),
            'telemetry_key': section.get('telemetry_key', fallback=defaults['telemetry_key']),
            'viz_internal_key': section.get('viz_internal_key', fallback=defaults['viz_internal_key']),
            'publish_cmd_raw': section.getboolean('publish_cmd_raw', fallback=defaults['publish_cmd_raw']),
            'subscribe_bridge_telemetry': section.getboolean(
                'subscribe_bridge_telemetry', fallback=defaults['subscribe_bridge_telemetry']
            ),
            'subscribe_viz_internal': section.getboolean(
                'subscribe_viz_internal', fallback=defaults['subscribe_viz_internal']
            ),
            'session': session if isinstance(session, dict) else {},
        }
