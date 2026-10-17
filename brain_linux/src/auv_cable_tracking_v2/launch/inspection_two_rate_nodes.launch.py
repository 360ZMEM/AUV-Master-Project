"""Opt-in process-isolated inspection candidate gate; bridge stays passive."""
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
    config = os.path.join(share, 'config', 'cable_tracking_v2_inspection.yaml')
    bridge = os.path.join(share, 'config', 'inspection_bridge_passive.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('config_file', default_value=config),
        DeclareLaunchArgument('bridge_config_file', default_value=bridge),
        DeclareLaunchArgument('enable_passive_bridge', default_value='false'),
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        DeclareLaunchArgument('candidate_timeout_s', default_value='0.35'),
        DeclareLaunchArgument('maximum_candidate_displacement_m', default_value='0.35'),
        DeclareLaunchArgument('declared_current_bound_mps', default_value='0.05'),
        DeclareLaunchArgument('output_thread_enabled', default_value='false'),
        DeclareLaunchArgument('inspection_decision_period_s', default_value='0.1'),
        DeclareLaunchArgument('inspection_latest_navigation_qos', default_value='false'),
        DeclareLaunchArgument('inspection_snapshot_freshness', default_value='false'),
        DeclareLaunchArgument('inspection_recoverable_input_stale', default_value='false'),
        DeclareLaunchArgument('sensor_timeout_s', default_value='0.5'),
        DeclareLaunchArgument('budget_timeout_s', default_value='1.5'),
        DeclareLaunchArgument('speed_feedforward_b', default_value='40.0'),
        DeclareLaunchArgument('controller_setpoint_source_timeout_s', default_value='0.0'),
        Node(package='auv_cable_tracking_v2', executable='cable_tracking_v2_node',
             name='auv_cable_tracking_v2_estimator', output='screen',
             remappings=[('/auv/control/setpoint', '/auv/control/setpoint_candidate')],
             parameters=[{'config_file': LaunchConfiguration('config_file'),
                          'inspection_decision_period_s': ParameterValue(
                              LaunchConfiguration('inspection_decision_period_s'), value_type=float),
                          'inspection_latest_navigation_qos': ParameterValue(
                              LaunchConfiguration('inspection_latest_navigation_qos'), value_type=bool),
                          'inspection_snapshot_freshness': ParameterValue(
                              LaunchConfiguration('inspection_snapshot_freshness'), value_type=bool),
                          'inspection_recoverable_input_stale': ParameterValue(
                              LaunchConfiguration('inspection_recoverable_input_stale'), value_type=bool),
                          'use_sim_time': ParameterValue(LaunchConfiguration('use_sim_time'), value_type=bool)}]),
        Node(package='auv_cable_tracking_v2', executable='inspection_setpoint_supervisor_node',
             name='auv_inspection_setpoint_supervisor', output='screen',
             parameters=[{'candidate_timeout_s': ParameterValue(
                            LaunchConfiguration('candidate_timeout_s'), value_type=float),
                          'sensor_timeout_s': ParameterValue(
                            LaunchConfiguration('sensor_timeout_s'), value_type=float),
                          'maximum_candidate_displacement_m': ParameterValue(
                            LaunchConfiguration('maximum_candidate_displacement_m'), value_type=float),
                          'declared_current_bound_mps': ParameterValue(
                            LaunchConfiguration('declared_current_bound_mps'), value_type=float),
                          'output_thread_enabled': ParameterValue(
                              LaunchConfiguration('output_thread_enabled'), value_type=bool),
                          'budget_timeout_s': ParameterValue(
                            LaunchConfiguration('budget_timeout_s'), value_type=float),
                          'use_sim_time': ParameterValue(LaunchConfiguration('use_sim_time'), value_type=bool)}]),
        Node(package='auv_cable_tracking_v2', executable='inspection_controller_node',
             parameters=[{'heading_mode': 'SETPOINT', 'depth_mode': 'SETPOINT',
                          'publish_arbiter_command': True, 'inspection_input_timeout_s': 1.5,
                          'inspection_speed_feedforward_b': ParameterValue(
                              LaunchConfiguration('speed_feedforward_b'), value_type=float),
                          'inspection_setpoint_source_timeout_s': ParameterValue(
                              LaunchConfiguration('controller_setpoint_source_timeout_s'), value_type=float),
                          'use_sim_time': ParameterValue(LaunchConfiguration('use_sim_time'), value_type=bool)}],
             output='screen'),
        Node(package='auv_cable_tracking_v2', executable='inspection_bridge_node',
             condition=IfCondition(LaunchConfiguration('enable_passive_bridge')),
             parameters=[{'params_file': LaunchConfiguration('bridge_config_file'),
                          'passive_mode': True, 'bridge_backend': 'protocol_udp',
                          'inspection_budget_status_timeout_s': 1.5,
                          'inspection_setpoint_timeout_s': .5}], output='screen'),
    ])
