#!/usr/bin/env python3
"""
Migrate from legacy config files to unified tools_config.ini

This script helps migrate settings from:
- config/text_replay_config.ini
- config/pcap_replay_config.ini

To the new unified config:
- config/tools_config.ini

Usage:
    python migrate_to_unified_config.py     # Preview migration
    python migrate_to_unified_config.py --execute  # Execute migration
"""

import sys
import os
from pathlib import Path


# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

try:
    from configobj import ConfigObj
except ImportError:
    print("Error: configobj not installed. Run: pip install configobj")
    sys.exit(1)


def migrate_text_replay_config():
    """Migrate text_replay_config.ini to tools_config.ini"""
    legacy_path = Path('config/text_replay_config.ini')
    unified_path = Path('config/tools_config.ini')

    if not legacy_path.exists():
        print("✓ Legacy text_replay_config.ini not found (already migrated)")
        return None

    # Read legacy config
    try:
        legacy = ConfigObj(str(legacy_path))
        sender = legacy.get('sender', {})
        network = legacy.get('network', {})

        migrations = []

        # Check for custom text_file
        if 'text_file' in sender:
            old_file = sender['text_file']
            if old_file != '20020101103632.txt':  # Non-default value
                migrations.append(('text_log_file', old_file))

        # Check for custom interval
        if 'replay_interval_ms' in sender:
            interval = sender['replay_interval_ms']
            if interval != '600':  # Non-default value
                migrations.append(('replay_interval_ms', interval))

        # Check for custom network settings
        for key in ['local_ip', 'local_port', 'target_ip', 'target_port']:
            if key in network:
                migrations.append((key, network[key]))

        if not migrations:
            print("✓ text_replay_config.ini: No custom settings to migrate")
            return None

        print(f"\nFound {len(migrations)} custom settings in text_replay_config.ini:")
        for key, value in migrations:
            print(f"  {key}: {value}")

        return migrations

    except Exception as e:
        print(f"✗ Error reading text_replay_config.ini: {e}")
        return None


def migrate_pcap_replay_config():
    """Migrate pcap_replay_config.ini to tools_config.ini"""
    legacy_path = Path('config/pcap_replay_config.ini')

    if not legacy_path.exists():
        print("✓ Legacy pcap_replay_config.ini not found (already migrated)")
        return None

    # Read legacy config
    try:
        legacy = ConfigObj(str(legacy_path))
        sender = legacy.get('sender', {})
        network = legacy.get('network', {})

        migrations = []

        # Check for custom pcap_file
        if 'pcap_file' in sender:
            old_file = sender['pcap_file']
            if old_file != 'PC104.pcapng':  # Non-default value
                migrations.append(('pcap_file', old_file))

        # Check for other settings (same as text_replay)
        if 'replay_interval_ms' in sender:
            interval = sender['replay_interval_ms']
            if interval != '600':
                migrations.append(('replay_interval_ms', interval))

        for key in ['local_ip', 'local_port', 'target_ip', 'target_port']:
            if key in network:
                if key not in [m[0] for m in migrations]:  # Avoid duplicates
                    migrations.append((key, network[key]))

        if not migrations:
            print("✓ pcap_replay_config.ini: No custom settings to migrate")
            return None

        print(f"\nFound {len(migrations)} custom settings in pcap_replay_config.ini:")
        for key, value in migrations:
            print(f"  {key}: {value}")

        return migrations

    except Exception as e:
        print(f"✗ Error reading pcap_replay_config.ini: {e}")
        return None


def backup_configs():
    """Backup existing config files"""
    import shutil
    from datetime import datetime

    backup_dir = Path('config/backup')
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    configs_to_backup = [
        'config/tools_config.ini',
        'config/text_replay_config.ini',
        'config/pcap_replay_config.ini'
    ]

    print(f"\nCreating backups in {backup_dir}/...")
    backed_up = []

    for config_path in configs_to_backup:
        if Path(config_path).exists():
            backup_name = f"{Path(config_path).stem}_{timestamp}{Path(config_path).suffix}"
            backup_path = backup_dir / backup_name
            shutil.copy2(config_path, backup_path)
            backed_up.append(backup_name)
            print(f"  ✓ Backed up: {backup_name}")

    if not backed_up:
        print("  No config files to backup")

    return True


def remove_legacy_configs(execute=False):
    """Remove or rename legacy config files"""
    import shutil

    legacy_configs = [
        ('config/text_replay_config.ini', 'config/text_replay_config.ini.old'),
        ('config/pcap_replay_config.ini', 'config/pcap_replay_config.ini.old'),
    ]

    print("\n" + "="*70)
    if execute:
        print("Renaming legacy config files (.old extension):")
    else:
        print("Would rename legacy config files (.old extension):")
    print("="*70)

    for original, new_name in legacy_configs:
        if Path(original).exists():
            if execute:
                try:
                    shutil.move(original, new_name)
                    print(f"  ✓ Renamed: {original} → {new_name}")
                except Exception as e:
                    print(f"  ✗ Error renaming {original}: {e}")
            else:
                print(f"  - {original} → {new_name}")

    return True


def main():
    """Main migration function"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Migrate to unified configuration system'
    )
    parser.add_argument('--execute', '-e', action='store_true',
                       help='Execute migration (default: preview only)')
    parser.add_argument('--backup', '-b', action='store_true',
                       help='Create backups before migration')

    args = parser.parse_args()

    print("="*70)
    print("AUV Console Tools - Configuration Migration")
    print("="*70)

    # Preview migrations
    print("\n[1/3] Scanning for legacy configurations...")
    print("-"*70)

    text_migrations = migrate_text_replay_config()
    pcap_migrations = migrate_pcap_replay_config()

    if not text_migrations and not pcap_migrations:
        print("\n✓ No custom settings found in legacy configs.")
        print("  Your system is already using unified configuration!")
        print("\nRecommended action:")
        print("  1. Remove or rename legacy config files:")
        print("     mv config/text_replay_config.ini config/text_replay_config.ini.old")
        print("     mv config/pcap_replay_config.ini config/pcap_replay_config.ini.old")
        print("  2. Or run: python migrate_to_unified_config.py --execute")
        return 0

    # Show current unified config
    print("\n[2/3] Current unified configuration...")
    print("-"*70)
    try:
        from config_loader import load_config
        config = load_config()
        print(f"  Text log: {config.get_text_log_path()}")
        print(f"  PCAP file: {config.get_pcap_path()}")
    except Exception as e:
        print(f"  ✗ Error reading config: {e}")

    # Ask for confirmation or show what would be done
    print("\n" + "="*70)
    if args.execute:
        if args.backup:
            backup_configs()

        print("[3/3] Executing migration...")
        print("-"*70)

        # Rename legacy configs
        remove_legacy_configs(execute=True)

        print("\n" + "="*70)
        print("✓ Migration complete!")
        print("="*70)
        print("\nNext steps:")
        print("  1. Verify your tools work correctly:")
        print("     python packet_viewer.py")
        print("     python test_text_tools.py")
        print("  2. If everything works, delete the .old backup files:")
        print("     rm config/text_replay_config.ini.old")
        print("     rm config/pcap_replay_config.ini.old")
        print("  3. To change data files, use:")
        print("     python set_data_file.py <filename>")

    else:
        print("[3/3] Preview mode - no changes made")
        print("-"*70)
        print("\nTo execute migration, run:")
        print("  python migrate_to_unified_config.py --execute")
        print("\nWith backup:")
        print("  python migrate_to_unified_config.py --execute --backup")
        print("\nThis will:")
        print("  1. Backup current config files to config/backup/")
        print("  2. Rename legacy configs to .old extension")
        print("  3. All tools will then use tools_config.ini exclusively")

    print("="*70)
    return 0


if __name__ == '__main__':
    sys.exit(main())
