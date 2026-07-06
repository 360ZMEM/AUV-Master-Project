"""Build a Foxglove Desktop layout JSON for AUV_Master_Project.

The export shape matches the known-good Foxglove Desktop layout in this
workspace: configById + layout.
"""

from __future__ import annotations

from typing import Any, Literal

from foxglove_layout_project.config.topics import COLORS, DISPLAY_FIELDS, PLOT_FIELDS, TOPICS, TopicConfig

LayoutProfile = Literal["classic", "mentor-demo", "probe", "pilot-1366", "acceptance-1366"]


def _compact_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}


def _build_message_path(*, topic: str, field: str | None = None) -> str:
    if not field:
        return topic
    return f"{topic}.{field}"


def _build_plot_series(*, topic: str, value: str, color: str) -> dict[str, Any]:
    return {
        "timestampMethod": "receiveTime",
        "value": f"{topic}.{value}",
        "enabled": True,
        "color": color,
    }


def _build_plot_config(
    *,
    title: str,
    y_axis_label: str,
    series: list[dict[str, Any]],
    min_y_value: float | None = None,
    max_y_value: float | None = None,
    time_window_mode: str = "sliding",
    following_view_width: float = 60.0,
    is_synced: bool = True,
    show_legend: bool = True,
    sidebar_dimension: int = 220,
) -> dict[str, Any]:
    return _compact_dict({
        "title": title,
        "legendDisplay": "floating",
        "showLegend": show_legend,
        "xAxisLabel": "时间",
        "yAxisLabel": y_axis_label,
        "paths": series,
        "sidebarDimension": sidebar_dimension,
        "timeWindowMode": time_window_mode,
        "followingViewWidth": following_view_width,
        "playbackBarPosition": "right",
        "isSynced": is_synced,
        "minYValue": min_y_value,
        "maxYValue": max_y_value,
        "showXAxisLabels": True,
        "showYAxisLabels": True,
        "showPlotValuesInLegend": True,
    })


def _build_raw_config(*, topic_path: str, title: str | None = None) -> dict[str, Any]:
    return _compact_dict({
        "title": title,
        "topicPath": topic_path,
        "diffEnabled": False,
        "expansion": "none",
        "showFullMessageForDiff": True,
    })


def _build_markdown_config(*, message_path: str, font_size: float | None = None) -> dict[str, Any]:
    return _compact_dict({
        "renderMode": "message",
        "messagePath": message_path,
        "fontSize": font_size,
    })


def _build_indicator_rule(*, raw_value: Any, label: str, color: str, operator: str = "=") -> dict[str, Any]:
    return {
        "rawValue": raw_value,
        "operator": operator,
        "color": color,
        "label": label,
    }


def _build_indicator_config(
    *,
    title: str,
    path: str,
    style: str,
    rules: list[dict[str, Any]],
    fallback_color: str,
    fallback_label: str,
    font_size: float | None = None,
) -> dict[str, Any]:
    return _compact_dict({
        "title": title,
        "path": path,
        "style": style,
        "fontSize": font_size,
        "rules": rules,
        "fallbackColor": fallback_color,
        "fallbackLabel": fallback_label,
    })


def _build_gauge_config(
    *,
    title: str,
    path: str,
    min_value: float,
    max_value: float,
    style: str = "bar",
    color_mode: str = "colormap",
    color_map: str = "red-yellow-green",
    reverse: bool = False,
) -> dict[str, Any]:
    return _compact_dict({
        "title": title,
        "path": path,
        "style": style,
        "minValue": min_value,
        "maxValue": max_value,
        "colorMode": color_mode,
        "colorMap": color_map,
        "reverse": reverse,
    })


def _build_3d_config(*, topics: TopicConfig, include_map_layer: bool, mentor_mode: bool) -> dict[str, Any]:
    camera_distance = 34 if mentor_mode else 30
    grid_color = COLORS.scene_grid if mentor_mode else "#444444"
    scene_transforms = {
        "editable": False,
        "showLabel": False if mentor_mode else True,
        "enablePreloading": True,
        "visible": True,
    }
    if mentor_mode:
        scene_transforms.update(
            {
                "axisSize": 0.18,
                "labelSize": 12,
                "lineWidth": 1,
                "lineColor": COLORS.transform_line,
                "drawBehind": True,
            }
        )

    topic_entries = {
        # Keep only one default AUV pose glyph in 3D. Showing filtered odom,
        # truth arrow, and body marker together can look like violent jitter
        # when those sources are in different coordinate origins or update at
        # different rates. The hidden layers remain available for manual debug.
        topics.state_filtered: {"visible": False, "type": "arrow", "axisScale": 1.5, "color": COLORS.state_3d},
        topics.auv_body: {"visible": True, "type": "cylinder", "axisScale": 1.0, "color": COLORS.auv_body_3d},
        topics.truth_pose: {"visible": False, "type": "arrow", "axisScale": 1.8, "color": COLORS.truth_3d},
        topics.seabed_mesh: {"visible": True, "color": COLORS.terrain_3d, "showOutlines": True},
        topics.cable_marker: {"visible": True, "type": "lineStrip", "axisScale": 1.0, "color": COLORS.cable_3d},
        topics.history_trail: {"visible": True, "type": "lineStrip", "axisScale": 1.0, "color": COLORS.trail_3d},
        topics.view_range: {"visible": True, "type": "lineStrip", "axisScale": 1.0, "color": COLORS.range_3d},
    }

    layers: dict[str, Any] = {}
    if include_map_layer:
        layers = {"map": {"type": "satellite", "enabled": True, "opacity": 1.0}}

    return {
        "cameraState": {
            "distance": camera_distance,
            "perspective": True,
            "phi": 60,
            "target": [0, 0, -5],
            "targetOffset": [0, 0, 0],
            "targetOrientation": [0, 0, 0, 1],
            "thetaOffset": 38 if mentor_mode else 45,
            "fovy": 45,
            "near": 0.1,
            "far": 5000,
        },
        "followMode": "follow-none",
        "followTf": "auv_base_link",
        "fixedFrame": "map",
        "scene": _compact_dict({
            "syncCamera": False,
            "backgroundColor": COLORS.scene_background if mentor_mode else None,
            "transforms": scene_transforms,
            "enableStats": False,
            "meshUpAxis": "z_up",
        }),
        "transforms": {},
        "grid": {
            "color": grid_color,
            "divisions": 12 if mentor_mode else 10,
            "size": 60 if mentor_mode else 50,
            "visible": True,
        },
        "topics": topic_entries,
        "layers": layers,
    }


def _build_top_view_config(*, topics: TopicConfig) -> dict[str, Any]:
    return {
        "cameraState": {
            "distance": 90,
            "perspective": False,
            "phi": 0,
            "target": [0, 0, -5],
            "targetOffset": [0, 0, 0],
            "targetOrientation": [0, 0, 0, 1],
            "thetaOffset": 0,
            "fovy": 45,
            "near": 0.1,
            "far": 5000,
        },
        "followMode": "follow-none",
        "followTf": "auv_base_link",
        "fixedFrame": "map",
        "scene": {
            "syncCamera": False,
            "backgroundColor": COLORS.scene_background,
            "transforms": {
                "editable": False,
                "showLabel": False,
                "enablePreloading": True,
                "visible": False,
            },
            "enableStats": False,
            "meshUpAxis": "z_up",
        },
        "transforms": {},
        "grid": {
            "color": COLORS.scene_grid,
            "divisions": 12,
            "size": 80,
            "visible": True,
        },
        "topics": {
            topics.auv_body: {"visible": True, "type": "cylinder", "axisScale": 1.0, "color": COLORS.auv_body_3d},
            topics.truth_pose: {"visible": False, "type": "arrow", "axisScale": 1.6, "color": COLORS.truth_3d},
            topics.cable_marker: {"visible": True, "type": "lineStrip", "axisScale": 1.0, "color": COLORS.cable_3d},
            topics.history_trail: {"visible": True, "type": "lineStrip", "axisScale": 1.0, "color": COLORS.trail_3d},
            topics.view_range: {"visible": True, "type": "lineStrip", "axisScale": 1.0, "color": COLORS.range_3d},
        },
        "layers": {},
    }


def _split(direction: str, first: Any, second: Any, split_percentage: float) -> dict[str, Any]:
    return {
        "direction": direction,
        "first": first,
        "second": second,
        "splitPercentage": split_percentage,
    }


def _build_classic_layout(*, topics: TopicConfig, include_map_layer: bool) -> dict[str, Any]:
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
        three_d_key: _build_3d_config(topics=topics, include_map_layer=include_map_layer, mentor_mode=False),
        depth_key: _build_plot_config(
            title="AUV深度",
            y_axis_label="深度 (m)",
            series=[
                _build_plot_series(topic=topics.depth, value=PLOT_FIELDS.depth_value, color=COLORS.depth_actual),
                _build_plot_series(topic=topics.setpoint, value=PLOT_FIELDS.setpoint_depth, color=COLORS.depth_target),
            ],
            time_window_mode="automatic",
            following_view_width=60.0,
            is_synced=False,
        ),
        speed_key: _build_plot_config(
            title="AUV速度",
            y_axis_label="速度 (m/s)",
            series=[
                _build_plot_series(topic=topics.dvl, value=PLOT_FIELDS.dvl_speed_x, color=COLORS.speed_actual),
                _build_plot_series(topic=topics.setpoint, value=PLOT_FIELDS.setpoint_speed, color=COLORS.speed_target),
            ],
            time_window_mode="automatic",
            following_view_width=60.0,
            is_synced=False,
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
            time_window_mode="automatic",
            following_view_width=60.0,
            is_synced=False,
        ),
        imu_key: _build_raw_config(topic_path=topics.imu, title="IMU传感器数据"),
        dvl_key: _build_raw_config(topic_path=topics.dvl, title="DVL速度信息"),
        state_key: _build_raw_config(topic_path=topics.state_filtered, title="滤波后状态"),
        setpoint_key: _build_raw_config(topic_path=topics.setpoint, title="控制目标"),
        cmd_vel_key: _build_raw_config(topic_path=topics.cmd_vel, title="速度指令"),
        status_key: _build_raw_config(topic_path=topics.status, title="传感器状态摘要"),
        mock_scene_key: _build_raw_config(topic_path=topics.mock_scene, title="mock场景摘要"),
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


def _build_probe_layout(*, topics: TopicConfig, include_map_layer: bool) -> dict[str, Any]:
    three_d_key = "3D!main"
    confidence_key = "Gauge!confidence"
    mode_key = "Indicator!mode"
    health_key = "Indicator!health"
    depth_key = "Plot!depth"
    setpoint_key = "RawMessages!setpoint"

    config_by_id: dict[str, dict[str, Any]] = {
        three_d_key: _build_3d_config(topics=topics, include_map_layer=include_map_layer, mentor_mode=True),
        confidence_key: _build_gauge_config(
            title="置信度",
            path=_build_message_path(topic=topics.status, field=DISPLAY_FIELDS.status_confidence),
            min_value=0.0,
            max_value=1.0,
        ),
        mode_key: _build_indicator_config(
            title="模式",
            path=_build_message_path(topic=topics.setpoint, field=DISPLAY_FIELDS.setpoint_mode),
            style="background",
            font_size=24,
            rules=[
                _build_indicator_rule(raw_value="ZIGZAG_SEARCH", label="SEARCHING", color=COLORS.mode_searching),
                _build_indicator_rule(raw_value="PARALLEL_TRACKING", label="TRACKING", color=COLORS.mode_tracking),
            ],
            fallback_color=COLORS.mode_idle,
            fallback_label="UNKNOWN",
        ),
        health_key: _build_indicator_config(
            title="健康状态",
            path=_build_message_path(topic=topics.status, field=DISPLAY_FIELDS.status_battery_low),
            style="background",
            rules=[
                _build_indicator_rule(raw_value=False, label="POWER OK", color=COLORS.status_ok),
                _build_indicator_rule(raw_value=True, label="BATTERY LOW", color=COLORS.status_warn),
            ],
            fallback_color=COLORS.status_idle,
            fallback_label="UNKNOWN",
        ),
        depth_key: _build_plot_config(
            title="深度跟踪 Probe",
            y_axis_label="深度 (m)",
            series=[
                _build_plot_series(topic=topics.depth, value=PLOT_FIELDS.depth_value, color=COLORS.depth_actual),
                _build_plot_series(topic=topics.setpoint, value=PLOT_FIELDS.setpoint_depth, color=COLORS.depth_target),
            ],
            min_y_value=0.0,
            max_y_value=15.0,
        ),
        setpoint_key: _build_raw_config(topic_path=topics.setpoint, title="控制目标 Probe"),
    }

    layout_tree = _split(
        "row",
        three_d_key,
        _split(
            "column",
            _split("column", mode_key, _split("row", confidence_key, health_key, 58), 42),
            _split("column", depth_key, setpoint_key, 66),
            48,
        ),
        70,
    )
    return {
        "configById": config_by_id,
        "globalVariables": {},
        "userNodes": {},
        "playbackConfig": {"speed": 1},
        "layout": layout_tree,
    }


def _build_mentor_demo_layout(*, topics: TopicConfig, include_map_layer: bool) -> dict[str, Any]:
    three_d_key = "3D!main"
    mode_key = "Markdown!mode"
    bt_status_key = "Markdown!bt_status"
    confidence_key = "Gauge!confidence"
    confidence_text_key = "Markdown!confidence_text"
    leak_key = "Indicator!leak"
    power_key = "Markdown!power"
    top_view_key = "3D!topview"
    error_key = "Plot!tracking_error"
    speed_key = "Plot!speed_control"
    cable_plot_key = "Plot!cable_tracking"
    cable_quality_key = "Plot!cable_quality"
    cable_tracking_key = "RawMessages!cable_tracking"
    cable_diag_key = "RawMessages!cable_diagnostics"
    dlt_summary_key = "Markdown!dlt1278_summary"

    config_by_id: dict[str, dict[str, Any]] = {
        three_d_key: _build_3d_config(topics=topics, include_map_layer=include_map_layer, mentor_mode=True),
        mode_key: _build_markdown_config(
            message_path=_build_message_path(topic=topics.setpoint, field=DISPLAY_FIELDS.setpoint_mode),
            font_size=30,
        ),
        bt_status_key: _build_markdown_config(
            message_path=_build_message_path(topic=topics.bt_status, field=DISPLAY_FIELDS.string_data),
            font_size=14,
        ),
        confidence_key: _build_gauge_config(
            title="定位置信度",
            path=_build_message_path(topic=topics.status, field=DISPLAY_FIELDS.status_confidence),
            min_value=0.0,
            max_value=1.0,
            style="bar",
        ),
        confidence_text_key: _build_markdown_config(
            message_path=_build_message_path(topic=topics.confidence_text, field=DISPLAY_FIELDS.string_data),
            font_size=26,
        ),
        leak_key: _build_indicator_config(
            title="渗漏风险",
            path=_build_message_path(topic=topics.status, field=DISPLAY_FIELDS.status_leak_level),
            style="background",
            rules=[
                _build_indicator_rule(raw_value=0, label="LEAK NONE", color=COLORS.status_ok),
                _build_indicator_rule(raw_value=1, label="LEAK WATCH", color=COLORS.status_warn),
                _build_indicator_rule(raw_value=2, label="LEAK ALERT", color=COLORS.status_error),
                _build_indicator_rule(raw_value=3, label="LEAK CRITICAL", color=COLORS.mode_emergency),
            ],
            fallback_color=COLORS.status_idle,
            fallback_label="UNKNOWN",
        ),
        power_key: _build_markdown_config(
            message_path=_build_message_path(topic=topics.power_text, field=DISPLAY_FIELDS.string_data),
            font_size=24,
        ),
        top_view_key: _build_top_view_config(topics=topics),
        error_key: _build_plot_config(
            title="Tracking Error",
            y_axis_label="误差 (m)",
            series=[
                _build_plot_series(topic=topics.diagnostics, value=PLOT_FIELDS.diagnostic_depth_error, color=COLORS.depth_error),
                _build_plot_series(topic=topics.diagnostics, value=PLOT_FIELDS.diagnostic_lateral_error, color=COLORS.lateral_error),
            ],
            following_view_width=90.0,
        ),
        speed_key: _build_plot_config(
            title="速度闭环",
            y_axis_label="速度 (m/s)",
            series=[
                _build_plot_series(topic=topics.dvl, value=PLOT_FIELDS.dvl_speed_x, color=COLORS.speed_actual),
                _build_plot_series(topic=topics.setpoint, value=PLOT_FIELDS.setpoint_speed, color=COLORS.speed_target),
            ],
            min_y_value=0.0,
            max_y_value=1.0,
            following_view_width=90.0,
        ),
        cable_plot_key: _build_plot_config(
            title="电缆跟踪核心量",
            y_axis_label="m / confidence",
            series=[
                _build_plot_series(topic=topics.cable_tracking, value=PLOT_FIELDS.cable_cross_track, color=COLORS.lateral_error),
                _build_plot_series(topic=topics.cable_tracking, value=PLOT_FIELDS.cable_burial_depth, color=COLORS.depth_target),
                _build_plot_series(topic=topics.cable_tracking, value=PLOT_FIELDS.cable_burial_sigma, color=COLORS.depth_error),
                _build_plot_series(topic=topics.cable_tracking, value=PLOT_FIELDS.cable_confidence, color=COLORS.confidence_high),
            ],
            following_view_width=90.0,
        ),
        cable_quality_key: _build_plot_config(
            title="声磁质量与验收证据",
            y_axis_label="SNR dB / confidence",
            series=[
                _build_plot_series(topic=topics.cable_tracking, value=PLOT_FIELDS.cable_magnetic_snr, color=COLORS.status_warn),
                _build_plot_series(topic=topics.cable_tracking, value=PLOT_FIELDS.cable_magnetic_confidence, color=COLORS.confidence_high),
                _build_plot_series(topic=topics.cable_tracking, value=PLOT_FIELDS.cable_confidence, color=COLORS.mode_tracking),
            ],
            following_view_width=90.0,
        ),
        cable_tracking_key: _build_raw_config(topic_path=topics.cable_tracking, title="电缆跟踪输出"),
        cable_diag_key: _build_raw_config(topic_path=topics.cable_diagnostics, title="电缆诊断/限幅"),
        dlt_summary_key: _build_markdown_config(
            message_path=_build_message_path(topic=topics.dlt1278_summary, field=DISPLAY_FIELDS.string_data),
            font_size=14,
        ),
    }

    status_row = _split(
        "row",
        _split("column", confidence_text_key, confidence_key, 34),
        _split("column", leak_key, power_key, 50),
        48,
    )

    lower_row = _split(
        "row",
        _split("column", error_key, speed_key, 54),
        _split(
            "column",
            top_view_key,
            _split(
                "column",
                _split("row", cable_plot_key, cable_quality_key, 50),
                _split("row", cable_tracking_key, cable_diag_key, 50),
                52,
            ),
            52,
        ),
        58,
    )

    cable_status_row = _split("row", bt_status_key, dlt_summary_key, 50)

    right_column = _split(
        "column",
        _split("column", mode_key, status_row, 30),
        _split("column", lower_row, cable_status_row, 82),
        36,
    )

    return {
        "configById": config_by_id,
        "globalVariables": {},
        "userNodes": {},
        "playbackConfig": {"speed": 1},
        "layout": _split("row", three_d_key, right_column, 68),
    }


def _build_pilot_1366_layout(*, topics: TopicConfig, include_map_layer: bool) -> dict[str, Any]:
    """Driving/debug layout tuned for a 1366x1024 browser viewport.

    Keep the operator loop on one screen. The 3D view is intentionally a small
    right-side situational pane; cable tracking and control trends get the main
    screen area at 1366x1024.
    """
    three_d_key = "3D!main"
    mode_key = "Markdown!mode"
    confidence_key = "Gauge!confidence"
    confidence_text_key = "Markdown!confidence_text"
    power_key = "Markdown!power"
    cable_ready_key = "Indicator!cable_ready"
    cable_pass_key = "Indicator!cable_pass"
    dlt_state_key = "Indicator!dlt1278_state"
    dlt_score_key = "Gauge!dlt1278_score"
    cable_status_key = "Markdown!cable_status"
    cable_flags_key = "Markdown!cable_flags"
    dlt_summary_key = "Markdown!dlt1278_summary"
    cable_confidence_key = "Gauge!cable_confidence"
    error_key = "Plot!tracking_error"
    speed_key = "Plot!speed_control"
    cable_tracking_key = "RawMessages!cable_tracking"

    config_by_id: dict[str, dict[str, Any]] = {
        three_d_key: _build_3d_config(topics=topics, include_map_layer=include_map_layer, mentor_mode=True),
        mode_key: _build_markdown_config(
            message_path=_build_message_path(topic=topics.setpoint, field=DISPLAY_FIELDS.setpoint_mode),
            font_size=26,
        ),
        confidence_key: _build_gauge_config(
            title="定位置信度",
            path=_build_message_path(topic=topics.status, field=DISPLAY_FIELDS.status_confidence),
            min_value=0.0,
            max_value=1.0,
            style="bar",
        ),
        confidence_text_key: _build_markdown_config(
            message_path=_build_message_path(topic=topics.confidence_text, field=DISPLAY_FIELDS.string_data),
            font_size=20,
        ),
        power_key: _build_markdown_config(
            message_path=_build_message_path(topic=topics.power_text, field=DISPLAY_FIELDS.string_data),
            font_size=18,
        ),
        cable_ready_key: _build_indicator_config(
            title="电缆巡检 Ready",
            path=_build_message_path(topic=topics.cable_industrial_ready, field=DISPLAY_FIELDS.string_data),
            style="background",
            rules=[
                _build_indicator_rule(raw_value=True, label="READY", color=COLORS.status_ok),
                _build_indicator_rule(raw_value=False, label="NOT READY", color=COLORS.status_error),
            ],
            fallback_color=COLORS.status_idle,
            fallback_label="NO DATA",
            font_size=20,
        ),
        cable_pass_key: _build_indicator_config(
            title="工业验收 Pass",
            path=_build_message_path(topic=topics.cable_industrial_acceptance_pass, field=DISPLAY_FIELDS.string_data),
            style="background",
            rules=[
                _build_indicator_rule(raw_value=True, label="PASS", color=COLORS.status_ok),
                _build_indicator_rule(raw_value=False, label="FAIL", color=COLORS.status_error),
            ],
            fallback_color=COLORS.status_idle,
            fallback_label="NO DATA",
            font_size=20,
        ),
        dlt_state_key: _build_indicator_config(
            title="DL/T状态",
            path=_build_message_path(topic=topics.dlt1278_state, field=DISPLAY_FIELDS.string_data),
            style="background",
            rules=[
                _build_indicator_rule(raw_value="正常状态", label="正常", color=COLORS.status_ok),
                _build_indicator_rule(raw_value="注意状态", label="注意", color=COLORS.status_warn),
                _build_indicator_rule(raw_value="异常状态", label="异常", color=COLORS.status_error),
                _build_indicator_rule(raw_value="严重状态", label="严重", color=COLORS.mode_emergency),
            ],
            fallback_color=COLORS.status_idle,
            fallback_label="NO DATA",
            font_size=20,
        ),
        dlt_score_key: _build_gauge_config(
            title="DL/T总分",
            path=_build_message_path(topic=topics.dlt1278_total_score, field=DISPLAY_FIELDS.string_data),
            min_value=0.0,
            max_value=100.0,
            style="bar",
            reverse=True,
        ),
        cable_status_key: _build_markdown_config(
            message_path=_build_message_path(topic=topics.cable_status_text, field=DISPLAY_FIELDS.string_data),
            font_size=15,
        ),
        cable_flags_key: _build_markdown_config(
            message_path=_build_message_path(topic=topics.cable_acceptance_flags, field=DISPLAY_FIELDS.string_data),
            font_size=18,
        ),
        dlt_summary_key: _build_markdown_config(
            message_path=_build_message_path(topic=topics.dlt1278_summary, field=DISPLAY_FIELDS.string_data),
            font_size=14,
        ),
        cable_confidence_key: _build_gauge_config(
            title="电缆置信度",
            path=_build_message_path(topic=topics.cable_confidence, field=DISPLAY_FIELDS.string_data),
            min_value=0.0,
            max_value=1.0,
            style="bar",
        ),
        error_key: _build_plot_config(
            title="跟踪误差",
            y_axis_label="误差 (m)",
            series=[
                _build_plot_series(topic=topics.diagnostics, value=PLOT_FIELDS.diagnostic_depth_error, color=COLORS.depth_error),
                _build_plot_series(topic=topics.diagnostics, value=PLOT_FIELDS.diagnostic_lateral_error, color=COLORS.lateral_error),
            ],
            following_view_width=90.0,
            sidebar_dimension=150,
        ),
        speed_key: _build_plot_config(
            title="速度闭环",
            y_axis_label="速度 (m/s)",
            series=[
                _build_plot_series(topic=topics.dvl, value=PLOT_FIELDS.dvl_speed_x, color=COLORS.speed_actual),
                _build_plot_series(topic=topics.setpoint, value=PLOT_FIELDS.setpoint_speed, color=COLORS.speed_target),
            ],
            min_y_value=0.0,
            max_y_value=1.0,
            following_view_width=90.0,
            sidebar_dimension=150,
        ),
        cable_tracking_key: _build_raw_config(topic_path=topics.cable_tracking, title="电缆 ready/pass JSON"),
    }

    status_grid = _split(
        "row",
        _split("column", mode_key, confidence_text_key, 48),
        _split("column", confidence_key, power_key, 56),
        46,
    )
    cable_summary = _split(
        "column",
        _split("row", _split("row", cable_ready_key, cable_pass_key, 50), _split("row", dlt_state_key, dlt_score_key, 50), 52),
        _split("row", cable_status_key, _split("column", cable_flags_key, dlt_summary_key, 36), 56),
        44,
    )
    trend_band = _split("row", speed_key, error_key, 50)
    main_column = _split("column", cable_summary, trend_band, 62)
    situational_column = _split("column", three_d_key, _split("column", status_grid, cable_tracking_key, 52), 50)

    return {
        "configById": config_by_id,
        "globalVariables": {},
        "userNodes": {},
        "playbackConfig": {"speed": 1},
        "layout": _split("row", main_column, situational_column, 68),
    }


def _build_acceptance_1366_layout(*, topics: TopicConfig, include_map_layer: bool) -> dict[str, Any]:
    """Cable acceptance/reporting layout tuned for a 1366x1024 browser viewport."""
    top_view_key = "3D!topview"
    cable_plot_key = "Plot!cable_tracking"
    cable_quality_key = "Plot!cable_quality"
    cable_tracking_key = "RawMessages!cable_tracking"
    cable_diag_key = "RawMessages!cable_diagnostics"
    cable_ready_key = "Indicator!cable_ready"
    cable_pass_key = "Indicator!cable_pass"
    dlt_state_key = "Indicator!dlt1278_state"
    dlt_score_key = "Gauge!dlt1278_score"
    dlt_summary_key = "Markdown!dlt1278_summary"
    cable_status_key = "Markdown!cable_status"
    cable_flags_key = "Markdown!cable_flags"
    bt_status_key = "Markdown!bt_status"

    config_by_id: dict[str, dict[str, Any]] = {
        top_view_key: _build_top_view_config(topics=topics),
        cable_plot_key: _build_plot_config(
            title="电缆跟踪核心量",
            y_axis_label="m / confidence",
            series=[
                _build_plot_series(topic=topics.cable_cross_track, value=PLOT_FIELDS.scalar_data, color=COLORS.lateral_error),
                _build_plot_series(topic=topics.cable_burial_depth, value=PLOT_FIELDS.scalar_data, color=COLORS.depth_target),
                _build_plot_series(topic=topics.cable_burial_sigma, value=PLOT_FIELDS.scalar_data, color=COLORS.depth_error),
                _build_plot_series(topic=topics.cable_confidence, value=PLOT_FIELDS.scalar_data, color=COLORS.confidence_high),
            ],
            following_view_width=120.0,
            sidebar_dimension=180,
        ),
        cable_quality_key: _build_plot_config(
            title="声磁质量与验收证据",
            y_axis_label="SNR dB / confidence",
            series=[
                _build_plot_series(topic=topics.cable_magnetic_snr, value=PLOT_FIELDS.scalar_data, color=COLORS.status_warn),
                _build_plot_series(topic=topics.cable_magnetic_confidence, value=PLOT_FIELDS.scalar_data, color=COLORS.confidence_high),
                _build_plot_series(topic=topics.cable_confidence, value=PLOT_FIELDS.scalar_data, color=COLORS.mode_tracking),
            ],
            following_view_width=120.0,
            sidebar_dimension=180,
        ),
        cable_tracking_key: _build_raw_config(topic_path=topics.cable_tracking, title="电缆跟踪输出"),
        cable_diag_key: _build_raw_config(topic_path=topics.cable_diagnostics, title="电缆诊断/限幅"),
        cable_ready_key: _build_indicator_config(
            title="工业结论",
            path=_build_message_path(topic=topics.cable_industrial_ready, field=DISPLAY_FIELDS.string_data),
            style="background",
            rules=[
                _build_indicator_rule(raw_value=True, label="READY", color=COLORS.status_ok),
                _build_indicator_rule(raw_value=False, label="NOT READY", color=COLORS.status_error),
            ],
            fallback_color=COLORS.status_idle,
            fallback_label="NO DATA",
            font_size=20,
        ),
        cable_pass_key: _build_indicator_config(
            title="工业验收",
            path=_build_message_path(topic=topics.cable_industrial_acceptance_pass, field=DISPLAY_FIELDS.string_data),
            style="background",
            rules=[
                _build_indicator_rule(raw_value=True, label="PASS", color=COLORS.status_ok),
                _build_indicator_rule(raw_value=False, label="FAIL", color=COLORS.status_error),
            ],
            fallback_color=COLORS.status_idle,
            fallback_label="NO DATA",
            font_size=20,
        ),
        dlt_state_key: _build_indicator_config(
            title="DL/T状态",
            path=_build_message_path(topic=topics.dlt1278_state, field=DISPLAY_FIELDS.string_data),
            style="background",
            rules=[
                _build_indicator_rule(raw_value="正常状态", label="正常", color=COLORS.status_ok),
                _build_indicator_rule(raw_value="注意状态", label="注意", color=COLORS.status_warn),
                _build_indicator_rule(raw_value="异常状态", label="异常", color=COLORS.status_error),
                _build_indicator_rule(raw_value="严重状态", label="严重", color=COLORS.mode_emergency),
            ],
            fallback_color=COLORS.status_idle,
            fallback_label="NO DATA",
            font_size=20,
        ),
        dlt_score_key: _build_gauge_config(
            title="DL/T总分",
            path=_build_message_path(topic=topics.dlt1278_total_score, field=DISPLAY_FIELDS.string_data),
            min_value=0.0,
            max_value=100.0,
            style="bar",
            reverse=True,
        ),
        dlt_summary_key: _build_markdown_config(
            message_path=_build_message_path(topic=topics.dlt1278_summary, field=DISPLAY_FIELDS.string_data),
            font_size=14,
        ),
        cable_status_key: _build_markdown_config(
            message_path=_build_message_path(topic=topics.cable_status_text, field=DISPLAY_FIELDS.string_data),
            font_size=15,
        ),
        cable_flags_key: _build_markdown_config(
            message_path=_build_message_path(topic=topics.cable_acceptance_flags, field=DISPLAY_FIELDS.string_data),
            font_size=18,
        ),
        bt_status_key: _build_markdown_config(
            message_path=_build_message_path(topic=topics.bt_status, field=DISPLAY_FIELDS.string_data),
            font_size=14,
        ),
    }

    plot_row = _split("row", cable_plot_key, cable_quality_key, 50)
    raw_row = _split("row", cable_tracking_key, cable_diag_key, 50)
    status_row = _split(
        "row",
        _split("row", cable_ready_key, cable_pass_key, 50),
        _split("row", dlt_state_key, dlt_score_key, 50),
        48,
    )
    text_row = _split("row", cable_status_key, _split("column", cable_flags_key, dlt_summary_key, 34), 58)
    evidence_column = _split(
        "column",
        _split("column", status_row, text_row, 42),
        _split("column", plot_row, _split("column", raw_row, bt_status_key, 74), 42),
        34,
    )

    return {
        "configById": config_by_id,
        "globalVariables": {},
        "userNodes": {},
        "playbackConfig": {"speed": 1},
        "layout": _split("row", evidence_column, top_view_key, 72),
    }


def build_auv_layout(
    *,
    include_map_layer: bool = False,
    topics: TopicConfig | None = None,
    layout_name: str = "AUV数据可视化",
    layout_description: str = "AUV传感器与数字孪生可视化面板",
    layout_id: str = "auv-data-visualization",
    profile: LayoutProfile = "mentor-demo",
) -> dict[str, Any]:
    """Construct the Foxglove Desktop layout for the AUV stack."""
    topics = topics or TOPICS

    _ = (layout_name, layout_description, layout_id)

    if profile == "classic":
        return _build_classic_layout(topics=topics, include_map_layer=include_map_layer)
    if profile == "probe":
        return _build_probe_layout(topics=topics, include_map_layer=include_map_layer)
    if profile == "mentor-demo":
        return _build_mentor_demo_layout(topics=topics, include_map_layer=include_map_layer)
    if profile == "pilot-1366":
        return _build_pilot_1366_layout(topics=topics, include_map_layer=include_map_layer)
    if profile == "acceptance-1366":
        return _build_acceptance_1366_layout(topics=topics, include_map_layer=include_map_layer)
    raise ValueError(f"Unsupported layout profile: {profile}")
