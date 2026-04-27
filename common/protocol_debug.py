"""AUV 协议调试格式化助手 - 用于 CLI 工具和 Mock AMD 日志的包展示。

本模块提供了将二进制协议包（$CKTH 下行、$AUV 上行）格式化为人类可读形式的函数。
用途：
  1. 实时包监控：在 sniffer.py 中展示网络通信的协议包
  2. 日志记录：生成可查询的 CSV 和 ASCII 格式的包日志
  3. 调试与诊断：快速识别包格式错误和校验和问题
  4. 性能分析：提供紧凑的单行摘要便于统计分析

设计特点：
  • 支持多种输出格式（原始、ASCII 块、单行摘要）
  • ANSI 颜色支持（自动检测终端能力）
  • 机器友好的 CSV 格式（便于离线分析）
  • 校验和和帧尾验证（自动检测格式错误）

典型使用流程：
  1. 通过 detect_protocol_direction() 判断包类型
  2. 调用 parse_downlink_packet() 或 parse_uplink_packet() 解码
  3. 选择合适的格式化函数输出（raw/ascii/compact）

"""

from __future__ import annotations

import os
from datetime import datetime
import sys
import time

from .enums import ControlModeByte, WorkInstruction
from .protocol import (
    DEFAULT_MAIN_MOTOR_RPM_SCALE, # 主推进器 RPM 转换系数，用于将协议中的 RPM 值转换为实际转速
    PROTOCOL_DOWNLINK_CHECKSUM_INDEX,
    PROTOCOL_DOWNLINK_HEADER,
    PROTOCOL_DOWNLINK_SIZE,
    PROTOCOL_UPLINK_HEADER,
    PROTOCOL_UPLINK_CHECKSUM_INDEX,
    PROTOCOL_UPLINK_SIZE,
    PROTOCOL_FRAME_TAIL,
    downlink_state_to_payload,
    parse_downlink_packet,
    parse_uplink_packet,
)

_ANSI = {
    "cyan": "\033[36m",  # 青色 - 下行包通常用青色
    "green": "\033[32m",  # 绿色 - 上行包（遥测）通常用绿色
    "yellow": "\033[33m",  # 黄色 - 未知或错误包用黄色
    "red": "\033[31m",  # 红色 - 解析错误时用红色
    "reset": "\033[0m",  # 重置格式
}
"""ANSI 颜色代码映射 - 用于终端输出的视觉区分"""


def supports_color(stream=None) -> bool:
    """
    @brief 检查给定的流是否支持 ANSI 颜色代码
    
    @param [in] stream 输出流（默认为 sys.stdout）
    
    @return bool，True 表示支持颜色，False 表示不支持或禁用
    
    @details
    判断逻辑：
      1. 检查 NO_COLOR 环境变量（若存在则禁用颜色）
      2. 检查流是否为 TTY（交互式终端）
    
    此函数用于在输出时自动适应终端能力，避免在管道/文件重定向时
    混入 ANSI 控制字符。
    """
    target = sys.stdout if stream is None else stream
    if os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(target, "isatty", lambda: False)())


def colorize(text: str, color: str, *, enabled: bool) -> str:
    """
    @brief 条件化为文本添加 ANSI 颜色代码
    
    @param [in] text 待着色的文本
    @param [in] color 颜色名称 (cyan/green/yellow/red中的一种)
    @param [in] enabled 是否启用着色
    
    @return str，如果启用且支持，返回着色的文本；否则返回原文本
    
    @details
    着色规则：
      1. 若 enabled=False 或颜色不支持，直接返回原文本
      2. 若颜色代码有效，包装为 {ansi_code}{text}{reset_code}
    
    此函数用于日志输出中的视觉区分，避免过度着色和兼容性问题。
    """
    if not enabled or color not in _ANSI:
        return text
    return f"{_ANSI[color]}{text}{_ANSI['reset']}"


def detect_protocol_direction(packet: bytes) -> str:
    """
    @brief 根据帧头识别协议包的方向（下行、上行或未知）
    
    @param [in] packet 原始数据包字节序列
    
    @return str，"downlink" / "uplink" / "unknown" 之一
    
    @details
    分类规则（按优先级）：
      1. 若帧头为 "$CKTH"（5 字节）→ 返回 "downlink"（PC → AUV 控制命令）
      2. 若帧头为 "$AUV\\x91"（5 字节）→ 返回 "uplink"（AUV → PC 遥测）
      3. 其他情况 → 返回 "unknown"（格式不支持）
    
    此函数是协议包处理的第一步，用于分发到不同的解析器。
    """
    if bytes(packet[: len(PROTOCOL_DOWNLINK_HEADER)]) == PROTOCOL_DOWNLINK_HEADER:
        return "downlink"
    if bytes(packet[: len(PROTOCOL_UPLINK_HEADER)]) == PROTOCOL_UPLINK_HEADER:
        return "uplink"
    return "unknown"


def hex_preview(packet: bytes, *, max_bytes: int = 48) -> str:
    """
    @brief 生成适合单行日志的十六进制预览
    
    @param [in] packet 数据包字节序列
    @param [in] max_bytes 最多显示的字节数（默认 48）
    
    @return str，十六进制预览（带空格分隔，若被截断则末尾加" ..."）
    
    @details
    输出格式示例：
      • "01 02 03 04 05" - 完整显示（少于 max_bytes）
      • "01 02 03 ... " - 被截断（超过 max_bytes）
    
    用途：在日志尾部快速显示包内容，便于验证包格式。
    """
    clipped = packet[: max(1, int(max_bytes))]
    preview = clipped.hex(" ")
    if len(packet) > len(clipped):
        return f"{preview} ..."
    return preview


def _enum_label(enum_cls, value: int) -> str:
    try:
        return enum_cls(value).name
    except Exception:
        return f"0x{int(value) & 0xFF:02X}"


def _control_mode_label(value: int) -> str:
    try:
        mode = ControlModeByte(value)
    except Exception:
        return f"UNKNOWN (0x{int(value) & 0xFF:02X})"

    labels = {
        ControlModeByte.SEND_ONLY: "SEND_ONLY (仅发送)",
        ControlModeByte.REMOTE_CONTROL: "REMOTE_CONTROL (遥控)",
        ControlModeByte.AUTO_FIXED_POINT: "AUTO_FIXED_POINT (定点)",
        ControlModeByte.AUTO_DIRECTION: "AUTO_DIRECTION (定向)",
        ControlModeByte.RETURN_HOME: "RETURN_HOME (回航)",
        ControlModeByte.JETSON_PROTOCOL: "AUTONOMOUS (自主模式)",
    }
    return labels.get(mode, f"UNKNOWN (0x{int(value) & 0xFF:02X})")


def _work_instruction_label(value: int) -> str:
    try:
        instruction = WorkInstruction(value)
    except Exception:
        return f"0x{int(value) & 0xFF:02X}"
    return instruction.name


def _checksum_status(packet: bytes, checksum_index: int) -> tuple[bool, int, int]:
    expected = sum(packet[:checksum_index]) & 0xFF
    actual = int(packet[checksum_index]) if checksum_index < len(packet) else -1
    return expected == actual, expected, actual


def _tail_status(packet: bytes) -> tuple[bool, bytes, bytes]:
    expected = PROTOCOL_FRAME_TAIL
    actual = bytes(packet[-2:]) if len(packet) >= 2 else b""
    return actual == expected, expected, actual


def _format_timestamp(include_timestamp: bool) -> str | None:
    if not include_timestamp:
        return None
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _format_block(title: str, lines: list[str]) -> str:
    body = ["=" * 50, title, "-" * 50]
    body.extend(lines)
    body.append("=" * 50)
    return "\n".join(body)


def format_protocol_packet_raw(
    packet: bytes,
    *,
    label: str = "protocol",
    source: str | None = None,
    color: bool = True,
    include_hex: bool = False,
    max_hex_bytes: int = 48,
    main_motor_rpm_scale: float = DEFAULT_MAIN_MOTOR_RPM_SCALE,
) -> str:
    """
    @brief 将协议包格式化为紧凑的 CSV 风格单行输出
    
    @param [in] packet 原始数据包
    @param [in] label 日志标签（例如 "sim", "real"）
    @param [in] source 来源标识（例如 "localhost:7447"）
    @param [in] color 是否启用着色（此格式中着色有限）
    @param [in] include_hex 是否在末尾附加十六进制预览
    @param [in] max_hex_bytes 十六进制预览的最大字节数
    @param [in] main_motor_rpm_scale RPM 转换系数
    
    @return str，CSV 格式的单行字符串
    
    @details
    输出格式（机器友好）：
      • 下行包 ($CKTH):
        $CKTH,frame_num,obj_addr,mode_byte,instr,right,top,left,bottom,thrust,main_rpm,side_rpm,heading
      
      • 上行包 ($AUV):
        $AUV,frame_num,auv_addr,mode_byte,instr,depth,heading,pitch,roll,lon,lat,voltage,current,main_rpm,right,top,left,bottom
      
      • 未知包:
        UNKNOWN,len_bytes
    
    用途：离线数据分析、Excel 导入、脚本处理。
    """
    direction = detect_protocol_direction(packet)

    if direction == "downlink":
        state = parse_downlink_packet(packet, main_motor_rpm_scale=main_motor_rpm_scale)
        values = [
            "$CKTH",
            str(state.frame_number),
            str(state.obj_address),
            str(state.control_mode_byte),
            str(state.work_instruction),
            f"{state.right_fin_deg:.1f}",
            f"{state.top_fin_deg:.1f}",
            f"{state.left_fin_deg:.1f}",
            f"{state.bottom_fin_deg:.1f}",
            f"{state.thrust_percent:.1f}",
            str(state.main_motor_rpm),
            str(state.side_motor_rpm),
            f"{state.orientation_deg:.1f}",
        ]
    elif direction == "uplink":
        telemetry = parse_uplink_packet(packet)
        values = [
            "$AUV",
            str(telemetry.frame_number),
            str(telemetry.auv_address),
            str(telemetry.control_mode_byte),
            str(telemetry.work_instruction),
            f"{telemetry.depth_m:.2f}",
            f"{telemetry.heading_deg:.1f}",
            f"{telemetry.pitch_deg:.1f}",
            f"{telemetry.roll_deg:.1f}",
            f"{telemetry.gps_lon_deg:.6f}",
            f"{telemetry.gps_lat_deg:.6f}",
            f"{telemetry.total_voltage_v:.1f}",
            f"{telemetry.total_current_a:.1f}",
            str(telemetry.main_motor_rpm),
            f"{telemetry.right_fin_deg:.1f}",
            f"{telemetry.top_fin_deg:.1f}",
            f"{telemetry.left_fin_deg:.1f}",
            f"{telemetry.bottom_fin_deg:.1f}",
        ]
    else:
        values = ["UNKNOWN", str(len(packet))]

    line = ",".join(values)
    if include_hex:
        line = f"{line} hex={hex_preview(packet, max_bytes=max_hex_bytes)}"
    return line


def format_protocol_packet_ascii(
    packet: bytes,
    *,
    label: str = "protocol",
    source: str | None = None,
    include_timestamp: bool = True,
    color: bool = True,
    main_motor_rpm_scale: float = DEFAULT_MAIN_MOTOR_RPM_SCALE,
) -> str:
    """
    @brief 将协议包格式化为详细的多行诊断块（ASCII 格式）
    
    @param [in] packet 原始数据包
    @param [in] label 日志标签
    @param [in] source 来源标识
    @param [in] include_timestamp 是否包含时间戳
    @param [in] color 是否启用着色
    @param [in] main_motor_rpm_scale RPM 转换系数
    
    @return str，格式化的多行 ASCII 块
    
    @details
    输出结构（易于人工阅读）：
      • 帧头信息：序号、地址、模式、指令
      • 控制/遥测数据：按功能分组（舵叶、推进、姿态等）
      • 帧完整性检查：校验和与帧尾验证结果
    
    示例输出（下行包）：
      ==================================================
      ASCII PROTOCOL PACKET - DOWNLINK ($CKTH)
      --------------------------------------------------
      Timestamp: 2026-04-27 15:30:45.123
      Label: sim
      Source: localhost
      
      HEADER INFO:
        Frame Number: 42
        ...
      ==================================================
    
    用途：实时监控、问题调试、协议规范验证。
    """
    direction = detect_protocol_direction(packet)
    timestamp = _format_timestamp(include_timestamp)
    lines: list[str] = []

    if timestamp is not None:
        lines.append(f"Timestamp: {timestamp}")
    if label:
        lines.append(f"Label: {label}")
    if source:
        lines.append(f"Source: {source}")

    if direction == "downlink":
        state = parse_downlink_packet(packet, main_motor_rpm_scale=main_motor_rpm_scale)
        checksum_ok, checksum_expected, checksum_actual = _checksum_status(packet, PROTOCOL_DOWNLINK_CHECKSUM_INDEX)
        tail_ok, tail_expected, tail_actual = _tail_status(packet)

        lines.extend([
            "",
            "HEADER INFO:",
            f"  Frame Number: {state.frame_number}",
            f"  Object Address: {state.obj_address}",
            f"  Control Mode Byte: 0x{state.control_mode_byte:02X}",
            f"    -> {_control_mode_label(state.control_mode_byte)}",
            f"  Work Instruction: 0x{state.work_instruction:02X}",
            f"    -> {_work_instruction_label(state.work_instruction)}",
            "",
            "CONTROL SURFACES:",
            f"  Right Fin:   {state.right_fin_deg:+.1f} deg",
            f"  Top Fin:     {state.top_fin_deg:+.1f} deg",
            f"  Left Fin:    {state.left_fin_deg:+.1f} deg",
            f"  Bottom Fin:  {state.bottom_fin_deg:+.1f} deg",
            f"  Thrust:      {state.thrust_percent:+.1f} %",
            "",
            "MOTORS:",
            f"  Main Motor:  {state.main_motor_rpm:>5d} RPM",
            f"  Side Motor:  {state.side_motor_rpm:>5d} RPM",
            "",
            "NAVIGATION:",
            f"  Target Heading: {state.orientation_deg:+6.1f} deg",
            "",
            "FRAME INTEGRITY:",
            f"  Checksum: {'OK' if checksum_ok else 'BAD'}",
            f"    Expected: 0x{checksum_expected:02X}",
            f"    Actual:   0x{checksum_actual:02X}",
            f"  Frame Tail: {'OK' if tail_ok else 'BAD'}",
            f"    Expected: 0x{tail_expected.hex().upper()}",
            f"    Actual:   0x{tail_actual.hex().upper()}",
        ])
        title = "ASCII PROTOCOL PACKET - DOWNLINK ($CKTH)"

    elif direction == "uplink":
        telemetry = parse_uplink_packet(packet)
        checksum_ok, checksum_expected, checksum_actual = _checksum_status(packet, PROTOCOL_UPLINK_CHECKSUM_INDEX)
        tail_ok, tail_expected, tail_actual = _tail_status(packet)

        lines.extend([
            "",
            "HEADER INFO:",
            f"  Frame Number: {telemetry.frame_number}",
            f"  AUV Address: {telemetry.auv_address}",
            f"  Control Mode Byte: 0x{telemetry.control_mode_byte:02X}",
            f"    -> {_control_mode_label(telemetry.control_mode_byte)}",
            f"  Work Instruction: 0x{telemetry.work_instruction:02X}",
            f"    -> {_work_instruction_label(telemetry.work_instruction)}",
            "",
            "TELEMETRY:",
            f"  Depth:        {telemetry.depth_m:.2f} m",
            f"  Heading:      {telemetry.heading_deg:+6.1f} deg",
            f"  Pitch:        {telemetry.pitch_deg:+6.1f} deg",
            f"  Roll:         {telemetry.roll_deg:+6.1f} deg",
            f"  GPS Lon:      {telemetry.gps_lon_deg:.6f}",
            f"  GPS Lat:      {telemetry.gps_lat_deg:.6f}",
            f"  Voltage:      {telemetry.total_voltage_v:.1f} V",
            f"  Current:      {telemetry.total_current_a:.1f} A",
            f"  Main Motor:   {telemetry.main_motor_rpm:>5d} RPM",
            f"  Side Motor:   {telemetry.side_motor_rpm:>5d} RPM",
            "",
            "CONTROL REPLAY:",
            f"  Right Fin:    {telemetry.right_fin_deg:+.1f} deg",
            f"  Top Fin:      {telemetry.top_fin_deg:+.1f} deg",
            f"  Left Fin:     {telemetry.left_fin_deg:+.1f} deg",
            f"  Bottom Fin:   {telemetry.bottom_fin_deg:+.1f} deg",
            "",
            "FRAME INTEGRITY:",
            f"  Checksum: {'OK' if checksum_ok else 'BAD'}",
            f"    Expected: 0x{checksum_expected:02X}",
            f"    Actual:   0x{checksum_actual:02X}",
            f"  Frame Tail: {'OK' if tail_ok else 'BAD'}",
            f"    Expected: 0x{tail_expected.hex().upper()}",
            f"    Actual:   0x{tail_actual.hex().upper()}",
        ])
        title = "ASCII PROTOCOL PACKET - UPLINK ($AUV)"

    else:
        title = "ASCII PROTOCOL PACKET - UNKNOWN"
        lines.extend([
            "",
            f"Packet Length: {len(packet)} bytes",
            f"Header: {hex_preview(packet, max_bytes=min(len(packet), 16))}",
            "",
            "FRAME INTEGRITY:",
            f"  Bytes: {len(packet)}",
        ])

    if not color:
        return _format_block(title, lines)

    # ASCII logs are kept plain-text so they remain easy to diff and grep.
    return _format_block(title, lines)


def summarize_downlink_packet(packet: bytes, *, main_motor_rpm_scale: float = DEFAULT_MAIN_MOTOR_RPM_SCALE) -> str:
    """
    @brief 为下行 ($CKTH) 包生成紧凑的单行摘要
    
    @param [in] packet 原始数据包（72 字节）
    @param [in] main_motor_rpm_scale RPM 转换系数
    
    @return str，格式为 "frame=X obj=X mode=0xXX instr=0xXX cmd=(r,t,l,b,thrust) ..."
    
    @details
    输出示例：
      frame=42 obj=1 mode=0xEE instr=0x01 cmd=(5.0,10.0,-5.0,-10.0,50.0) \
      main_rpm=750 side_rpm=100 heading=45.0deg
    
    用途：快速定位包的关键信息，便于日志过滤和问题追踪。
    """
    state = parse_downlink_packet(packet, main_motor_rpm_scale=main_motor_rpm_scale)
    payload = downlink_state_to_payload(state)
    return (
        f"frame={payload['frame_number']} obj={payload['obj_address']} "
        f"mode=0x{payload['control_mode_byte']:02X} instr=0x{payload['work_instruction']:02X} "
        f"cmd=({payload['right']:.1f},{payload['top']:.1f},{payload['left']:.1f},"
        f"{payload['bottom']:.1f},{payload['thrust']:.1f}) "
        f"main_rpm={payload['main_motor_rpm']} side_rpm={payload['side_motor_rpm']} "
        f"heading={payload['orientation_deg']:.1f}deg"
    )


def summarize_uplink_packet(packet: bytes) -> str:
    """
    @brief 为上行 ($AUV) 包生成紧凑的单行摘要
    
    @param [in] packet 原始数据包（145 字节）
    
    @return str，格式为 "frame=X auv=X mode=0xXX instr=0xXX depth=X.XXm heading=X.Xdeg ..."
    
    @details
    输出示例：
      frame=42 auv=1 mode=0x01 instr=0x00 depth=12.50m heading=45.0deg \
      gps=(139.123456,35.654321) voltage=48.0V cmd=(5.0,10.0,-5.0,-10.0,750)
    
    用途：快速验证 AUV 状态，便于实时监控和性能分析。
    """
    telemetry = parse_uplink_packet(packet)
    return (
        f"frame={telemetry.frame_number} auv={telemetry.auv_address} "
        f"mode=0x{telemetry.control_mode_byte:02X} instr=0x{telemetry.work_instruction:02X} "
        f"depth={telemetry.depth_m:.2f}m heading={telemetry.heading_deg:.1f}deg "
        f"gps=({telemetry.gps_lon_deg:.6f},{telemetry.gps_lat_deg:.6f}) "
        f"voltage={telemetry.total_voltage_v:.1f}V "
        f"cmd=({telemetry.right_fin_deg:.1f},{telemetry.top_fin_deg:.1f},"
        f"{telemetry.left_fin_deg:.1f},{telemetry.bottom_fin_deg:.1f},"
        f"{telemetry.main_motor_rpm})"
    )


def format_protocol_packet(
    packet: bytes,
    *,
    label: str = "protocol",
    source: str | None = None,
    color: bool = True,
    include_hex: bool = False,
    max_hex_bytes: int = 48,
    main_motor_rpm_scale: float = DEFAULT_MAIN_MOTOR_RPM_SCALE,
) -> str:
    """
    @brief 将协议包格式化为一致的单行日志视图（推荐用于日志输出）
    
    @param [in] packet 原始数据包
    @param [in] label 日志标签
    @param [in] source 来源标识
    @param [in] color 是否启用 ANSI 着色
    @param [in] include_hex 是否附加十六进制预览
    @param [in] max_hex_bytes 十六进制预览的最大字节数
    @param [in] main_motor_rpm_scale RPM 转换系数
    
    @return str，单行格式化输出
    
    @details
    输出格式（着色 + 摘要）：
      [protocol][CKTH][localhost:7447] frame=42 obj=1 ... hex=24 43 4B ...
    
    着色规则：
      • [tag] 青色：下行包（下行命令）
      • [tag] 绿色：上行包（遥测正常）
      • [tag] 黄色：未知包（格式不支持）
      • [tag] 红色：解析失败
    
    用途：日志轮转、实时监控、问题诊断。这是最常用的格式函数。
    """
    direction = detect_protocol_direction(packet)
    tag_parts = [label]

    if direction == "downlink":
        tag_parts.append("CKTH")
        summary_color = "cyan"
        try:
            summary = summarize_downlink_packet(packet, main_motor_rpm_scale=main_motor_rpm_scale)
        except Exception as exc:
            summary = f"decode_failed={exc}"
            summary_color = "red"
    elif direction == "uplink":
        tag_parts.append("AUV")
        summary_color = "green"
        try:
            summary = summarize_uplink_packet(packet)
        except Exception as exc:
            summary = f"decode_failed={exc}"
            summary_color = "red"
    else:
        tag_parts.append("UNKNOWN")
        summary = f"len={len(packet)} unsupported header"
        summary_color = "yellow"

    if source:
        tag_parts.append(source)

    tag_text = "[" + "][".join(tag_parts) + "]"
    parts = [colorize(tag_text, summary_color, enabled=color and supports_color())]
    parts.append(summary)

    if include_hex:
        parts.append(f"hex={hex_preview(packet, max_bytes=max_hex_bytes)}")

    return " ".join(parts)


__all__ = [
    "colorize",
    "detect_protocol_direction",
    "format_protocol_packet",
    "format_protocol_packet_ascii",
    "format_protocol_packet_raw",
    "hex_preview",
    "supports_color",
    "summarize_downlink_packet",
    "summarize_uplink_packet",
]