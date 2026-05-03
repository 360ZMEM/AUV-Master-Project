"""
AUV 通信协议常量定义
====================

本模块定义了 AUV 通信协议的所有常量，包括：
- 帧头和帧尾
- 数据包大小
- 通信模式
- 工作模式
- 工作指令命令

C# 源码参考：Form1.cs
"""

# ========== 帧头和帧尾 ==========

# 发送数据包帧头: $CKTH (Console to AUV Header)
FRAME_HEADER_SEND = bytes([0x24, 0x43, 0x4B, 0x54, 0x48])

# 接收数据包帧头: $AUV▒ (AUV Telemetry Header)
FRAME_HEADER_RECV = bytes([0x24, 0x41, 0x55, 0x56, 0x91])

# 北斗数据包帧头: $CKT"
FRAME_HEADER_BEIDOU = bytes([0x24, 0x43, 0x4B, 0x54, 0x22])

# 帧尾: 0xFF 0xFF
FRAME_TRAILER = bytes([0xFF, 0xFF])

# ========== 数据包大小 ==========

# 发送数据包大小（字节）
SEND_PACKET_SIZE = 72

# 接收数据包大小（字节）
RECV_PACKET_SIZE = 145

# 北斗数据包大小（字节）
BEIDOU_PACKET_SIZE = 34

# ========== 通信模式 ==========

COMM_MODE_RADIO = 1   # 无线电串口模式
COMM_MODE_WIFI = 2    # WiFi UDP 模式（默认）
COMM_MODE_BEIDOU = 3  # 北斗卫星模式

# ========== 工作模式 ==========

WORK_MODE_SEND_ONLY = 0x00          # 仅发送模式
WORK_MODE_REMOTE_CONTROL = 0x01     # 遥控模式
WORK_MODE_AUTO_FIXED_POINT = 0x02   # 自主定点模式
WORK_MODE_AUTO_DIRECTION = 0x03     # 自主定向模式
WORK_MODE_RETURN = 0x04             # 回航模式
CONTROL_MODE_JETSON_PROTOCOL = 0xEE  # Linux bridge 仲裁请求模式

# ========== 工作指令命令 ==========

# 基本任务指令 (0x01-0x02)
CMD_TASK_START = 0x01       # 任务开启
CMD_TASK_CANCEL = 0x02      # 任务取消

# 系统控制指令 (0x91-0x94)
CMD_CLEAR_FAULT = 0x91      # 清除故障
CMD_INITIALIZE = 0x92       # 初始化
CMD_SPARE_1 = 0x93          # 备用指令1
CMD_SPARE_2 = 0x94          # 备用指令2

# ========== 设备电源指令 (0x11-0x28) ==========

# 主推进器
CMD_MAIN_THRUSTER_ON = 0x11     # 主推上电
CMD_MAIN_THRUSTER_OFF = 0x12    # 主推断电

# 侧推进器
CMD_SIDE_THRUSTER_ON = 0x13     # 侧推上电
CMD_SIDE_THRUSTER_OFF = 0x14    # 侧推断电

# 水平舵机
CMD_HORIZONTAL_RUDDER_ON = 0x15     # 水平舵机上电
CMD_HORIZONTAL_RUDDER_OFF = 0x16    # 水平舵机断电

# 垂直舵机
CMD_VERTICAL_RUDDER_ON = 0x17       # 垂直舵机上电
CMD_VERTICAL_RUDDER_OFF = 0x18      # 垂直舵机断电

# 应急压载
CMD_EMERGENCY_BALLAST_ON = 0x19     # 应急压载上电
CMD_EMERGENCY_BALLAST_OFF = 0x20    # 应急压载断电

# DVL 和罗经
CMD_DVL_ON = 0x21          # DVL 上电
CMD_DVL_OFF = 0x22         # DVL 断电
CMD_COMPASS_ON = 0x23      # 罗经上电
CMD_COMPASS_OFF = 0x24     # 罗经断电

# 备用设备
CMD_SPARE1_ON = 0x25       # 备用设备1上电
CMD_SPARE1_OFF = 0x26      # 备用设备1断电
CMD_SPARE2_ON = 0x27       # 备用设备2上电
CMD_SPARE2_OFF = 0x28      # 备用设备2断电

# ========== 测试指令 (0x41-0x42) ==========

CMD_DIVE_TEST = 0x41       # 下潜测试
CMD_SPARE_TEST = 0x42      # 备用测试

# ========== 参数调整指令 (0x51-0x54) ==========

CMD_PARAM_ADJUST_ON = 0x51     # 参数调整开启
CMD_PARAM_ADJUST_OFF = 0x52    # 参数调整关闭
CMD_SPARE_ADJUST_ON = 0x53     # 备用调整开启
CMD_SPARE_ADJUST_OFF = 0x54    # 备用调整关闭

# ========== 查询指令 (0x61-0x62) ==========

CMD_QUERY_1 = 0x61          # 查询指令1
CMD_QUERY_2 = 0x62          # 查询指令2

# ========== 航行控制指令 (0x71-0x74) ==========

CMD_DIRECTIONAL_NAV_ON = 0x71   # 定向航行开启
CMD_DIRECTIONAL_NAV_OFF = 0x72  # 定向航行关闭
CMD_NAV_SPARE_ON = 0x73         # 航行备用开启
CMD_NAV_SPARE_OFF = 0x74        # 航行备用关闭

# ========== 载荷指令 (0x81-0x83) ==========

CMD_PAYLOAD_1 = 0x81        # 载荷指令1
CMD_PAYLOAD_2 = 0x82        # 载荷指令2
CMD_PAYLOAD_3 = 0x83        # 载荷指令3

# ========== 北斗卫星通信 ==========

# 北斗目标地址 (用户机地址)
BEIDOU_DEST_ADDRESS = (0x09, 0x89, 0x56, 0x64)  # 0989564

# ========== 工作模式名称映射 ==========

WORK_MODE_NAMES = {
    0x00: "仅发送模式",
    0x01: "遥控模式",
    0x02: "自主定点航行",
    0x03: "自主定向航行",
    0x04: "回航模式",
    0xEE: "Jetson仲裁模式",
}
