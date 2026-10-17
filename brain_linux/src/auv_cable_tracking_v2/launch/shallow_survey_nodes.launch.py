"""Synthetic-only multi-crossing ROS/PID/optional passive bridge entrypoint."""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    share = get_package_share_directory("auv_cable_tracking_v2")
    parent = os.path.join(share, "launch", "flythrough_nodes.launch.py")
    config = os.path.join(share, "config", "cable_tracking_v2_shallow_survey_sim.yaml")
    return LaunchDescription([
        DeclareLaunchArgument("config_file", default_value=config),
        DeclareLaunchArgument("enable_passive_bridge", default_value="false"),
        DeclareLaunchArgument("use_sim_time", default_value="true"),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(parent),
            launch_arguments={
                "config_file": LaunchConfiguration("config_file"),
                "use_sim_time": LaunchConfiguration("use_sim_time"),
                "enable_passive_bridge": LaunchConfiguration("enable_passive_bridge"),
                "enable_sonar_quality": "false",
            }.items(),
        ),
    ])
