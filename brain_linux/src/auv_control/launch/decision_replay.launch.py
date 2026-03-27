"""AUV 决策联调启动文件。

一键启动两个节点：
1) mock_sensor_input：回放海试日志并发布 /auv/sensors/status
2) decision_node：消费传感状态并发布 /auv/control/goal

用法示例：
ros2 launch auv_decision_ros decision_replay.launch.py \
  log_file:=/home/zmem063/auv_console_python/auv_console_python/20020101103632.txt \
  publish_hz:=10.0 confidence_threshold:=0.7
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """生成 launch 描述。"""
    log_file_arg = DeclareLaunchArgument(
        'log_file',
        default_value='/home/zmem063/auv_console_python/auv_console_python/20020101103632.txt',
        description='海试文本日志路径',
    )
    publish_hz_arg = DeclareLaunchArgument(
        'publish_hz',
        default_value='10.0',
        description='日志回放发布频率 (Hz)',
    )
    voltage_threshold_arg = DeclareLaunchArgument(
        'battery_low_voltage_threshold',
        default_value='95.0',
        description='低电压阈值 (V)，低于该值将标记 battery_low=True',
    )
    seabed_depth_arg = DeclareLaunchArgument(
        'seabed_depth_m',
        default_value='15.0',
        description='海底参考深度 (m)，用于近底/穿底告警',
    )
    seabed_proximity_margin_arg = DeclareLaunchArgument(
        'seabed_proximity_margin_m',
        default_value='1.5',
        description='近底告警余量 (m)，接近海底时提前减速',
    )
    confidence_threshold_arg = DeclareLaunchArgument(
        'confidence_threshold',
        default_value='0.7',
        description='行为树置信度阈值，大于该值走并行巡检分支',
    )
    tree_print_period_arg = DeclareLaunchArgument(
        'tree_print_period',
        default_value='1.0',
        description='行为树 Unicode 树图打印周期 (秒)',
    )
    summary_log_period_arg = DeclareLaunchArgument(
        'summary_log_period',
        default_value='1.0',
        description='决策摘要日志打印周期 (秒)',
    )

    mock_node = Node(
        package='auv_decision_ros',
        executable='mock_sensor_input',
        name='mock_sensor_input',
        output='screen',
        parameters=[
            {
                'log_file': LaunchConfiguration('log_file'),
                'publish_hz': LaunchConfiguration('publish_hz'),
                'battery_low_voltage_threshold': LaunchConfiguration('battery_low_voltage_threshold'),
                'seabed_depth_m': LaunchConfiguration('seabed_depth_m'),
                'seabed_proximity_margin_m': LaunchConfiguration('seabed_proximity_margin_m'),
            }
        ],
    )

    decision_node = Node(
        package='auv_decision_ros',
        executable='decision_node',
        name='auv_decision_node',
        output='screen',
        parameters=[
            {
                'confidence_threshold': LaunchConfiguration('confidence_threshold'),
                'tree_print_period': LaunchConfiguration('tree_print_period'),
                'summary_log_period': LaunchConfiguration('summary_log_period'),
            }
        ],
    )

    return LaunchDescription(
        [
            log_file_arg,
            publish_hz_arg,
            voltage_threshold_arg,
            seabed_depth_arg,
            seabed_proximity_margin_arg,
            confidence_threshold_arg,
            tree_print_period_arg,
            summary_log_period_arg,
            mock_node,
            decision_node,
        ]
    )
