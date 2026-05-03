#!/usr/bin/env python3
"""
Unified Configuration Loader for AUV Console Tools

This module provides centralized configuration management for all AUV analysis tools:
- packet_viewer.py
- text_replay_sender.py
- pcap_replay_sender.py
- test_text_tools.py

Usage:
    from config_loader import load_config

    config = load_config()
    text_file = config.get_text_log_path()
    pcap_file = config.get_pcap_path()
"""

import os
import configparser
from pathlib import Path
from typing import Optional


class ToolsConfig:
    """Unified configuration manager for AUV tools"""

    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize configuration

        Args:
            config_file: Path to config file (default: config/tools_config.ini)
        """
        if config_file is None:
            # Default to config/tools_config.ini relative to this file
            script_dir = Path(__file__).parent
            config_file = script_dir / 'config' / 'tools_config.ini'

        self.config_file = Path(config_file)
        self.config = configparser.ConfigParser()

        # Load configuration
        if self.config_file.exists():
            self.config.read(self.config_file, encoding='utf-8')
            self.loaded = True
        else:
            print(f"Warning: Config file not found: {self.config_file}")
            print("Using default values")
            self.loaded = False

    def get_text_log_path(self, default: str = '20020101103632.txt') -> str:
        """
        Get path to text log file

        Args:
            default: Default filename if not configured

        Returns:
            Absolute or relative path to text log file
        """
        if self.loaded:
            filename = self.config.get('files', 'text_log_file', fallback=default)
        else:
            filename = default

        # Check if it's an absolute path
        if os.path.isabs(filename):
            return filename

        # Resolve relative to data_dir or current directory
        if self.loaded:
            data_dir = self.config.get('paths', 'data_dir', fallback='')
            if data_dir:
                return os.path.join(data_dir, filename)

        # Default: relative to current directory
        return filename

    def get_pcap_path(self, default: str = 'capture.pcapng') -> str:
        """
        Get path to PCAP capture file

        Args:
            default: Default filename if not configured

        Returns:
            Absolute or relative path to PCAP file
        """
        if self.loaded:
            filename = self.config.get('files', 'pcap_file', fallback=default)
        else:
            filename = default

        # Check if it's an absolute path
        if os.path.isabs(filename):
            return filename

        # Resolve relative to data_dir or current directory
        if self.loaded:
            data_dir = self.config.get('paths', 'data_dir', fallback='')
            if data_dir:
                return os.path.join(data_dir, filename)

        # Default: relative to current directory
        return filename

    def get_replay_interval(self) -> int:
        """Get replay interval in milliseconds"""
        if self.loaded:
            return self.config.getint('analysis', 'replay_interval_ms', fallback=600)
        return 600

    def get_replay_loop(self) -> bool:
        """Get replay loop setting"""
        if self.loaded:
            return self.config.getboolean('analysis', 'replay_loop', fallback=True)
        return True

    def get_replay_auto_start(self) -> bool:
        """Get replay auto-start setting"""
        if self.loaded:
            return self.config.getboolean('analysis', 'replay_auto_start', fallback=False)
        return False

    def get_gps_precision(self) -> int:
        """Get GPS coordinate precision (decimal places)"""
        if self.loaded:
            return self.config.getint('display', 'gps_precision', fallback=6)
        return 6

    def get_local_mode(self) -> bool:
        """Get local simulation mode setting"""
        if self.loaded:
            return self.config.getboolean('network', 'local_mode', fallback=True)
        return True

    def get_local_ip(self) -> str:
        """Get local IP for simulation"""
        if self.loaded:
            return self.config.get('network', 'local_ip', fallback='127.0.0.1')
        return '127.0.0.1'

    def get_console_port(self) -> int:
        """Get console port number"""
        if self.loaded:
            return self.config.getint('network', 'console_port', fallback=21)
        return 21

    def get_auv_port(self) -> int:
        """Get AUV port number"""
        if self.loaded:
            return self.config.getint('network', 'auv_port', fallback=52364)
        return 52364


# Global configuration instance
_global_config: Optional[ToolsConfig] = None


def load_config(config_file: Optional[str] = None) -> ToolsConfig:
    """
    Load or get global configuration instance

    Args:
        config_file: Optional path to config file

    Returns:
        ToolsConfig instance
    """
    global _global_config

    if _global_config is None:
        _global_config = ToolsConfig(config_file)

    return _global_config


def get_text_log_path(default: str = '20020101103632.txt') -> str:
    """Convenience function to get text log path"""
    config = load_config()
    return config.get_text_log_path(default)


def get_pcap_path(default: str = 'capture.pcapng') -> str:
    """Convenience function to get PCAP path"""
    config = load_config()
    return config.get_pcap_path(default)


if __name__ == '__main__':
    """Test configuration loading"""
    print("="*60)
    print("AUV Tools Configuration Test")
    print("="*60)

    config = load_config()

    print(f"\nConfig file: {config.config_file}")
    print(f"Loaded: {config.loaded}")

    print(f"\nFiles:")
    print(f"  Text log: {config.get_text_log_path()}")
    print(f"  PCAP file: {config.get_pcap_path()}")

    print(f"\nAnalysis:")
    print(f"  Replay interval: {config.get_replay_interval()}ms")
    print(f"  Replay loop: {config.get_replay_loop()}")
    print(f"  GPS precision: {config.get_gps_precision()} decimals")

    print(f"\nNetwork:")
    print(f"  Local mode: {config.get_local_mode()}")
    print(f"  Local IP: {config.get_local_ip()}")
    print(f"  Console port: {config.get_console_port()}")
    print(f"  AUV port: {config.get_auv_port()}")

    print("\n" + "="*60)
    print("✓ Configuration loaded successfully")
    print("="*60)
