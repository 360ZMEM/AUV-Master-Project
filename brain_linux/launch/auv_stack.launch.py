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

    params = LaunchConfiguration('params_file')

    bridge = Node(
        package='auv_bridge',
        executable='zenoh_json_bridge_node',
        name='zenoh_json_bridge_node',
        condition=IfCondition(LaunchConfiguration('enable_bridge')),
        output='screen',
        parameters=[{'params_file': params}],
    )

    localization = Node(
        package='auv_localization',
        executable='auv_localization_node',
        name='auv_localization_node',
        condition=IfCondition(LaunchConfiguration('enable_localization')),
        output='screen',
        parameters=[{'params_file': params}],
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
                'tree_print_period': 1.0,
                'summary_log_period': 1.0,
            }
        ],
    )

    return LaunchDescription(
        [
            params_arg,
            start_ros2dds_arg,
            enable_bridge_arg,
            enable_localization_arg,
            enable_controller_arg,
            enable_decision_arg,
            bridge,
            TimerAction(period=2.0, actions=[localization]),
            TimerAction(period=4.0, actions=[controller]),
            TimerAction(period=6.0, actions=[decision]),
        ]
    )
