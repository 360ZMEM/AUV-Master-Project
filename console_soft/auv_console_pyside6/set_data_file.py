#!/usr/bin/env python3
"""
Quick configuration switcher for AUV Console Tools

Allows easy switching between different data files without editing config files.

Usage:
    python set_data_file.py                    # Show current configuration
    python set_data_file.py --list            # List available data files
    python set_data_file.py <filename>        # Set text log file
    python set_data_file.py --pcap <filename> # Set PCAP file
    python set_data_file.py --reset           # Reset to defaults
"""

import sys
import os
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

try:
    from config_loader import ToolsConfig
except ImportError:
    print("Error: config_loader.py not found")
    sys.exit(1)


def list_data_files(directory='.', extension='.txt'):
    """List available data files in directory"""
    txt_files = list(Path(directory).glob(f'*{extension}'))
    return sorted([f.name for f in txt_files if f.is_file()])


def show_current_config():
    """Display current configuration"""
    print("="*70)
    print("Current Configuration")
    print("="*70)

    config = ToolsConfig()

    print(f"\nConfig file: {config.config_file}")
    print(f"Config loaded: {config.loaded}")

    print(f"\n[files]")
    print(f"  Text log: {config.get_text_log_path()}")
    print(f"  PCAP file: {config.get_pcap_path()}")

    print(f"\n[analysis]")
    print(f"  Replay interval: {config.get_replay_interval()}ms")
    print(f"  Replay loop: {config.get_replay_loop()}")

    print(f"\n[network]")
    print(f"  Local mode: {config.get_local_mode()}")
    print(f"  Local IP: {config.get_local_ip()}")

    print("\n" + "="*70)


def set_text_file(filename):
    """Set text log file in configuration"""
    config_path = Path(__file__).parent / 'config' / 'tools_config.ini'

    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        return False

    # Read current config
    with open(config_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Update text_log_file
    updated = False
    for i, line in enumerate(lines):
        if line.strip().startswith('text_log_file'):
            lines[i] = f'text_log_file = {filename}\n'
            updated = True
            break

    if not updated:
        # Add to [files] section if not found
        for i, line in enumerate(lines):
            if line.strip() == '[files]':
                lines.insert(i + 1, f'text_log_file = {filename}\n')
                updated = True
                break

    # Write back
    with open(config_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    print(f"✓ Updated text_log_file to: {filename}")
    return True


def set_pcap_file(filename):
    """Set PCAP file in configuration"""
    config_path = Path(__file__).parent / 'config' / 'tools_config.ini'

    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        return False

    # Read current config
    with open(config_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Update pcap_file
    updated = False
    for i, line in enumerate(lines):
        if line.strip().startswith('pcap_file'):
            lines[i] = f'pcap_file = {filename}\n'
            updated = True
            break

    if not updated:
        # Add to [files] section if not found
        for i, line in enumerate(lines):
            if line.strip() == '[files]':
                lines.insert(i + 1, f'pcap_file = {filename}\n')
                updated = True
                break

    # Write back
    with open(config_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    print(f"✓ Updated pcap_file to: {filename}")
    return True


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Switch AUV Console Tools data files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python set_data_file.py                    # Show current config
  python set_data_file.py --list            # List available .txt files
  python set_data_file.py log.txt           # Set text log file
  python set_data_file.py --pcap cap.pcapng # Set PCAP file
  python set_data_file.py --reset           # Reset to defaults
        """
    )

    parser.add_argument('filename', nargs='?', help='Data file name')
    parser.add_argument('--list', '-l', action='store_true', help='List available data files')
    parser.add_argument('--pcap', '-p', action='store_true', help='Set PCAP file instead of text log')
    parser.add_argument('--reset', '-r', action='store_true', help='Reset to default configuration')
    parser.add_argument('--show', '-s', action='store_true', help='Show current configuration')

    args = parser.parse_args()

    # Show current config by default or with --show
    if not args.filename and not args.list and not args.reset:
        args.show = True

    # List available files
    if args.list:
        print("="*70)
        print("Available Data Files")
        print("="*70)

        txt_files = list_data_files('.', '.txt')
        pcap_files = list_data_files('.', '.pcapng')

        print(f"\nText log files ({len(txt_files)}):")
        for f in txt_files[:20]:  # Show first 20
            print(f"  - {f}")
        if len(txt_files) > 20:
            print(f"  ... and {len(txt_files) - 20} more")

        print(f"\nPCAP files ({len(pcap_files)}):")
        for f in pcap_files[:20]:
            print(f"  - {f}")
        if len(pcap_files) > 20:
            print(f"  ... and {len(pcap_files) - 20} more")

        print("\n" + "="*70)
        return 0

    # Reset to defaults
    if args.reset:
        print("Resetting to default configuration...")
        if set_text_file('20020101103632.txt') and set_pcap_file('capture.pcapng'):
            print("\n✓ Configuration reset to defaults")
            show_current_config()
            return 0
        return 1

    # Show current configuration
    if args.show:
        show_current_config()
        return 0

    # Set file
    if args.filename:
        if args.pcap:
            success = set_pcap_file(args.filename)
        else:
            success = set_text_file(args.filename)

        if success:
            print("\nConfiguration updated. Run with --show to verify.")
            return 0
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
