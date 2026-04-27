"""AUV 决策联调启动文件。

一键启动两个节点：
1) mock_sensor_input：回放海试日志并发布 /auv/sensors/status
2) decision_node：消费传感状态并发布 /auv/control/goal

用法示例（使用仓库内置样例日志）：
  cd /home/gwxie/master_work-tmp/AUV_Master_Project
  source brain_linux/install/setup.bash
  ros2 launch auv_decision_ros decision_replay.launch.py \
    log_file:=/home/gwxie/master_work-tmp/Console上位机软件/auv_console_python/20020101103632.txt \
    publish_hz:=10.0 confidence_threshold:=0.7

不传 log_file 时，mock_sensor_input 会自动在仓库内搜索样例日志。
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """生成 launch 描述。"""
    log_file_arg = DeclareLaunchArgument(
        'log_file',
        default_value='/home/gwxie/master_work-tmp/Console上位机软件/auv_console_python/20020101103632.txt',
        description='海试文本日志路径（$AUV 格式）。不传时 mock_sensor_input 自动搜索仓库内置样例。',
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
    bt_status_publish_period_arg = DeclareLaunchArgument(
        'bt_status_publish_period',
        default_value='0.5',
        description='行为树状态发布周期 (秒)',
    )
    tree_print_period_arg = DeclareLaunchArgument(
        'tree_print_period',
        default_value='5.0',
        description='行为树 Unicode 树图打印周期 (秒)',
    )
    summary_log_period_arg = DeclareLaunchArgument(
        'summary_log_period',
        default_value='2.0',
        description='决策摘要日志打印周期 (秒)',
    )
    debug_level_arg = DeclareLaunchArgument(
        'debug_level',
        default_value='0',
        description='算法透明度级别 (0:AUTO, 1:HOLD, 2:PATH, 3:FULL)',
    )
    transition_threshold_arg = DeclareLaunchArgument(
        'transition_threshold_m',
        default_value='2.0',
        description='触发平滑过渡的跳变阈值 (米)',
    )
    transition_duration_arg = DeclareLaunchArgument(
        'transition_duration_s',
        default_value='3.0',
        description='平滑过渡持续时间 (秒)',
    )
    mock_amd_timeout_arg = DeclareLaunchArgument(
        'mock_amd_timeout_s',
        default_value='5.0',
        description='Mock AMD 时间同步超时 (秒)',
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
                'bt_status_publish_period': LaunchConfiguration('bt_status_publish_period'),
                'tree_print_period': LaunchConfiguration('tree_print_period'),
                'summary_log_period': LaunchConfiguration('summary_log_period'),
                'debug_level': LaunchConfiguration('debug_level'),
                'transition_threshold_m': LaunchConfiguration('transition_threshold_m'),
                'transition_duration_s': LaunchConfiguration('transition_duration_s'),
                'mock_amd_timeout_s': LaunchConfiguration('mock_amd_timeout_s'),
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
            bt_status_publish_period_arg,
            tree_print_period_arg,
            summary_log_period_arg,
            debug_level_arg,
            transition_threshold_arg,
            transition_duration_arg,
            mock_amd_timeout_arg,
            mock_node,
            decision_node,
        ]
    )
