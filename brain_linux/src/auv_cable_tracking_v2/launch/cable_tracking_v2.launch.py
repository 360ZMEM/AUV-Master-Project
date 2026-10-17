from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description() -> LaunchDescription:
    default_config = os.path.join(
        get_package_share_directory("auv_cable_tracking_v2"),
        "config",
        "cable_tracking_v2.yaml",
    )
    config_arg = DeclareLaunchArgument(
        "config_file",
        default_value=default_config,
        description="Independent cable-tracking v2 configuration",
    )
    node = Node(
        package="auv_cable_tracking_v2",
        executable="cable_tracking_v2_node",
        name="auv_cable_tracking_v2_node",
        output="screen",
        parameters=[{"config_file": LaunchConfiguration("config_file")}],
    )
    return LaunchDescription([config_arg, node])
