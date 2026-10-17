"""Full ROS stack overlay that substitutes the independent cable v2 node."""

import os
from pathlib import Path

import yaml

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def reject_unguarded_inspection_stack(context):
    """Keep flythrough off the legacy controller/bridge full-stack path."""
    config_path = Path(LaunchConfiguration("config_file").perform(context)).expanduser()
    with config_path.open(encoding="utf-8") as stream:
        document = yaml.safe_load(stream) or {}
    cable = document.get("cable_tracking", {}) if isinstance(document, dict) else {}
    v2 = cable.get("v2", {}) if isinstance(cable, dict) else {}
    geometry = v2.get("mission_geometry") if isinstance(v2, dict) else None
    if str(geometry).strip().lower() in {"flythrough", "shallow_survey"}:
        raise RuntimeError(
            "inspection geometry requires the dedicated "
            "flythrough_nodes.launch.py controller and inspection bridge; "
            "auv_stack_v2.launch.py uses the general controller and bridge"
        )
    return []


def generate_launch_description() -> LaunchDescription:
    v2_share = get_package_share_directory("auv_cable_tracking_v2")
    decision_share = get_package_share_directory("auv_decision_ros")
    default_v2_config = os.path.join(v2_share, "config", "cable_tracking_v2.yaml")
    default_stack_params = os.path.join(decision_share, "config", "params.yaml")
    stack_launch = os.path.join(decision_share, "launch", "auv_stack.launch.py")

    config_arg = DeclareLaunchArgument("config_file", default_value=default_v2_config)
    params_arg = DeclareLaunchArgument("params_file", default_value=default_stack_params)
    bridge_backend_arg = DeclareLaunchArgument("bridge_backend", default_value="protocol_udp")
    protocol_mode_arg = DeclareLaunchArgument("protocol_control_mode_byte", default_value="238")
    motor_scale_arg = DeclareLaunchArgument("main_motor_rpm_scale", default_value="15.0")
    passive_mode_arg = DeclareLaunchArgument("passive_mode", default_value="false")
    enable_bridge_arg = DeclareLaunchArgument("enable_bridge", default_value="true")
    enable_localization_arg = DeclareLaunchArgument("enable_localization", default_value="true")
    enable_controller_arg = DeclareLaunchArgument("enable_controller", default_value="true")
    # The v2 node owns /auv/control/setpoint for cable missions.  Running the
    # legacy behavior-tree decision node at the same time creates two command
    # publishers and makes the controller alternate between incompatible
    # headings, which prevents a clean cross scan and FWHM estimate.
    enable_decision_arg = DeclareLaunchArgument("enable_decision", default_value="false")
    enable_sensor_supervisor_arg = DeclareLaunchArgument(
        "enable_sensor_supervisor", default_value="true"
    )
    enable_viz_bridge_arg = DeclareLaunchArgument("enable_viz_bridge", default_value="true")
    viz_mock_mode_arg = DeclareLaunchArgument("viz_mock_mode", default_value="false")
    viz_mock_fallback_timeout_arg = DeclareLaunchArgument(
        "viz_mock_fallback_timeout_s", default_value="2.0"
    )
    # A fresh stack must not silently reissue an inspection mission after a
    # process-local RECOVERY_REQUIRED latch. Synthetic demos opt in explicitly.
    enable_mission_arg = DeclareLaunchArgument("enable_cable_mission_autostart", default_value="false")
    mission_id_arg = DeclareLaunchArgument("cable_mission_id", default_value="")
    target_id_arg = DeclareLaunchArgument("cable_mission_target_id", default_value="")
    mission_depth_arg = DeclareLaunchArgument("cable_mission_target_depth", default_value="12.0")
    mission_speed_arg = DeclareLaunchArgument("cable_mission_target_speed_mps", default_value="0.8")

    base_stack = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(stack_launch),
        launch_arguments={
            "params_file": LaunchConfiguration("params_file"),
            "bridge_backend": LaunchConfiguration("bridge_backend"),
            "protocol_control_mode_byte": LaunchConfiguration("protocol_control_mode_byte"),
            "main_motor_rpm_scale": LaunchConfiguration("main_motor_rpm_scale"),
            "passive_mode": LaunchConfiguration("passive_mode"),
            "enable_bridge": LaunchConfiguration("enable_bridge"),
            "enable_localization": LaunchConfiguration("enable_localization"),
            "enable_controller": LaunchConfiguration("enable_controller"),
            "enable_decision": LaunchConfiguration("enable_decision"),
            "enable_sensor_supervisor": LaunchConfiguration("enable_sensor_supervisor"),
            "enable_viz_bridge": LaunchConfiguration("enable_viz_bridge"),
            "viz_mock_mode": LaunchConfiguration("viz_mock_mode"),
            "viz_mock_fallback_timeout_s": LaunchConfiguration("viz_mock_fallback_timeout_s"),
            "enable_cable_tracking": "false",
            "enable_cable_mission_autostart": LaunchConfiguration(
                "enable_cable_mission_autostart"
            ),
            "cable_mission_id": LaunchConfiguration("cable_mission_id"),
            "cable_mission_target_id": LaunchConfiguration("cable_mission_target_id"),
            "cable_mission_target_depth": LaunchConfiguration("cable_mission_target_depth"),
            "cable_mission_target_speed_mps": LaunchConfiguration(
                "cable_mission_target_speed_mps"
            ),
            "heading_mode": "SETPOINT",
            "cable_tracking_config": LaunchConfiguration("config_file"),
        }.items(),
    )
    v2_node = Node(
        package="auv_cable_tracking_v2",
        executable="cable_tracking_v2_node",
        name="auv_cable_tracking_v2_node",
        output="screen",
        parameters=[{"config_file": LaunchConfiguration("config_file")}],
    )
    return LaunchDescription(
        [
            config_arg,
            params_arg,
            bridge_backend_arg,
            protocol_mode_arg,
            motor_scale_arg,
            passive_mode_arg,
            enable_bridge_arg,
            enable_localization_arg,
            enable_controller_arg,
            enable_decision_arg,
            enable_sensor_supervisor_arg,
            enable_viz_bridge_arg,
            viz_mock_mode_arg,
            viz_mock_fallback_timeout_arg,
            enable_mission_arg,
            mission_id_arg,
            target_id_arg,
            mission_depth_arg,
            mission_speed_arg,
            OpaqueFunction(function=reject_unguarded_inspection_stack),
            base_stack,
            v2_node,
        ]
    )
