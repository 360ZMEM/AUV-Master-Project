"""
航路点状态机 - 基于时间序列的任务目标生成器。

该模块实现行为层的航路点切换逻辑，为下层控制器提供阶段性目标。
主要用于 ES-EKF 状态估计实验的基准轨迹生成。

工作原理：
  1. 预定义一系列时间戳对应的航路点
  2. 根据当前仿真时间选择活跃航路点
  3. 输出目标位置（xyz）和目标速度供 LOS 导引使用

与 ROS2 行为树的区别：
  - 这是仿真侧的简化实现，用于独立测试
  - ROS2 决策侧的行为树（auv_decision）提供更复杂的多阶段任务逻辑
"""

import numpy as np


class WaypointStateMachine:
    """────────────────────────────────────────────────────────────────
    行为层目标生成器
    ────────────────────────────────────────────────────────────────

    职责：
      1. 管理时间序列的航路点列表
      2. 根据当前时间选择活跃航路点
      3. 输出 LOS 导引所需的目标位置和目标速度

    使用场景：
      - ES-EKF 状态估计实验：提供可预测的基准轨迹
      - 独立仿真测试：无需复杂行为树的简单任务
      - 性能基准：与 ROS2 行为树对比控制器性能

    航路点格式：
      {
        "t": 8.0,              # 触发时间（秒）
        "xyz": [8.0, 0.0, -6.0] # 目标位置 [北, 东, 地]
      }
    """

    def __init__(self, cfg):
        """
        初始化航点状态机。

        参数：
            cfg (dict)：配置字典，包含：
              - waypoints (list[dict])：航点列表，默认 3 点
              - target_u (float)：目标巡航速度（米/秒），默认 1.0

        默认航点序列：
          t=0s:  (0, 0, -0.5)    起始位置，浅层下潜
          t=8s:  (8, 0, -6.0)    前进 8m，下潜至 6m
          t=20s: (18, 5, -8.0)   斜向前进，深度 8m
        """
        self.waypoints = cfg.get(
            "waypoints",
            [
                {"t": 0.0, "xyz": [0.0, 0.0, -0.5]},
                {"t": 8.0, "xyz": [8.0, 0.0, -6.0]},
                {"t": 20.0, "xyz": [18.0, 5.0, -8.0]},
            ],
        )
        self.target_u = float(cfg.get("target_u", 1.0))

    def tick(self, state):
        """
        根据当前仿真时间更新状态机并输出目标。

        逻辑：
          1. 从 state 中提取当前仿真时间
          2. 线性搜索航点列表，找到最新的触发航点
          3. 返回该航点的位置作为目标，配置的目标速度

        参数：
            state (dict)：当前仿真状态，必须包含 "t" 键（仿真时间）

        返回值：
            dict：包含：
              - target_xyz (ndarray[3])：目标位置 [北, 东, 地]
              - target_u (float)：目标速度（米/秒）

        示例：
            >>> sm = WaypointStateMachine({})
            >>> state = {"t": 10.0}  # 10 秒时
            >>> goal = sm.tick(state)
            >>> print(goal["target_xyz"])  # [8. 0. -6.] (第二个航点)
            >>> print(goal["target_u"])    # 1.0
        """
        t_sec = float(state.get("t", 0.0))
        current = self.waypoints[0]
        # ────────────────────────────────────────────────
        # 搜索最新触发的航点
        # ────────────────────────────────────────────────
        for wp in self.waypoints:
            if t_sec >= float(wp.get("t", 0.0)):
                current = wp
            else:
                break
        return {
            "target_xyz": np.array(current["xyz"], dtype=float),
            "target_u": self.target_u,
        }
