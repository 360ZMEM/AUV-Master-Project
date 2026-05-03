#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Manual Protocol Injector (手动协议注入工具)
用于 AUV (Jetson -> AMD) 的远程联调。不运行复杂算法，仅用于手动构造并发送 $CKTH 协议报文。
目标环境：Ubuntu 22.04 / macOS
通信协议：UDP, 大端序
"""

import argparse
import socket
import sys
import time
from pathlib import Path
import binascii

# 将项目根目录加入 sys.path，以便导入 common.protocol
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from common.protocol import (
        build_downlink_packet,
        KEY_THRUST, KEY_LEFT, KEY_RIGHT, KEY_TOP, KEY_BOTTOM
    )
except ImportError as e:
    print(f"Error importing common.protocol: {e}")
    sys.exit(1)

def build_ckth_packet(frame_counter: int, params: dict) -> bytes:
    """
    构造 $CKTH 报文
    """
    # 从 params 构建 command_payload
    # 注意: UI上的主推转速(Motor_Speed1)对应于 RPM, 但是 build_downlink_packet 中的 KEY_THRUST
    # 期望的是百分比 (thrust = Motor_Speed1 / main_motor_rpm_scale)
    # 因为 build_downlink_packet 内部会进行 thrust * scale 的换算，所以直接除以 15.0 传进去。
    command_payload = {
        KEY_THRUST: params.get("motor_speed1", 0) / 15.0,
        KEY_LEFT: params.get("rudder_left", 0.0),
        KEY_RIGHT: params.get("rudder_right", 0.0),
        KEY_TOP: params.get("rudder_top", 0.0),
        KEY_BOTTOM: params.get("rudder_bottom", 0.0),
    }

    packet = build_downlink_packet(
        command_payload=command_payload,
        frame_counter=frame_counter,
        obj_address=1,
        control_mode_byte=params.get("ctrl_mode", 0x00),
        work_instruction=params.get("work_cmd", 0x00),
        orientation_deg=0.0,
        depth_protect_params=(params.get("depth_min", 0), params.get("depth_max", 50)),
        bottom_protect_params=(params.get("bottom_min", 0), params.get("bottom_max", 5)),
        preset_time_tenths_min=0,
        spare_params=(0, 0),
        parameter_values=params.get("parameters", [0]*12),
        main_motor_rpm_scale=15.0,
        side_motor_rpm=params.get("motor_speed2", 0)
    )
    return packet

def run_headless(args):
    """
    在没有 GUI 的环境下运行
    """
    ip = args.ip
    port = args.port
    continuous = args.continuous

    print(f"Starting in Headless Mode. Target: {ip}:{port}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    frame_counter = 0
    default_params = {
        "ctrl_mode": args.ctrl_mode,
        "work_cmd": args.work_cmd,
        "motor_speed1": args.motor1,
        "motor_speed2": args.motor2,
        "rudder_left": args.rudder_left,
        "rudder_right": args.rudder_right,
        "rudder_top": args.rudder_top,
        "rudder_bottom": args.rudder_bottom,
        "depth_min": 0,
        "depth_max": 50,
        "bottom_min": 0,
        "bottom_max": 5,
        "parameters": [0] * 12
    }

    try:
        while True:
            packet = build_ckth_packet(frame_counter, default_params)
            sock.sendto(packet, (ip, port))
            checksum = packet[69]
            hex_str = binascii.hexlify(packet).decode('ascii').upper()
            hex_str = ' '.join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
            print(f"[{frame_counter:03d}] Sent packet. Checksum: 0x{checksum:02X}")
            print(f"Hex: {hex_str}\n")
            
            frame_counter = (frame_counter + 1) % 256
            if not continuous:
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        sock.close()

def run_gui(ip: str, port: int):
    """
    启动 PySide6 GUI
    """
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
        QFormLayout, QGroupBox, QLineEdit, QComboBox, QSpinBox, 
        QDoubleSpinBox, QPushButton, QCheckBox, QLabel, QTextEdit
    )
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QFont

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Manual Protocol Injector")
            self.resize(600, 800)
            
            self.frame_counter = 0
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            self.timer = QTimer()
            self.timer.timeout.connect(self.send_packet)
            
            self._init_ui()
            
            self.ip_input.setText(ip)
            self.port_input.setText(str(port))
            
        def _init_ui(self):
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            main_layout = QVBoxLayout(central_widget)
            
            # 创建两列布局
            columns_layout = QHBoxLayout()
            
            # 左列
            left_column = QVBoxLayout()
            
            # 网络设置区
            net_group = QGroupBox("网络设置区")
            net_layout = QHBoxLayout()
            self.ip_input = QLineEdit()
            self.port_input = QLineEdit()
            net_layout.addWidget(QLabel("目标 IP:"))
            net_layout.addWidget(self.ip_input)
            net_layout.addWidget(QLabel("端口:"))
            net_layout.addWidget(self.port_input)
            net_group.setLayout(net_layout)
            left_column.addWidget(net_group)
            
            # 核心控制区
            ctrl_group = QGroupBox("核心控制区 (可干预位)")
            ctrl_layout = QFormLayout()
            
            self.ctrl_mode_combo = QComboBox()
            self.ctrl_mode_combo.addItem("00: 默认", 0x00)
            self.ctrl_mode_combo.addItem("01: 遥控", 0x01)
            self.ctrl_mode_combo.addItem("02: 自主定点", 0x02)
            self.ctrl_mode_combo.addItem("03: 自主定向", 0x03)
            self.ctrl_mode_combo.addItem("04: 回航", 0x04)
            ctrl_layout.addRow("Ctrl_Mode (Byte 7):", self.ctrl_mode_combo)
            
            self.work_cmd_combo = QComboBox()
            cmds = [
                ("00: 默认", 0x00), ("01: 任务开启", 0x01), ("02: 任务取消", 0x02),
                ("11: 主推上电", 0x11), ("12: 主推断电", 0x12),
                ("13: 侧推上电", 0x13), ("14: 侧推断电", 0x14),
                ("15: 水平舵上电", 0x15), ("16: 水平舵断电", 0x16),
                ("17: 垂直舵上电", 0x17), ("18: 垂直舵断电", 0x18),
                ("91: 初始化开启", 0x91)
            ]
            for text, val in cmds:
                self.work_cmd_combo.addItem(text, val)
            ctrl_layout.addRow("Work_Cmd (Byte 22):", self.work_cmd_combo)
            ctrl_group.setLayout(ctrl_layout)
            left_column.addWidget(ctrl_group)
            
            # 电机动力
            motor_group = QGroupBox("电机动力 (Byte 23-26)")
            motor_layout = QFormLayout()
            self.motor1_spin = QSpinBox()
            self.motor1_spin.setRange(-1500, 1500)
            self.motor1_spin.setSingleStep(10)
            self.motor2_spin = QSpinBox()
            self.motor2_spin.setRange(-4000, 4000)
            self.motor2_spin.setSingleStep(10)
            motor_layout.addRow("Motor_Speed1 (主推):", self.motor1_spin)
            motor_layout.addRow("Motor_Speed2 (侧推):", self.motor2_spin)
            motor_group.setLayout(motor_layout)
            left_column.addWidget(motor_group)
            
            # 舵机角度
            rudder_group = QGroupBox("舵机角度 (Byte 27-34)")
            rudder_layout = QFormLayout()
            self.rudder_left = QDoubleSpinBox()
            self.rudder_right = QDoubleSpinBox()
            self.rudder_top = QDoubleSpinBox()
            self.rudder_bottom = QDoubleSpinBox()
            for w in (self.rudder_left, self.rudder_right, self.rudder_top, self.rudder_bottom):
                w.setRange(-30.0, 30.0)
                w.setSingleStep(0.1)
                w.setDecimals(1)
            rudder_layout.addRow("左水平舵:", self.rudder_left)
            rudder_layout.addRow("右水平舵:", self.rudder_right)
            rudder_layout.addRow("上垂直舵:", self.rudder_top)
            rudder_layout.addRow("下垂直舵:", self.rudder_bottom)
            rudder_group.setLayout(rudder_layout)
            left_column.addWidget(rudder_group)
            
            columns_layout.addLayout(left_column)
            
            # 右列
            right_column = QVBoxLayout()
            
            # 保护参数
            protect_group = QGroupBox("保护参数 (Byte 8-15)")
            protect_layout = QFormLayout()
            self.depth_max_spin = QSpinBox()
            self.depth_max_spin.setRange(0, 65535)
            self.depth_max_spin.setValue(50)
            self.bottom_min_spin = QSpinBox()
            self.bottom_min_spin.setRange(0, 65535)
            self.bottom_min_spin.setValue(5)
            protect_layout.addRow("超深保护最大值:", self.depth_max_spin)
            protect_layout.addRow("离底保护最小值:", self.bottom_min_spin)
            protect_group.setLayout(protect_layout)
            right_column.addWidget(protect_group)
            
            # 调参区
            param_group = QGroupBox("调参区 (Byte 37-68)")
            param_layout = QFormLayout()
            self.params_spins = []
            for i in range(12):
                spin = QSpinBox()
                if i < 4:
                    spin.setRange(-2147483648, 2147483647) # int32
                else:
                    spin.setRange(-32768, 32767) # int16
                param_layout.addRow(f"Para{i+1}:", spin)
                self.params_spins.append(spin)
            param_group.setLayout(param_layout)
            right_column.addWidget(param_group)
            
            # 动作执行区
            action_group = QGroupBox("动作执行区")
            action_layout = QHBoxLayout()
            self.send_btn = QPushButton("发送单次包")
            self.send_btn.clicked.connect(self.send_packet)
            
            self.continuous_cb = QCheckBox("连续发送 (2Hz)")
            self.continuous_cb.stateChanged.connect(self.toggle_continuous)
            
            self.status_light = QLabel("●")
            self.status_light.setFont(QFont("Arial", 20))
            self.status_light.setStyleSheet("color: gray;")
            
            self.estop_btn = QPushButton("🔴 紧急停止")
            self.estop_btn.setStyleSheet("background-color: red; color: white; font-weight: bold; font-size: 16px;")
            self.estop_btn.clicked.connect(self.emergency_stop)
            
            action_layout.addWidget(self.send_btn)
            action_layout.addWidget(self.continuous_cb)
            action_layout.addWidget(self.status_light)
            action_layout.addWidget(self.estop_btn)
            action_group.setLayout(action_layout)
            right_column.addWidget(action_group)
            
            # 原始监测区
            monitor_group = QGroupBox("原始监测区")
            monitor_layout = QVBoxLayout()
            self.hex_display = QTextEdit()
            self.hex_display.setReadOnly(True)
            self.hex_display.setMaximumHeight(80)
            self.checksum_label = QLabel("Checksum: N/A")
            monitor_layout.addWidget(QLabel("原始 Hex 字节流:"))
            monitor_layout.addWidget(self.hex_display)
            monitor_layout.addWidget(self.checksum_label)
            monitor_group.setLayout(monitor_layout)
            right_column.addWidget(monitor_group)
            
            columns_layout.addLayout(right_column)
            
            # 添加两列到主布局
            main_layout.addLayout(columns_layout)

        def get_current_params(self):
            return {
                "ctrl_mode": self.ctrl_mode_combo.currentData(),
                "work_cmd": self.work_cmd_combo.currentData(),
                "motor_speed1": self.motor1_spin.value(),
                "motor_speed2": self.motor2_spin.value(),
                "rudder_left": self.rudder_left.value(),
                "rudder_right": self.rudder_right.value(),
                "rudder_top": self.rudder_top.value(),
                "rudder_bottom": self.rudder_bottom.value(),
                "depth_min": 0,
                "depth_max": self.depth_max_spin.value(),
                "bottom_min": self.bottom_min_spin.value(),
                "bottom_max": 5, # Dummy max value for bottom protect
                "parameters": [s.value() for s in self.params_spins]
            }

        def send_packet(self):
            params = self.get_current_params()
            packet = build_ckth_packet(self.frame_counter, params)
            
            target_ip = self.ip_input.text()
            target_port = int(self.port_input.text())
            try:
                self.sock.sendto(packet, (target_ip, target_port))
            except Exception as e:
                self.hex_display.setText(f"Error sending packet: {e}")
                return

            checksum = packet[69]
            hex_str = binascii.hexlify(packet).decode('ascii').upper()
            hex_str = ' '.join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
            
            self.hex_display.setText(hex_str)
            self.checksum_label.setText(f"Checksum: 0x{checksum:02X}")
            
            self.frame_counter = (self.frame_counter + 1) % 256

        def toggle_continuous(self, state):
            if self.continuous_cb.isChecked():
                self.timer.start(500) # 2Hz
                self.status_light.setStyleSheet("color: green;")
            else:
                self.timer.stop()
                self.status_light.setStyleSheet("color: gray;")

        def emergency_stop(self):
            # 停止所有动作并设为任务取消
            self.motor1_spin.setValue(0)
            self.motor2_spin.setValue(0)
            self.rudder_left.setValue(0)
            self.rudder_right.setValue(0)
            self.rudder_top.setValue(0)
            self.rudder_bottom.setValue(0)
            
            # Work_Cmd 设为 02 (任务取消)
            index = self.work_cmd_combo.findData(0x02)
            if index >= 0:
                self.work_cmd_combo.setCurrentIndex(index)
            
            # 立即发送一次
            self.send_packet()

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

def main():
    parser = argparse.ArgumentParser(description="Manual Protocol Injector")
    parser.add_argument("--headless", action="store_true", help="Run without GUI")
    parser.add_argument("--continuous", action="store_true", help="Send continuously at 2Hz in headless mode")
    parser.add_argument("--ip", default="192.168.0.101", help="Target IP address")
    parser.add_argument("--port", type=int, default=52364, help="Target UDP port")
    parser.add_argument("--ctrl-mode", type=lambda x: int(x, 0), default=0x00, help="Control mode byte")
    parser.add_argument("--work-cmd", type=lambda x: int(x, 0), default=0x00, help="Work command byte")
    parser.add_argument("--motor1", type=int, default=0, help="Main motor speed")
    parser.add_argument("--motor2", type=int, default=0, help="Side motor speed")
    parser.add_argument("--rudder-left", type=float, default=0.0, help="Left rudder angle")
    parser.add_argument("--rudder-right", type=float, default=0.0, help="Right rudder angle")
    parser.add_argument("--rudder-top", type=float, default=0.0, help="Top rudder angle")
    parser.add_argument("--rudder-bottom", type=float, default=0.0, help="Bottom rudder angle")
    args = parser.parse_args()

    if args.headless:
        run_headless(args)
    else:
        run_gui(args.ip, args.port)

if __name__ == "__main__":
    main()
