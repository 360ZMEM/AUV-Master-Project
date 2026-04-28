"""
ROS2 真实 AUV 桥接适配器 - 未来实物集成的预留接口。

该模块为实物 AUV（运行 ROS2 Humble + 嵌入式控制系统）提供接口适配层。
目前为占位符（stub）实现，等待与实物硬件集成。

设计思路：
  保持与仿真侧 sim_wrapper.py 相同的 API 契约，使得上层代码可以不修改
  地在仿真和实物之间切换。

预期流程（未来实现）：
  1. ROS2Node：连接到实物 AUV 的控制和传感器节点
  2. 下行命令：通过 ROS2 topic 发送控制指令
  3. 上行反馈：订阅实物传感器和状态 topic
  4. 状态封装：统一为与仿真侧兼容的 state dict 格式

注意：
  当前版本故意抛出 NotImplementedError，防止误调用。
  实现时需要依赖 rclpy（ROS2 Python 客户库）。
"""


class ROS2Wrapper:
    """────────────────────────────────────────────────────────────────
    ROS2 真实 AUV 适配器（预留接口）
    ────────────────────────────────────────────────────────────────

    职责（预期）：
      - 连接到运行 ROS2 的实物 AUV 平台
      - 订阅实物传感器数据（IMU、DVL、深度、磁力计）
      - 发布控制命令（推力、舵角）
      - 统一状态格式为与仿真兼容的字典
      - 管理 ROS2 节点的生命周期

    API 契约：
      open()：初始化 ROS2 节点和数据流
      step(command5)：发送控制命令，接收最新传感器数据
      reset_and_tick()：复位平台（仅适用于有自动复位机制的平台）
      close()：关闭连接和释放资源

    状态格式（返回值）：
      {
          agent_name: {
              "PoseSensor": 4×4 变换矩阵,
              "DVLSensor": [vx, vy, vz] 速度,
              "IMUSensor": [ax, ay, az, gx, gy, gz] 加速度和角速度,
              "DepthSensor": [depth_m] 深度,
          }
      }
    """

    def __init__(self, config):
        """
        初始化 ROS2 适配器（不连接）。

        参数：
            config (dict)：来自全局配置，包含：
              - ros2 节点配置
              - 订阅/发布 topic 路径
              - 坐标系变换参数
        """
        self.config = config

    def open(self):
        """
        连接到实物 AUV 的 ROS2 系统。

        预期实现步骤：
          1. 初始化 rclpy 节点
          2. 创建 subscription 通道，订阅：
             - /auv/sensors/imu
             - /auv/sensors/dvl
             - /auv/sensors/depth
             - /auv/sensors/magnetic
          3. 创建 publisher 通道，发布：
             - /cmd_vel（控制命令）
          4. 启动后台线程监听回调
          5. 返回 self，支持链式调用

        返回值：
            self（预期）

        异常：
            NotImplementedError：当前为占位符版本
        """
        raise NotImplementedError("ROS2 wrapper shell only. Implement with rclpy.Node in future.")

    def reset_and_tick(self):
        """
        复位平台并接收首次传感器数据。

        预期行为：
          - 仅在有自动复位机制（如模拟器）的平台实现
          - 实物 AUV 可能无法复位，此时应返回当前状态

        返回值：
            dict：当前平台状态

        异常：
            NotImplementedError：当前为占位符版本
        """
        raise NotImplementedError("ROS2 wrapper shell only.")

    def step(self, command5):
        """
        发送控制命令并接收最新传感器数据（一个控制周期）。

        参数：
            command5 (array-like)，形状 (5,)：
              [right_fin_deg, top_fin_deg, left_fin_deg, bottom_fin_deg, thrust_percent]
              - 舵角：度数，范围 [-45, 45]（或其他硬件限制）
              - 推力：百分比，范围 [-100, 100]

        返回值：
            dict：更新后的平台状态

        异常：
            NotImplementedError：当前为占位符版本
        """
        raise NotImplementedError("ROS2 wrapper shell only.")

    def close(self):
        """
        关闭 ROS2 连接，释放资源。

        预期实现：
          - 撤销所有 subscription 和 publisher
          - 销毁 ROS2 节点
          - 停止监听线程

        返回值：
            None
        """
        return None
