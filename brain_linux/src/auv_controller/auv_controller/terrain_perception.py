"""
地形跟踪（Terrain Following）感知适配层

该模块提供一个后端无关的感知接口 `BaseTerrainPerception`，用于隔离不同
仿真后端（PVS/HoloOcean）或实机硬件。通过该接口，核心地形算法能够稳定
获取所需的 DVL 高度、深度计深度、前向速度及预留的声呐斜率。
"""

from abc import ABC, abstractmethod
from typing import Optional

from .virtual_sonar_wrapper import VirtualSonarWrapper

class BaseTerrainPerception(ABC):
    """
    地形跟踪基础感知接口抽象类
    
    规定了地形跟踪引擎所需的所有状态信息。
    包括失效情况下的补偿逻辑（Dead Reckoning）。
    """
    
    def __init__(self):
        self._last_valid_seafloor_depth: Optional[float] = None
        self._sonar = VirtualSonarWrapper()

    @abstractmethod
    def get_altitude(self) -> float:
        """获取当前 AUV 的离底高度 (h)。"""
        pass

    @abstractmethod
    def get_current_depth(self) -> float:
        """获取当前 AUV 的绝对深度 (z)。"""
        pass

    @abstractmethod
    def get_forward_velocity(self) -> float:
        """获取当前 AUV 的前向速度 (u)。"""
        pass

    def get_sonar_slope(self) -> float:
        """获取前方地形的预测斜率。目前通过 VirtualSonarWrapper 占位返回。"""
        return self._sonar.predict_slope()
        
    def get_estimated_seafloor_depth(self) -> Optional[float]:
        """
        获取最后一次合法的海床深度估计值 (S = z + h)。
        
        Returns:
            float: 最后一次合法的海床深度估计，若从未获取合法数据则返回 None。
        """
        return self._last_valid_seafloor_depth

    def _update_seafloor_estimate(self, current_depth: float, current_altitude: float) -> None:
        """
        更新最后一次合法的海床深度估计。此方法应在子类更新状态时调用。
        
        Args:
            current_depth (float): 当前有效深度
            current_altitude (float): 当前有效高度
        """
        if current_altitude > 0.01:  # 高度大于0时视为有效
            self._last_valid_seafloor_depth = current_depth + current_altitude


class ROSTerrainPerception(BaseTerrainPerception):
    """
    基于 ROS2 话题订阅的感知接口实现。
    
    通过 ROS2 Controller 节点周期性地将传感器数据灌入此实例，
    以此解耦 ROS 依赖与核心算法。
    """
    
    def __init__(self):
        super().__init__()
        self._current_altitude = 0.0
        self._current_depth = 0.0
        self._forward_velocity = 0.0

    def update_state(self, altitude: float, depth: float, forward_velocity: float) -> None:
        """
        由上层节点调用，刷新内部状态缓存。
        
        同时执行缺失补偿逻辑：若当前 altitude 失效（如反馈为 0 且存在有效历史），
        将通过最后一次合法的海床深度进行航位推算。
        """
        self._current_depth = depth
        self._forward_velocity = forward_velocity
        
        if altitude > 0.01:
            # 传感器数据有效
            self._current_altitude = altitude
            self._update_seafloor_estimate(depth, altitude)
        else:
            # DVL 数据失效，尝试补偿
            last_seafloor = self.get_estimated_seafloor_depth()
            if last_seafloor is not None and last_seafloor > depth:
                self._current_altitude = last_seafloor - depth
            else:
                self._current_altitude = 0.0

    def get_altitude(self) -> float:
        return self._current_altitude

    def get_current_depth(self) -> float:
        return self._current_depth

    def get_forward_velocity(self) -> float:
        return self._forward_velocity
