from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    start_ros2dds_arg = DeclareLaunchArgument(
        'start_ros2dds_bridge',
        default_value='false',
        description='Whether to launch external zenoh-bridge-ros2dds process',
    )

    ros2dds_cmd = ExecuteProcess(
        cmd=['zenoh-bridge-ros2dds'],
        output='screen',
        condition=IfCondition(LaunchConfiguration('start_ros2dds_bridge')),
    )

    json_bridge_node = Node(
        package='auv_bridge',
        executable='zenoh_json_bridge_node',
        name='zenoh_json_bridge_node',
        output='screen',
    )

    return LaunchDescription([
        start_ros2dds_arg,
        ros2dds_cmd,
        json_bridge_node,
    ])
