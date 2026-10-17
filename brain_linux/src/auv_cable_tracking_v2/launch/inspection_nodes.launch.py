"""Inspection algorithm + guarded controller; no bridge or hardware startup."""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    config = os.path.join(get_package_share_directory('auv_cable_tracking_v2'), 'config', 'cable_tracking_v2_inspection.yaml')
    bridge_config = os.path.join(get_package_share_directory('auv_cable_tracking_v2'), 'config', 'inspection_bridge_passive.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('config_file', default_value=config),
        DeclareLaunchArgument('bridge_config_file', default_value=bridge_config),
        DeclareLaunchArgument('enable_passive_bridge', default_value='false'),
        DeclareLaunchArgument('inspection_budget_status_timeout_s', default_value='1.5'),
        DeclareLaunchArgument('inspection_setpoint_timeout_s', default_value='0.5'),
        Node(package='auv_cable_tracking_v2', executable='cable_tracking_v2_node',
             parameters=[{'config_file': LaunchConfiguration('config_file')}], output='screen'),
        Node(package='auv_cable_tracking_v2', executable='inspection_controller_node',
             parameters=[{'heading_mode': 'SETPOINT', 'depth_mode': 'SETPOINT',
                          'publish_arbiter_command': True, 'inspection_input_timeout_s': 1.5}], output='screen'),
        Node(package='auv_cable_tracking_v2', executable='inspection_bridge_node',
             condition=IfCondition(LaunchConfiguration('enable_passive_bridge')),
             parameters=[{'params_file': LaunchConfiguration('bridge_config_file'),
                          'passive_mode': True, 'bridge_backend': 'protocol_udp',
                          'inspection_budget_status_timeout_s': ParameterValue(
                              LaunchConfiguration('inspection_budget_status_timeout_s'),
                              value_type=float),
                          'inspection_setpoint_timeout_s': ParameterValue(
                              LaunchConfiguration('inspection_setpoint_timeout_s'),
                              value_type=float)}], output='screen'),
    ])
