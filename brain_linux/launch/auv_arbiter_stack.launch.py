from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from pathlib import Path


def generate_launch_description() -> LaunchDescription:
    launch_dir = Path(__file__).resolve().parent
    default_params = str(launch_dir.parent / 'config' / 'params.protocol_udp_arbiter.yaml')
    stack_launch = str(launch_dir / 'auv_stack.launch.py')

    params_arg = DeclareLaunchArgument(
        'params_file',
        default_value=default_params,
        description='Arbiter-enabled params file path',
    )

    include_stack = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(stack_launch),
        launch_arguments={
            'params_file': LaunchConfiguration('params_file'),
            'bridge_backend': 'protocol_udp',
            'protocol_control_mode_byte': '238',
            'passive_mode': 'false',
            'publish_raw_state': 'true',
            'bypass_ekf': 'false',
        }.items(),
    )

    return LaunchDescription([
        params_arg,
        include_stack,
    ])