"""Build a Foxglove Desktop layout JSON for AUV_Master_Project.

The export shape matches the known-good Foxglove Desktop layout in this
workspace: configById + layout.
"""

from __future__ import annotations

import math
from typing import Any

from foxglove_layout_project.config.topics import COLORS, PLOT_FIELDS, TOPICS, TopicConfig


def _build_plot_series(*, topic: str, value: str, color: str) -> dict[str, Any]:
    return {
        "timestampMethod": "receiveTime",
        "value": f"{topic}.{value}",
        "enabled": True,
        "color": color,
    }


def _build_plot_config(*, title: str, y_axis_label: str, series: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "title": title,
        "legendDisplay": "floating",
        "showLegend": True,
        "xAxisLabel": "时间",
        "yAxisLabel": y_axis_label,
        "paths": series,
        "sidebarDimension": 240,
        "timeWindowMode": "automatic",
        "showXAxisLabels": True,
        "showYAxisLabels": True,
        "showPlotValuesInLegend": True,
    }


def _build_raw_config(*, topic_path: str, description: str) -> dict[str, Any]:
    return {
        "topicPath": topic_path,
        "diffEnabled": False,
        "expansion": "none",
        "showFullMessageForDiff": True,
    }


def _build_3d_config(*, topics: TopicConfig, include_map_layer: bool) -> dict[str, Any]:
    camera_phi = math.radians(60.0)
    camera_theta = math.radians(45.0)

    topic_entries = {
        topics.state_filtered: {"visible": True, "type": "arrow", "axisScale": 1.5, "color": COLORS.state_3d},
        topics.truth_pose: {"visible": True, "type": "arrow", "axisScale": 1.8, "color": COLORS.truth_3d},
        topics.seabed_cloud: {"visible": True, "type": "pointCloud", "axisScale": 1.0, "color": COLORS.terrain_3d},
        topics.cable_marker: {"visible": True, "type": "lineStrip", "axisScale": 1.0, "color": COLORS.cable_3d},
        topics.history_trail: {"visible": True, "type": "lineStrip", "axisScale": 1.0, "color": COLORS.trail_3d},
        topics.view_range: {"visible": True, "type": "cylinder", "axisScale": 1.0, "color": COLORS.range_3d},
    }

    layers: dict[str, Any] = {}
    if include_map_layer:
        layers = {"map": {"type": "satellite", "enabled": True, "opacity": 1.0}}

    return {
        "cameraState": {
            "distance": 30,
            "perspective": True,
            "phi": 60,
            "target": [0, 0, -5],
            "targetOffset": [0, 0, 0],
            "targetOrientation": [0, 0, 0, 1],
            "thetaOffset": 45,
            "fovy": 45,
            "near": 0.1,
            "far": 5000,
        },
        "followMode": "follow-none",
        "followTf": "auv_base_link",
        "fixedFrame": "map",
        "scene": {
            "syncCamera": False,
            "transforms": {
                "editable": False,
                "showLabel": True,
                "enablePreloading": True,
                "visible": True,
            },
            "enableStats": False,
            "meshUpAxis": "z_up",
        },
        "transforms": {},
        "grid": {
            "color": "#444444",
            "divisions": 10,
            "size": 50,
            "visible": True,
        },
        "topics": topic_entries,
        "layers": layers,
    }


def _split(direction: str, first: Any, second: Any, split_percentage: float) -> dict[str, Any]:
    return {
        "direction": direction,
        "first": first,
        "second": second,
        "splitPercentage": split_percentage,
    }


def build_auv_layout(
    *,
    include_map_layer: bool = False,
    topics: TopicConfig | None = None,
    layout_name: str = "AUV数据可视化",
    layout_description: str = "AUV传感器与数字孪生可视化面板",
    layout_id: str = "auv-data-visualization",
) -> dict[str, Any]:
    """Construct the Foxglove Desktop layout for the AUV stack."""
    topics = topics or TOPICS

    three_d_config = _build_3d_config(topics=topics, include_map_layer=include_map_layer)

    three_d_key = "3D!auv3d"
    depth_key = "Plot!depth"
    speed_key = "Plot!speed"
    control_key = "Plot!control"
    imu_key = "RawMessages!imu"
    dvl_key = "RawMessages!dvl"
    state_key = "RawMessages!state"
    setpoint_key = "RawMessages!setpoint"
    cmd_vel_key = "RawMessages!cmdvel"
    status_key = "RawMessages!status"
    mock_scene_key = "RawMessages!mockscene"

    config_by_id: dict[str, dict[str, Any]] = {
        three_d_key: three_d_config,
        depth_key: _build_plot_config(
            title="AUV深度",
            y_axis_label="深度 (m)",
            series=[
                _build_plot_series(topic=topics.depth, value=PLOT_FIELDS.depth_value, color=COLORS.depth_actual),
                _build_plot_series(topic=topics.setpoint, value=PLOT_FIELDS.setpoint_depth, color=COLORS.depth_target),
            ],
        ),
        speed_key: _build_plot_config(
            title="AUV速度",
            y_axis_label="速度 (m/s)",
            series=[
                _build_plot_series(topic=topics.dvl, value=PLOT_FIELDS.dvl_speed_x, color=COLORS.speed_actual),
                _build_plot_series(topic=topics.setpoint, value=PLOT_FIELDS.setpoint_speed, color=COLORS.speed_target),
            ],
        ),
        control_key: _build_plot_config(
            title="Twist 指令",
            y_axis_label="Twist 指令",
            series=[
                _build_plot_series(topic=topics.cmd_vel, value=PLOT_FIELDS.cmd_thrust, color=COLORS.cmd_thrust),
                _build_plot_series(topic=topics.cmd_vel, value=PLOT_FIELDS.cmd_right, color=COLORS.cmd_right),
                _build_plot_series(topic=topics.cmd_vel, value=PLOT_FIELDS.cmd_top, color=COLORS.cmd_top),
                _build_plot_series(topic=topics.cmd_vel, value=PLOT_FIELDS.cmd_left, color=COLORS.cmd_left),
                _build_plot_series(topic=topics.cmd_vel, value=PLOT_FIELDS.cmd_bottom, color=COLORS.cmd_bottom),
            ],
        ),
        imu_key: _build_raw_config(topic_path=topics.imu, description="IMU传感器数据"),
        dvl_key: _build_raw_config(topic_path=topics.dvl, description="DVL速度信息"),
        state_key: _build_raw_config(topic_path=topics.state_filtered, description="滤波后状态"),
        setpoint_key: _build_raw_config(topic_path=topics.setpoint, description="控制目标"),
        cmd_vel_key: _build_raw_config(topic_path=topics.cmd_vel, description="速度指令"),
        status_key: _build_raw_config(topic_path=topics.status, description="传感器状态摘要"),
        mock_scene_key: _build_raw_config(topic_path=topics.mock_scene, description="mock场景摘要"),
    }

    layout_tree = _split(
        "row",
        _split("row", three_d_key, _split("column", depth_key, speed_key, 50), 55),
        _split(
            "column",
            _split("row", control_key, _split("column", imu_key, dvl_key, 50), 50),
            _split(
                "row",
                _split("column", state_key, setpoint_key, 50),
                _split("column", cmd_vel_key, _split("column", status_key, mock_scene_key, 50), 50),
                50,
            ),
            50,
        ),
        55,
    )

    return {
        "configById": config_by_id,
        "globalVariables": {},
        "userNodes": {},
        "playbackConfig": {"speed": 1},
        "layout": layout_tree,
    }
