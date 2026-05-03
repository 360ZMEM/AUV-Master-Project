"""
Settings dialog for port configuration (Form3 equivalent)
C# Reference: Form3.cs
"""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                               QComboBox, QLabel, QLineEdit,
                               QPushButton, QGroupBox, QMessageBox)
from PySide6.QtCore import Qt
import serial.tools.list_ports


class SettingsDialog(QDialog):
    """
    Settings dialog for port configuration (Form3 equivalent)
    C# Reference: Form3.cs
    """

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.init_ui()
        self.load_current_config()

    def init_ui(self):
        """Initialize settings UI"""
        self.setWindowTitle("端口设置")
        self.setGeometry(300, 300, 500, 300)

        layout = QVBoxLayout()

        # Serial port selection group
        serial_group = QGroupBox("串口配置")
        serial_layout = QVBoxLayout()

        # Radio port
        radio_row = QHBoxLayout()
        radio_row.addWidget(QLabel("无线电串口:"))
        self.radio_combo = QComboBox()
        self.populate_serial_ports(self.radio_combo)
        radio_row.addWidget(self.radio_combo)
        self.radio_current_label = QLabel()
        radio_row.addWidget(self.radio_current_label)
        serial_layout.addLayout(radio_row)

        # Beidou port
        beidou_row = QHBoxLayout()
        beidou_row.addWidget(QLabel("北斗串口:"))
        self.beidou_combo = QComboBox()
        self.populate_serial_ports(self.beidou_combo)
        beidou_row.addWidget(self.beidou_combo)
        self.beidou_current_label = QLabel()
        beidou_row.addWidget(self.beidou_current_label)
        serial_layout.addLayout(beidou_row)

        serial_group.setLayout(serial_layout)
        layout.addWidget(serial_group)

        # Network configuration group
        network_group = QGroupBox("网络配置")
        network_layout = QVBoxLayout()

        # Console IP
        console_ip_row = QHBoxLayout()
        console_ip_row.addWidget(QLabel("操控台IP:"))
        self.console_ip_edit = QLineEdit()
        console_ip_row.addWidget(self.console_ip_edit)
        network_layout.addLayout(console_ip_row)

        # Console port
        console_port_row = QHBoxLayout()
        console_port_row.addWidget(QLabel("操控台端口:"))
        self.console_port_edit = QLineEdit()
        console_port_row.addWidget(self.console_port_edit)
        network_layout.addLayout(console_port_row)

        # AUV IP
        auv_ip_row = QHBoxLayout()
        auv_ip_row.addWidget(QLabel("AUV IP:"))
        self.auv_ip_edit = QLineEdit()
        auv_ip_row.addWidget(self.auv_ip_edit)
        network_layout.addLayout(auv_ip_row)

        # AUV port
        auv_port_row = QHBoxLayout()
        auv_port_row.addWidget(QLabel("AUV端口:"))
        self.auv_port_edit = QLineEdit()
        auv_port_row.addWidget(self.auv_port_edit)
        network_layout.addLayout(auv_port_row)

        network_group.setLayout(network_layout)
        layout.addWidget(network_group)

        # Warning label
        warning_label = QLabel("修改完成后退出系统重新开启软件")
        warning_label.setStyleSheet("color: red;")
        layout.addWidget(warning_label)

        # Buttons
        button_row = QHBoxLayout()
        self.btn_save = QPushButton("保存配置")
        self.btn_save.clicked.connect(self.save_configuration)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.close)
        button_row.addWidget(self.btn_save)
        button_row.addWidget(self.btn_cancel)
        button_row.addStretch()
        layout.addLayout(button_row)

        layout.addStretch()
        self.setLayout(layout)

    def populate_serial_ports(self, combo_box: QComboBox):
        """Populate combo box with available serial ports"""
        ports = serial.tools.list_ports.comports()
        combo_box.clear()
        for port in ports:
            combo_box.addItem(port.device)

    def load_current_config(self):
        """Load current configuration from port_set.txt"""
        config = self.main_window.config_manager.load_port_config()

        # Set current labels
        self.radio_current_label.setText(f"当前: {config['radio_port']}")
        self.beidou_current_label.setText(f"当前: {config['beidou_port']}")

        # Set edit fields
        self.console_ip_edit.setText(config['console_ip'])
        self.console_port_edit.setText(str(config['console_port']))
        self.auv_ip_edit.setText(config['auv_ip'])
        self.auv_port_edit.setText(str(config['auv_port']))

        # Set combo box selections if available
        index_radio = self.radio_combo.findText(config['radio_port'])
        if index_radio >= 0:
            self.radio_combo.setCurrentIndex(index_radio)

        index_beidou = self.beidou_combo.findText(config['beidou_port'])
        if index_beidou >= 0:
            self.beidou_combo.setCurrentIndex(index_beidou)

    def save_configuration(self):
        """Save configuration to port_set.txt"""
        config = {
            'radio_port': self.radio_combo.currentText(),
            'beidou_port': self.beidou_combo.currentText(),
            'console_ip': self.console_ip_edit.text(),
            'console_port': int(self.console_port_edit.text()),
            'auv_ip': self.auv_ip_edit.text(),
            'auv_port': int(self.auv_port_edit.text())
        }

        # Save to file
        self.main_window.config_manager.save_port_config(config)

        # Update labels
        self.radio_current_label.setText(f"当前: {config['radio_port']}")
        self.beidou_current_label.setText(f"当前: {config['beidou_port']}")

        QMessageBox.information(
            self,
            "成功",
            "端口配置文件修改成功，请重新开启软件！"
        )

    def closeEvent(self, event):
        """Handle dialog close"""
        self.main_window.settings_form = None
        event.accept()
