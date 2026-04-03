from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from pathlib import Path


def generate_launch_description() -> LaunchDescription:
    default_params = str(Path(__file__).resolve().parents[1] / 'config' / 'params.yaml')

    params_arg = DeclareLaunchArgument(
        'params_file',
        default_value=default_params,
        description='Unified params file path, relative to brain_linux workspace',
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

    protocol_control_mode_byte_arg = DeclareLaunchArgument(
        'protocol_control_mode_byte',
        default_value='238',
        description='Ctrl_Mode byte used when protocol_udp backend is active',
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

    params = LaunchConfiguration('params_file')

    bridge = Node(
        package='auv_bridge',
        executable='zenoh_json_bridge_node',
        name='zenoh_json_bridge_node',
        condition=IfCondition(LaunchConfiguration('enable_bridge')),
        output='screen',
        parameters=[{'params_file': params}, {'bridge_backend': LaunchConfiguration('bridge_backend')}],
    )

    localization = Node(
        package='auv_localization',
        executable='auv_localization_node',
        name='auv_localization_node',
        condition=IfCondition(LaunchConfiguration('enable_localization')),
        output='screen',
        parameters=[
            {'params_file': params},
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
        parameters=[{'params_file': params}],
    )

    decision = Node(
        package='auv_decision_ros',
        executable='decision_node',
        name='auv_decision_node',
        condition=IfCondition(LaunchConfiguration('enable_decision')),
        output='screen',
        parameters=[
            {
                'confidence_threshold': 0.7,
                'bt_status_publish_period': 0.5,
                'tree_print_period': 5.0,
                'summary_log_period': 2.0,
                'bridge_backend': LaunchConfiguration('bridge_backend'),
                'protocol_control_mode_byte': LaunchConfiguration('protocol_control_mode_byte'),
            }
        ],
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

    return LaunchDescription(
        [
            params_arg,
            start_ros2dds_arg,
            enable_bridge_arg,
            bridge_backend_arg,
            enable_localization_arg,
            enable_controller_arg,
            enable_decision_arg,
            protocol_control_mode_byte_arg,
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
            seabed_depth_arg,
            seabed_proximity_margin_arg,
            bridge,
            TimerAction(period=2.0, actions=[localization]),
            TimerAction(period=3.0, actions=[viz_bridge]),
            TimerAction(period=4.0, actions=[controller]),
            TimerAction(period=6.0, actions=[decision]),
        ]
    )
