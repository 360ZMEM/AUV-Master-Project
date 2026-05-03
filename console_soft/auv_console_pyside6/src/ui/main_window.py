"""
Main AUV Control Console Window
C# Reference: Form1.cs (complete implementation)
"""

import os
import time
import json
import yaml
from datetime import datetime
from pathlib import Path
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QGroupBox, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QTabWidget, QStatusBar, QTextEdit,
                               QComboBox, QSpinBox, QCheckBox, QButtonGroup, QMessageBox,
                               QLineEdit, QDoubleSpinBox)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction

from ..data_structures import Preferences, GPSQueue
from ..communication.comm_manager import CommunicationManager, CommunicationMode
from ..protocol.packet_builder import PacketBuilder
from ..protocol.constants import *
from ..utils.config_manager import ConfigManager
from ..utils.mode_manager import ModeConfigManager
from ..utils.offline_replay import OfflineReplayManager
from ..utils.xml_handler import XMLHandler
from .map_widget import MapWidget


class MainWindow(QMainWindow):
    """
    Main AUV Control Console Window (Form1 equivalent)
    C# Reference: Form1.cs lines 1-2299
    """

    def __init__(self):
        super().__init__()

        # Data structures
        self.preferences = Preferences()
        self.work_instruct = 0x00
        self.arbiter_control_mode_override = None  # Store the control mode override from the user
        self.autonomy_mode_active = False          # True = AUTONOMY (0xEE), False = MANUAL (0x01)
        self.estop_active = False                  # 紧急切断标志
        self.estop_locked = False                  # ESTOP 显式锁死标志
        self.last_command_ts = 0.0                 # 最后发送命令时间戳
        self.zenoh_router_ip = "127.0.0.1"         # Zenoh Router IP (从配置文件加载)
        self.config_path = None                    # 配置文件路径
        self.gps_queue = GPSQueue()
        self.dead_reckoning_queue = GPSQueue()
        self.autofixed_points = []
        self._last_arbiter_signature = None
        self._last_side_channel_status = ""

        # Position data
        self.auv_longitude = 0.0
        self.auv_latitude = 0.0
        self.auv_heading = 0.0

        # Communication
        self.config_manager = ConfigManager()
        self.mode_manager = ModeConfigManager()
        self.comm_manager = CommunicationManager()
        self.packet_builder = PacketBuilder()

        # Offline replay
        self.offline_replay = OfflineReplayManager()
        self.is_offline_mode = False

        # Control parameters
        self.motor_speed1 = 0
        self.motor_speed2 = 0
        self.rudder_angle_lh = 0
        self.rudder_angle_rh = 0
        self.rudder_angle_uv = 0
        self.rudder_angle_lv = 0
        self.orientation_angle = 0

        # 12 parameters
        self.params = [0] * 12

        # Forms
        self.extend_form = None
        self.settings_form = None

        # Waypoint selection state
        self.selecting_waypoint = False

        # Initialize UI
        self.init_ui()
        self.setup_timers()
        self.load_configuration()
        self.connect_signals()

    def init_ui(self):
        """Initialize all UI components"""
        self.setWindowTitle("AUV Console (Python/PySide6)")
        self.setGeometry(100, 100, 1400, 900)

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Top section: Telemetry displays
        telemetry_group = self.create_telemetry_group()
        main_layout.addWidget(telemetry_group)

        # Middle section: Map and controls
        middle_split = QHBoxLayout()

        # Map widget
        self.map_widget = MapWidget(self)
        middle_split.addWidget(self.map_widget, stretch=1)

        # Control panel
        control_panel = self.create_control_panel()
        middle_split.addWidget(control_panel, stretch=1)

        main_layout.addLayout(middle_split)

        # Bottom: Tab widget (compressed height)
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.create_waypoint_tab(), "航点规划")
        self.tab_widget.addTab(self.create_mission_tab(), "任务配置")
        self.tab_widget.addTab(self.create_message_tab(), "消息")
        main_layout.addWidget(self.tab_widget, stretch=2)  # More space for tab widget

        # 新增：底部控制台 - 最高优先级操作区（拉高高度）
        self.control_bar = self.create_bottom_control_bar()
        main_layout.addWidget(self.control_bar, stretch=1)  # Balanced height

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("工作指令接收反馈区域")

        # Menu bar
        self.create_menu_bar()

    def create_telemetry_group(self) -> QGroupBox:
        """Create telemetry display group"""
        group = QGroupBox("实时遥测数据")
        layout = QVBoxLayout()

        # Create labels dictionary
        self.labels = {}

        # Row 1: Basic info
        row1 = QHBoxLayout()
        self.labels['frame'] = QLabel("报文编号: --")
        self.labels['address'] = QLabel("本机地址: --")
        self.labels['mode'] = QLabel("工作模式: --")
        row1.addWidget(self.labels['frame'])
        row1.addWidget(self.labels['address'])
        row1.addWidget(self.labels['mode'])
        layout.addLayout(row1)

        # Row 2: Position data
        row2 = QHBoxLayout()
        self.labels['longitude'] = QLabel("经度: --")
        self.labels['latitude'] = QLabel("纬度: --")
        self.labels['depth'] = QLabel("深度: --")
        self.labels['heading'] = QLabel("航向: --")
        row2.addWidget(self.labels['longitude'])
        row2.addWidget(self.labels['latitude'])
        row2.addWidget(self.labels['depth'])
        row2.addWidget(self.labels['heading'])
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        self.labels['arbiter'] = QLabel("控制归属: --")
        self.labels['auto_state'] = QLabel("自主状态: --")
        self.labels['deny_reason'] = QLabel("拒绝原因: --")
        self.labels['freshness'] = QLabel("链路时延: --")
        row3.addWidget(self.labels['arbiter'])
        row3.addWidget(self.labels['auto_state'])
        row3.addWidget(self.labels['deny_reason'])
        row3.addWidget(self.labels['freshness'])
        layout.addLayout(row3)

        group.setLayout(layout)
        return group

    def create_control_panel(self) -> QGroupBox:
        """Create control panel with two-column layout to save vertical space"""
        group = QGroupBox("控制面板")
        group.setContentsMargins(8, 10, 8, 8)  # Balanced margins
        main_layout = QHBoxLayout()  # Main layout is horizontal (two columns)
        main_layout.setContentsMargins(4, 4, 4, 4)  # Balanced inner margins
        main_layout.setSpacing(4)  # Reasonable spacing

        # Left column
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(3, 3, 3, 3)
        left_layout.setSpacing(3)

        # Task control - 2x2 grid layout
        task_group = QGroupBox("任务控制")
        task_group.setStyleSheet("QGroupBox { margin-top: 5px; padding-top: 5px; }")
        task_layout = QVBoxLayout()
        task_layout.setContentsMargins(3, 3, 3, 3)
        task_layout.setSpacing(2)

        self.btn_task_start = QPushButton("任务开启")
        self.btn_task_cancel = QPushButton("任务取消")
        self.btn_clear_fault = QPushButton("清除故障")
        self.btn_init = QPushButton("初始化")

        # Row 1
        task_row1 = QHBoxLayout()
        task_row1.addWidget(self.btn_task_start)
        task_row1.addWidget(self.btn_task_cancel)
        task_layout.addLayout(task_row1)

        # Row 2
        task_row2 = QHBoxLayout()
        task_row2.addWidget(self.btn_clear_fault)
        task_row2.addWidget(self.btn_init)
        task_layout.addLayout(task_row2)

        task_group.setLayout(task_layout)
        left_layout.addWidget(task_group)

        arbiter_group = QGroupBox("仲裁控制")
        arbiter_group.setStyleSheet("QGroupBox { margin-top: 5px; padding-top: 5px; }")
        arbiter_layout = QVBoxLayout()
        arbiter_layout.setContentsMargins(3, 3, 3, 3)
        arbiter_layout.setSpacing(2)
        arbiter_button_row = QHBoxLayout()

        self.btn_request_autonomy = QPushButton("请求自主")
        self.btn_request_autonomy.setCheckable(True)
        self.btn_request_autonomy.setStyleSheet("QPushButton:checked { background-color: LightBlue; }")
        self.btn_manual_takeover = QPushButton("手动接管")

        arbiter_button_row.addWidget(self.btn_request_autonomy)
        arbiter_button_row.addWidget(self.btn_manual_takeover)
        arbiter_layout.addLayout(arbiter_button_row)

        self.labels['arbiter_request'] = QLabel("请求保持: 遥控")
        self.labels['arbiter_feedback'] = QLabel("拒绝反馈: --")
        arbiter_layout.addWidget(self.labels['arbiter_request'])
        arbiter_layout.addWidget(self.labels['arbiter_feedback'])
        arbiter_group.setLayout(arbiter_layout)

        left_layout.addWidget(arbiter_group)
        left_layout.addStretch()

        # Right column
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(3, 3, 3, 3)
        right_layout.setSpacing(3)

        # Communication mode
        comm_group = QGroupBox("通信模式")
        comm_group.setStyleSheet("QGroupBox { margin-top: 5px; padding-top: 5px; }")
        comm_layout = QVBoxLayout()  # Changed to vertical to fit in narrow column
        comm_layout.setContentsMargins(3, 3, 3, 3)
        comm_layout.setSpacing(2)

        self.btn_radio = QPushButton("无线电")
        self.btn_wifi = QPushButton("WiFi")
        self.btn_wifi.setCheckable(True)
        self.btn_wifi.setChecked(True)
        self.btn_beidou = QPushButton("北斗")

        comm_row1 = QHBoxLayout()
        comm_row1.addWidget(self.btn_radio)
        comm_row1.addWidget(self.btn_wifi)
        comm_layout.addLayout(comm_row1)
        comm_layout.addWidget(self.btn_beidou)
        comm_group.setLayout(comm_layout)

        right_layout.addWidget(comm_group)

        # Operation mode
        mode_group = QGroupBox("运行模式")
        mode_group.setStyleSheet("QGroupBox { margin-top: 5px; padding-top: 5px; }")
        mode_layout = QHBoxLayout()
        mode_layout.setContentsMargins(3, 3, 3, 3)
        mode_layout.setSpacing(2)

        self.btn_online_mode = QPushButton("在线模式")
        self.btn_online_mode.setCheckable(True)
        self.btn_offline_mode = QPushButton("离线模式")
        self.btn_offline_mode.setCheckable(True)

        # Create button group for mutual exclusion
        self.mode_button_group = QButtonGroup()
        self.mode_button_group.addButton(self.btn_online_mode, 0)  # ID 0 = online
        self.mode_button_group.addButton(self.btn_offline_mode, 1)  # ID 1 = offline
        self.mode_button_group.setExclusive(True)

        # Set styling for checked buttons
        self.btn_online_mode.setStyleSheet("QPushButton:checked { background-color: LightGreen; }")
        self.btn_offline_mode.setStyleSheet("QPushButton:checked { background-color: LightGreen; }")

        mode_layout.addWidget(self.btn_online_mode)
        mode_layout.addWidget(self.btn_offline_mode)
        mode_group.setLayout(mode_layout)

        right_layout.addWidget(mode_group)

        # Quick actions (compact vertical layout)
        action_group = QGroupBox("快捷操作")
        action_group.setStyleSheet("QGroupBox { margin-top: 5px; padding-top: 5px; }")
        action_layout = QVBoxLayout()
        action_layout.setContentsMargins(3, 3, 3, 3)
        action_layout.setSpacing(2)

        self.btn_extend = QPushButton("扩展控制...")
        self.btn_settings = QPushButton("端口设置...")
        self.btn_load_xml = QPushButton("导入航点...")
        self.btn_save_xml = QPushButton("导出航点...")

        # Two-row layout for buttons
        action_row1 = QHBoxLayout()
        action_row1.addWidget(self.btn_extend)
        action_row1.addWidget(self.btn_settings)
        action_layout.addLayout(action_row1)
        
        action_row2 = QHBoxLayout()
        action_row2.addWidget(self.btn_load_xml)
        action_row2.addWidget(self.btn_save_xml)
        action_layout.addLayout(action_row2)
        
        action_group.setLayout(action_layout)
        right_layout.addWidget(action_group)
        right_layout.addStretch()

        # Add both columns to main layout (RIGHT column first - comm/mode/actions, LEFT column second - task/arbiter)
        main_layout.addLayout(right_layout, stretch=1)
        main_layout.addLayout(left_layout, stretch=1)

        group.setLayout(main_layout)
        return group

    def create_waypoint_tab(self) -> QWidget:
        """Create waypoint planning tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)  # Reduce margins to save space
        layout.setSpacing(2)  # Reduce spacing

        # Waypoint table (compact mode)
        self.waypoint_table = QTableWidget()
        self.waypoint_table.setColumnCount(7)
        self.waypoint_table.setHorizontalHeaderLabels([
            "序号", "经度", "纬度", "策略", "参数", "电机转速", "设备控制"
        ])
        self.waypoint_table.setMaximumHeight(150)  # Limit height to compress tab
        layout.addWidget(self.waypoint_table)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_start_waypoint = QPushButton("开始选点")
        self.btn_end_waypoint = QPushButton("结束选点")
        self.btn_clear_waypoints = QPushButton("清空航点")

        btn_layout.addWidget(self.btn_start_waypoint)
        btn_layout.addWidget(self.btn_end_waypoint)
        btn_layout.addWidget(self.btn_clear_waypoints)
        layout.addLayout(btn_layout)

        widget.setLayout(layout)
        return widget

    def create_mission_tab(self) -> QWidget:
        """Create mission configuration tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Preferences inputs
        prefs_group = QGroupBox("首选项")
        prefs_layout = QVBoxLayout()

        # Target address
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("目标地址:"))
        self.combo_address = QComboBox()
        self.combo_address.addItems(["1", "2", "3"])
        row1.addWidget(self.combo_address)

        row1.addWidget(QLabel("工作模式:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["仅发送", "遥控", "定点", "定向", "回航"])
        row1.addWidget(self.combo_mode)
        prefs_layout.addLayout(row1)

        # Depth protection
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("深度保护1:"))
        self.spin_depth1 = QSpinBox()
        self.spin_depth1.setRange(0, 65535)
        row2.addWidget(self.spin_depth1)

        row2.addWidget(QLabel("深度保护2:"))
        self.spin_depth2 = QSpinBox()
        self.spin_depth2.setRange(0, 65535)
        row2.addWidget(self.spin_depth2)
        prefs_layout.addLayout(row2)

        # Confirm button
        self.btn_confirm_prefs = QPushButton("确认首选项")
        prefs_layout.addWidget(self.btn_confirm_prefs)

        prefs_group.setLayout(prefs_layout)
        layout.addWidget(prefs_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_message_tab(self) -> QWidget:
        """Create message tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        self.message_log = QTextEdit()
        self.message_log.setReadOnly(True)
        self.message_log.setPlaceholderText("仲裁状态、side channel 和联调反馈会记录在这里")
        layout.addWidget(self.message_log)

        widget.setLayout(layout)
        return widget

    def load_console_config(self) -> dict:
        """加载上位机配置文件 console_config.yaml"""
        try:
            config_file = Path(__file__).parent.parent.parent / "console_config.yaml"
            self.config_path = config_file
            if config_file.exists():
                import yaml
                with open(config_file, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
        except Exception as exc:
            print(f"[config] 加载配置文件失败: {exc}")
        return {}

    def create_bottom_control_bar(self) -> QWidget:
        """创建底部控制台 - 最高优先级操作区"""
        bar = QWidget()
        bar.setStyleSheet("background-color: #1e1e1e; border-top: 2px solid #555;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        # 1. 紧急切断按钮（醒目红色，带显式复位）
        estop_layout = QVBoxLayout()
        self.btn_estop = QPushButton("🛑 紧急切断 ESTOP")
        self.btn_estop.setMinimumWidth(180)
        self.btn_estop.setMinimumHeight(50)
        self.btn_estop.setStyleSheet(
            "QPushButton { background-color: #cc0000; color: white; font-weight: bold; "
            "font-size: 15px; padding: 8px; border-radius: 5px; }"
            "QPushButton:pressed { background-color: #990000; }"
            "QPushButton:disabled { background-color: #666; color: #999; }"
        )
        self.btn_estop_reset = QPushButton("🔓 解除急停")
        self.btn_estop_reset.setMinimumWidth(180)
        self.btn_estop_reset.setMinimumHeight(35)
        self.btn_estop_reset.setEnabled(False)
        self.btn_estop_reset.setStyleSheet(
            "QPushButton { background-color: #ff6600; color: white; font-weight: bold; "
            "font-size: 13px; padding: 6px; border-radius: 5px; }"
            "QPushButton:pressed { background-color: #cc5200; }"
            "QPushButton:disabled { background-color: #555; color: #888; }"
        )
        estop_layout.addWidget(self.btn_estop)
        estop_layout.addWidget(self.btn_estop_reset)
        layout.addLayout(estop_layout, stretch=0)

        # 2. 模式切换开关（手动/自主）
        mode_group = QGroupBox("控制模式")
        mode_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        mode_layout = QVBoxLayout()
        self.toggle_mode = QPushButton("手动遥控 MANUAL")
        self.toggle_mode.setCheckable(True)
        self.toggle_mode.setMinimumWidth(200)
        self.toggle_mode.setMinimumHeight(45)
        self.toggle_mode.setStyleSheet(
            "QPushButton { background-color: #0066cc; color: white; font-weight: bold; "
            "font-size: 14px; padding: 8px; border-radius: 5px; }"
            "QPushButton:checked { background-color: #009933; }"
            "QPushButton:disabled { background-color: #555; color: #888; }"
        )
        self.lbl_arbiter_status = QLabel("仲裁状态: UNKNOWN")
        self.lbl_arbiter_status.setStyleSheet("color: #aaa; font-size: 11px;")
        mode_layout.addWidget(self.toggle_mode)
        mode_layout.addWidget(self.lbl_arbiter_status)
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group, stretch=0)

        # 3. Zenoh 连接状态
        zenoh_group = QGroupBox("Zenoh 链路")
        zenoh_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        zenoh_layout = QVBoxLayout()
        zenoh_row = QHBoxLayout()
        zenoh_row.addWidget(QLabel("Router IP:"))
        self.edit_zenoh_ip = QLineEdit("127.0.0.1")
        self.edit_zenoh_ip.setMaximumWidth(120)
        zenoh_row.addWidget(self.edit_zenoh_ip)
        zenoh_layout.addLayout(zenoh_row)

        self.lbl_zenoh_status = QLabel("状态: 未连接")
        self.lbl_zenoh_status.setStyleSheet("color: #ff4444; font-size: 11px;")
        zenoh_layout.addWidget(self.lbl_zenoh_status)

        self.btn_zenoh_connect = QPushButton("连接 Zenoh")
        self.btn_zenoh_connect.setMinimumHeight(30)
        zenoh_layout.addWidget(self.btn_zenoh_connect)
        zenoh_group.setLayout(zenoh_layout)
        layout.addWidget(zenoh_group, stretch=0)

        # 4. 自主任务参数输入区
        task_group = QGroupBox("自主任务参数")
        task_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        task_layout = QVBoxLayout()

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("目标深度(m):"))
        self.spin_target_depth = QDoubleSpinBox()
        self.spin_target_depth.setRange(0.0, 500.0)
        self.spin_target_depth.setValue(5.0)
        self.spin_target_depth.setSingleStep(0.5)
        self.spin_target_depth.setMaximumWidth(80)
        row1.addWidget(self.spin_target_depth)

        row1.addWidget(QLabel("巡检距离(m):"))
        self.spin_track_distance = QDoubleSpinBox()
        self.spin_track_distance.setRange(0.0, 10000.0)
        self.spin_track_distance.setValue(500.0)
        self.spin_track_distance.setSingleStep(50.0)
        self.spin_track_distance.setMaximumWidth(90)
        row1.addWidget(self.spin_track_distance)
        task_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("任务超时(s):"))
        self.spin_task_timeout = QSpinBox()
        self.spin_task_timeout.setRange(60, 7200)
        self.spin_task_timeout.setValue(1200)
        self.spin_task_timeout.setSingleStep(60)
        self.spin_task_timeout.setMaximumWidth(80)
        row2.addWidget(self.spin_task_timeout)

        row2.addWidget(QLabel("任务类型:"))
        self.combo_mission_type = QComboBox()
        self.combo_mission_type.addItems([
            "CABLE_TRACKING",
            "AREA_SEARCH",
            "PIPELINE_INSPECT"
        ])
        self.combo_mission_type.setMaximumWidth(140)
        row2.addWidget(self.combo_mission_type)

        self.btn_send_mission = QPushButton("下发任务")
        self.btn_send_mission.setMinimumHeight(30)
        row2.addWidget(self.btn_send_mission)

        task_layout.addLayout(row2)
        task_group.setLayout(task_layout)
        layout.addWidget(task_group, stretch=1)

        # 5. 置信度显示
        conf_group = QGroupBox("传感器置信度")
        conf_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        conf_layout = QVBoxLayout()
        self.lbl_confidence = QLabel("置信度: --")
        self.lbl_confidence.setStyleSheet("color: #aaa; font-size: 16px; font-weight: bold;")
        conf_layout.addWidget(self.lbl_confidence)
        conf_group.setLayout(conf_layout)
        layout.addWidget(conf_group, stretch=0)

        return bar

    def create_menu_bar(self):
        """Create menu bar"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("文件")
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("视图")
        extend_action = QAction("扩展窗口", self)
        extend_action.triggered.connect(self.open_extended_control)
        view_menu.addAction(extend_action)

        # Settings menu
        settings_menu = menubar.addMenu("设置")
        settings_action = QAction("端口设置", self)
        settings_action.triggered.connect(self.open_settings)
        settings_menu.addAction(settings_action)

    def setup_timers(self):
        """Setup timers"""
        # Timer 1: Data transmission - 600ms (C# timer1_Tick)
        self.tx_timer = QTimer()
        self.tx_timer.timeout.connect(self.transmit_data)
        self.tx_timer.start(600)

        # Timer 2: Beidou control - 100ms
        self.beidou_timer = QTimer()
        self.beidou_timer.timeout.connect(self.handle_beidou_timeout)
        self.beidou_timer.start(100)

        # Timer 3: Map refresh - 100ms
        self.map_refresh_timer = QTimer()
        self.map_refresh_timer.timeout.connect(self.map_widget.update)
        self.map_refresh_timer.start(100)

    def connect_signals(self):
        """Connect all signals and slots"""
        # Task control buttons
        self.btn_task_start.clicked.connect(lambda: self.set_work_instruct(CMD_TASK_START))
        self.btn_task_cancel.clicked.connect(lambda: self.set_work_instruct(CMD_TASK_CANCEL))
        self.btn_clear_fault.clicked.connect(lambda: self.set_work_instruct(CMD_CLEAR_FAULT))
        self.btn_init.clicked.connect(lambda: self.set_work_instruct(CMD_INITIALIZE))
        self.btn_request_autonomy.clicked.connect(self.request_autonomy)
        self.btn_manual_takeover.clicked.connect(self.manual_takeover)

        # Communication mode buttons
        self.btn_radio.clicked.connect(lambda: self.switch_comm_mode(CommunicationMode.RADIO))
        self.btn_wifi.clicked.connect(lambda: self.switch_comm_mode(CommunicationMode.WIFI))
        self.btn_beidou.clicked.connect(lambda: self.switch_comm_mode(CommunicationMode.BEIDOU))

        # Operation mode buttons
        self.btn_online_mode.clicked.connect(self.switch_to_online_mode)
        self.btn_offline_mode.clicked.connect(self.switch_to_offline_mode)

        # Quick action buttons
        self.btn_extend.clicked.connect(self.open_extended_control)
        self.btn_settings.clicked.connect(self.open_settings)
        self.btn_load_xml.clicked.connect(self.load_waypoint_xml)
        self.btn_save_xml.clicked.connect(self.save_waypoint_xml)

        # Waypoint buttons
        self.btn_start_waypoint.clicked.connect(self.start_waypoint_selection)
        self.btn_end_waypoint.clicked.connect(self.end_waypoint_selection)
        self.btn_clear_waypoints.clicked.connect(self.clear_waypoints)

        # Preferences confirm button
        self.btn_confirm_prefs.clicked.connect(self.save_preferences)

        # Optional Zenoh side channel updates
        self.comm_manager.bridge_telemetry_received.connect(self.update_bridge_sidechannel_display)
        self.comm_manager.arbiter_state_received.connect(self.update_arbiter_state_display)
        self.comm_manager.side_channel_status_changed.connect(self.on_side_channel_status_changed)

        # 新增：底部控制台信号
        self.btn_estop.clicked.connect(self.trigger_estop)
        self.btn_estop_reset.clicked.connect(self.reset_estop)
        self.toggle_mode.clicked.connect(self.on_mode_toggle)
        self.btn_send_mission.clicked.connect(self.send_mission_command)
        self.btn_zenoh_connect.clicked.connect(self.toggle_zenoh_connection)

    def load_configuration(self):
        """Load configuration files"""
        # 加载 console_config.yaml
        console_cfg = self.load_console_config()
        if console_cfg:
            zenoh_cfg = console_cfg.get('zenoh', {})
            self.zenoh_router_ip = zenoh_cfg.get('router_ip', '127.0.0.1')
            self.edit_zenoh_ip.setText(self.zenoh_router_ip)
            defaults = console_cfg.get('defaults', {})
            self.spin_target_depth.setValue(defaults.get('target_depth_m', 5.0))
            self.spin_track_distance.setValue(defaults.get('track_distance_m', 500.0))
            self.spin_task_timeout.setValue(defaults.get('task_timeout_s', 1200))
            mission_type = defaults.get('mission_type', 'CABLE_TRACKING')
            idx = self.combo_mission_type.findText(mission_type)
            if idx >= 0:
                self.combo_mission_type.setCurrentIndex(idx)

        # Load port configuration first (needed for both modes)
        port_config = self.config_manager.load_port_config()
        port_config['zenoh_side_channel'] = self.config_manager.load_side_channel_config()
        self.comm_manager.initialize(port_config)

        # Load parameters
        params = self.config_manager.load_parameters()
        self.preferences = Preferences(**params)

        # Update UI with parameters
        self.combo_address.setCurrentIndex(self.preferences.obj_address - 1)
        self.combo_mode.setCurrentIndex(self.preferences.work_mode)
        self.spin_depth1.setValue(self.preferences.depth_proprotect_param1)
        self.spin_depth2.setValue(self.preferences.depth_proprotect_param2)

        # Load mode configuration and initialize mode
        mode_config = self.mode_manager.load_config()
        current_mode = mode_config.get('mode', 'online')

        # Initialize based on mode
        if current_mode == 'offline':
            # Start in offline mode
            self.is_offline_mode = True
            self.btn_online_mode.setChecked(False)
            self.btn_offline_mode.setChecked(True)

            # Load offline configuration
            offline_config = mode_config.get('offline', {})
            pcap_file = offline_config.get('pcap_file', '../PC104.pcapng')
            interval_ms = int(offline_config.get('replay_interval_ms', 600))
            loop_playback = offline_config.get('loop_playback', 'true').lower() == 'true'

            # Load pcap and start replay
            import os
            # Get project root (auv_console_python directory)
            # __file__ is src/ui/main_window.py
            # dirname gives src/ui, dirname again gives src, dirname again gives auv_console_python
            ui_dir = os.path.dirname(os.path.abspath(__file__))
            src_dir = os.path.dirname(ui_dir)
            project_root = os.path.dirname(src_dir)
            pcap_path = os.path.abspath(os.path.join(project_root, pcap_file))

            if self.offline_replay.load_pcap(pcap_path):
                self.offline_replay.packet_received.connect(self.on_offline_packet_received)
                self.offline_replay.start_replay(interval_ms, loop_playback)
                print(f"Started offline mode with {self.offline_replay.get_packet_count()} packets")
                self.status_bar.showMessage(f"离线模式: {self.offline_replay.get_packet_count()} 包已加载", 5000)
            else:
                print("Warning: Could not load PCAP file, falling back to online mode")
                self.is_offline_mode = False
                self.btn_online_mode.setChecked(True)
                self.btn_offline_mode.setChecked(False)
                # Start UDP for online mode
                self.comm_manager.get_udp_communicator().start()
                self.comm_manager.set_side_channel_active(True)
                self.status_bar.showMessage("无法加载 PCAP，已切换到在线模式", 5000)
        else:
            # Start in online mode
            self.is_offline_mode = False
            self.btn_online_mode.setChecked(True)
            self.btn_offline_mode.setChecked(False)
            # Start UDP for online mode
            self.comm_manager.get_udp_communicator().start()
            self.comm_manager.set_side_channel_active(True)
            self.status_bar.showMessage("在线模式: 已连接到 AUV", 5000)

        self.update_arbiter_control_ui()

    def set_work_instruct(self, code: int):
        """Set work instruction byte"""
        self.work_instruct = code & 0xFF
        mode_names = {
            CMD_TASK_START: "任务开启",
            CMD_TASK_CANCEL: "任务取消",
            CMD_CLEAR_FAULT: "清除故障",
            CMD_INITIALIZE: "初始化"
        }
        name = mode_names.get(code, f"命令{code:#x}")
        self.append_message("指令", f"工作指令切换为 {name} ({code:#04x})")
        self.status_bar.showMessage(f"工作指令: {name} ({code:#x})")

    def switch_comm_mode(self, mode: int):
        """Switch communication mode"""
        if mode != CommunicationMode.WIFI:
            self.clear_autonomy_hold(reason="离开 WiFi 模式", send_override=True)
        self.comm_manager.switch_mode(mode)
        self.update_arbiter_control_ui()

    def transmit_data(self):
        """Transmit data packet - 600ms timer (C# timer1_Tick) with 5Hz heartbeat"""
        self.last_command_ts = time.time()

        # ─── 紧急切断：强制发送 ESTOP 包 ───
        if self.estop_active:
            self._send_estop_packet()
            # 同时通过 Zenoh 发送自主心跳（保持 Jetson 连接感知）
            self.send_autonomy_heartbeat()
            return True

        # ─── 自主模式：发送语义 JSON 心跳 + 传统 0xEE 包 ───
        if self.autonomy_mode_active:
            self.send_autonomy_heartbeat()
            # 同时发送传统包保持向后兼容（Jetson 通过 UDP 也能收到）
            packet = self.packet_builder.build_send_packet(
                preferences=self.preferences,
                work_instruct=0x00,
                motor_speeds=(0, 0),
                rudder_angles=(0, 0, 0, 0),
                orientation=0,
                parameters=tuple(self.params),
                control_mode_byte=0xEE,
            )
            sent = self.comm_manager.send_packet(packet, self.preferences, 0x00)
            self.packet_builder.increment_frame()
            return bool(sent)

        # ─── 手动模式：发送 CKTH 包（直连 AMD） ───
        effective_control_mode = self.get_effective_control_mode()

        # Check if we should send (not in send-only or return mode)
        if effective_control_mode in [WORK_MODE_SEND_ONLY, WORK_MODE_RETURN]:
            return False

        # Build packet
        packet = self.packet_builder.build_send_packet(
            preferences=self.preferences,
            work_instruct=self.work_instruct,
            motor_speeds=(self.motor_speed1, self.motor_speed2),
            rudder_angles=(self.rudder_angle_lh, self.rudder_angle_rh,
                          self.rudder_angle_uv, self.rudder_angle_lv),
            orientation=self.orientation_angle,
            parameters=tuple(self.params),
            control_mode_byte=effective_control_mode,
        )

        # Send packet
        sent = self.comm_manager.send_packet(
            packet,
            self.preferences,
            self.work_instruct
        )

        # Increment frame counter
        self.packet_builder.increment_frame()
        return bool(sent)

    def handle_beidou_timeout(self):
        """Handle Beidou 65-second transmission cycle"""
        pass  # TODO: Implement Beidou timing logic

    def update_telemetry_display(self, telemetry):
        """Update UI with received telemetry"""
        # Update labels
        self.labels['frame'].setText(f"报文编号: {telemetry.frame_number}")
        self.labels['address'].setText(f"本机地址: {telemetry.auv_address}号机器人")

        mode_name = WORK_MODE_NAMES.get(telemetry.work_mode, "未知")
        self.labels['mode'].setText(f"工作模式: {mode_name}")

        # Update position
        self.auv_longitude = telemetry.gps_lon
        self.auv_latitude = telemetry.gps_lat
        self.auv_heading = telemetry.compass_heading

        self.labels['longitude'].setText(f"经度: {telemetry.gps_lon:.6f}")
        self.labels['latitude'].setText(f"纬度: {telemetry.gps_lat:.6f}")
        self.labels['depth'].setText(f"深度: {telemetry.depth:.1f} m")
        self.labels['heading'].setText(f"航向: {telemetry.compass_heading:.1f}°")

        # Update GPS queue
        if self.auv_longitude != 0 and self.auv_latitude != 0:
            self.gps_queue.enqueue(self.auv_longitude, self.auv_latitude)

            # Update map origin on first GPS
            self.map_widget.set_map_origin(self.auv_longitude, self.auv_latitude)

    def save_preferences(self):
        """Save preferences to param.txt"""
        self.preferences.obj_address = self.combo_address.currentIndex() + 1
        self.preferences.work_mode = self.combo_mode.currentIndex()
        self.preferences.depth_proprotect_param1 = self.spin_depth1.value()
        self.preferences.depth_proprotect_param2 = self.spin_depth2.value()

        # Convert to dict and save
        params = {
            'obj_address': self.preferences.obj_address,
            'work_mode': self.preferences.work_mode,
            'depth_proprotect_param1': self.preferences.depth_proprotect_param1,
            'depth_proprotect_param2': self.preferences.depth_proprotect_param2,
            'bottom_proprotect_param1': self.preferences.bottom_proprotect_param1,
            'bottom_proprotect_param2': self.preferences.bottom_proprotect_param2,
            'preset_time': self.preferences.preset_time,
            'spare_param1': self.preferences.spare_param1,
            'spare_param2': self.preferences.spare_param2,
            'return_longitude': self.preferences.return_longitude,
            'return_latitude': self.preferences.return_latitude
        }

        self.config_manager.save_parameters(params)
        self.status_bar.showMessage("首选项已保存", 3000)

    def open_extended_control(self):
        """Open extended control window"""
        if self.extend_form is None:
            from .extended_control import ExtendedControlWindow
            self.extend_form = ExtendedControlWindow(self)
        self.extend_form.show()
        self.extend_form.raise_()

    def open_settings(self):
        """Open settings dialog"""
        if self.settings_form is None:
            from .settings_dialog import SettingsDialog
            self.settings_form = SettingsDialog(self)
        self.settings_form.show()
        self.settings_form.raise_()

    def load_waypoint_xml(self):
        """Load waypoints from XML"""
        xml_handler = XMLHandler()
        self.autofixed_points = xml_handler.load_waypoints()
        self.update_waypoint_table()
        self.status_bar.showMessage(f"已加载 {len(self.autofixed_points)} 个航点", 3000)

    def save_waypoint_xml(self):
        """Save waypoints to XML"""
        xml_handler = XMLHandler()
        xml_handler.save_waypoints(self.autofixed_points)
        self.status_bar.showMessage(f"已保存 {len(self.autofixed_points)} 个航点", 3000)

    def update_waypoint_table(self):
        """Update waypoint table display"""
        self.waypoint_table.setRowCount(len(self.autofixed_points))

        for i, wp in enumerate(self.autofixed_points):
            self.waypoint_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.waypoint_table.setItem(i, 1, QTableWidgetItem(f"{wp.longitude:.6f}"))
            self.waypoint_table.setItem(i, 2, QTableWidgetItem(f"{wp.latitude:.6f}"))
            self.waypoint_table.setItem(i, 3, QTableWidgetItem(str(wp.control_strategy)))
            self.waypoint_table.setItem(i, 4, QTableWidgetItem(str(wp.control_param)))
            self.waypoint_table.setItem(i, 5, QTableWidgetItem(str(wp.motor_speed)))
            self.waypoint_table.setItem(i, 6, QTableWidgetItem(f"{wp.device_control:08b}"))

    def start_waypoint_selection(self):
        """Start waypoint selection mode"""
        self.selecting_waypoint = True
        self.status_bar.showMessage("地图选点模式已开启 - 请在地图上点击添加航点", 5000)
        self.btn_start_waypoint.setEnabled(False)
        self.btn_end_waypoint.setEnabled(True)

    def end_waypoint_selection(self):
        """End waypoint selection mode"""
        self.selecting_waypoint = False
        self.status_bar.showMessage(f"地图选点模式已结束 - 共添加 {len(self.autofixed_points)} 个航点", 3000)
        self.btn_start_waypoint.setEnabled(True)
        self.btn_end_waypoint.setEnabled(False)

    def clear_waypoints(self):
        """Clear all waypoints"""
        self.autofixed_points.clear()
        self.update_waypoint_table()
        self.map_widget.update()
        self.status_bar.showMessage("已清空所有航点", 3000)

    def add_waypoint_from_map(self, longitude: float, latitude: float):
        """
        Add waypoint from map click
        Args:
            longitude: GPS longitude
            latitude: GPS latitude
        """
        from ..data_structures import AutoFixedPoint

        # Create new waypoint with default values
        wp = AutoFixedPoint()
        wp.longitude = longitude
        wp.latitude = latitude
        wp.control_strategy = 0  # Default: fixed depth
        wp.control_param = 0.0
        wp.motor_speed = 0
        wp.device_control = 0b00000000

        self.autofixed_points.append(wp)
        self.update_waypoint_table()
        self.map_widget.update()

        self.status_bar.showMessage(f"已添加航点 #{len(self.autofixed_points)}: {latitude:.6f}, {longitude:.6f}", 3000)

    def switch_to_online_mode(self):
        """Switch to online mode (connect to real AUV)"""
        print("Switching to ONLINE mode...")

        # Stop offline replay if running
        if self.offline_replay.is_replaying:
            self.offline_replay.stop_replay()

        # Update UI state (button is already checked by click)
        self.is_offline_mode = False

        # Save configuration
        self.mode_manager.set_online_mode()

        # Enable communication
        self.comm_manager.get_udp_communicator().start()
        self.comm_manager.set_side_channel_active(True)
        self.update_arbiter_control_ui()

        self.status_bar.showMessage("已切换到在线模式 - 连接真实 AUV", 5000)

    def switch_to_offline_mode(self):
        """Switch to offline mode (pcap replay)"""
        print("Switching to OFFLINE mode...")

        self.clear_autonomy_hold(reason="切换到离线模式", send_override=True)

        # Stop online communication
        self.comm_manager.get_udp_communicator().stop()
        self.comm_manager.set_side_channel_active(False)

        # Update UI state (button is already checked by click)
        self.is_offline_mode = True

        # Save configuration
        self.mode_manager.set_offline_mode()

        # Load offline configuration
        mode_config = self.mode_manager.load_config()
        offline_config = mode_config.get('offline', {})

        pcap_file = offline_config.get('pcap_file', 'PC104.pcapng')
        interval_ms = int(offline_config.get('replay_interval_ms', 600))
        loop_playback = offline_config.get('loop_playback', 'true').lower() == 'true'

        # Load pcap file (relative to project root)
        import os
        ui_dir = os.path.dirname(os.path.abspath(__file__))
        src_dir = os.path.dirname(ui_dir)
        project_root = os.path.dirname(src_dir)
        pcap_path = os.path.abspath(os.path.join(project_root, pcap_file))

        if self.offline_replay.load_pcap(pcap_path):
            # Start replay
            self.offline_replay.start_replay(interval_ms, loop_playback)

            # Connect packet signal
            self.offline_replay.packet_received.connect(self.on_offline_packet_received)

            self.status_bar.showMessage(f"已切换到离线模式 - 回放: {os.path.basename(pcap_file)}", 5000)
        else:
            self.status_bar.showMessage("离线模式：无法加载 PCAP 文件", 5000)

        self.update_arbiter_control_ui()

    def on_offline_packet_received(self, data: bytes):
        """Handle packet from offline replay"""
        # Parse and display (same as online mode)
        try:
            telemetry = self.packet_builder.parse_recv_packet(data)
            self.update_telemetry_display(telemetry)
        except Exception as e:
            print(f"Error parsing offline packet: {e}")

    def update_bridge_sidechannel_display(self, payload: dict):
        """Show bridge telemetry metadata from optional Zenoh side channel."""
        if not isinstance(payload, dict):
            return
        if 'active_arbiter' in payload:
            self.labels['arbiter'].setText(f"控制归属: {payload.get('active_arbiter', '--')}")
            # 同步更新底部仲裁状态标签
            arb = payload.get('active_arbiter', '--')
            if arb == 'REMOTE':
                self.lbl_arbiter_status.setText("仲裁状态: REMOTE")
                self.lbl_arbiter_status.setStyleSheet("color: #00cc66;")
            elif arb == 'AUTONOMOUS':
                self.lbl_arbiter_status.setText("仲裁状态: AUTONOMOUS")
                self.lbl_arbiter_status.setStyleSheet("color: #0099ff; font-weight: bold;")
            elif 'ESTOP' in str(arb):
                self.lbl_arbiter_status.setText(f"仲裁状态: {arb}")
                self.lbl_arbiter_status.setStyleSheet("color: #ff0000; font-weight: bold;")
        if 'auto_state' in payload:
            self.labels['auto_state'].setText(f"自主状态: {payload.get('auto_state', '--')}")
        if 'deny_reason' in payload:
            self.labels['deny_reason'].setText(f"拒绝原因: {payload.get('deny_reason', '--')}")
        freshness = payload.get('telemetry_freshness_ms')
        if isinstance(freshness, (int, float)):
            self.labels['freshness'].setText(f"链路时延: {float(freshness):.1f} ms")
        if 'confidence' in payload:
            conf = float(payload.get('confidence', 0.0))
            self.lbl_confidence.setText(f"置信度: {conf:.2f}")
            if conf < 0.5:
                self.lbl_confidence.setStyleSheet("color: #ff4444; font-size: 16px; font-weight: bold;")
            elif conf < 0.7:
                self.lbl_confidence.setStyleSheet("color: #ffaa00; font-size: 16px; font-weight: bold;")
            else:
                self.lbl_confidence.setStyleSheet("color: #00cc66; font-size: 16px; font-weight: bold;")
        self.update_arbiter_feedback(
            str(payload.get('auto_state', '--')),
            str(payload.get('deny_reason', 'NONE')),
        )

    def update_arbiter_state_display(self, payload: dict):
        """Update arbiter labels and status bar from side-channel state view."""
        if not isinstance(payload, dict):
            return
        self.labels['arbiter'].setText(f"控制归属: {payload.get('active_arbiter', '--')}")
        self.labels['auto_state'].setText(f"自主状态: {payload.get('auto_state', '--')}")
        self.labels['deny_reason'].setText(f"拒绝原因: {payload.get('deny_reason', '--')}")
        freshness = payload.get('telemetry_freshness_ms')
        if isinstance(freshness, (int, float)):
            self.labels['freshness'].setText(f"链路时延: {float(freshness):.1f} ms")
        deny_reason = str(payload.get('deny_reason', 'NONE'))
        auto_state = str(payload.get('auto_state', '--'))
        active_arbiter = str(payload.get('active_arbiter', '--'))
        self.update_arbiter_feedback(auto_state, deny_reason)
        self.log_arbiter_state(active_arbiter, auto_state, deny_reason)
        self.status_bar.showMessage(f"仲裁状态: {auto_state} | 拒绝原因: {deny_reason}", 3000)

    def on_side_channel_status_changed(self, message: str):
        """Surface Zenoh side-channel runtime status without coupling UI to transport."""
        if not message:
            return
        if message != self._last_side_channel_status:
            self._last_side_channel_status = message
            self.append_message("链路", message)
        self.update_arbiter_control_ui()
        self.status_bar.showMessage(message, 3000)

    def request_autonomy(self):
        """Hold the outgoing control mode at 0xEE so the bridge keeps seeing autonomy requests."""
        ready, reason = self.can_send_arbiter_action()
        if not ready:
            self.arbiter_control_mode_override = None
            self.update_arbiter_control_ui()
            self.append_message("仲裁", f"自主请求未发送: {reason}")
            self.status_bar.showMessage(f"自主请求未发送: {reason}", 4000)
            return

        self.arbiter_control_mode_override = CONTROL_MODE_JETSON_PROTOCOL
        self.update_arbiter_control_ui()
        if self.send_control_snapshot(control_mode_byte=CONTROL_MODE_JETSON_PROTOCOL):
            self.append_message("仲裁", "已发送自主请求，后续周期包将保持 mode=0xEE")
            self.status_bar.showMessage("已开始持续发送自主请求", 4000)

    def manual_takeover(self):
        """Cancel the autonomy hold locally and send one remote override packet immediately."""
        ready, reason = self.can_send_arbiter_action()
        self.arbiter_control_mode_override = None
        self.update_arbiter_control_ui()

        if not ready:
            self.append_message("仲裁", f"已切回本地遥控，但未发送接管包: {reason}")
            self.status_bar.showMessage(f"已切回本地遥控，但未发送接管包: {reason}", 4000)
            return

        if self.send_control_snapshot(
            control_mode_byte=WORK_MODE_REMOTE_CONTROL,
            work_instruct=CMD_TASK_CANCEL,
        ):
            self.append_message("仲裁", "已发送手动接管包，桥侧将锁回遥控")
            self.status_bar.showMessage("已发送手动接管", 4000)

    def clear_autonomy_hold(self, reason: str, *, send_override: bool):
        """Release the local autonomy hold and optionally emit one manual override packet."""
        had_hold = self.arbiter_control_mode_override == CONTROL_MODE_JETSON_PROTOCOL
        if not had_hold:
            return

        self.arbiter_control_mode_override = None
        self.update_arbiter_control_ui()
        self.append_message("仲裁", f"{reason}，已撤销自主请求保持")

        if not send_override:
            return

        ready, _ = self.can_send_arbiter_action()
        if ready:
            self.send_control_snapshot(
                control_mode_byte=WORK_MODE_REMOTE_CONTROL,
                work_instruct=CMD_TASK_CANCEL,
            )

    def can_send_arbiter_action(self):
        """Check whether the UI can safely drive the bridge arbiter through the WiFi side channel."""
        if self.is_offline_mode:
            return False, "离线模式下不发送仲裁控制包"
        if self.comm_manager.comm_mode != CommunicationMode.WIFI:
            return False, "仅 WiFi 模式支持仲裁 side channel"
        if not self.comm_manager.is_side_channel_active():
            return False, "Zenoh side channel 未激活"
        return True, ""

    def get_effective_control_mode(self) -> int:
        """Return the control mode byte currently held by the UI."""
        if self.arbiter_control_mode_override is not None:
            return int(self.arbiter_control_mode_override)
        return int(self.preferences.work_mode)

    def send_control_snapshot(self, *, control_mode_byte: int, work_instruct: int = None) -> bool:
        """Build and send one immediate control snapshot without waiting for the next timer tick."""
        effective_work_instruct = self.work_instruct if work_instruct is None else int(work_instruct)
        packet = self.packet_builder.build_send_packet(
            preferences=self.preferences,
            work_instruct=effective_work_instruct,
            motor_speeds=(self.motor_speed1, self.motor_speed2),
            rudder_angles=(self.rudder_angle_lh, self.rudder_angle_rh,
                          self.rudder_angle_uv, self.rudder_angle_lv),
            orientation=self.orientation_angle,
            parameters=tuple(self.params),
            control_mode_byte=control_mode_byte,
        )
        sent = self.comm_manager.send_packet(packet, self.preferences, effective_work_instruct)
        self.packet_builder.increment_frame()
        return bool(sent)

    # ========================================================================
    # 新增：底部控制台核心逻辑 (ESTOP / 模式切换 / 任务下发 / Zenoh 连接)
    # ========================================================================

    def trigger_estop(self):
        """触发紧急切断 - 立即发送 ESTOP 包并锁死状态"""
        if self.estop_locked:
            return  # 已经锁死，需要先解锁

        self.estop_active = True
        self.estop_locked = True
        self.autonomy_mode_active = False
        self.toggle_mode.setChecked(False)
        self.toggle_mode.setEnabled(False)

        # UI 更新
        self.btn_estop.setEnabled(False)
        self.btn_estop_reset.setEnabled(True)
        self.lbl_arbiter_status.setText("仲裁状态: ESTOP LOCKED")
        self.lbl_arbiter_status.setStyleSheet("color: #ff0000; font-weight: bold; font-size: 14px;")

        self.append_message("安全", "🛑 紧急切断已触发！所有推力归零，状态锁死")
        self.status_bar.showMessage("🛑 紧急切断生效 - 必须显式复位", 5000)

        # 立即发送 ESTOP 包 (mode=0x01, work=0x02, thrust=0)
        self._send_estop_packet()

    def _send_estop_packet(self):
        """发送 ESTOP 包: mode=0x01, work=0x02, 推力归零"""
        packet = self.packet_builder.build_send_packet(
            preferences=self.preferences,
            work_instruct=CMD_TASK_CANCEL,  # 0x02
            motor_speeds=(0, 0),
            rudder_angles=(0, 0, 0, 0),
            orientation=0,
            parameters=tuple(self.params),
            control_mode_byte=0x01,  # 强制手动模式
        )
        self.comm_manager.send_packet(packet, self.preferences, CMD_TASK_CANCEL)
        self.packet_builder.increment_frame()

    def reset_estop(self):
        """解除急停 - 仅在推力归零时允许"""
        # 检查推力是否归零
        thrust_ok = (abs(self.motor_speed1) < 0.1 and abs(self.motor_speed2) < 0.1)
        if not thrust_ok:
            self.append_message("安全", "⚠ 推力未归零！请将遥杆回中后再解除急停")
            self.status_bar.showMessage("⚠ 推力未归零，无法解除急停", 3000)
            return

        self.estop_active = False
        self.estop_locked = False

        # UI 恢复
        self.btn_estop.setEnabled(True)
        self.btn_estop_reset.setEnabled(False)
        self.toggle_mode.setEnabled(True)
        self.lbl_arbiter_status.setText("仲裁状态: REMOTE")
        self.lbl_arbiter_status.setStyleSheet("color: #00cc66;")

        self.append_message("安全", "✅ 急停已解除，恢复手动遥控模式")
        self.status_bar.showMessage("急停已解除", 3000)

    def on_mode_toggle(self, checked: bool):
        """模式切换：手动 ↔ 自主"""
        if self.estop_active:
            self.append_message("仲裁", "⚠ 急停状态下无法切换模式")
            self.toggle_mode.setChecked(False)
            return

        if checked:
            self.autonomy_mode_active = True
            self.toggle_mode.setText("自主授权 AUTONOMY")
            self.lbl_arbiter_status.setText("仲裁状态: 请求自主...")
            self.lbl_arbiter_status.setStyleSheet("color: #ffcc00;")
            self.append_message("仲裁", "切换至自主模式，等待 Jetson 确认")

            # 发送自主请求包 (mode=0xEE)
            self.send_autonomy_heartbeat()
        else:
            self.autonomy_mode_active = False
            self.toggle_mode.setText("手动遥控 MANUAL")
            self.lbl_arbiter_status.setText("仲裁状态: REMOTE")
            self.lbl_arbiter_status.setStyleSheet("color: #00cc66;")
            self.clear_autonomy_hold(reason="手动模式切换", send_override=True)
            self.append_message("仲裁", "切换至手动遥控模式")

    def send_mission_command(self):
        """下发语义任务指令"""
        if not self.autonomy_mode_active:
            self.append_message("任务", "⚠ 请先切换至自主模式")
            self.status_bar.showMessage("请先切换至自主模式", 2000)
            return

        mission_json = {
            "control_mode_byte": 0xEE,
            "work_instruction": 0x01,  # TASK_START
            "mission": self.combo_mission_type.currentText(),
            "search_depth": self.spin_target_depth.value(),
            "track_distance": self.spin_track_distance.value(),
            "timeout_s": self.spin_task_timeout.value(),
            "ts": time.time(),
            "thrust": 0.0,
            "left": 0.0,
            "right": 0.0,
        }

        # 通过 Zenoh 发布任务
        success = self._publish_json_to_zenoh(mission_json)
        if success:
            self.append_message("任务", f"已下发任务: {mission_json['mission']}")
            self.status_bar.showMessage(f"任务已下发: {mission_json['mission']}", 3000)
        else:
            self.append_message("任务", "⚠ Zenoh 链路未连接，任务下发失败")
            self.status_bar.showMessage("Zenoh 未连接", 3000)

    def toggle_zenoh_connection(self):
        """切换 Zenoh 连接状态"""
        if self.comm_manager.is_side_channel_active():
            # 断开连接
            self.comm_manager.set_side_channel_active(False)
            self.lbl_zenoh_status.setText("状态: 未连接")
            self.lbl_zenoh_status.setStyleSheet("color: #ff4444;")
            self.btn_zenoh_connect.setText("连接 Zenoh")
            self.append_message("链路", "Zenoh 连接已断开")
        else:
            # 连接 Zenoh Router
            ip = self.edit_zenoh_ip.text().strip() or "127.0.0.1"
            self.zenoh_router_ip = ip
            try:
                # 尝试通过 side channel 连接到指定 IP
                self.comm_manager.connect_zenoh_to_ip(ip)
                self.lbl_zenoh_status.setText(f"状态: 已连接 ({ip})")
                self.lbl_zenoh_status.setStyleSheet("color: #00cc66;")
                self.btn_zenoh_connect.setText("断开 Zenoh")
                self.append_message("链路", f"Zenoh 已连接到 {ip}:7447")
                self.status_bar.showMessage(f"Zenoh 已连接到 {ip}", 3000)
            except Exception as exc:
                self.append_message("链路", f"Zenoh 连接失败: {exc}")
                self.status_bar.showMessage(f"Zenoh 连接失败: {exc}", 5000)

    def send_autonomy_heartbeat(self):
        """自主模式下发送心跳到 rt/pc/cmd_raw"""
        if not self.comm_manager.is_side_channel_active():
            return

        heartbeat = {
            "control_mode_byte": 0xEE,
            "work_instruction": 0x00,
            "mission": self.combo_mission_type.currentText(),
            "target_depth": self.spin_target_depth.value(),
            "track_distance": self.spin_track_distance.value(),
            "timeout_s": self.spin_task_timeout.value(),
            "ts": time.time(),
            "thrust": 0.0,
            "left": 0.0,
            "right": 0.0,
        }
        self._publish_json_to_zenoh(heartbeat)

    def _publish_json_to_zenoh(self, cmd_dict: dict) -> bool:
        """发布 JSON 命令到 Zenoh rt/pc/cmd_raw topic"""
        try:
            if not self.comm_manager.is_side_channel_active():
                return False
            sc = self.comm_manager.side_channel
            if hasattr(sc, 'publish_json_command'):
                return sc.publish_json_command(cmd_dict)
            elif hasattr(sc, 'publish_pc_cmd_raw'):
                import json
                return sc.publish_pc_cmd_raw(json.dumps(cmd_dict).encode('utf-8'))
            return False
        except Exception as exc:
            self.append_message("链路", f"Zenoh 发布失败: {exc}")
            return False

    def update_arbiter_control_ui(self):
        """Refresh arbiter buttons and hold-state labels from current transport state."""
        hold_autonomy = self.arbiter_control_mode_override == CONTROL_MODE_JETSON_PROTOCOL
        ready, reason = self.can_send_arbiter_action()

        self.btn_request_autonomy.setChecked(hold_autonomy)
        self.labels['arbiter_request'].setText(
            f"请求保持: {'自主接管' if hold_autonomy else '遥控'}"
        )

        self.btn_request_autonomy.setEnabled(ready)
        self.btn_manual_takeover.setEnabled(ready or hold_autonomy)

        tooltip = "可通过 WiFi + Zenoh side channel 发送仲裁控制包" if ready else reason
        self.btn_request_autonomy.setToolTip(tooltip)
        self.btn_manual_takeover.setToolTip(tooltip)

    def update_arbiter_feedback(self, auto_state: str, deny_reason: str):
        """Render deny feedback in a dedicated UI label instead of only using the status bar."""
        normalized_state = auto_state or "--"
        normalized_deny = deny_reason or "NONE"

        if normalized_state == "DENIED" and normalized_deny != "NONE":
            self.labels['arbiter_feedback'].setText(f"拒绝反馈: {normalized_deny}")
            self.labels['arbiter_feedback'].setStyleSheet("color: FireBrick; font-weight: bold;")
            return

        if normalized_state == "ACTIVE":
            self.labels['arbiter_feedback'].setText("拒绝反馈: 已通过")
            self.labels['arbiter_feedback'].setStyleSheet("color: DarkGreen;")
            return

        self.labels['arbiter_feedback'].setText("拒绝反馈: --")
        self.labels['arbiter_feedback'].setStyleSheet("")

    def log_arbiter_state(self, active_arbiter: str, auto_state: str, deny_reason: str):
        """Deduplicate bridge state logs so the message tab highlights only real transitions."""
        signature = (active_arbiter, auto_state, deny_reason)
        if signature == self._last_arbiter_signature:
            return
        self._last_arbiter_signature = signature

        message = f"控制归属={active_arbiter}，自主状态={auto_state}"
        if deny_reason and deny_reason != "NONE":
            message += f"，拒绝原因={deny_reason}"
        self.append_message("桥侧", message)

    def append_message(self, category: str, message: str):
        """Append a timestamped message into the operator-facing message tab."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.message_log.append(f"[{timestamp}] [{category}] {message}")

    def closeEvent(self, event):
        """Handle window close"""
        self.comm_manager.cleanup()
        event.accept()
