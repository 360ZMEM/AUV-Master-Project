"""Core telemetry snapshot builders for decision observability."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from math import isfinite
from typing import Any

from .models import SensorStatusData


@dataclass(frozen=True)
class DecisionTelemetrySnapshot:
    """供 ROS 适配层消费的结构化决策遥测快照。

    该快照把行为树当前状态、传感器状态、目标指令和可视化文本统一打包，
    便于在 /auv/bt_status、/auv/diagnostics 和控制日志之间复用同一份事实来源。
    """

    current_behavior: str
    active_path: str
    mode: str
    confidence: float
    leak_level: int
    battery_low: bool
    total_voltage_v: float
    anomaly_detected: bool
    depth_m: float
    target_depth_m: float
    depth_error_m: float
    speed_mps: float
    target_speed_mps: float
    has_lateral_error: bool
    lateral_error_m: float
    has_magnetic_magnitude: bool
    magnetic_magnitude: float
    seabed_clearance_m: float
    seabed_proximity_warning: bool
    seabed_penetration_warning: bool
    high_priority: bool
    note: str
    tree_snapshot: str
    bt_status_markdown: str
    summary_line: str


def _sanitize_optional_metric(value: float | None) -> tuple[bool, float]:
    """把可选数值归一化为“是否存在 + 数值”二元组。"""
    if value is None:
        return False, 0.0
    numeric = float(value)
    if not isfinite(numeric):
        return False, 0.0
    return True, numeric


def _goal_float(goal: dict[str, Any], key: str, default: float = 0.0) -> float:
    """从目标字典中安全提取浮点字段。"""
    value = goal.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _format_metric_line(label: str, value: float, unit: str, available: bool = True) -> str:
    """格式化单行指标文本，供 Markdown 状态面板使用。"""
    if not available:
        return f'- {label}: N/A'
    return f'- {label}: {value:.2f}{unit}'


def build_bt_status_markdown(
    *,
    tree_snapshot: str,
    current_behavior: str,
    active_path: str,
    mode: str,
    depth_error_m: float,
    has_lateral_error: bool,
    lateral_error_m: float,
    has_magnetic_magnitude: bool,
    magnetic_magnitude: float,
) -> str:
    """构建适合 Foxglove 展示的 Markdown 行为树状态文本。"""
    lines = [
        '## Behavior Tree',
        f'- Active: {current_behavior}',
        f'- Mode: {mode}',
        f'- Path: {active_path}',
        _format_metric_line('Depth Error', depth_error_m, ' m'),
        _format_metric_line('Lateral Error', lateral_error_m, ' m', has_lateral_error),
        _format_metric_line('Magnetic |B|', magnetic_magnitude, ' uT', has_magnetic_magnitude),
        '',
        '```text',
        tree_snapshot.rstrip(),
        '```',
    ]
    return '\n'.join(lines)


def build_summary_line(snapshot: DecisionTelemetrySnapshot) -> str:
    """构建适合控制台日志输出的一行摘要文本。"""
    lateral_text = f'{snapshot.lateral_error_m:.2f}m' if snapshot.has_lateral_error else 'N/A'
    magnetic_text = f'{snapshot.magnetic_magnitude:.2f}uT' if snapshot.has_magnetic_magnitude else 'N/A'
    return (
        '[状态摘要] '
        f'mode={snapshot.mode} | '
        f'behavior={snapshot.current_behavior} | '
        f'depth={snapshot.depth_m:.2f}m | '
        f'depth_error={snapshot.depth_error_m:.2f}m | '
        f'lateral_error={lateral_text} | '
        f'magnetic={magnetic_text} | '
        f'confidence={snapshot.confidence:.2f} | '
        f'voltage={snapshot.total_voltage_v:.2f}V | '
        f'leak_level={snapshot.leak_level} | '
        f'battery_low={snapshot.battery_low} | '
        f'anomaly={snapshot.anomaly_detected} | '
        f'seabed_clearance={snapshot.seabed_clearance_m:.2f}m | '
        f'seabed_warn={snapshot.seabed_proximity_warning} | '
        f'seabed_penetration={snapshot.seabed_penetration_warning} | '
        f'goal_speed={snapshot.target_speed_mps:.2f}m/s | '
        f'goal_depth={snapshot.target_depth_m:.2f}m | '
        f'priority={snapshot.high_priority}'
    )


def build_decision_telemetry_snapshot(
    *,
    sensor_status: SensorStatusData,
    goal: dict[str, Any] | None,
    current_behavior: str,
    active_path: str,
    tree_snapshot: str,
    depth_error_m: float | None,
    lateral_error_m: float | None,
    magnetic_magnitude: float | None,
) -> DecisionTelemetrySnapshot:
    """把传感器状态、目标指令和运行时指标组装成稳定的遥测快照。"""
    goal = goal or {}
    _, depth_error_value = _sanitize_optional_metric(depth_error_m)
    has_lateral_error, lateral_error_value = _sanitize_optional_metric(lateral_error_m)
    has_magnetic_magnitude, magnetic_value = _sanitize_optional_metric(magnetic_magnitude)
    mode = str(goal.get('mode', 'IDLE'))
    snapshot = DecisionTelemetrySnapshot(
        current_behavior=current_behavior,
        active_path=active_path,
        mode=mode,
        confidence=float(sensor_status.confidence),
        leak_level=int(sensor_status.leak_level),
        battery_low=bool(sensor_status.battery_low),
        total_voltage_v=float(sensor_status.total_voltage_v),
        anomaly_detected=bool(sensor_status.anomaly_detected),
        depth_m=float(sensor_status.depth_m),
        target_depth_m=_goal_float(goal, 'target_depth_m'),
        depth_error_m=depth_error_value,
        speed_mps=float(sensor_status.speed_mps),
        target_speed_mps=_goal_float(goal, 'target_speed_mps'),
        has_lateral_error=has_lateral_error,
        lateral_error_m=lateral_error_value,
        has_magnetic_magnitude=has_magnetic_magnitude,
        magnetic_magnitude=magnetic_value,
        seabed_clearance_m=float(sensor_status.seabed_clearance_m),
        seabed_proximity_warning=bool(sensor_status.seabed_proximity_warning),
        seabed_penetration_warning=bool(sensor_status.seabed_penetration_warning),
        high_priority=bool(goal.get('high_priority', False)),
        note=str(goal.get('note', '')),
        tree_snapshot=tree_snapshot,
        bt_status_markdown='',
        summary_line='',
    )
    snapshot = replace(
        snapshot,
        bt_status_markdown=build_bt_status_markdown(
            tree_snapshot=tree_snapshot,
            current_behavior=current_behavior,
            active_path=active_path,
            mode=mode,
            depth_error_m=snapshot.depth_error_m,
            has_lateral_error=has_lateral_error,
            lateral_error_m=lateral_error_value,
            has_magnetic_magnitude=has_magnetic_magnitude,
            magnetic_magnitude=magnetic_value,
        ),
    )
    return replace(snapshot, summary_line=build_summary_line(snapshot))