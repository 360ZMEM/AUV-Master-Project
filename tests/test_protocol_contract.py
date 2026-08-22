from __future__ import annotations

import math

from common.enums import ArbiterMode, ArbiterSource, AutoState, ControlModeByte, DenyReason, WorkInstruction
from common.protocol import (
    KEY_ACTIVE_ARBITER,
    KEY_ARBITER_SOURCE,
    KEY_AUTO_STATE,
    KEY_BOTTOM,
    KEY_BOTTOM_PROTECT_PARAMS,
    KEY_CONTROL_MODE_BYTE,
    KEY_DENY_REASON,
    KEY_DEPTH_M,
    KEY_DEPTH_PROTECT_PARAMS,
    KEY_FRAME_NUMBER,
    KEY_LEFT,
    KEY_OBJ_ADDRESS,
    KEY_ORIENTATION_DEG,
    KEY_PARAMETERS,
    KEY_PRESET_TIME_TENTHS_MIN,
    KEY_PC104_DOWNLINK_ECHO_FRAME,
    KEY_PC104_DOWNLINK_ECHO_VALID,
    KEY_PC104_DOWNLINK_RECV_UPTIME_MS,
    KEY_PC104_DVL_BI_TIME_VALID,
    KEY_PC104_DVL_BI_UPTIME_MS,
    KEY_PC104_DVL_LOST,
    KEY_PC104_JETSON_TIMEOUT,
    KEY_PC104_SYSTEM_COMM_FAULT,
    KEY_PC104_TIME_VALID,
    KEY_PC104_UPTIME_MS,
    KEY_RIGHT,
    KEY_SIDE_MOTOR_RPM,
    KEY_SPARE_PARAMS,
    KEY_TELEMETRY_FRESHNESS_MS,
    KEY_TARGET_DEPTH_M,
    KEY_THRUST,
    KEY_TOP,
    KEY_WORK_INSTRUCTION,
    KEY_SYS_ABNORM_INFO,
    PROTOCOL_UPLINK_DOWNLINK_ECHO_MARKER,
    PROTOCOL_UPLINK_PC104_TIME_VALID_MARKER,
    PROTOCOL_UPLINK_PARA1_OFFSET,
    PROTOCOL_UPLINK_PARA3_OFFSET,
    PROTOCOL_UPLINK_PARA4_OFFSET,
    PROTOCOL_UPLINK_PARA12_OFFSET,
    PROTOCOL_UPLINK_SPARE1_OFFSET,
    PROTOCOL_UPLINK_SPARE2_OFFSET,
    build_bridge_telemetry_payload,
    build_downlink_packet,
    build_downlink_packet_from_payload,
    build_uplink_packet,
    calculate_byte_sum_checksum,
    decode_pc104_sys_abnorm_info,
    parse_downlink_packet,
    parse_downlink_packet_to_payload,
    parse_uplink_packet,
)


def test_decode_pc104_fault_bits_for_cross_layer_safety() -> None:
    fault_word = (1 << 5) | (1 << 13) | (1 << 14) | (1 << 31)

    decoded = decode_pc104_sys_abnorm_info(fault_word)

    assert decoded[KEY_SYS_ABNORM_INFO] == fault_word
    assert decoded[KEY_PC104_SYSTEM_COMM_FAULT] is True
    assert decoded[KEY_PC104_DVL_LOST] is True
    assert decoded[KEY_PC104_JETSON_TIMEOUT] is True
    assert decode_pc104_sys_abnorm_info(0) == {
        KEY_SYS_ABNORM_INFO: 0,
        KEY_PC104_SYSTEM_COMM_FAULT: False,
        KEY_PC104_DVL_LOST: False,
        KEY_PC104_JETSON_TIMEOUT: False,
    }


def test_downlink_payload_roundtrip_preserves_auxiliary_fields() -> None:
    payload = {
        KEY_FRAME_NUMBER: 9,
        KEY_OBJ_ADDRESS: 3,
        KEY_CONTROL_MODE_BYTE: int(ControlModeByte.REMOTE_CONTROL),
        KEY_WORK_INSTRUCTION: int(WorkInstruction.AUTONOMOUS_CONTROL),
        KEY_RIGHT: 4.5,
        KEY_TOP: -1.5,
        KEY_LEFT: 2.0,
        KEY_BOTTOM: -3.0,
        KEY_THRUST: 12.0,
        KEY_SIDE_MOTOR_RPM: 77,
        KEY_ORIENTATION_DEG: 42.0,
        KEY_DEPTH_PROTECT_PARAMS: (100, 200),
        KEY_BOTTOM_PROTECT_PARAMS: (300, 400),
        KEY_PRESET_TIME_TENTHS_MIN: 50,
        KEY_SPARE_PARAMS: (-11, 22),
        KEY_PARAMETERS: (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12),
    }

    packet = build_downlink_packet_from_payload(payload, main_motor_rpm_scale=10.0)
    decoded = parse_downlink_packet_to_payload(packet, main_motor_rpm_scale=10.0)

    assert decoded[KEY_FRAME_NUMBER] == 9
    assert decoded[KEY_OBJ_ADDRESS] == 3
    assert decoded[KEY_CONTROL_MODE_BYTE] == int(ControlModeByte.REMOTE_CONTROL)
    assert decoded[KEY_WORK_INSTRUCTION] == int(WorkInstruction.AUTONOMOUS_CONTROL)
    assert decoded[KEY_RIGHT] == 4.5
    assert decoded[KEY_TOP] == -1.5
    assert decoded[KEY_LEFT] == 2.0
    assert decoded[KEY_BOTTOM] == -3.0
    assert decoded[KEY_THRUST] == 12.0
    assert decoded[KEY_SIDE_MOTOR_RPM] == 77
    assert decoded[KEY_ORIENTATION_DEG] == 42.0
    assert decoded[KEY_DEPTH_PROTECT_PARAMS] == (100, 200)
    assert decoded[KEY_BOTTOM_PROTECT_PARAMS] == (300, 400)
    assert decoded[KEY_PRESET_TIME_TENTHS_MIN] == 50
    assert decoded[KEY_SPARE_PARAMS] == (-11, 22)
    assert decoded[KEY_PARAMETERS] == (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)


def test_downlink_packet_reads_target_depth_from_payload_dict() -> None:
    payload = {
        KEY_RIGHT: 0.0,
        KEY_TOP: 0.0,
        KEY_LEFT: 0.0,
        KEY_BOTTOM: 0.0,
        KEY_THRUST: 20.0,
        KEY_TARGET_DEPTH_M: 11.8,
    }

    packet = build_downlink_packet(payload, main_motor_rpm_scale=10.0)
    decoded = parse_downlink_packet(packet)

    assert abs(decoded.target_depth_m - 11.8) < 1.0e-9


def test_bridge_telemetry_payload_adds_arbiter_metadata() -> None:
    telemetry = parse_uplink_packet(
        build_uplink_packet(
            frame_counter=7,
            auv_address=2,
            control_mode_byte=int(ControlModeByte.JETSON_PROTOCOL),
            work_instruction=int(WorkInstruction.AUTONOMOUS_CONTROL),
            main_motor_rpm=180,
            side_motor_rpm=21,
            left_fin_deg=12.0,
            right_fin_deg=-23.0,
            top_fin_deg=34.0,
            bottom_fin_deg=-45.0,
            depth_m=8.6,
            heading_deg=91.2,
            pitch_deg=-3.1,
            roll_deg=2.4,
            total_voltage_v=48.7,
            total_current_a=13.2,
            soc=88,
            soh=93,
        )
    )

    payload = build_bridge_telemetry_payload(
        telemetry,
        ts=123.456,
        active_arbiter=ArbiterMode.AUTONOMOUS,
        arbiter_source=ArbiterSource.JETSON_MPC,
        auto_state=AutoState.ACTIVE,
        deny_reason=DenyReason.NONE,
        telemetry_freshness_ms=25.0,
    )

    assert payload[KEY_FRAME_NUMBER] == 7
    assert payload[KEY_CONTROL_MODE_BYTE] == int(ControlModeByte.JETSON_PROTOCOL)
    assert payload[KEY_WORK_INSTRUCTION] == int(WorkInstruction.AUTONOMOUS_CONTROL)
    assert math.isclose(payload[KEY_LEFT], 12.0)
    assert math.isclose(payload[KEY_RIGHT], -23.0)
    assert math.isclose(payload[KEY_TOP], 34.0)
    assert math.isclose(payload[KEY_BOTTOM], -45.0)
    assert math.isclose(payload[KEY_DEPTH_M], 8.6)
    assert payload[KEY_ACTIVE_ARBITER] == ArbiterMode.AUTONOMOUS.value
    assert payload[KEY_ARBITER_SOURCE] == ArbiterSource.JETSON_MPC.value
    assert payload[KEY_AUTO_STATE] == AutoState.ACTIVE.value
    assert payload[KEY_DENY_REASON] == DenyReason.NONE.value
    assert payload[KEY_TELEMETRY_FRESHNESS_MS] == 25.0
    assert payload[KEY_SYS_ABNORM_INFO] == 0
    assert payload[KEY_PC104_SYSTEM_COMM_FAULT] is False
    assert payload[KEY_PC104_DVL_LOST] is False
    assert payload[KEY_PC104_JETSON_TIMEOUT] is False


def _control_payload(right: float, top: float, left: float, bottom: float, thrust: float) -> dict[str, float]:
    return {
        KEY_RIGHT: right,
        KEY_TOP: top,
        KEY_LEFT: left,
        KEY_BOTTOM: bottom,
        KEY_THRUST: thrust,
    }


def test_downlink_endianness() -> None:
    packet = build_downlink_packet(
        _control_payload(right=1.2, top=-2.3, left=3.4, bottom=-4.5, thrust=6.5),
        frame_counter=0x12,
        obj_address=0x34,
        control_mode_byte=0x56,
        work_instruction=0x78,
        orientation_deg=321.4,
        depth_protect_params=(0x0102, 0x0304),
        bottom_protect_params=(0x0506, 0x0708),
        preset_time_tenths_min=0x0910,
        spare_params=(-1234, 2345),
        parameter_values=(0x01020304, -0x01020304, 0x10203040, -0x10203040, 1, -2, 3, -4, 5, -6, 7, -8),
        main_motor_rpm_scale=10.0,
        side_motor_rpm=-222,
    )

    assert len(packet) == 72
    assert packet[0:5] == b"$CKTH"
    assert packet[8:10] == (0x0102).to_bytes(2, "big")
    assert packet[10:12] == (0x0304).to_bytes(2, "big")
    assert packet[12:14] == (0x0506).to_bytes(2, "big")
    assert packet[14:16] == (0x0708).to_bytes(2, "big")
    assert packet[18:20] == (-1234).to_bytes(2, "big", signed=True)
    assert packet[20:22] == (2345).to_bytes(2, "big", signed=True)
    assert packet[23:25] == (65).to_bytes(2, "big", signed=True)
    assert packet[25:27] == (-222).to_bytes(2, "big", signed=True)
    assert packet[27:29] == (34).to_bytes(2, "big", signed=True)
    assert packet[29:31] == (12).to_bytes(2, "big", signed=True)
    assert packet[31:33] == (-23).to_bytes(2, "big", signed=True)
    assert packet[33:35] == (-45).to_bytes(2, "big", signed=True)
    assert packet[35:37] == (3214).to_bytes(2, "big")
    assert packet[37:41] == (0x01020304).to_bytes(4, "big", signed=True)


def test_downlink_scaling() -> None:
    packet = build_downlink_packet(
        _control_payload(right=2.5, top=-1.5, left=1.25, bottom=-0.75, thrust=7.5),
        orientation_deg=123.4,
        parameter_values=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12),
        main_motor_rpm_scale=12.0,
        side_motor_rpm=90,
    )

    assert packet[23:25] == (90).to_bytes(2, "big", signed=True)
    assert packet[27:29] == (12).to_bytes(2, "big", signed=True)
    assert packet[29:31] == (25).to_bytes(2, "big", signed=True)
    assert packet[31:33] == (-15).to_bytes(2, "big", signed=True)
    assert packet[33:35] == (-8).to_bytes(2, "big", signed=True)
    assert packet[35:37] == (1234).to_bytes(2, "big")


def test_downlink_checksum() -> None:
    packets = [
        build_downlink_packet(
            _control_payload(right=0.0, top=0.0, left=0.0, bottom=0.0, thrust=0.0),
            frame_counter=1,
            parameter_values=(0,) * 12,
        ),
        build_downlink_packet(
            _control_payload(right=4.5, top=-4.5, left=3.5, bottom=-3.5, thrust=9.9),
            frame_counter=250,
            orientation_deg=359.9,
            parameter_values=(0x7FFFFFFF, -0x7FFFFFFF, 0x10203040, -0x10203040, 32767, -32768, 1, -1, 2, -2, 3, -3),
            main_motor_rpm_scale=15.0,
            side_motor_rpm=32767,
        ),
    ]

    for packet in packets:
        assert packet[69] == calculate_byte_sum_checksum(packet[:69])
        assert packet[70:72] == b"\xFF\xFF"


def test_uplink_endianness() -> None:
    packet = build_uplink_packet(
        frame_counter=0x21,
        auv_address=0x43,
        control_mode_byte=0x65,
        work_instruction=0x87,
        main_motor_rpm=123,
        side_motor_rpm=-45,
        left_fin_deg=12.0,
        right_fin_deg=-23.0,
        top_fin_deg=34.0,
        bottom_fin_deg=-45.0,
        orientation_deg=87.6,
        depth_m=12.3,
        heading_deg=123.4,
        pitch_deg=-12.3,
        roll_deg=45.6,
        gps_heading_deg=210.3,
        gps_speed_mps=4.5,
        dvl_speed_mps=-3.2,
        altitude_m=6.7,
        dead_reckoning_lon_deg=-123.456789,
        dead_reckoning_lat_deg=31.2304,
        gps_lon_deg=121.4734,
        gps_lat_deg=-31.2304,
        total_voltage_v=48.7,
        total_current_a=13.2,
        soc=88,
        soh=93,
        internal_pressure_psi=9.876,
        internal_temp_c=-6,
        device_power_status=0x01020304,
        operation_feedback=0x05060708,
        task_status=0x090A0B0C,
        system_alarm=0x11,
        depth_alarm=0x22,
        bottom_alarm=0x33,
    )

    assert len(packet) == 145
    assert packet[0:5] == b"$AUV\x91"
    assert packet[35:37] == (9876).to_bytes(2, "big")
    assert packet[27:29] == (12).to_bytes(2, "big", signed=True)
    assert packet[29:31] == (-23).to_bytes(2, "big", signed=True)
    assert packet[31:33] == (34).to_bytes(2, "big", signed=True)
    assert packet[33:35] == (-45).to_bytes(2, "big", signed=True)
    assert packet[72:74] == (1234).to_bytes(2, "big", signed=True)
    assert packet[74:76] == (-123).to_bytes(2, "big", signed=True)
    assert packet[76:78] == (456).to_bytes(2, "big", signed=True)
    assert packet[86:90] == (-123456789).to_bytes(4, "big", signed=True)
    assert packet[90:94] == (31230400).to_bytes(4, "big", signed=True)
    assert packet[102:104] == (487).to_bytes(2, "big")
    assert packet[104:106] == (132).to_bytes(2, "big")
    assert packet[114:118] == (0x01020304).to_bytes(4, "big")
    assert packet[118:122] == (0x05060708).to_bytes(4, "big")
    assert packet[122:126] == (0x090A0B0C).to_bytes(4, "big")
    assert packet[127:130] == bytes((0x11, 0x22, 0x33))


def test_uplink_scaling() -> None:
    packet = build_uplink_packet(
        orientation_deg=98.7,
        internal_pressure_psi=4.321,
        depth_m=5.6,
        heading_deg=180.5,
        pitch_deg=-5.3,
        roll_deg=12.7,
        gps_heading_deg=270.1,
        gps_speed_mps=3.4,
        dvl_speed_mps=1.23,
        altitude_m=2.5,
        dead_reckoning_lon_deg=121.4734,
        dead_reckoning_lat_deg=31.2304,
        total_voltage_v=48.5,
        total_current_a=13.2,
        device_power_status=1,
        operation_feedback=2,
        task_status=3,
    )

    assert packet[35:37] == (4321).to_bytes(2, "big")
    assert packet[38:40] == (56).to_bytes(2, "big")
    assert packet[72:74] == (1805).to_bytes(2, "big", signed=True)
    assert packet[74:76] == (-53).to_bytes(2, "big", signed=True)
    assert packet[76:78] == (127).to_bytes(2, "big", signed=True)
    assert packet[78:80] == (2701).to_bytes(2, "big")
    assert packet[80:82] == (34).to_bytes(2, "big")
    assert packet[82:84] == (12).to_bytes(2, "big", signed=True)
    assert packet[84:86] == (25).to_bytes(2, "big")
    assert packet[86:90] == (121473400).to_bytes(4, "big", signed=True)
    assert packet[90:94] == (31230400).to_bytes(4, "big", signed=True)
    assert packet[102:104] == (485).to_bytes(2, "big")
    assert packet[104:106] == (132).to_bytes(2, "big")


def test_uplink_checksum() -> None:
    packets = [
        build_uplink_packet(frame_counter=1, internal_pressure_psi=1.0, total_voltage_v=48.1),
        build_uplink_packet(
            frame_counter=2,
            internal_pressure_psi=9.999,
            heading_deg=359.9,
            pitch_deg=-9.9,
            roll_deg=8.8,
            dead_reckoning_lon_deg=-179.999999,
            dead_reckoning_lat_deg=89.999999,
            total_voltage_v=54.3,
            total_current_a=21.7,
        ),
    ]

    for packet in packets:
        assert packet[142] == calculate_byte_sum_checksum(packet[:142])
        assert packet[143:145] == b"\xFF\xFF"


def test_downlink_roundtrip() -> None:
    payload = _control_payload(right=4.6, top=-3.2, left=2.8, bottom=-1.4, thrust=7.5)
    packet = build_downlink_packet(
        payload,
        frame_counter=17,
        obj_address=9,
        control_mode_byte=int(ControlModeByte.REMOTE_CONTROL),
        work_instruction=int(WorkInstruction.AUTONOMOUS_CONTROL),
        orientation_deg=123.4,
        depth_protect_params=(100, 200),
        bottom_protect_params=(300, 400),
        preset_time_tenths_min=50,
        spare_params=(-11, 22),
        parameter_values=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12),
        main_motor_rpm_scale=12.0,
        side_motor_rpm=77,
    )

    parsed = parse_downlink_packet(packet, main_motor_rpm_scale=12.0)

    assert parsed.frame_number == 17
    assert parsed.obj_address == 9
    assert parsed.control_mode_byte == int(ControlModeByte.REMOTE_CONTROL)
    assert parsed.work_instruction == int(WorkInstruction.AUTONOMOUS_CONTROL)
    assert math.isclose(parsed.right_fin_deg, 4.6)
    assert math.isclose(parsed.top_fin_deg, -3.2)
    assert math.isclose(parsed.left_fin_deg, 2.8)
    assert math.isclose(parsed.bottom_fin_deg, -1.4)
    assert math.isclose(parsed.thrust_percent, 7.5)
    assert parsed.main_motor_rpm == 90
    assert parsed.side_motor_rpm == 77
    assert math.isclose(parsed.orientation_deg, 123.4)
    assert parsed.depth_protect_params == (100, 200)
    assert parsed.bottom_protect_params == (300, 400)
    assert parsed.preset_time_tenths_min == 50
    assert parsed.spare_params == (-11, 22)
    assert parsed.parameters == (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)


def test_uplink_roundtrip() -> None:
    packet = build_uplink_packet(
        frame_counter=31,
        auv_address=7,
        control_mode_byte=int(ControlModeByte.JETSON_PROTOCOL),
        work_instruction=int(WorkInstruction.AUTONOMOUS_CONTROL),
        main_motor_rpm=180,
        side_motor_rpm=21,
        left_fin_deg=12.0,
        right_fin_deg=-23.0,
        top_fin_deg=34.0,
        bottom_fin_deg=-45.0,
        orientation_deg=42.0,
        depth_m=8.6,
        heading_deg=91.2,
        pitch_deg=-3.1,
        roll_deg=2.4,
        gps_heading_deg=182.3,
        gps_speed_mps=4.5,
        dvl_speed_mps=-1.2,
        altitude_m=6.7,
        dead_reckoning_lon_deg=121.4734,
        dead_reckoning_lat_deg=31.2304,
        gps_lon_deg=120.1234,
        gps_lat_deg=30.5678,
        total_voltage_v=48.7,
        total_current_a=13.2,
        soc=88,
        soh=93,
        internal_pressure_psi=9.876,
        internal_temp_c=-6,
        device_power_status=0x01020304,
        operation_feedback=0x05060708,
        task_status=0x090A0B0C,
        system_alarm=0x11,
        depth_alarm=0x22,
        bottom_alarm=0x33,
    )

    parsed = parse_uplink_packet(packet)

    assert parsed.frame_number == 31
    assert parsed.auv_address == 7
    assert parsed.control_mode_byte == int(ControlModeByte.JETSON_PROTOCOL)
    assert parsed.work_instruction == int(WorkInstruction.AUTONOMOUS_CONTROL)
    assert parsed.main_motor_rpm == 180
    assert parsed.side_motor_rpm == 21
    assert math.isclose(parsed.left_fin_deg, 12.0)
    assert math.isclose(parsed.right_fin_deg, -23.0)
    assert math.isclose(parsed.top_fin_deg, 34.0)
    assert math.isclose(parsed.bottom_fin_deg, -45.0)
    assert math.isclose(parsed.internal_pressure_psi, 9.876, abs_tol=0.001)
    assert math.isclose(parsed.orientation_deg, 987.6)
    assert parsed.internal_temp_c == -6
    assert math.isclose(parsed.depth_m, 8.6)
    assert math.isclose(parsed.heading_deg, 91.2)
    assert math.isclose(parsed.pitch_deg, -3.1)
    assert math.isclose(parsed.roll_deg, 2.4)
    assert math.isclose(parsed.gps_heading_deg, 182.3)
    assert math.isclose(parsed.gps_speed_mps, 4.5)
    assert math.isclose(parsed.dvl_speed_mps, -1.2)
    assert math.isclose(parsed.altitude_m, 6.7)
    assert math.isclose(parsed.dead_reckoning_lon_deg, 121.4734)
    assert math.isclose(parsed.dead_reckoning_lat_deg, 31.2304)
    assert math.isclose(parsed.gps_lon_deg, 120.1234)
    assert math.isclose(parsed.gps_lat_deg, 30.5678)
    assert math.isclose(parsed.total_voltage_v, 48.7)
    assert math.isclose(parsed.total_current_a, 13.2)
    assert parsed.soc == 88
    assert parsed.soh == 93
    assert parsed.device_power_status == 0x01020304
    assert parsed.operation_feedback == 0x05060708
    assert parsed.task_status == 0x090A0B0C
    assert parsed.system_alarm == 0x11
    assert parsed.depth_alarm == 0x22
    assert parsed.bottom_alarm == 0x33


def test_uplink_anomaly_bitmap() -> None:
    packet = build_uplink_packet(
        device_power_status=0xDEADBEEF,
        operation_feedback=0x01020304,
        task_status=0xA0B0C0D0,
        system_alarm=0x11,
        depth_alarm=0x22,
        bottom_alarm=0x33,
    )

    parsed = parse_uplink_packet(packet)

    assert packet[114:118] == (0xDEADBEEF).to_bytes(4, "big")
    assert packet[118:122] == (0x01020304).to_bytes(4, "big")
    assert packet[122:126] == (0xA0B0C0D0).to_bytes(4, "big")
    assert packet[127:130] == bytes((0x11, 0x22, 0x33))
    assert parsed.device_power_status == 0xDEADBEEF
    assert parsed.operation_feedback == 0x01020304
    assert parsed.task_status == 0xA0B0C0D0
    assert parsed.system_alarm == 0x11
    assert parsed.depth_alarm == 0x22
    assert parsed.bottom_alarm == 0x33


def test_uplink_pc104_relative_time_fields_are_decoded() -> None:
    packet = build_uplink_packet(pc104_uptime_ms=123456, dvl_bi_uptime_ms=123400)
    parsed = parse_uplink_packet(packet)

    assert packet[PROTOCOL_UPLINK_PARA3_OFFSET:PROTOCOL_UPLINK_PARA3_OFFSET + 4] == (123456).to_bytes(4, "big", signed=True)
    assert packet[PROTOCOL_UPLINK_PARA4_OFFSET:PROTOCOL_UPLINK_PARA4_OFFSET + 4] == (123400).to_bytes(4, "big", signed=True)
    assert packet[PROTOCOL_UPLINK_PARA12_OFFSET:PROTOCOL_UPLINK_PARA12_OFFSET + 2] == PROTOCOL_UPLINK_PC104_TIME_VALID_MARKER.to_bytes(2, "big", signed=True)
    assert parsed.pc104_uptime_ms == 123456
    assert parsed.pc104_time_valid is True
    assert parsed.pc104_dvl_bi_uptime_ms == 123400
    assert parsed.pc104_dvl_bi_time_valid is True

    payload = build_bridge_telemetry_payload(parsed, ts=10.0)
    assert payload[KEY_PC104_UPTIME_MS] == 123456
    assert payload[KEY_PC104_TIME_VALID] is True
    assert payload[KEY_PC104_DVL_BI_UPTIME_MS] == 123400
    assert payload[KEY_PC104_DVL_BI_TIME_VALID] is True


def test_uplink_pc104_downlink_echo_fields_are_decoded() -> None:
    packet = build_uplink_packet(
        pc104_uptime_ms=123500,
        pc104_downlink_echo_frame=42,
        pc104_downlink_recv_uptime_ms=123450,
    )
    parsed = parse_uplink_packet(packet)

    assert packet[PROTOCOL_UPLINK_SPARE1_OFFSET:PROTOCOL_UPLINK_SPARE1_OFFSET + 2] == (
        PROTOCOL_UPLINK_DOWNLINK_ECHO_MARKER
    ).to_bytes(2, "big", signed=True)
    assert packet[PROTOCOL_UPLINK_SPARE2_OFFSET:PROTOCOL_UPLINK_SPARE2_OFFSET + 2] == (42).to_bytes(
        2,
        "big",
        signed=True,
    )
    assert packet[PROTOCOL_UPLINK_PARA1_OFFSET:PROTOCOL_UPLINK_PARA1_OFFSET + 4] == (123450).to_bytes(
        4,
        "big",
        signed=True,
    )
    assert parsed.pc104_downlink_echo_valid is True
    assert parsed.pc104_downlink_echo_frame == 42
    assert parsed.pc104_downlink_recv_uptime_ms == 123450

    payload = build_bridge_telemetry_payload(parsed, ts=10.0)
    assert payload[KEY_PC104_DOWNLINK_ECHO_VALID] is True
    assert payload[KEY_PC104_DOWNLINK_ECHO_FRAME] == 42
    assert payload[KEY_PC104_DOWNLINK_RECV_UPTIME_MS] == 123450


def test_uplink_decodes_forward_sonar_slope_from_para11() -> None:
    packet = build_uplink_packet(
        parameter_values=(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -1234, 0),
    )
    parsed = parse_uplink_packet(packet)

    assert packet[68:70] == (-1234).to_bytes(2, "big", signed=True)
    assert math.isclose(parsed.forward_sonar_slope, -0.1234)


def test_uplink_pc104_relative_time_is_legacy_safe_without_marker() -> None:
    packet = build_uplink_packet(parameter_values=(0, 0, 123456, 0, 0, 0, 0, 0, 0, 0, 0, 0))
    parsed = parse_uplink_packet(packet)

    assert parsed.pc104_uptime_ms == 123456
    assert parsed.pc104_time_valid is False
    assert parsed.pc104_dvl_bi_time_valid is False
    assert parsed.pc104_downlink_echo_valid is False
