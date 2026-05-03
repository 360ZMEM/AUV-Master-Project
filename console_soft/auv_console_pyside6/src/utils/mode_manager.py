"""
Mode configuration manager for online/offline switching
"""

from configobj import ConfigObj
import os
from typing import Dict


class ModeConfigManager:
    """
    Manage operation mode configuration (online/offline)
    """

    MODE_ONLINE = "online"
    MODE_OFFLINE = "offline"

    def __init__(self, config_path: str = None):
        """
        Initialize mode configuration manager

        Args:
            config_path: Path to mode_config.ini
        """
        if config_path is None:
            # Get project root
            current_dir = os.path.dirname(os.path.abspath(__file__))
            src_dir = os.path.dirname(current_dir)
            project_root = os.path.dirname(src_dir)
            config_path = os.path.join(project_root, "config", "mode_config.ini")

        self.config_path = config_path
        self.config = None

    def load_config(self) -> Dict:
        """
        Load mode configuration

        Returns:
            Dictionary with configuration
        """
        try:
            self.config = ConfigObj(self.config_path)
            mode = self.config.get('mode', 'online')

            result = {
                'mode': mode,
                'online': {},
                'offline': {}
            }

            if 'online' in self.config:
                result['online'] = dict(self.config['online'])

            if 'offline' in self.config:
                result['offline'] = dict(self.config['offline'])

            return result

        except Exception as e:
            print(f"Error loading mode config: {e}")
            # Return default configuration
            return {
                'mode': 'online',
                'online': {'enabled': True},
                'offline': {
                    'pcap_file': '../PC104抓包结果.pcapng',
                    'replay_interval_ms': 600,
                    'loop_playback': 'true'
                }
            }

    def save_config(self, config: Dict):
        """
        Save mode configuration

        Args:
            config: Configuration dictionary
        """
        try:
            from configobj import ConfigObj
            self.config = ConfigObj()
            self.config.filename = self.config_path
            self.config.encoding = 'UTF-8'

            # Add mode
            self.config['mode'] = config.get('mode', 'online')

            # Add online section
            if 'online' in config:
                self.config['online'] = config['online']

            # Add offline section
            if 'offline' in config:
                self.config['offline'] = config['offline']

            # Save
            self.config.write()

            print(f"Mode configuration saved to {self.config_path}")

        except Exception as e:
            print(f"Error saving mode config: {e}")

    def get_mode(self) -> str:
        """Get current mode"""
        config = self.load_config()
        return config.get('mode', self.MODE_ONLINE)

    def is_online_mode(self) -> bool:
        """Check if in online mode"""
        return self.get_mode() == self.MODE_ONLINE

    def is_offline_mode(self) -> bool:
        """Check if in offline mode"""
        return self.get_mode() == self.MODE_OFFLINE

    def set_online_mode(self):
        """Set to online mode"""
        config = self.load_config()
        config['mode'] = self.MODE_ONLINE
        self.save_config(config)
        print("Switched to ONLINE mode")

    def set_offline_mode(self):
        """Set to offline mode"""
        config = self.load_config()
        config['mode'] = self.MODE_OFFLINE
        self.save_config(config)
        print("Switched to OFFLINE mode")
