#!/usr/bin/env python3
"""
AUV Packet Protocol Viewer
Visualizes communication packets from text log file for learning and analysis

Features:
- Parse CKTH (Console to AUV) and AUV (AUV to Console) packets
- Display byte-by-byte protocol field meanings
- Navigate through time sequence
- Show raw bytes and decoded values

Usage:
    python packet_viewer.py
"""

import sys
import os
import re
import struct
from typing import List, Dict, Tuple, Optional
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QPushButton, QTextEdit,
                               QTableWidget, QTableWidgetItem, QHeaderView,
                               QGroupBox, QSplitter, QFrame, QFileDialog, QMessageBox)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QKeyEvent

# Import configuration loader
try:
    from config_loader import get_text_log_path
except ImportError:
    # Fallback if config_loader not available
    def get_text_log_path(default='20020101103632.txt'):
        return default


# Protocol constants (from packet_builder.py)
FRAME_HEADER_SEND = b'\x24\x43\x4B\x54\x48'  # $CKTH
FRAME_HEADER_RECV = b'\x24\x41\x55\x56\x91'  # $AUV
FRAME_TRAILER = b'\xFF\xFF'

SEND_PACKET_SIZE = 72
RECV_PACKET_SIZE = 145


class PacketEntry:
    """Single packet entry with timestamp and parsed data"""

    def __init__(self, timestamp: str, packet_type: str, raw_data: dict):
        self.timestamp = timestamp
        self.packet_type = packet_type  # 'CKTH' or 'AUV'
        self.raw_data = raw_data
        self.decoded = None

    def decode(self):
        """Decode packet based on type"""
        try:
            if self.packet_type == 'CKTH':
                self.decoded = self._decode_ckth()
            else:
                self.decoded = self._decode_auv()
        except Exception as e:
            print(f"Warning: Error decoding {self.packet_type} packet: {e}")
            # Create minimal decoded info
            self.decoded = [{
                'offset': 0,
                'name': 'Error',
                'bytes': 0,
                'value': 'N/A',
                'meaning': f'Failed to decode: {e}'
            }]

    def _decode_ckth(self) -> List[dict]:
        """Decode CKTH (send) packet"""
        fields = []
        data = self.raw_data

        # Frame header
        fields.append({
            'offset': 0,
            'name': '帧头',
            'bytes': 5,
            'value': '$CKTH',
            'meaning': '发送报文标识 (0x24 0x43 0x4B 0x54 0x48)'
        })

        # Frame number
        frame_num = data.get('frame', 0)
        fields.append({
            'offset': 5,
            'name': '帧序号',
            'bytes': 1,
            'value': frame_num,
            'meaning': f'报文计数器 (0x{frame_num:02X})'
        })

        # Target address
        addr = data.get('address', 1)
        fields.append({
            'offset': 6,
            'name': '目标地址',
            'bytes': 1,
            'value': addr,
            'meaning': f'AUV设备编号 (1-3)'
        })

        # Work mode
        mode = data.get('mode', 0)
        mode_names = ['仅发送', '遥控', '定点', '定向', '回航']
        fields.append({
            'offset': 7,
            'name': '工作模式',
            'bytes': 1,
            'value': mode,
            'meaning': f'{mode_names[mode] if mode < 5 else "未知"} (0x{mode:02X})'
        })

        # Depth protection
        depth1 = data.get('depth1', 500)
        depth2 = data.get('depth2', 500)
        fields.append({
            'offset': 8,
            'name': '深度保护1',
            'bytes': 2,
            'value': depth1,
            'meaning': f'深度下限参数1 ({depth1/10:.1f}m)'
        })
        fields.append({
            'offset': 10,
            'name': '深度保护2',
            'bytes': 2,
            'value': depth2,
            'meaning': f'深度下限参数2 ({depth2/10:.1f}m)'
        })

        # Bottom protection
        bottom1 = data.get('bottom1', 500)
        bottom2 = data.get('bottom2', 500)
        fields.append({
            'offset': 12,
            'name': '离底保护1',
            'bytes': 2,
            'value': bottom1,
            'meaning': f'离底高度参数1 ({bottom1/10:.1f}m)'
        })
        fields.append({
            'offset': 14,
            'name': '离底保护2',
            'bytes': 2,
            'value': bottom2,
            'meaning': f'离底高度参数2 ({bottom2/10:.1f}m)'
        })

        # Preset time
        preset = data.get('preset', 0)
        fields.append({
            'offset': 16,
            'name': '预设时间',
            'bytes': 2,
            'value': preset,
            'meaning': f'任务预设时间 ({preset*0.1:.1f}分钟)'
        })

        # Work instruction
        work_inst = data.get('work_instruct', 0)
        cmd_names = {
            0x00: '无', 0x01: '任务开启', 0x02: '任务取消', 0x03: '清除故障',
            0x04: '初始化', 0x11: '主推上电', 0x12: '主推断电'
        }
        cmd_name = cmd_names.get(work_inst, f'未知(0x{work_inst:02X})')
        fields.append({
            'offset': 22,
            'name': '工作指令',
            'bytes': 1,
            'value': f'0x{work_inst:02X}',
            'meaning': cmd_name
        })

        # Motor speeds
        motor1 = data.get('motor1', 0)
        motor2 = data.get('motor2', 0)
        fields.append({
            'offset': 23,
            'name': '主推进器1',
            'bytes': 2,
            'value': motor1,
            'meaning': f'转速1 ({motor1 if motor1 >= 0 else "N/A"})'
        })
        fields.append({
            'offset': 25,
            'name': '主推进器2',
            'bytes': 2,
            'value': motor2,
            'meaning': f'转速2 ({motor2 if motor2 >= 0 else "N/A"})'
        })

        # Rudder angles
        for i, name in enumerate(['左水平舵', '右水平舵', '上垂直舵', '左垂直舵']):
            angle = data.get(f'rudder{i}', 0)
            fields.append({
                'offset': 27 + i*2,
                'name': name,
                'bytes': 2,
                'value': angle,
                'meaning': f'角度 ({angle/10.0:.1f}°)' if angle != -1800 else '无效'
            })

        # Orientation
        orientation = data.get('orientation', 0)
        fields.append({
            'offset': 35,
            'name': '航向角',
            'bytes': 2,
            'value': orientation,
            'meaning': f'目标航向 ({orientation/10.0:.1f}°)'
        })

        # Parameters
        for i in range(12):
            param = data.get(f'param{i+1}', 0)
            if i < 4:
                meaning = f'参数{i+1} (GPS坐标×1000000 = {param/1000000:.6f})'
            elif i < 8:
                meaning = f'参数{i+1} (×10000 = {param/10000:.4f})'
            else:
                meaning = f'参数{i+1} (×1000 = {param/1000:.3f})'

            byte_size = 4 if i < 4 else 2
            fields.append({
                'offset': 37 + (4 if i < 4 else 2) * i,
                'name': f'参数{i+1}',
                'bytes': byte_size,
                'value': param,
                'meaning': meaning
            })

        # Checksum
        checksum = data.get('checksum', 0)
        fields.append({
            'offset': 69,
            'name': '校验和',
            'bytes': 1,
            'value': f'0x{checksum:02X}',
            'meaning': '字节和校验'
        })

        # Frame trailer
        fields.append({
            'offset': 70,
            'name': '帧尾',
            'bytes': 2,
            'value': '0xFFFF',
            'meaning': '帧结束标识'
        })

        return fields

    def _decode_auv(self) -> List[dict]:
        """Decode AUV (receive) packet"""
        fields = []
        data = self.raw_data

        # Frame header
        fields.append({
            'offset': 0,
            'name': '帧头',
            'bytes': 5,
            'value': '$AUV',
            'meaning': '接收报文标识 (0x24 0x41 0x55 0x56 0x91)'
        })

        # Packet length / fifth header byte
        length = data.get('length', 145)
        fields.append({
            'offset': 4,
            'name': '头字节/长度',
            'bytes': 1,
            'value': length,
            'meaning': 'ASCII日志首字段；二进制帧中为 $AUV 后的 0x91'
        })

        # Frame number
        frame_num = data.get('frame', 0)
        fields.append({
            'offset': 6,
            'name': '帧序号',
            'bytes': 1,
            'value': frame_num,
            'meaning': f'报文计数器 (0x{frame_num:02X})'
        })

        # Device address
        addr = data.get('address', 1)
        fields.append({
            'offset': 7,
            'name': '本机地址',
            'bytes': 1,
            'value': addr,
            'meaning': f'AUV设备编号 (1-3)'
        })

        # Work mode
        mode = data.get('mode', 0)
        mode_names = ['仅发送', '遥控', '定点', '定向', '回航']
        fields.append({
            'offset': 8,
            'name': '工作模式',
            'bytes': 1,
            'value': mode,
            'meaning': f'{mode_names[mode] if mode < 5 else "未知"} (0x{mode:02X})'
        })

        for key, name, offset in [
            ('depth_protect_1', '深度保护1', 8),
            ('depth_protect_2', '深度保护2', 10),
            ('bottom_protect_1', '离底保护1', 12),
            ('bottom_protect_2', '离底保护2', 14),
            ('remain_time', '预设时间', 16),
        ]:
            value = data.get(key, 0)
            fields.append({
                'offset': offset,
                'name': name,
                'bytes': 2,
                'value': value,
                'meaning': f'ASCII固定字段，原始值 {value}'
            })

        work_cmd = data.get('work_instruction', 0)
        fields.append({
            'offset': 22,
            'name': '工作指令',
            'bytes': 1,
            'value': f'0x{work_cmd:02X}',
            'meaning': 'ASCII固定字段'
        })

        for key, name, offset in [
            ('motor1', '主推进器1', 23),
            ('motor2', '主推进器2', 25),
            ('rudder_lh', '左水平舵', 27),
            ('rudder_rh', '右水平舵', 29),
            ('rudder_uv', '上垂直舵', 31),
            ('rudder_lv', '下垂直舵', 33),
        ]:
            value = data.get(key, 0)
            meaning = f'角度 ({value/10.0:.1f}°)' if key.startswith('rudder_') else f'转速 ({value} rpm)'
            fields.append({
                'offset': offset,
                'name': name,
                'bytes': 2,
                'value': value,
                'meaning': meaning
            })

        pressure = data.get('internal_pressure_raw', 0)
        fields.append({
            'offset': 35,
            'name': '舱体内压',
            'bytes': 2,
            'value': pressure,
            'meaning': f'压力 ({pressure * 0.001:.3f} psi)，由 txt[19] 定界'
        })

        temp = data.get('internal_temp_raw', 0)
        fields.append({
            'offset': 37,
            'name': '舱体温度',
            'bytes': 1,
            'value': temp,
            'meaning': f'温度原始值 {temp}，由 txt[20] 定界'
        })

        depth = data.get('depth', 0)
        fields.append({
            'offset': 38,
            'name': '当前深度',
            'bytes': 2,
            'value': depth,
            'meaning': f'深度 ({depth/10.0:.1f}m)，由 txt[21] 定界'
        })

        status_candidate = data.get('status_candidate')
        if status_candidate is not None:
            fields.append({
                'offset': '未知',
                'name': '状态候选',
                'bytes': '-',
                'value': status_candidate,
                'meaning': 'txt[38] 常见为 0/256/1280；尚不能可靠绑定到异常位图'
            })

        lon = data.get('longitude', 0)
        lat = data.get('latitude', 0)
        fields.append({
            'offset': 94,
            'name': '经度',
            'bytes': 4,
            'value': lon,
            'meaning': f'GPS样经度×1000000 ({lon/1000000:.6f}°)，按数值范围识别'
        })
        fields.append({
            'offset': 98,
            'name': '纬度',
            'bytes': 4,
            'value': lat,
            'meaning': f'GPS样纬度×1000000 ({lat/1000000:.6f}°)，按数值范围识别'
        })

        # Checksum
        checksum = data.get('checksum', 0)
        fields.append({
            'offset': 142,
            'name': '校验和',
            'bytes': 1,
            'value': f'0x{checksum:02X}',
            'meaning': '字节和校验'
        })

        # Frame trailer
        fields.append({
            'offset': 143,
            'name': '帧尾',
            'bytes': 2,
            'value': '0xFFFF',
            'meaning': '帧结束标识'
        })

        return fields


class PacketFileParser:
    """Parse packet text log file"""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.packets: List[PacketEntry] = []
        self.current_timestamp = ""

    def parse(self) -> bool:
        """Parse the packet file"""
        try:
            print(f"Opening file: {self.filepath}")
            with open(self.filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # Split by lines and clean up
            lines = content.split('\n')
            print(f"File has {len(lines)} lines")

            i = 0
            ckth_count = 0
            auv_count = 0
            error_count = 0

            while i < len(lines):
                line = lines[i].strip()

                # Skip empty lines
                if not line:
                    i += 1
                    continue

                # Check for timestamp line
                if re.match(r'\d{2}:\d{2}:\d{2}::::', line):
                    self.current_timestamp = line.split(':')[0:3]
                    self.current_timestamp = ':'.join(self.current_timestamp)
                    i += 1
                    continue

                # Check for CKTH packet (data may be on same line or next line)
                if '$CKTH' in line:
                    # Extract data from the same line after $CKTH marker
                    try:
                        # Find position after $CKTH
                        ckth_pos = line.index('$CKTH')
                        data_part = line[ckth_pos + 5:].strip()

                        # If no data on same line, try next line
                        if not data_part and i + 1 < len(lines):
                            data_part = lines[i + 1].strip()
                            i += 1

                        if data_part:
                            parsed = self._parse_ckth_data(data_part)
                            if parsed:
                                entry = PacketEntry(self.current_timestamp, 'CKTH', parsed)
                                entry.decode()
                                self.packets.append(entry)
                                ckth_count += 1
                                if ckth_count <= 3:  # Show first 3
                                    print(f"  [{ckth_count}] CKTH packet at {self.current_timestamp}: frame={parsed.get('frame', 0)}, mode={parsed.get('mode', 0)}")
                    except Exception as e:
                        error_count += 1
                        if error_count <= 5:  # Show first 5 errors
                            print(f"  Error parsing CKTH: {e}")
                    i += 1
                    continue

                # Check for AUV packet (data may be on same line or next line)
                if '$AUV' in line:
                    try:
                        # Find position after $AUV
                        auv_pos = line.index('$AUV')
                        data_part = line[auv_pos + 4:].strip()

                        # If no data on same line, try next line
                        if not data_part and i + 1 < len(lines):
                            data_part = lines[i + 1].strip()
                            i += 1

                        if data_part:
                            parsed = self._parse_auv_data(data_part)
                            if parsed:
                                entry = PacketEntry(self.current_timestamp, 'AUV', parsed)
                                entry.decode()
                                self.packets.append(entry)
                                auv_count += 1
                                if auv_count <= 3:  # Show first 3
                                    print(f"  [{auv_count}] AUV packet at {self.current_timestamp}: frame={parsed.get('frame', 0)}, depth={parsed.get('depth', 0)}, heading={parsed.get('heading', 0)}")
                    except Exception as e:
                        error_count += 1
                        if error_count <= 5:  # Show first 5 errors
                            print(f"  Error parsing AUV: {e}")
                    i += 1
                    continue

                i += 1

            print(f"\nParsing complete:")
            print(f"  CKTH packets: {ckth_count}")
            print(f"  AUV packets:  {auv_count}")
            print(f"  Total:        {len(self.packets)}")
            print(f"  Errors:       {error_count}")

            return len(self.packets) > 0

        except Exception as e:
            print(f"Error parsing file: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _parse_ckth_data(self, line: str) -> Optional[dict]:
        """Parse CKTH data line

        Format: $CKTH< address length frame mode depth1 depth2 bottom1 bottom2 ...
        Example: < 1 72 60 1 1 2 200 100 0 23 0 0 0 0 0 0 0 de
        """
        try:
            parts = line.split()
            if len(parts) < 8:
                return None

            data = {}

            # Remove control characters from each part
            parts = [''.join(c for c in p if ord(c) >= 32) for p in parts]

            try:
                # Extract frame character from first field (e.g., '<', '=', '?')
                if parts[0] and len(parts[0]) >= 1:
                    frame_char = parts[0]
                    data['frame'] = ord(frame_char)

                idx = 1

                # Target address (byte 6)
                if idx < len(parts) and parts[idx].isdigit():
                    addr = int(parts[idx])
                    if 1 <= addr <= 3:  # Valid address range
                        data['address'] = addr
                    idx += 1
                else:
                    idx += 1

                # Packet length (72, skip)
                idx += 1

                # Frame number (already captured as char, skip)
                idx += 1

                # Work mode (byte 7)
                if idx < len(parts) and parts[idx].isdigit():
                    mode = int(parts[idx])
                    if 0 <= mode <= 4:  # Valid mode range
                        data['mode'] = mode
                    idx += 1
                else:
                    idx += 1

                # Protection parameters (depth1, depth2, bottom1, bottom2)
                # These are typically 200-500 range
                if idx + 4 < len(parts):
                    for param_idx, param_name in enumerate(['depth1', 'depth2', 'bottom1', 'bottom2']):
                        if parts[idx + param_idx].lstrip('-').isdigit():
                            val = int(parts[idx + param_idx])
                            if 0 <= val <= 10000:  # Reasonable range
                                data[param_name] = val
                idx += 4

                # Preset time and other parameters
                if idx < len(parts) and parts[idx].lstrip('-').isdigit():
                    data['preset'] = int(parts[idx])

                # Checksum (hex value at end)
                for part in reversed(parts):
                    if re.match(r'^[0-9a-fA-F]{2}$', part):
                        data['checksum'] = int(part, 16)
                        break

                # Fill in defaults if missing
                if 'address' not in data:
                    data['address'] = 1
                if 'mode' not in data:
                    data['mode'] = 2

            except (ValueError, IndexError) as e:
                print(f"  Warning: Partial parse error: {e}")

            return data if len(data) > 2 else None

        except Exception as e:
            print(f"Error parsing CKTH line: {e}")
            return None

    def _parse_auv_data(self, line: str) -> Optional[dict]:
        """Parse AUV data line based on actual observed format

        Format: $AUV 145 frame address mode ... GPS_long GPS_lat ... checksum
        Example: 145 3 1 0 0 0 0 0 0 0 0 180 -180 180 -180 0 0 0 203 140 1714 ...
        """
        try:
            # 日志行是“协议字段值列表”，不是原始 145 字节。
            # 这里仅解析由 VxWorks ToUI12 字段顺序和样本日志共同定界的字段。
            parts = [int(x) for x in re.findall(r'-?\d+', line)]
            if len(parts) < 22:
                return None

            data = {}
            data['length'] = parts[0]
            data['frame'] = parts[1]
            data['address'] = parts[2]
            data['mode'] = parts[3]

            fixed_map = {
                'depth_protect_1': 4,
                'depth_protect_2': 5,
                'bottom_protect_1': 6,
                'bottom_protect_2': 7,
                'remain_time': 8,
                'work_instruction': 9,
                'motor1': 10,
                'motor2': 11,
                'rudder_lh': 12,
                'rudder_rh': 13,
                'rudder_uv': 14,
                'rudder_lv': 15,
                # txt[16:18] 在样本中为预留/未知字段，暂不绑定协议含义。
                'internal_pressure_raw': 19,
                'internal_temp_raw': 20,
                'depth': 21,
                # txt[38] 在样本中出现 0/256/1280，但不能可靠等价为异常位图。
                'status_candidate': 38,
            }
            for key, pos in fixed_map.items():
                if pos < len(parts):
                    data[key] = parts[pos]

            for val in parts:
                if 70000000 < val < 140000000 and 'longitude' not in data:
                    data['longitude'] = val
                elif 10000000 < val < 55000000 and 'latitude' not in data:
                    data['latitude'] = val

            # Checksum (hex value at end)
            for part in reversed(parts):
                if 0 <= part <= 0xFF:
                    data.setdefault('checksum', part)

            return data if len(data) > 3 else None

        except Exception as e:
            print(f"Error parsing AUV line: {e}")
            return None


class PacketViewerWindow(QMainWindow):
    """Main packet viewer window"""

    def __init__(self, parser: PacketFileParser):
        super().__init__()
        self.parser = parser
        self.current_index = 0

        self.init_ui()
        self.update_display()

    def init_ui(self):
        """Initialize UI"""
        self.setWindowTitle("AUV报文协议查看器")
        self.setGeometry(100, 100, 1400, 900)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Info label
        info_label = QLabel(f"文件: {self.parser.filepath} | "
                           f"总报文数: {len(self.parser.packets)} | "
                           f"当前: 第 {self.current_index + 1} 条")
        info_label.setFont(QFont("Arial", 11))
        layout.addWidget(info_label)

        self.info_label = info_label

        # Navigation buttons
        nav_layout = QHBoxLayout()

        self.btn_prev = QPushButton("◀ 上一条 (←)")
        self.btn_prev.clicked.connect(self.prev_packet)
        self.btn_prev.setMinimumHeight(40)

        self.btn_next = QPushButton("下一条 (→) ▶")
        self.btn_next.clicked.connect(self.next_packet)
        self.btn_next.setMinimumHeight(40)

        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.btn_next)

        layout.addLayout(nav_layout)

        # Main content splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left: Packet list
        left_panel = QGroupBox("报文列表")
        left_layout = QVBoxLayout()

        self.packet_table = QTableWidget()
        self.packet_table.setColumnCount(4)
        self.packet_table.setHorizontalHeaderLabels(["时间", "类型", "帧号", "摘要"])
        self.packet_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.packet_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.packet_table.setSelectionMode(QTableWidget.SingleSelection)
        self.packet_table.cellClicked.connect(self.on_table_click)

        left_layout.addWidget(self.packet_table)
        left_panel.setLayout(left_layout)

        # Right: Packet details
        right_panel = QGroupBox("报文详情")
        right_layout = QVBoxLayout()

        # Timestamp and type
        self.detail_header = QLabel()
        self.detail_header.setFont(QFont("Arial", 12, QFont.Bold))
        right_layout.addWidget(self.detail_header)

        # Protocol fields table
        self.fields_table = QTableWidget()
        self.fields_table.setColumnCount(5)
        self.fields_table.setHorizontalHeaderLabels([
            "字节偏移", "字段名称", "长度", "数值", "含义"
        ])
        self.fields_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        right_layout.addWidget(self.fields_table)

        right_panel.setLayout(right_layout)

        # Add panels to splitter
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)

        # Status bar
        self.statusBar().showMessage("就绪 - 使用方向键或按钮导航")

        # Populate packet list
        self.populate_packet_list()

    def populate_packet_list(self):
        """Fill packet list table"""
        self.packet_table.setRowCount(len(self.parser.packets))

        for i, packet in enumerate(self.parser.packets):
            # Time
            self.packet_table.setItem(i, 0, QTableWidgetItem(packet.timestamp))

            # Type
            type_item = QTableWidgetItem(packet.packet_type)
            if packet.packet_type == 'CKTH':
                type_item.setForeground(Qt.darkBlue)
            else:
                type_item.setForeground(Qt.darkGreen)
            self.packet_table.setItem(i, 1, type_item)

            # Frame number
            frame = packet.raw_data.get('frame', 0)
            self.packet_table.setItem(i, 2, QTableWidgetItem(str(frame)))

            # Summary
            if packet.packet_type == 'CKTH':
                mode = packet.raw_data.get('mode', 0)
                summary = f"发送 | 模式:{mode}"
            else:
                depth = packet.raw_data.get('depth', 0)
                heading = packet.raw_data.get('heading', 0)
                summary = f"接收 | 深度:{depth/10:.1f}m 航向:{heading/10:.0f}°"

            self.packet_table.setItem(i, 3, QTableWidgetItem(summary))

    def update_display(self):
        """Update display for current packet"""
        if not self.parser.packets:
            return

        packet = self.parser.packets[self.current_index]

        # Update info label
        self.info_label.setText(
            f"文件: {os.path.basename(self.parser.filepath)} | "
            f"总报文数: {len(self.parser.packets)} | "
            f"当前: 第 {self.current_index + 1}/{len(self.parser.packets)} 条"
        )

        # Update detail header
        type_color = "🔵" if packet.packet_type == 'CKTH' else "🟢"
        type_name = "上位机 → AUV" if packet.packet_type == 'CKTH' else "AUV → 上位机"
        self.detail_header.setText(
            f"{type_color} {type_name} | 时间: {packet.timestamp} | "
            f"帧序号: {packet.raw_data.get('frame', 0)}"
        )

        # Update fields table
        if packet.decoded:
            self.fields_table.setRowCount(len(packet.decoded))

            for i, field in enumerate(packet.decoded):
                self.fields_table.setItem(i, 0, QTableWidgetItem(str(field['offset'])))
                self.fields_table.setItem(i, 1, QTableWidgetItem(field['name']))
                self.fields_table.setItem(i, 2, QTableWidgetItem(str(field['bytes'])))
                self.fields_table.setItem(i, 3, QTableWidgetItem(str(field['value'])))
                self.fields_table.setItem(i, 4, QTableWidgetItem(field['meaning']))

                # Highlight header/trailer
                if field['name'] in ['帧头', '帧尾']:
                    for j in range(5):
                        item = self.fields_table.item(i, j)
                        if item:
                            item.setBackground(Qt.lightGray)

        # Highlight current row in packet table
        self.packet_table.selectRow(self.current_index)

        # Update status bar
        progress = f"{self.current_index + 1}/{len(self.parser.packets)}"
        self.statusBar().showMessage(f"当前显示: {progress} | 方向键导航 | 双击列表跳转")

    def prev_packet(self):
        """Go to previous packet"""
        if self.current_index > 0:
            self.current_index -= 1
            self.update_display()

    def next_packet(self):
        """Go to next packet"""
        if self.current_index < len(self.parser.packets) - 1:
            self.current_index += 1
            self.update_display()

    def on_table_click(self, row: int, column: int):
        """Handle table row click"""
        self.current_index = row
        self.update_display()

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard navigation"""
        if event.key() == Qt.Key_Left:
            self.prev_packet()
        elif event.key() == Qt.Key_Right:
            self.next_packet()
        else:
            super().keyPressEvent(event)


def main():
    """Main entry point"""
    import sys

    # Check for file argument
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        # Use configured default file
        filepath = get_text_log_path()

        # If file doesn't exist, show file dialog
        if not os.path.exists(filepath):
            print(f"Warning: Configured file not found: {filepath}")
            print("You can:")
            print("  1. Place the text file in the current directory")
            print("  2. Update config/tools_config.ini")
            print("  3. Specify file as argument: python packet_viewer.py <file.txt>")
            print()

            # Try to find .txt files in current directory
            txt_files = [f for f in os.listdir('.') if f.endswith('.txt') and os.path.isfile(f)]
            if txt_files:
                print(f"Found {len(txt_files)} .txt file(s) in current directory:")
                for f in txt_files[:5]:
                    print(f"  - {f}")

            sys.exit(1)

    print("=" * 70)
    print("AUV报文协议查看器")
    print("=" * 70)
    print(f"加载文件: {filepath}")

    # Parse file
    parser = PacketFileParser(filepath)
    if not parser.parse():
        print("Error: Failed to parse packet file")
        sys.exit(1)

    print(f"✓ 成功解析 {len(parser.packets)} 条报文")
    print()

    # Create Qt application
    app = QApplication(sys.argv)

    # Create main window
    viewer = PacketViewerWindow(parser)
    viewer.show()

    print("报文查看器已启动")
    print("-" * 70)
    print("操作说明:")
    print("  • 左右方向键: 前后导航")
    print("  • 点击按钮: 前后导航")
    print("  • 双击列表: 跳转到指定报文")
    print("-" * 70)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
