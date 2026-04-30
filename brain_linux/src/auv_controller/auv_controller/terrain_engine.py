"""
地形跟踪（Terrain Following）核心算法引擎

该模块实现基于预测前瞻与斜坡约束的地形跟随控制。
根据历史的海床深度估计和预留的声呐前瞻计算未来地形的深度，
结合期望的离底高度和动态斜率约束输出下发给 AMD 的深度指令。
"""

import math
import time
from collections import deque
from typing import Tuple

from .terrain_perception import BaseTerrainPerception

class TerrainFollower:
    def __init__(self, lookahead_time_s: float = 2.0, lpf_alpha: float = 0.2):
        """
        初始化地形跟随引擎。
        
        Args:
            lookahead_time_s (float): 前瞻预测的时间窗口大小（秒）。
            lpf_alpha (float): 目标深度的低通滤波系数 (0.0~1.0)，用于约束俯仰变化率。
        """
        self._lookahead_time_s = lookahead_time_s
        self._lpf_alpha = lpf_alpha
        
        # 历史海床深度队列：存储 (timestamp, seafloor_depth)
        self._history_queue: deque[Tuple[float, float]] = deque()
        self._history_window_s = 2.0  # 过去 2 秒的记录用于计算斜率
        
        self._last_z_target: float = -1.0
        self._first_run = True

    def _estimate_slope(self, current_time: float) -> float:
        """
        根据过去 2 秒的 S (seafloor depth) 记录，利用最小二乘法估计海床坡度。
        
        Returns:
            float: 坡度值 tan(alpha)。正值表示地形正在变深（下坡），负值表示变浅（上坡）。
        """
        # 清理过期数据
        while self._history_queue and (current_time - self._history_queue[0][0] > self._history_window_s):
            self._history_queue.popleft()
            
        n = len(self._history_queue)
        if n < 2:
            return 0.0
            
        sum_t = 0.0
        sum_S = 0.0
        sum_t2 = 0.0
        sum_tS = 0.0
        
        t0 = self._history_queue[0][0]
        for t_abs, S in self._history_queue:
            t = t_abs - t0
            sum_t += t
            sum_S += S
            sum_t2 += t * t
            sum_tS += t * S
            
        denominator = n * sum_t2 - sum_t * sum_t
        if denominator < 1e-6:
            return 0.0
            
        # 斜率 dS/dt (m/s)
        dS_dt = (n * sum_tS - sum_t * sum_S) / denominator
        
        # 假设 AUV 的航速为 u (前向速度)，则 tan(alpha) = (dS/dt) / u
        # 但在算法外层直接用 u * tan(alpha) 相当于 dS/dt，
        # 为了与声呐的预测一致，这里返回 dS/dt。
        return dS_dt

    def compute(self, perception: BaseTerrainPerception, target_altitude_m: float) -> Tuple[float, dict]:
        """
        计算地形跟踪控制输出。
        
        Args:
            perception (BaseTerrainPerception): 后端无关的感知接口实例。
            target_altitude_m (float): 目标离底高度 (h_set)。
            
        Returns:
            Tuple[float, dict]: 
                - z_target: 约束后的目标深度指令。
                - debug_info: 用于监控的调试字典，包含 estimated_slope, lookahead_z_target 等。
        """
        now = time.time()
        current_depth = perception.get_current_depth()
        current_altitude = perception.get_altitude()
        u = perception.get_forward_velocity()
        
        # 1. 海床建模：S = z + h
        if current_altitude > 0.01:
            S_now = current_depth + current_altitude
            self._history_queue.append((now, S_now))
        else:
            # DVL 失效且无历史，无法估计海床，保持当前深度
            S_now = perception.get_estimated_seafloor_depth()
            if S_now is None:
                S_now = current_depth
        
        # 2. 斜率估计 (融合历史斜率与声呐前瞻)
        # 获取基于历史推算的深度变化率 (m/s)
        dS_dt_history = self._estimate_slope(now)
        
        # 尝试获取声呐前瞻斜率 (tan(alpha))
        sonar_slope = perception.get_sonar_slope()
        if abs(sonar_slope) > 1e-3 and u > 0.1:
            # 如果声呐有效，使用声呐斜率（假设声呐更准确地反映未来）
            dS_dt = u * sonar_slope
            slope_source = "sonar"
            estimated_slope = sonar_slope
        else:
            # 否则使用历史推算
            dS_dt = dS_dt_history
            slope_source = "history"
            estimated_slope = (dS_dt / u) if u > 0.1 else 0.0
            
        # 3. 前瞻预测 (Look-ahead)
        # 预测未来 t_look 秒的海床深度
        S_future = S_now + (dS_dt * self._lookahead_time_s)
        
        # 4. 高度闭环
        z_target_raw = S_future - target_altitude_m
        
        # 5. 动态约束 (LPF)
        if self._first_run:
            self._last_z_target = z_target_raw
            self._first_run = False
            
        z_target = (1.0 - self._lpf_alpha) * self._last_z_target + self._lpf_alpha * z_target_raw
        
        # 进一步的俯仰角限制：通过最大深度变化率限制
        # 如果 z_target 变化过快，可能导致 AUV 产生过大俯仰角。
        # 这里交由底层的 PID 速度前馈或深度外环控制（外部），
        # 仅在此维持平滑。
        self._last_z_target = z_target
        
        debug_info = {
            "S_now": S_now,
            "S_future": S_future,
            "estimated_slope": estimated_slope,
            "slope_source": slope_source,
            "lookahead_z_target": z_target_raw,
            "filtered_z_target": z_target,
        }
        
        return z_target, debug_info
