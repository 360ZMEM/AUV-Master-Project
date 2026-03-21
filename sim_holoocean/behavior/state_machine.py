import numpy as np


class WaypointStateMachine:
    """Behavior-layer target generator.

    - 默认沿时间切换航点（可用于ES-EKF实验）
    - 提供 LOS 任务目标输出接口，供主控制循环调用
    """

    def __init__(self, cfg):
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
        t_sec = float(state.get("t", 0.0))
        current = self.waypoints[0]
        for wp in self.waypoints:
            if t_sec >= float(wp.get("t", 0.0)):
                current = wp
            else:
                break
        return {
            "target_xyz": np.array(current["xyz"], dtype=float),
            "target_u": self.target_u,
        }
