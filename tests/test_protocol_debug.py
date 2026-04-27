from __future__ import annotations

from common.protocol import build_downlink_packet, build_uplink_packet
from common.protocol_debug import detect_protocol_direction, format_protocol_packet


def test_format_protocol_packet_summarizes_downlink() -> None:
    packet = build_downlink_packet(
        {"right": 1.0, "top": 2.0, "left": 3.0, "bottom": 4.0, "thrust": 5.0},
        frame_counter=7,
        obj_address=2,
        control_mode_byte=0xEE,
        work_instruction=0x01,
        orientation_deg=12.0,
        side_motor_rpm=11,
    )

    rendered = format_protocol_packet(packet, label="test", color=False, include_hex=True)

    assert detect_protocol_direction(packet) == "downlink"
    assert "[test][CKTH]" in rendered
    assert "frame=7 obj=2 mode=0xEE instr=0x01" in rendered
    assert "hex=" in rendered


def test_format_protocol_packet_summarizes_uplink() -> None:
    packet = build_uplink_packet(
        frame_counter=3,
        auv_address=1,
        control_mode_byte=0x01,
        work_instruction=0x02,
        main_motor_rpm=120,
        side_motor_rpm=10,
        left_fin_deg=1.0,
        right_fin_deg=2.0,
        top_fin_deg=3.0,
        bottom_fin_deg=4.0,
        depth_m=6.5,
        heading_deg=90.0,
        pitch_deg=1.0,
        roll_deg=2.0,
        gps_heading_deg=88.0,
        gps_speed_mps=1.2,
        dvl_speed_mps=1.1,
        altitude_m=8.0,
        total_voltage_v=48.5,
        total_current_a=12.0,
        soc=90,
        soh=95,
    )

    rendered = format_protocol_packet(packet, label="test", color=False)

    assert detect_protocol_direction(packet) == "uplink"
    assert "[test][AUV]" in rendered
    assert "frame=3 auv=1 mode=0x01 instr=0x02" in rendered
    assert "depth=6.50m" in rendered