from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, TimerAction, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from pathlib import Path

def generate_nodes(context, *args, **kwargs):
    params = LaunchConfiguration('params_file')
    feature_flags = str(Path(__file__).resolve().parents[1] / 'config' / 'feature_flags.yaml')
    
    minimal = context.launch_configurations.get('minimal', 'false').lower() == 'true'
    passive_mode = context.launch_configurations.get('passive_mode', 'false').lower() == 'true'
    
    # 构建基础参数列表
    bridge_params = [{'params_file': params}, feature_flags, 
                    {'bridge_backend': LaunchConfiguration('bridge_backend')},
                    {'main_motor_rpm_scale': LaunchConfiguration('main_motor_rpm_scale')}]
    
    controller_params = [{'params_file': params}, feature_flags,
                        {'bypass_ekf': LaunchConfiguration('bypass_ekf')}]
    
    decision_params = [{'params_file': params}, feature_flags, {
        'confidence_threshold': 0.7,
        'bt_status_publish_period': 0.5,
        'tree_print_period': 5.0,
        'summary_log_period': 2.0,
        'bridge_backend': LaunchConfiguration('bridge_backend'),
        'protocol_control_mode_byte': LaunchConfiguration('protocol_control_mode_byte'),
        'debug_level': LaunchConfiguration('debug_level'),
        'transition_threshold_m': LaunchConfiguration('transition_threshold_m'),
        'transition_duration_s': LaunchConfiguration('transition_duration_s'),
        'mock_amd_timeout_s': LaunchConfiguration('mock_amd_timeout_s'),
    }]

    # 如果启用了 minimal 模式，追加覆盖参数
    if minimal:
        bridge_params.append({'passive_mode': True})
        controller_params.append({'bypass_zero_effort': True})
        decision_params.append({'enable_behavior_tree': False})
    else:
        bridge_params.append({'passive_mode': passive_mode})

    bridge = Node(
        package='auv_bridge',
        executable='zenoh_json_bridge_node',
        name='zenoh_json_bridge_node',
        condition=IfCondition(LaunchConfiguration('enable_bridge')),
        output='screen',
        parameters=bridge_params,
    )

    localization = Node(
        package='auv_localization',
        executable='auv_localization_node',
        name='auv_localization_node',
        condition=IfCondition(LaunchConfiguration('enable_localization')),
        output='screen',
        parameters=[
            {'params_file': params},
            feature_flags,
            {'world_frame_id': LaunchConfiguration('world_frame_id')},
            {'base_frame_id': LaunchConfiguration('base_frame_id')},
            {'imu_frame_id': LaunchConfiguration('imu_frame_id')},
            {'dvl_frame_id': LaunchConfiguration('dvl_frame_id')},
            {'depth_frame_id': LaunchConfiguration('depth_frame_id')},
            {'camera_frame_id': LaunchConfiguration('camera_frame_id')},
            {'sonar_frame_id': LaunchConfiguration('sonar_frame_id')},
            {'imu_frame_offset_xyz': LaunchConfiguration('imu_frame_offset_xyz')},
            {'dvl_frame_offset_xyz': LaunchConfiguration('dvl_frame_offset_xyz')},
            {'depth_frame_offset_xyz': LaunchConfiguration('depth_frame_offset_xyz')},
            {'camera_frame_offset_xyz': LaunchConfiguration('camera_frame_offset_xyz')},
            {'sonar_frame_offset_xyz': LaunchConfiguration('sonar_frame_offset_xyz')},
            {'publish_imu_tf': LaunchConfiguration('publish_imu_tf')},
            {'publish_dvl_tf': LaunchConfiguration('publish_dvl_tf')},
            {'publish_depth_tf': LaunchConfiguration('publish_depth_tf')},
            {'publish_camera_tf': LaunchConfiguration('publish_camera_tf')},
            {'publish_sonar_tf': LaunchConfiguration('publish_sonar_tf')},
            {'publish_sensor_status': LaunchConfiguration('publish_sensor_status')},
            {'publish_raw_state': LaunchConfiguration('publish_raw_state')},
            {'seabed_depth_m': LaunchConfiguration('seabed_depth_m')},
            {'seabed_proximity_margin_m': LaunchConfiguration('seabed_proximity_margin_m')},
        ],
    )

    controller = Node(
        package='auv_controller',
        executable='auv_controller_node',
        name='auv_controller_node',
        condition=IfCondition(LaunchConfiguration('enable_controller')),
        output='screen',
        parameters=controller_params,
    )

    decision = Node(
        package='auv_decision_ros',
        executable='decision_node',
        name='auv_decision_node',
        condition=IfCondition(LaunchConfiguration('enable_decision')),
        output='screen',
        parameters=decision_params,
    )

    viz_bridge = Node(
        package='auv_viz_bridge',
        executable='zenoh_viz_bridge_node',
        name='zenoh_viz_bridge_node',
        condition=IfCondition(LaunchConfiguration('enable_viz_bridge')), 
        output='screen',
        parameters=[
            {
                'params_file': params,
                'mock_mode': LaunchConfiguration('viz_mock_mode'),
                'mock_fallback_timeout_s': LaunchConfiguration('viz_mock_fallback_timeout_s'),
            }
        ],
    )

    cable_tracking = Node(
        package='auv_decision_ros',
        executable='cable_tracking_node',
        name='auv_cable_tracking_node',
        condition=IfCondition(LaunchConfiguration('enable_cable_tracking')),
        output='screen',
        parameters=[
            {
                'config_file': LaunchConfiguration('cable_tracking_config'),
                'enabled': LaunchConfiguration('enable_cable_tracking'),
            }
        ],
    )

    sensor_supervisor = Node(
        package='auv_decision_ros',
        executable='sensor_supervisor_node',
        name='auv_sensor_supervisor_node',
        condition=IfCondition(LaunchConfiguration('enable_sensor_supervisor')),
        output='screen',
        parameters=[
            {
                'config_file': LaunchConfiguration('sensor_supervisor_config'),
                'enabled': LaunchConfiguration('enable_sensor_supervisor'),
            }
        ],
    )

    mock_magnetic_wrapper = Node(
        package='auv_decision_ros',
        executable='magnetic_sensor_wrapper_node',
        name='auv_mock_magnetic_wrapper_node',
        condition=IfCondition(LaunchConfiguration('enable_mock_magnetic_wrapper')),
        output='screen',
        parameters=[
            {
                'mock_mode': True,
                'output_topic': LaunchConfiguration('mock_magnetic_topic'),
                'frame_id': LaunchConfiguration('mock_magnetic_frame_id'),
                'publish_rate_hz': LaunchConfiguration('mock_magnetic_rate_hz'),
                'mock_field_t': LaunchConfiguration('mock_magnetic_field_t'),
            }
        ],
    )

    real_magnetic_wrapper = Node(
        package='auv_decision_ros',
        executable='magnetic_sensor_wrapper_node',
        name='auv_real_magnetic_wrapper_node',
        condition=IfCondition(LaunchConfiguration('enable_real_magnetic_wrapper')),
        output='screen',
        parameters=[LaunchConfiguration('magnetic_wrapper_params_file')],
    )

    mock_forward_sonar_wrapper = Node(
        package='auv_decision_ros',
        executable='forward_sonar_wrapper_node',
        name='auv_mock_forward_sonar_wrapper_node',
        condition=IfCondition(LaunchConfiguration('enable_mock_forward_sonar_wrapper')),
        output='screen',
        parameters=[
            {
                'mock_mode': True,
                'slope_topic': LaunchConfiguration('mock_forward_sonar_topic'),
                'publish_rate_hz': LaunchConfiguration('mock_forward_sonar_rate_hz'),
                'mock_slope': LaunchConfiguration('mock_forward_sonar_slope'),
                'mock_range_m': LaunchConfiguration('mock_forward_sonar_range_m'),
            }
        ],
    )

    cable_mission_autostart = Node(
        package='auv_decision_ros',
        executable='cable_mission_autostart_node',
        name='auv_cable_mission_autostart_node',
        condition=IfCondition(LaunchConfiguration('enable_cable_mission_autostart')),
        output='screen',
        parameters=[
            {
                'mission_type': LaunchConfiguration('cable_mission_type'),
                'target_depth': LaunchConfiguration('cable_mission_target_depth'),
                'target_speed_mps': LaunchConfiguration('cable_mission_target_speed_mps'),
                'start_delay_s': LaunchConfiguration('cable_mission_start_delay_s'),
                'publish_duration_s': LaunchConfiguration('cable_mission_publish_duration_s'),
                'publish_rate_hz': LaunchConfiguration('cable_mission_publish_rate_hz'),
                'publish_general_mission': LaunchConfiguration('cable_mission_publish_general'),
                'publish_cable_mission': LaunchConfiguration('cable_mission_publish_cable'),
            }
        ],
    )

    return [
        bridge,
        TimerAction(period=2.0, actions=[localization]),
        TimerAction(period=3.0, actions=[viz_bridge]),
        TimerAction(period=3.5, actions=[sensor_supervisor]),
        TimerAction(period=3.7, actions=[real_magnetic_wrapper]),
        TimerAction(period=3.8, actions=[mock_magnetic_wrapper]),
        TimerAction(period=3.9, actions=[mock_forward_sonar_wrapper]),
        TimerAction(period=4.0, actions=[controller]),
        TimerAction(period=6.0, actions=[decision]),
        TimerAction(period=7.0, actions=[cable_tracking]),
        TimerAction(period=8.0, actions=[cable_mission_autostart]),
    ]

def generate_launch_description() -> LaunchDescription:
    default_params = str(Path(__file__).resolve().parents[1] / 'config' / 'params.yaml')
    feature_flags = str(Path(__file__).resolve().parents[1] / 'config' / 'feature_flags.yaml')

    params_arg = DeclareLaunchArgument(
        'params_file',
        default_value=default_params,
        description='Unified params file path, relative to brain_linux workspace',
    )

    minimal_arg = DeclareLaunchArgument(
        'minimal',
        default_value='false',
        description='Minimal mode: disable advanced algorithms, output zero effort for basic connectivity',
    )

    start_ros2dds_arg = DeclareLaunchArgument(
        'start_ros2dds_bridge',
        default_value='false',
        description='Start external zenoh-bridge-ros2dds process in bridge launch',
    )

    enable_bridge_arg = DeclareLaunchArgument(
        'enable_bridge',
        default_value='true',
        description='Enable Zenoh JSON bridge node',
    )

    passive_mode_arg = DeclareLaunchArgument(
        'passive_mode',
        default_value='false',
        description='Run bridge in passive shadow mode without sending downstream commands',
    )

    bridge_backend_arg = DeclareLaunchArgument(
        'bridge_backend',
        default_value='zenoh_json',
        description='Bridge backend: zenoh_json or protocol_udp',
    )

    enable_localization_arg = DeclareLaunchArgument(
        'enable_localization',
        default_value='true',
        description='Enable localization node',
    )

    enable_controller_arg = DeclareLaunchArgument(
        'enable_controller',
        default_value='true',
        description='Enable controller node',
    )

    enable_decision_arg = DeclareLaunchArgument(
        'enable_decision',
        default_value='true',
        description='Enable decision node',
    )

    enable_cable_tracking_arg = DeclareLaunchArgument(
        'enable_cable_tracking',
        default_value='false',
        description='Enable AUV-Master-Mag cable tracking adapter node',
    )

    enable_sensor_supervisor_arg = DeclareLaunchArgument(
        'enable_sensor_supervisor',
        default_value='true',
        description='Enable Jetson-side topic freshness and capability supervisor',
    )

    sensor_supervisor_config_arg = DeclareLaunchArgument(
        'sensor_supervisor_config',
        default_value=str(Path(__file__).resolve().parents[1] / 'config' / 'sensor_supervisor.yaml'),
        description='YAML config file for sensor_supervisor_node',
    )

    enable_mock_magnetic_wrapper_arg = DeclareLaunchArgument(
        'enable_mock_magnetic_wrapper',
        default_value='false',
        description='Enable a Jetson-side mock magnetic wrapper publisher',
    )

    enable_real_magnetic_wrapper_arg = DeclareLaunchArgument(
        'enable_real_magnetic_wrapper',
        default_value='false',
        description='Enable the real FK2301/TMR8637 magnetic wrapper publisher',
    )

    magnetic_wrapper_params_file_arg = DeclareLaunchArgument(
        'magnetic_wrapper_params_file',
        default_value=str(Path(__file__).resolve().parents[1] / 'config' / 'magnetic_wrapper_fangkong.yaml'),
        description='ROS parameter file for the real magnetic wrapper node',
    )

    mock_magnetic_topic_arg = DeclareLaunchArgument(
        'mock_magnetic_topic',
        default_value='/auv/sensors/magnetic',
        description='Output topic for the mock magnetic wrapper',
    )

    mock_magnetic_frame_id_arg = DeclareLaunchArgument(
        'mock_magnetic_frame_id',
        default_value='mag_link',
        description='Frame id for the mock magnetic wrapper',
    )

    mock_magnetic_rate_hz_arg = DeclareLaunchArgument(
        'mock_magnetic_rate_hz',
        default_value='50.0',
        description='Publish rate for the mock magnetic wrapper',
    )

    mock_magnetic_field_t_arg = DeclareLaunchArgument(
        'mock_magnetic_field_t',
        default_value='[3.0e-5, 0.0, -1.0e-5]',
        description='Mock magnetic field vector in Tesla',
    )

    enable_mock_forward_sonar_wrapper_arg = DeclareLaunchArgument(
        'enable_mock_forward_sonar_wrapper',
        default_value='false',
        description='Enable a Jetson-side mock forward sonar wrapper publisher',
    )

    mock_forward_sonar_topic_arg = DeclareLaunchArgument(
        'mock_forward_sonar_topic',
        default_value='/auv/sensors/forward_sonar_slope',
        description='Output topic for the mock forward sonar wrapper',
    )

    mock_forward_sonar_rate_hz_arg = DeclareLaunchArgument(
        'mock_forward_sonar_rate_hz',
        default_value='20.0',
        description='Publish rate for the mock forward sonar wrapper',
    )

    mock_forward_sonar_slope_arg = DeclareLaunchArgument(
        'mock_forward_sonar_slope',
        default_value='0.05',
        description='Mock forward sonar terrain slope',
    )

    mock_forward_sonar_range_m_arg = DeclareLaunchArgument(
        'mock_forward_sonar_range_m',
        default_value='8.0',
        description='Mock forward sonar range in meters',
    )

    cable_tracking_config_arg = DeclareLaunchArgument(
        'cable_tracking_config',
        default_value=str(Path(__file__).resolve().parents[1] / 'config' / 'cable_tracking.yaml'),
        description='YAML config file for cable_tracking_node',
    )

    enable_cable_mission_autostart_arg = DeclareLaunchArgument(
        'enable_cable_mission_autostart',
        default_value='false',
        description='Automatically publish a cable tracking mission command for full-flow experiments',
    )

    cable_mission_type_arg = DeclareLaunchArgument(
        'cable_mission_type',
        default_value='CABLE_TRACKING',
        description='Mission type published by cable_mission_autostart_node',
    )

    cable_mission_target_depth_arg = DeclareLaunchArgument(
        'cable_mission_target_depth',
        default_value='12.0',
        description='Cable mission target depth in meters',
    )

    cable_mission_target_speed_arg = DeclareLaunchArgument(
        'cable_mission_target_speed_mps',
        default_value='0.8',
        description='Cable mission target speed in meters per second',
    )

    cable_mission_start_delay_arg = DeclareLaunchArgument(
        'cable_mission_start_delay_s',
        default_value='2.0',
        description='Delay before cable mission autostart begins publishing',
    )

    cable_mission_publish_duration_arg = DeclareLaunchArgument(
        'cable_mission_publish_duration_s',
        default_value='90.0',
        description='Duration for repeated cable mission autostart publishing',
    )

    cable_mission_publish_rate_arg = DeclareLaunchArgument(
        'cable_mission_publish_rate_hz',
        default_value='2.0',
        description='Cable mission autostart publish rate',
    )

    cable_mission_publish_general_arg = DeclareLaunchArgument(
        'cable_mission_publish_general',
        default_value='true',
        description='Publish cable autostart mission to /auv/mission_command',
    )

    cable_mission_publish_cable_arg = DeclareLaunchArgument(
        'cable_mission_publish_cable',
        default_value='true',
        description='Publish cable autostart mission to /auv/cable/mission_command',
    )

    protocol_control_mode_byte_arg = DeclareLaunchArgument(
        'protocol_control_mode_byte',
        default_value='238',
        description='Ctrl_Mode byte used when protocol_udp backend is active',
    )

    main_motor_rpm_scale_arg = DeclareLaunchArgument(
        'main_motor_rpm_scale',
        default_value='15.0',
        description='Protocol scaling factor used for main motor rpm conversion',
    )

    enable_viz_bridge_arg = DeclareLaunchArgument(
        'enable_viz_bridge',
        default_value='true',
        description='Enable digital twin visualization bridge',
    )

    viz_mock_mode_arg = DeclareLaunchArgument(
        'viz_mock_mode',
        default_value='false',
        description='Force synthetic mock visualization even when Zenoh is available',
    )

    viz_mock_fallback_timeout_arg = DeclareLaunchArgument(
        'viz_mock_fallback_timeout_s',
        default_value='3.0',
        description='Fallback timeout before the visualization bridge switches to mock mode',
    )

    world_frame_arg = DeclareLaunchArgument(
        'world_frame_id',
        default_value='world',
        description='Global frame used for localization TF output',
    )

    base_frame_arg = DeclareLaunchArgument(
        'base_frame_id',
        default_value='auv/base_link',
        description='Robot base frame used by localization TF output',
    )

    imu_frame_id_arg = DeclareLaunchArgument(
        'imu_frame_id',
        default_value='auv/imu_link',
        description='IMU frame name used by localization TF output',
    )

    dvl_frame_id_arg = DeclareLaunchArgument(
        'dvl_frame_id',
        default_value='auv/dvl_link',
        description='DVL frame name used by localization TF output',
    )

    depth_frame_id_arg = DeclareLaunchArgument(
        'depth_frame_id',
        default_value='auv/depth_link',
        description='Depth sensor frame name used by localization TF output',
    )

    camera_frame_id_arg = DeclareLaunchArgument(
        'camera_frame_id',
        default_value='auv/camera_link',
        description='Optional camera frame name reserved for future TF expansion',
    )

    sonar_frame_id_arg = DeclareLaunchArgument(
        'sonar_frame_id',
        default_value='auv/sonar_link',
        description='Optional sonar frame name reserved for future TF expansion',
    )

    imu_frame_offset_arg = DeclareLaunchArgument(
        'imu_frame_offset_xyz',
        default_value='0.0,0.0,0.0',
        description='IMU frame offset xyz as comma separated values',
    )

    dvl_frame_offset_arg = DeclareLaunchArgument(
        'dvl_frame_offset_xyz',
        default_value='0.0,0.0,0.0',
        description='DVL frame offset xyz as comma separated values',
    )

    depth_frame_offset_arg = DeclareLaunchArgument(
        'depth_frame_offset_xyz',
        default_value='0.0,0.0,0.0',
        description='Depth sensor frame offset xyz as comma separated values',
    )

    camera_frame_offset_arg = DeclareLaunchArgument(
        'camera_frame_offset_xyz',
        default_value='0.0,0.0,0.0',
        description='Optional camera frame offset xyz as comma separated values',
    )

    sonar_frame_offset_arg = DeclareLaunchArgument(
        'sonar_frame_offset_xyz',
        default_value='0.0,0.0,0.0',
        description='Optional sonar frame offset xyz as comma separated values',
    )

    publish_imu_tf_arg = DeclareLaunchArgument(
        'publish_imu_tf',
        default_value='true',
        description='Publish the IMU static TF frame',
    )

    publish_dvl_tf_arg = DeclareLaunchArgument(
        'publish_dvl_tf',
        default_value='true',
        description='Publish the DVL static TF frame',
    )

    publish_depth_tf_arg = DeclareLaunchArgument(
        'publish_depth_tf',
        default_value='true',
        description='Publish the depth sensor static TF frame',
    )

    publish_camera_tf_arg = DeclareLaunchArgument(
        'publish_camera_tf',
        default_value='false',
        description='Publish the optional camera static TF frame',
    )

    publish_sonar_tf_arg = DeclareLaunchArgument(
        'publish_sonar_tf',
        default_value='false',
        description='Publish the optional sonar static TF frame',
    )

    publish_sensor_status_arg = DeclareLaunchArgument(
        'publish_sensor_status',
        default_value='true',
        description='Publish live /auv/sensors/status from localization node',
    )

    publish_raw_state_arg = DeclareLaunchArgument(
        'publish_raw_state',
        default_value='false',
        description='Publish raw dead-reckoning odometry from localization node',
    )

    bypass_ekf_arg = DeclareLaunchArgument(
        'bypass_ekf',
        default_value='false',
        description='Make controller consume /auv/state/raw_dr instead of filtered state',
    )

    seabed_depth_arg = DeclareLaunchArgument(
        'seabed_depth_m',
        default_value='15.0',
        description='Sea bottom reference depth used for risk warnings',
    )

    seabed_proximity_margin_arg = DeclareLaunchArgument(
        'seabed_proximity_margin_m',
        default_value='1.5',
        description='Near-bottom warning margin used for safety limiting',
    )

    debug_level_arg = DeclareLaunchArgument(
        'debug_level',
        default_value='0',
        description='Algorithm transparency level forwarded to decision_node',
    )

    transition_threshold_arg = DeclareLaunchArgument(
        'transition_threshold_m',
        default_value='2.0',
        description='Jump threshold for decision-side transition smoothing',
    )

    transition_duration_arg = DeclareLaunchArgument(
        'transition_duration_s',
        default_value='3.0',
        description='Smoothing duration for decision-side transition interpolation',
    )

    mock_amd_timeout_arg = DeclareLaunchArgument(
        'mock_amd_timeout_s',
        default_value='5.0',
        description='Mock AMD time synchronization timeout for decision_node',
    )

    return LaunchDescription(
        [
            params_arg,
            minimal_arg,
            start_ros2dds_arg,
            enable_bridge_arg,
            passive_mode_arg,
            bridge_backend_arg,
            enable_localization_arg,
            enable_controller_arg,
            enable_decision_arg,
            enable_cable_tracking_arg,
            enable_sensor_supervisor_arg,
            sensor_supervisor_config_arg,
            enable_real_magnetic_wrapper_arg,
            magnetic_wrapper_params_file_arg,
            enable_mock_magnetic_wrapper_arg,
            mock_magnetic_topic_arg,
            mock_magnetic_frame_id_arg,
            mock_magnetic_rate_hz_arg,
            mock_magnetic_field_t_arg,
            enable_mock_forward_sonar_wrapper_arg,
            mock_forward_sonar_topic_arg,
            mock_forward_sonar_rate_hz_arg,
            mock_forward_sonar_slope_arg,
            mock_forward_sonar_range_m_arg,
            cable_tracking_config_arg,
            enable_cable_mission_autostart_arg,
            cable_mission_type_arg,
            cable_mission_target_depth_arg,
            cable_mission_target_speed_arg,
            cable_mission_start_delay_arg,
            cable_mission_publish_duration_arg,
            cable_mission_publish_rate_arg,
            cable_mission_publish_general_arg,
            cable_mission_publish_cable_arg,
            protocol_control_mode_byte_arg,
            main_motor_rpm_scale_arg,
            enable_viz_bridge_arg,
            viz_mock_mode_arg,
            viz_mock_fallback_timeout_arg,
            world_frame_arg,
            base_frame_arg,
            imu_frame_id_arg,
            dvl_frame_id_arg,
            depth_frame_id_arg,
            camera_frame_id_arg,
            sonar_frame_id_arg,
            imu_frame_offset_arg,
            dvl_frame_offset_arg,
            depth_frame_offset_arg,
            camera_frame_offset_arg,
            sonar_frame_offset_arg,
            publish_imu_tf_arg,
            publish_dvl_tf_arg,
            publish_depth_tf_arg,
            publish_camera_tf_arg,
            publish_sonar_tf_arg,
            publish_sensor_status_arg,
            publish_raw_state_arg,
            bypass_ekf_arg,
            seabed_depth_arg,
            seabed_proximity_margin_arg,
            debug_level_arg,
            transition_threshold_arg,
            transition_duration_arg,
            mock_amd_timeout_arg,
            OpaqueFunction(function=generate_nodes),
        ]
    )
