"""Passive full-stack wiring for flythrough inspection review.

The base stack provides localization, supervisor and visualization. Its
general bridge, controller, decision and mission injector are disabled;
the inspection-specific nodes own those interfaces. The bridge is always
passive here and cannot send actuator commands to PC104.
"""

from pathlib import Path

import yaml

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def require_flythrough_config(context):
    path = Path(LaunchConfiguration('config_file').perform(context)).expanduser()
    with path.open(encoding='utf-8') as stream:
        document = yaml.safe_load(stream) or {}
    cable = document.get('cable_tracking', {}) if isinstance(document, dict) else {}
    v2 = cable.get('v2', {}) if isinstance(cable, dict) else {}
    geometry = v2.get('mission_geometry') if isinstance(v2, dict) else None
    if geometry != 'flythrough':
        raise RuntimeError('inspection_shadow_stack requires v2.mission_geometry: flythrough')
    if LaunchConfiguration('enable_imu_sidecar').perform(context).lower() == 'true':
        bridge_path = Path(LaunchConfiguration('bridge_config_file').perform(context)).expanduser()
        with bridge_path.open(encoding='utf-8') as stream:
            bridge_document = yaml.safe_load(stream) or {}
        bridge = bridge_document.get('bridge', {})
        udp = bridge.get('protocol_udp', {})
        if (bridge.get('inspection_sensor_source') != 'imu_sidecar_candidate'
                or bridge.get('passive_mode') is not True
                or udp.get('local_host') != '127.0.0.1'
                or udp.get('remote_host') != '127.0.0.1'):
            raise RuntimeError('IMU sidecar requires reviewed passive loopback candidate bridge profile')
        if LaunchConfiguration('use_sim_time').perform(context).lower() == 'true':
            raise RuntimeError('IMU sidecar UDP receiver requires wall-clock ROS time')
    return []


def generate_launch_description():
    v2_share = Path(get_package_share_directory('auv_cable_tracking_v2'))
    decision_share = Path(get_package_share_directory('auv_decision_ros'))
    base_launch = decision_share / 'launch/auv_stack.launch.py'
    base_params = decision_share / 'config/params.yaml'
    bridge_params = v2_share / 'config/inspection_bridge_passive.yaml'

    base_stack = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(base_launch)),
        launch_arguments={
            'params_file': LaunchConfiguration('params_file'),
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'navigation_imu_max_age_s': LaunchConfiguration('inspection_navigation_imu_max_age_s'),
            'enable_bridge': 'false',
            'enable_controller': 'false',
            'enable_decision': 'false',
            'enable_cable_tracking': 'false',
            'enable_cable_mission_autostart': 'false',
            'enable_localization': LaunchConfiguration('enable_localization'),
            'enable_sensor_supervisor': LaunchConfiguration('enable_sensor_supervisor'),
            'enable_viz_bridge': LaunchConfiguration('enable_viz_bridge'),
            'viz_mock_mode': 'false',
            'viz_allow_synthetic_scene_fallback': 'false',
            'viz_publish_sim_ground_truth': 'false',
            'enable_perception_quality_shadow': 'false',
            'enable_tracking_authority_shadow': 'false',
            'start_ros2dds_bridge': 'false',
            'enable_real_magnetic_wrapper': LaunchConfiguration('enable_real_magnetic_wrapper'),
            'magnetic_wrapper_params_file': LaunchConfiguration('magnetic_wrapper_params_file'),
        }.items(),
    )
    return LaunchDescription([
        DeclareLaunchArgument('config_file', description='Reviewed flythrough v2 YAML; required'),
        DeclareLaunchArgument('params_file', default_value=str(base_params)),
        DeclareLaunchArgument('bridge_config_file', default_value=str(bridge_params)),
        DeclareLaunchArgument('enable_localization', default_value='true'),
        DeclareLaunchArgument('enable_sensor_supervisor', default_value='true'),
        DeclareLaunchArgument('enable_viz_bridge', default_value='true'),
        DeclareLaunchArgument('enable_real_magnetic_wrapper', default_value='false'),
        DeclareLaunchArgument('magnetic_wrapper_params_file', default_value=''),
        DeclareLaunchArgument('enable_sonar_quality', default_value='false'),
        DeclareLaunchArgument('sonar_calibration_file', default_value=''),
        DeclareLaunchArgument('calibration_domain', default_value='physical'),
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        DeclareLaunchArgument('inspection_navigation_imu_max_age_s', default_value='0.75'),
        DeclareLaunchArgument('inspection_navigation_heading_uncertainty_source', default_value='ekf'),
        DeclareLaunchArgument('inspection_speed_feedforward_b', default_value='40.0'),
        DeclareLaunchArgument('inspection_controller_setpoint_source_timeout_s', default_value='0.0'),
        DeclareLaunchArgument('inspection_budget_status_timeout_s', default_value='1.5'),
        DeclareLaunchArgument('inspection_setpoint_timeout_s', default_value='0.5'),
        DeclareLaunchArgument('enable_imu_sidecar', default_value='false'),
        DeclareLaunchArgument('imu_sidecar_port', default_value='53667'),
        DeclareLaunchArgument('imu_sidecar_synthetic_navigation', default_value='false'),
        DeclareLaunchArgument('imu_sidecar_yaw_alignment_deg', default_value='9999.0'),
        DeclareLaunchArgument('imu_sidecar_synthetic_orientation_variance_rad2', default_value='0.0'),
        OpaqueFunction(function=require_flythrough_config),
        base_stack,
        Node(
            package='auv_cable_tracking_v2', executable='cable_tracking_v2_node',
            name='auv_cable_tracking_v2_node', output='screen',
            parameters=[{
                'config_file': LaunchConfiguration('config_file'),
                'use_sim_time': ParameterValue(LaunchConfiguration('use_sim_time'), value_type=bool),
                'navigation_heading_uncertainty_source': LaunchConfiguration(
                    'inspection_navigation_heading_uncertainty_source'),
            }],
        ),
        Node(
            package='auv_decision_ros', executable='perception_quality_node',
            condition=IfCondition(LaunchConfiguration('enable_sonar_quality')),
            output='screen', parameters=[{
                'sonar_calibration_file': LaunchConfiguration('sonar_calibration_file'),
                'calibration_domain': LaunchConfiguration('calibration_domain'),
                'use_sim_time': ParameterValue(LaunchConfiguration('use_sim_time'), value_type=bool),
            }],
        ),
        Node(
            package='auv_cable_tracking_v2', executable='inspection_controller_node',
            name='auv_inspection_controller_node', output='screen',
            parameters=[{
                'heading_mode': 'SETPOINT', 'depth_mode': 'SETPOINT',
                'publish_arbiter_command': True,
                'inspection_input_timeout_s': 1.5,
                'inspection_speed_feedforward_b': ParameterValue(
                    LaunchConfiguration('inspection_speed_feedforward_b'), value_type=float),
                'inspection_setpoint_source_timeout_s': ParameterValue(
                    LaunchConfiguration('inspection_controller_setpoint_source_timeout_s'), value_type=float),
                'use_sim_time': ParameterValue(LaunchConfiguration('use_sim_time'), value_type=bool),
            }],
        ),
        Node(
            package='auv_cable_tracking_v2', executable='inspection_bridge_node',
            name='auv_inspection_bridge_node', output='screen',
            parameters=[{
                'params_file': LaunchConfiguration('bridge_config_file'),
                'passive_mode': True,
                'bridge_backend': 'protocol_udp',
                'inspection_budget_status_timeout_s': ParameterValue(
                    LaunchConfiguration('inspection_budget_status_timeout_s'), value_type=float),
                'inspection_setpoint_timeout_s': ParameterValue(
                    LaunchConfiguration('inspection_setpoint_timeout_s'), value_type=float),
            }],
        ),
        Node(
            package='auv_cable_tracking_v2', executable='imu_sidecar_node',
            condition=IfCondition(LaunchConfiguration('enable_imu_sidecar')),
            name='auv_inspection_imu_sidecar_node', output='screen',
            parameters=[{
                'local_host': '127.0.0.1',
                'source_host': '127.0.0.1',
                'local_port': ParameterValue(LaunchConfiguration('imu_sidecar_port'), value_type=int),
                'publish_navigation_imu': ParameterValue(
                    LaunchConfiguration('imu_sidecar_synthetic_navigation'), value_type=bool),
                'synthetic_fixture_only': ParameterValue(
                    LaunchConfiguration('imu_sidecar_synthetic_navigation'), value_type=bool),
                'yaw_alignment_deg': ParameterValue(
                    LaunchConfiguration('imu_sidecar_yaw_alignment_deg'), value_type=float),
                'synthetic_orientation_variance_rad2': ParameterValue(
                    LaunchConfiguration('imu_sidecar_synthetic_orientation_variance_rad2'), value_type=float),
            }],
        ),
    ])
