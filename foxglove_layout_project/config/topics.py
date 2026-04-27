"""Foxglove topic and field configuration for AUV_Master_Project.

This module mirrors the reference project pattern: keep all topic names,
field paths, and colors centralized so the generator never hardcodes them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TopicConfig:
    """Topic registry for the Foxglove layout generator."""

    state_filtered: str = "/auv/state/filtered"
    state_raw_dr: str = "/auv/state/raw_dr"
    setpoint: str = "/auv/control/setpoint"
    cmd_vel: str = "/cmd_vel"

    bridge_shadow_cmd: str = "/auv/bridge/shadow_cmd"
    bridge_shadow_telemetry: str = "/auv/bridge/shadow_telemetry"

    imu: str = "/auv/sensors/imu"
    dvl: str = "/auv/sensors/dvl"
    depth: str = "/auv/sensors/depth"
    status: str = "/auv/sensors/status"
    depth_error: str = "/auv/metrics/depth_error"
    lateral_error: str = "/auv/metrics/lateral_error"
    bt_status: str = "/auv/bt_status"
    diagnostics: str = "/auv/diagnostics"
    confidence_text: str = "/auv/display/confidence_text"
    power_text: str = "/auv/display/power_text"

    ground_truth: str = "/auv/sensors/ground_truth"
    magnetic: str = "/auv/sensors/magnetic"
    sonar: str = "/auv/sensors/sonar"

    seabed_cloud: str = "/auv/visual/seabed_cloud"
    seabed_mesh: str = "/auv/visual/seabed_mesh"
    cable_marker: str = "/auv/visual/cable_marker"
    auv_body: str = "/auv/visual/auv_body"
    truth_pose: str = "/auv/visual/truth_marker"
    history_trail: str = "/auv/visual/history_trail"
    view_range: str = "/auv/visual/view_range"
    mock_scene: str = "/auv/mock/scene"


@dataclass(frozen=True)
class PlotFieldConfig:
    """Field paths used by the Foxglove plot panels."""

    depth_value: str = "data"
    dvl_speed_x: str = "twist.linear.x"
    setpoint_depth: str = "target_depth_m"
    setpoint_speed: str = "target_speed_mps"
    cmd_right: str = "angular.x"
    cmd_top: str = "angular.y"
    cmd_left: str = "angular.z"
    cmd_bottom: str = "linear.z"
    cmd_thrust: str = "linear.x"
    odom_lateral_y: str = "pose.pose.position.y"
    scalar_data: str = "data"
    diagnostic_depth_error: str = "depth_error_m"
    diagnostic_lateral_error: str = "lateral_error_m"
    diagnostic_magnetic_magnitude: str = "magnetic_magnitude"


@dataclass(frozen=True)
class DisplayFieldConfig:
    """Field paths used by mentor-demo status panels."""

    setpoint_mode: str = "mode"
    status_confidence: str = "confidence"
    status_leak_level: str = "leak_level"
    status_battery_low: str = "battery_low"
    status_total_voltage_v: str = "total_voltage_v"
    string_data: str = "data"


@dataclass(frozen=True)
class ColorConfig:
    """Panel colors used to keep plots visually stable across generations."""

    state_3d: str = "#00ff88"
    terrain_3d: str = "#d2b48c"
    cable_3d: str = "#f6d64a"
    auv_body_3d: str = "#58a6ff"
    truth_3d: str = "#00b7ff"
    trail_3d: str = "#4f9cff"
    range_3d: str = "#ff4d4d"
    mock_scene: str = "#f08c00"
    depth_actual: str = "#00ff00"
    depth_target: str = "#66cc66"
    depth_error: str = "#ff6b6b"
    lateral_error: str = "#ffd166"
    speed_actual: str = "#0066ff"
    speed_target: str = "#66aaff"
    cmd_right: str = "#ff6600"
    cmd_top: str = "#ff9900"
    cmd_left: str = "#cc5500"
    cmd_bottom: str = "#aa3300"
    cmd_thrust: str = "#9933ff"
    scene_background: str = "#07131d"
    scene_grid: str = "#1f3542"
    transform_line: str = "#345362"
    confidence_low: str = "#c0392b"
    confidence_high: str = "#2ecc71"
    status_ok: str = "#2ecc71"
    status_warn: str = "#f39c12"
    status_error: str = "#e74c3c"
    status_idle: str = "#6c7a89"
    mode_searching: str = "#1abc9c"
    mode_tracking: str = "#2980b9"
    mode_diving: str = "#16a085"
    mode_emergency: str = "#c0392b"
    mode_idle: str = "#7f8c8d"


def with_topic_prefix(config: TopicConfig, prefix: str) -> TopicConfig:
    """Return a new topic config with a namespace prefix applied.

    Example:
    - prefix="/sim" -> /sim/auv/state/filtered
    - prefix="sim"  -> /sim/auv/state/filtered
    """
    cleaned = prefix.strip()
    if not cleaned:
        return config

    cleaned = cleaned if cleaned.startswith("/") else f"/{cleaned}"

    def _join(topic: str) -> str:
        if topic.startswith(cleaned + "/"):
            return topic
        return f"{cleaned}{topic}"

    return TopicConfig(
        state_filtered=_join(config.state_filtered),
        state_raw_dr=_join(config.state_raw_dr),
        setpoint=_join(config.setpoint),
        cmd_vel=_join(config.cmd_vel),
        bridge_shadow_cmd=_join(config.bridge_shadow_cmd),
        bridge_shadow_telemetry=_join(config.bridge_shadow_telemetry),
        imu=_join(config.imu),
        dvl=_join(config.dvl),
        depth=_join(config.depth),
        status=_join(config.status),
        depth_error=_join(config.depth_error),
        lateral_error=_join(config.lateral_error),
        bt_status=_join(config.bt_status),
        diagnostics=_join(config.diagnostics),
        confidence_text=_join(config.confidence_text),
        power_text=_join(config.power_text),
        ground_truth=_join(config.ground_truth),
        magnetic=_join(config.magnetic),
        sonar=_join(config.sonar),
        seabed_cloud=_join(config.seabed_cloud),
        seabed_mesh=_join(config.seabed_mesh),
        cable_marker=_join(config.cable_marker),
        auv_body=_join(config.auv_body),
        truth_pose=_join(config.truth_pose),
        history_trail=_join(config.history_trail),
        view_range=_join(config.view_range),
        mock_scene=_join(config.mock_scene),
    )


TOPICS = TopicConfig()
PLOT_FIELDS = PlotFieldConfig()
DISPLAY_FIELDS = DisplayFieldConfig()
COLORS = ColorConfig()
