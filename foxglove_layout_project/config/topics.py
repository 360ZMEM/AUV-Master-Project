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
    setpoint: str = "/auv/control/setpoint"
    cmd_vel: str = "/cmd_vel"

    imu: str = "/auv/sensors/imu"
    dvl: str = "/auv/sensors/dvl"
    depth: str = "/auv/sensors/depth"
    status: str = "/auv/sensors/status"

    ground_truth: str = "/auv/sensors/ground_truth"
    magnetic: str = "/auv/sensors/magnetic"
    sonar: str = "/auv/sensors/sonar"

    seabed_cloud: str = "/auv/visual/seabed_cloud"
    cable_marker: str = "/auv/visual/cable_marker"
    truth_pose: str = "/auv/visual/truth_pose"
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


@dataclass(frozen=True)
class ColorConfig:
    """Panel colors used to keep plots visually stable across generations."""

    state_3d: str = "#00ff88"
    terrain_3d: str = "#2bb673"
    cable_3d: str = "#f6d64a"
    truth_3d: str = "#00b7ff"
    trail_3d: str = "#4f9cff"
    range_3d: str = "#ff4d4d"
    mock_scene: str = "#f08c00"
    depth_actual: str = "#00ff00"
    depth_target: str = "#66cc66"
    speed_actual: str = "#0066ff"
    speed_target: str = "#66aaff"
    cmd_right: str = "#ff6600"
    cmd_top: str = "#ff9900"
    cmd_left: str = "#cc5500"
    cmd_bottom: str = "#aa3300"
    cmd_thrust: str = "#9933ff"


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
        setpoint=_join(config.setpoint),
        cmd_vel=_join(config.cmd_vel),
        imu=_join(config.imu),
        dvl=_join(config.dvl),
        depth=_join(config.depth),
        status=_join(config.status),
        ground_truth=_join(config.ground_truth),
        magnetic=_join(config.magnetic),
        sonar=_join(config.sonar),
        seabed_cloud=_join(config.seabed_cloud),
        cable_marker=_join(config.cable_marker),
        truth_pose=_join(config.truth_pose),
        history_trail=_join(config.history_trail),
        view_range=_join(config.view_range),
        mock_scene=_join(config.mock_scene),
    )


TOPICS = TopicConfig()
PLOT_FIELDS = PlotFieldConfig()
COLORS = ColorConfig()
