"""
虚拟声呐包装器（Virtual Sonar Wrapper）

该模块接收仿真侧透传的前向地形斜率数据，
为地形跟踪算法提供前瞻预测能力。
当无外部数据灌入时自动回退（返回0.0），terrain_engine将使用历史斜率。
"""

import logging


class VirtualSonarWrapper:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._slope = 0.0
            cls._instance._logger = logging.getLogger("VirtualSonarWrapper")
        return cls._instance

    def update_slope(self, slope: float) -> None:
        self._slope = slope

    def predict_slope(self) -> float:
        return self._slope
