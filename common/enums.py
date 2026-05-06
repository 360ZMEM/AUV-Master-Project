"""Shared enums for behavior and fault states."""

from __future__ import annotations

from enum import Enum, IntEnum


class BehaviorMode(str, Enum):
    """统一行为模式标签，用于行为树、控制链路和可视化界面之间传递高层任务语义。

    该枚举不承载算法细节，只定义系统对外暴露的稳定状态名，便于 ROS2、
    仿真桥接和调试工具共享同一套行为标识。
    """

    IDLE = "IDLE"
    DIVING = "DIVING"
    ZIGZAG_SEARCH = "ZIGZAG_SEARCH"
    PARALLEL_TRACK = "PARALLEL_TRACK"
    EMERGENCY_SURFACE = "EMERGENCY_SURFACE"
    STABILIZE_HOLD = "STABILIZE_HOLD"
    ANALYTICAL_PATH = "ANALYTICAL_PATH"


class BridgeBackend(str, Enum):
    """桥接后端类型标签，用于选择 Zenoh JSON 或协议 UDP 等通信实现。

    该枚举的作用是把“如何传输数据”从业务逻辑中剥离出来，避免控制和感知模块
    直接依赖具体传输协议。
    """

    ZENOH_JSON = "zenoh_json"
    PROTOCOL_UDP = "protocol_udp"


class ControlModeByte(IntEnum):
    """控制模式字节值，映射底层二进制协议中的控制权限状态。

    这些值用于仿真、桥接和实物协议之间保持一致的控制模式约定，例如遥控、
    自动定点、自动定向以及返航等状态。

    对应协议的第7字节
    """

    SEND_ONLY = 0x00
    REMOTE_CONTROL = 0x01
    AUTO_FIXED_POINT = 0x02
    AUTO_DIRECTION = 0x03
    RETURN_HOME = 0x04
    JETSON_PROTOCOL = 0xEE
    JETSON_HYBRID = 0xEF


class WorkInstruction(IntEnum):
    """工作指令字节值，用于桥接或仲裁器在二进制协议中表达操作命令。

    这组枚举用于表达“开始任务”“切换模式”“进入保持”等较高层的控制意图，
    适合跨进程、跨语言传输。

    对应协议的第22字节
    """

    NONE = 0x00
    TASK_START = 0x01
    TASK_CANCEL = 0x02
    MAIN_THRUSTER_ON = 0x11
    MAIN_THRUSTER_OFF = 0x12
    SIDE_THRUSTER_ON = 0x13
    SIDE_THRUSTER_OFF = 0x14
    HORIZONTAL_RUDDER_ON = 0x15
    HORIZONTAL_RUDDER_OFF = 0x16
    VERTICAL_RUDDER_ON = 0x17
    VERTICAL_RUDDER_OFF = 0x18
    DVL_ON = 0x21
    DVL_OFF = 0x22
    COMPASS_ON = 0x23
    COMPASS_OFF = 0x24
    DIRECTIONAL_NAV_ON = 0x71
    DIRECTIONAL_NAV_OFF = 0x72
    CLEAR_FAULT = 0x91
    INITIALIZE = 0x92
    AUTONOMOUS_CONTROL = 0xEE # 新增
    HOLD_DEBUG = 0xA1
    ANALYTICAL_PATH_DEBUG = 0xA2


class AutoState(str, Enum):
    """Autonomy handshake states shared by bridge, UI, and safety logic."""

    LOCKED = "LOCKED"
    REQUESTING = "REQUESTING"
    ACTIVE = "ACTIVE"
    DENIED = "DENIED"


class ArbiterMode(str, Enum):
    """Effective control owner after arbitration."""

    REMOTE = "REMOTE"
    AUTONOMOUS = "AUTONOMOUS"


class ArbiterSource(str, Enum):
    """Source that produced the active command output."""

    NONE = "NONE"
    PC_RAW = "PC_RAW"
    JETSON_MPC = "JETSON_MPC"
    SAFETY_FALLBACK = "SAFETY_FALLBACK"


class StateEstimateSource(str, Enum):
    """State estimate source selected by control and analysis tooling."""

    FILTERED = "FILTERED"
    RAW_DR = "RAW_DR"


class DenyReason(str, Enum):
    """Reasons that block or revoke autonomous takeover."""

    NONE = "NONE"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"
    LEAK_DETECTED = "LEAK_DETECTED"
    LOW_VOLTAGE = "LOW_VOLTAGE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    AMD_UPLINK_STALE = "AMD_UPLINK_STALE"
    MPC_HEARTBEAT_TIMEOUT = "MPC_HEARTBEAT_TIMEOUT"
    COMM_LINK_FAILURE = "COMM_LINK_FAILURE"
    UNKNOWN = "UNKNOWN"


class DebugLevel(str, Enum):
    """Algorithm transparency level for decision stack debugging."""

    AUTO = "AUTO"
    HOLD = "HOLD"
    PATH = "PATH"
    FULL = "FULL"


class FaultCode(str, Enum):
    """High-level fault classification for cross-module checks."""

    LEAK_DETECTED = "LEAK_DETECTED"
    LOW_VOLTAGE = "LOW_VOLTAGE"


class LeakLevel(IntEnum):
    """Leak levels aligned with current ROS2 SensorStatus conventions."""

    NONE = 0
    INTERNAL = 1
    EXTERNAL = 2
    BOTH = 3
