"""
Extended control window (Form2 equivalent)
C# Reference: Form2.cs
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                               QGroupBox, QPushButton, QLabel, QSpinBox)
from PySide6.QtCore import QTimer, Qt


class ExtendedControlWindow(QWidget):
    """
    Extended control window (Form2 equivalent)
    C# Reference: Form2.cs lines 1-400
    """

    def __init__(self, main_window):
        super().__init__()  # Remove parent to make it independent
        self.main_window = main_window
        self.init_ui()
        self.setup_timer()

        # Set window flags to make it independent
        self.setWindowFlags(Qt.Window)

    def init_ui(self):
        """Initialize extended control UI"""
        self.setWindowTitle("扩展控制")
        self.setGeometry(200, 200, 800, 600)

        layout = QVBoxLayout()

        # Device power control section
        device_group = QGroupBox("设备电源控制")
        device_layout = self.create_device_power_controls()
        device_group.setLayout(device_layout)
        layout.addWidget(device_group)

        # Motor speed controls
        motor_group = QGroupBox("电机转速控制")
        motor_layout = self.create_motor_controls()
        motor_group.setLayout(motor_layout)
        layout.addWidget(motor_group)

        # Rudder angle controls
        rudder_group = QGroupBox("舵角控制")
        rudder_layout = self.create_rudder_controls()
        rudder_group.setLayout(rudder_layout)
        layout.addWidget(rudder_group)

        layout.addStretch()
        self.setLayout(layout)

    def create_device_power_controls(self) -> QVBoxLayout:
        """Create device power control buttons"""
        layout = QVBoxLayout()

        # Main thruster
        row1 = QHBoxLayout()
        self.btn_main_thruster_on = QPushButton("主推上电 (0x11)")
        self.btn_main_thruster_off = QPushButton("主推断电 (0x12)")
        row1.addWidget(self.btn_main_thruster_on)
        row1.addWidget(self.btn_main_thruster_off)
        layout.addLayout(row1)

        # Side thruster
        row2 = QHBoxLayout()
        self.btn_side_thruster_on = QPushButton("侧推上电 (0x13)")
        self.btn_side_thruster_off = QPushButton("侧推断电 (0x14)")
        row2.addWidget(self.btn_side_thruster_on)
        row2.addWidget(self.btn_side_thruster_off)
        layout.addLayout(row2)

        # Horizontal rudder
        row3 = QHBoxLayout()
        self.btn_horz_rudder_on = QPushButton("水平舵上电 (0x15)")
        self.btn_horz_rudder_off = QPushButton("水平舵断电 (0x16)")
        row3.addWidget(self.btn_horz_rudder_on)
        row3.addWidget(self.btn_horz_rudder_off)
        layout.addLayout(row3)

        # Vertical rudder
        row4 = QHBoxLayout()
        self.btn_vert_rudder_on = QPushButton("垂直舵上电 (0x17)")
        self.btn_vert_rudder_off = QPushButton("垂直舵断电 (0x18)")
        row4.addWidget(self.btn_vert_rudder_on)
        row4.addWidget(self.btn_vert_rudder_off)
        layout.addLayout(row4)

        # DVL
        row5 = QHBoxLayout()
        self.btn_dvl_on = QPushButton("DVL上电 (0x21)")
        self.btn_dvl_off = QPushButton("DVL断电 (0x22)")
        row5.addWidget(self.btn_dvl_on)
        row5.addWidget(self.btn_dvl_off)
        layout.addLayout(row5)

        # Compass
        row6 = QHBoxLayout()
        self.btn_compass_on = QPushButton("罗经上电 (0x23)")
        self.btn_compass_off = QPushButton("罗经断电 (0x24)")
        row6.addWidget(self.btn_compass_on)
        row6.addWidget(self.btn_compass_off)
        layout.addLayout(row6)

        # Connect buttons
        self.btn_main_thruster_on.clicked.connect(
            lambda: self.set_work_instruct(0x11))
        self.btn_main_thruster_off.clicked.connect(
            lambda: self.set_work_instruct(0x12))
        self.btn_side_thruster_on.clicked.connect(
            lambda: self.set_work_instruct(0x13))
        self.btn_side_thruster_off.clicked.connect(
            lambda: self.set_work_instruct(0x14))
        self.btn_horz_rudder_on.clicked.connect(
            lambda: self.set_work_instruct(0x15))
        self.btn_horz_rudder_off.clicked.connect(
            lambda: self.set_work_instruct(0x16))
        self.btn_vert_rudder_on.clicked.connect(
            lambda: self.set_work_instruct(0x17))
        self.btn_vert_rudder_off.clicked.connect(
            lambda: self.set_work_instruct(0x18))
        self.btn_dvl_on.clicked.connect(
            lambda: self.set_work_instruct(0x21))
        self.btn_dvl_off.clicked.connect(
            lambda: self.set_work_instruct(0x22))
        self.btn_compass_on.clicked.connect(
            lambda: self.set_work_instruct(0x23))
        self.btn_compass_off.clicked.connect(
            lambda: self.set_work_instruct(0x24))

        return layout

    def create_motor_controls(self) -> QHBoxLayout:
        """Create motor speed control inputs"""
        layout = QHBoxLayout()

        # Motor 1
        motor1_layout = QVBoxLayout()
        motor1_layout.addWidget(QLabel("电机转速1 (-1500 to 1500):"))
        self.motor1_spinbox = QSpinBox()
        self.motor1_spinbox.setRange(-1500, 1500)
        self.motor1_spinbox.setValue(0)
        self.motor1_spinbox.setSuffix(" RPM")
        self.motor1_spinbox.valueChanged.connect(self.update_motor_speed1)
        motor1_layout.addWidget(self.motor1_spinbox)

        # Motor 2
        motor2_layout = QVBoxLayout()
        motor2_layout.addWidget(QLabel("电机转速2 (-4000 to 4000):"))
        self.motor2_spinbox = QSpinBox()
        self.motor2_spinbox.setRange(-4000, 4000)
        self.motor2_spinbox.setValue(0)
        self.motor2_spinbox.setSuffix(" RPM")
        self.motor2_spinbox.valueChanged.connect(self.update_motor_speed2)
        motor2_layout.addWidget(self.motor2_spinbox)

        layout.addLayout(motor1_layout)
        layout.addLayout(motor2_layout)

        return layout

    def create_rudder_controls(self) -> QVBoxLayout:
        """Create rudder angle controls (4 channels, ±30°)"""
        layout = QVBoxLayout()

        # Left horizontal rudder
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("左水平舵角:"))
        self.rudder_lh_spinbox = QSpinBox()
        self.rudder_lh_spinbox.setRange(-30, 30)
        self.rudder_lh_spinbox.setValue(0)
        self.rudder_lh_spinbox.setSuffix("°")
        self.rudder_lh_spinbox.valueChanged.connect(self.update_rudder_lh)
        row1.addWidget(self.rudder_lh_spinbox)
        layout.addLayout(row1)

        # Right horizontal rudder
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("右水平舵角:"))
        self.rudder_rh_spinbox = QSpinBox()
        self.rudder_rh_spinbox.setRange(-30, 30)
        self.rudder_rh_spinbox.setValue(0)
        self.rudder_rh_spinbox.setSuffix("°")
        self.rudder_rh_spinbox.valueChanged.connect(self.update_rudder_rh)
        row2.addWidget(self.rudder_rh_spinbox)
        layout.addLayout(row2)

        # Upper vertical rudder
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("上垂直舵角:"))
        self.rudder_uv_spinbox = QSpinBox()
        self.rudder_uv_spinbox.setRange(-30, 30)
        self.rudder_uv_spinbox.setValue(0)
        self.rudder_uv_spinbox.setSuffix("°")
        self.rudder_uv_spinbox.valueChanged.connect(self.update_rudder_uv)
        row3.addWidget(self.rudder_uv_spinbox)
        layout.addLayout(row3)

        # Lower vertical rudder
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("下垂直舵角:"))
        self.rudder_lv_spinbox = QSpinBox()
        self.rudder_lv_spinbox.setRange(-30, 30)
        self.rudder_lv_spinbox.setValue(0)
        self.rudder_lv_spinbox.setSuffix("°")
        self.rudder_lv_spinbox.valueChanged.connect(self.update_rudder_lv)
        row4.addWidget(self.rudder_lv_spinbox)
        layout.addLayout(row4)

        return layout

    def setup_timer(self):
        """Setup 200ms timer to sync button states"""
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_button_states)
        self.timer.start(200)

    def update_button_states(self):
        """Update button visual states based on work_instruct"""
        work_code = self.main_window.work_instruct

        # Map command codes to buttons
        buttons = {
            0x11: self.btn_main_thruster_on,
            0x12: self.btn_main_thruster_off,
            0x13: self.btn_side_thruster_on,
            0x14: self.btn_side_thruster_off,
            0x15: self.btn_horz_rudder_on,
            0x16: self.btn_horz_rudder_off,
            0x17: self.btn_vert_rudder_on,
            0x18: self.btn_vert_rudder_off,
            0x21: self.btn_dvl_on,
            0x22: self.btn_dvl_off,
            0x23: self.btn_compass_on,
            0x24: self.btn_compass_off,
        }

        # Reset all buttons
        for btn in buttons.values():
            btn.setStyleSheet("")

        # Highlight active button
        if work_code in buttons:
            buttons[work_code].setStyleSheet("background-color: SkyBlue;")

    def set_work_instruct(self, code: int):
        """Set work instruction in main window"""
        self.main_window.set_work_instruct(code)

    def update_motor_speed1(self, value):
        """Update motor speed 1"""
        self.main_window.motor_speed1 = value

    def update_motor_speed2(self, value):
        """Update motor speed 2"""
        self.main_window.motor_speed2 = value

    def update_rudder_lh(self, value):
        """Update left horizontal rudder (×10 for protocol)"""
        self.main_window.rudder_angle_lh = value * 10

    def update_rudder_rh(self, value):
        """Update right horizontal rudder (×10 for protocol)"""
        self.main_window.rudder_angle_rh = value * 10

    def update_rudder_uv(self, value):
        """Update upper vertical rudder (×10 for protocol)"""
        self.main_window.rudder_angle_uv = value * 10

    def update_rudder_lv(self, value):
        """Update lower vertical rudder (×10 for protocol)"""
        self.main_window.rudder_angle_lv = value * 10

    def closeEvent(self, event):
        """Handle window close"""
        self.timer.stop()
        self.main_window.extend_form = None
        event.accept()
