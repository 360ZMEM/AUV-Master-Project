"""有限状态机基准引擎。

说明：
1) 本文件实现与行为树等价的有限状态机决策逻辑；
2) 使用传统的 enter/update/exit 模式实现状态流转；
3) 每个状态的 update() 内部独立检测紧急中断，模拟真实 FSM 的逐层中断处理；
4) 接受相同的 SensorStatusData 输入，输出相同的 MotionGoal；
5) 用于与行为树引擎进行量化基准对比。
"""

from __future__ import annotations

import time

from .models import MotionGoal, SensorStatusData


class FiniteStateMachineEngine:
    """AUV 决策有限状态机引擎（纯 Python）。

    架构特点：
    - 使用 enter/update/exit 生命周期模式；
    - 紧急中断检测分散在各个状态的 update() 中（非全局检查）；
    - 这模拟了真实 FSM 架构中跨层级中断需要逐层退出的延迟；
    - 状态转移通过 _dispatch 方法路由到各状态的 handler。

    状态集合：
        IDLE, DIVE_TO_DEPTH, PARALLEL_TRACKING, ZIGZAG_SEARCH,
        EMERGENCY_SURFACE, STABILIZE_HOLD, ANALYTICAL_PATH
    """

    DIVE_TARGET_DEPTH = 4.0

    def __init__(self, confidence_threshold: float = 0.7) -> None:
        self.confidence_threshold = confidence_threshold
        self.current_state: str = 'IDLE'
        self.last_goal: MotionGoal = MotionGoal()
        self._state_history: list[tuple[int, str, float]] = []
        self._tick_count: int = 0
        self._hold_target_depth: float = 0.0
        self._hold_target_heading: float = 0.0
        self._enter_count: int = 0

    def _is_emergency(self, sensor: SensorStatusData) -> bool:
        return sensor.is_leaking() or sensor.battery_low or sensor.is_seabed_penetrated()

    def _emergency_goal(self, sensor: SensorStatusData) -> MotionGoal:
        if sensor.is_seabed_penetrated():
            note = '检测到穿底风险，执行紧急上浮。'
        elif sensor.is_leaking() or sensor.battery_low:
            note = '检测到漏水或低电，执行紧急上浮。'
        else:
            note = '执行紧急上浮。'
        return MotionGoal(
            mode='EMERGENCY_SURFACE',
            target_depth_m=0.0,
            target_speed_mps=0.8,
            high_priority=True,
            note=note,
        )

    def _make_goal(
        self,
        mode: str,
        target_depth_m: float = 0.0,
        target_speed_mps: float = 0.0,
        sine_amplitude: float = 0.0,
        sine_period_s: float = 0.0,
        high_priority: bool = False,
        note: str = '',
        target_heading_rad: float = 0.0,
        target_x_m: float = 0.0,
        target_y_m: float = 0.0,
    ) -> MotionGoal:
        return MotionGoal(
            mode=mode,
            target_depth_m=target_depth_m,
            target_speed_mps=target_speed_mps,
            sine_amplitude=sine_amplitude,
            sine_period_s=sine_period_s,
            high_priority=high_priority,
            note=note,
            target_heading_rad=target_heading_rad,
            target_x_m=target_x_m,
            target_y_m=target_y_m,
        )

    def _transition(self, new_state: str, goal: MotionGoal, sensor: SensorStatusData) -> MotionGoal:
        if new_state != self.current_state:
            self.current_state = new_state
            self._enter_count += 1
        self.last_goal = goal
        ts = time.perf_counter()
        self._state_history.append((self._tick_count, self.current_state, ts))
        return goal

    def _handle_idle(self, sensor: SensorStatusData) -> MotionGoal:
        return self._transition(
            'DIVE_TO_DEPTH',
            self._make_goal(
                mode='DIVE_TO_DEPTH',
                target_depth_m=self.DIVE_TARGET_DEPTH,
                target_speed_mps=0.5,
                note='主任务流：先下潜到巡检深度。',
            ),
            sensor,
        )

    def _handle_dive_to_depth(self, sensor: SensorStatusData) -> MotionGoal:
        if self._is_emergency(sensor):
            return self._transition('EMERGENCY_SURFACE', self._emergency_goal(sensor), sensor)
        if sensor.depth_m >= self.DIVE_TARGET_DEPTH:
            if sensor.confidence > self.confidence_threshold:
                return self._transition(
                    'PARALLEL_TRACKING',
                    self._make_goal(
                        mode='PARALLEL_TRACKING',
                        target_depth_m=4.0,
                        target_speed_mps=0.6,
                        sine_amplitude=0.15,
                        sine_period_s=12.0,
                        note='高置信度巡检：输出并行跟踪速度与正弦扰动参数。',
                    ),
                    sensor,
                )
            else:
                return self._transition(
                    'ZIGZAG_SEARCH',
                    self._make_goal(
                        mode='ZIGZAG_SEARCH',
                        target_depth_m=4.0,
                        target_speed_mps=0.4,
                        sine_amplitude=0.35,
                        sine_period_s=8.0,
                        note='低置信度：切换之字形搜索以提升覆盖率。',
                    ),
                    sensor,
                )
        return self._transition(
            'DIVE_TO_DEPTH',
            self._make_goal(
                mode='DIVE_TO_DEPTH',
                target_depth_m=self.DIVE_TARGET_DEPTH,
                target_speed_mps=0.5,
                note='主任务流：先下潜到巡检深度。',
            ),
            sensor,
        )

    def _handle_parallel_tracking(self, sensor: SensorStatusData) -> MotionGoal:
        if self._is_emergency(sensor):
            return self._transition('EMERGENCY_SURFACE', self._emergency_goal(sensor), sensor)
        if sensor.confidence < self.confidence_threshold:
            return self._transition(
                'ZIGZAG_SEARCH',
                self._make_goal(
                    mode='ZIGZAG_SEARCH',
                    target_depth_m=4.0,
                    target_speed_mps=0.4,
                    sine_amplitude=0.35,
                    sine_period_s=8.0,
                    note='低置信度：切换之字形搜索以提升覆盖率。',
                ),
                sensor,
            )
        return self._transition(
            'PARALLEL_TRACKING',
            self._make_goal(
                mode='PARALLEL_TRACKING',
                target_depth_m=4.0,
                target_speed_mps=0.6,
                sine_amplitude=0.15,
                sine_period_s=12.0,
                note='高置信度巡检：输出并行跟踪速度与正弦扰动参数。',
            ),
            sensor,
        )

    def _handle_zigzag_search(self, sensor: SensorStatusData) -> MotionGoal:
        if self._is_emergency(sensor):
            return self._transition('EMERGENCY_SURFACE', self._emergency_goal(sensor), sensor)
        if sensor.confidence >= self.confidence_threshold:
            return self._transition(
                'PARALLEL_TRACKING',
                self._make_goal(
                    mode='PARALLEL_TRACKING',
                    target_depth_m=4.0,
                    target_speed_mps=0.6,
                    sine_amplitude=0.15,
                    sine_period_s=12.0,
                    note='高置信度巡检：输出并行跟踪速度与正弦扰动参数。',
                ),
                sensor,
            )
        return self._transition(
            'ZIGZAG_SEARCH',
            self._make_goal(
                mode='ZIGZAG_SEARCH',
                target_depth_m=4.0,
                target_speed_mps=0.4,
                sine_amplitude=0.35,
                sine_period_s=8.0,
                note='低置信度：切换之字形搜索以提升覆盖率。',
            ),
            sensor,
        )

    def _handle_emergency_surface(self, sensor: SensorStatusData) -> MotionGoal:
        if not self._is_emergency(sensor):
            return self._transition(
                'DIVE_TO_DEPTH',
                self._make_goal(
                    mode='DIVE_TO_DEPTH',
                    target_depth_m=self.DIVE_TARGET_DEPTH,
                    target_speed_mps=0.5,
                    note='故障清除，重新下潜到巡检深度。',
                ),
                sensor,
            )
        return self._transition(
            'EMERGENCY_SURFACE',
            self._make_goal(
                mode='EMERGENCY_SURFACE',
                target_depth_m=0.0,
                target_speed_mps=0.8,
                high_priority=True,
                note='紧急故障持续中，保持上浮。',
            ),
            sensor,
        )

    def _handle_stabilize_hold(self, sensor: SensorStatusData) -> MotionGoal:
        if self._is_emergency(sensor):
            return self._transition('EMERGENCY_SURFACE', self._emergency_goal(sensor), sensor)
        return self._transition(
            'STABILIZE_HOLD',
            self._make_goal(
                mode='STABILIZE_HOLD',
                target_depth_m=self._hold_target_depth,
                target_speed_mps=0.0,
                target_heading_rad=self._hold_target_heading,
                note='L1 Hold 模式：定深定航稳定，验证 PID 控制稳定性。',
            ),
            sensor,
        )

    def _handle_analytical_path(self, sensor: SensorStatusData) -> MotionGoal:
        if self._is_emergency(sensor):
            return self._transition('EMERGENCY_SURFACE', self._emergency_goal(sensor), sensor)
        return self._transition(
            'ANALYTICAL_PATH',
            self._make_goal(
                mode='ANALYTICAL_PATH',
                target_depth_m=4.0,
                target_speed_mps=0.6,
                target_x_m=0.0,
                target_y_m=0.0,
                target_heading_rad=0.0,
                note='L2 AnalyticalPath 模式：跟踪解析式轨迹',
            ),
            sensor,
        )

    def tick(self, sensor: SensorStatusData) -> MotionGoal:
        self._tick_count += 1

        if sensor.debug_level == 1 and self.current_state not in ('STABILIZE_HOLD', 'EMERGENCY_SURFACE'):
            if self.current_state != 'STABILIZE_HOLD':
                self._hold_target_depth = sensor.depth_m
                self._hold_target_heading = sensor.heading_rad
            return self._transition(
                'STABILIZE_HOLD',
                self._make_goal(
                    mode='STABILIZE_HOLD',
                    target_depth_m=self._hold_target_depth,
                    target_speed_mps=0.0,
                    target_heading_rad=self._hold_target_heading,
                    note='L1 Hold 模式：定深定航稳定，验证 PID 控制稳定性。',
                ),
                sensor,
            )

        if sensor.debug_level == 2 and self.current_state not in ('ANALYTICAL_PATH', 'EMERGENCY_SURFACE'):
            return self._transition(
                'ANALYTICAL_PATH',
                self._make_goal(
                    mode='ANALYTICAL_PATH',
                    target_depth_m=4.0,
                    target_speed_mps=0.6,
                    target_x_m=0.0,
                    target_y_m=0.0,
                    target_heading_rad=0.0,
                    note='L2 AnalyticalPath 模式：跟踪解析式轨迹',
                ),
                sensor,
            )

        handlers = {
            'IDLE': self._handle_idle,
            'DIVE_TO_DEPTH': self._handle_dive_to_depth,
            'PARALLEL_TRACKING': self._handle_parallel_tracking,
            'ZIGZAG_SEARCH': self._handle_zigzag_search,
            'EMERGENCY_SURFACE': self._handle_emergency_surface,
            'STABILIZE_HOLD': self._handle_stabilize_hold,
            'ANALYTICAL_PATH': self._handle_analytical_path,
        }

        handler = handlers.get(self.current_state, self._handle_idle)
        return handler(sensor)

    def get_state_history(self) -> list[tuple[int, str, float]]:
        return list(self._state_history)

    def get_current_state(self) -> str:
        return self.current_state

    def reset(self) -> None:
        self.current_state = 'IDLE'
        self.last_goal = MotionGoal()
        self._state_history.clear()
        self._tick_count = 0
        self._hold_target_depth = 0.0
        self._hold_target_heading = 0.0
        self._enter_count = 0

    def count_transitions(self) -> int:
        if len(self._state_history) < 2:
            return 0
        count = 0
        for i in range(1, len(self._state_history)):
            if self._state_history[i][1] != self._state_history[i - 1][1]:
                count += 1
        return count

    def compute_cyclomatic_complexity(self) -> int:
        try:
            import mccabe
            import ast

            file_path = __file__
            with open(file_path, 'r') as f:
                source = f.read()
            tree = ast.parse(source)
            visitor = mccabe.PathGraphingAstVisitor()
            visitor.preorder(tree, visitor)
            total = 0
            for graph in visitor.graphs.values():
                c = graph.complexity() if callable(graph.complexity) else graph.complexity
                total += c
            return total
        except Exception:
            return -1
