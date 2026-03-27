from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from pathlib import Path


def generate_launch_description() -> LaunchDescription:
    default_params = str(Path(__file__).resolve().parents[3] / 'config' / 'params.yaml')

    params_arg = DeclareLaunchArgument(
        'params_file',
        default_value=default_params,
        description='Unified params file path, relative to brain_linux workspace',
    )

    mock_mode_arg = DeclareLaunchArgument(
        'mock_mode',
        default_value='true',
        description='Run with synthetic fallback even if Zenoh or HoloOcean is unavailable',
    )

    node = Node(
        package='auv_viz_bridge',
        executable='zenoh_viz_bridge_node',
        name='zenoh_viz_bridge_node',
        output='screen',
        parameters=[
            {
                'params_file': LaunchConfiguration('params_file'),
                'mock_mode': LaunchConfiguration('mock_mode'),
            }
        ],
    )

    return LaunchDescription([params_arg, mock_mode_arg, node])