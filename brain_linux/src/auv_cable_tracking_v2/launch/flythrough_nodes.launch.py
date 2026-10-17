"""Opt-in PVS flythrough diagnostic stack; no bridge or hardware by default."""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    share = get_package_share_directory('auv_cable_tracking_v2')
    config = os.path.join(share, 'config', 'cable_tracking_v2_flythrough.yaml')
    bridge_config = os.path.join(share, 'config', 'inspection_bridge_passive.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('config_file', default_value=config),
        DeclareLaunchArgument('bridge_config_file', default_value=bridge_config),
        DeclareLaunchArgument('enable_passive_bridge', default_value='false'),
        DeclareLaunchArgument('enable_sonar_quality', default_value='false'),
        DeclareLaunchArgument('sonar_calibration_file', default_value=''),
        DeclareLaunchArgument('calibration_domain', default_value='physical'),
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        DeclareLaunchArgument('speed_feedforward_b', default_value='40.0'),
        DeclareLaunchArgument('inspection_budget_status_timeout_s', default_value='1.5'),
        DeclareLaunchArgument('inspection_setpoint_timeout_s', default_value='0.5'),
        Node(package='auv_cable_tracking_v2', executable='cable_tracking_v2_node',
             parameters=[{'config_file': LaunchConfiguration('config_file'),
                          'use_sim_time': ParameterValue(
                              LaunchConfiguration('use_sim_time'), value_type=bool)}], output='screen'),
        Node(package='auv_decision_ros', executable='perception_quality_node',
             condition=IfCondition(LaunchConfiguration('enable_sonar_quality')),
             parameters=[{'sonar_calibration_file': LaunchConfiguration('sonar_calibration_file'),
                          'calibration_domain': LaunchConfiguration('calibration_domain'),
                          'use_sim_time': ParameterValue(
                              LaunchConfiguration('use_sim_time'), value_type=bool)}], output='screen'),
        Node(package='auv_cable_tracking_v2', executable='inspection_controller_node',
             parameters=[{'heading_mode': 'SETPOINT', 'depth_mode': 'SETPOINT',
                          'publish_arbiter_command': True, 'inspection_input_timeout_s': 1.5,
                          'use_sim_time': ParameterValue(
                              LaunchConfiguration('use_sim_time'), value_type=bool),
                          'inspection_speed_feedforward_b': ParameterValue(
                              LaunchConfiguration('speed_feedforward_b'), value_type=float)}],
             output='screen'),
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
