"""物理映射层：控制指令到协议量的非线性映射。

本模块提供从"物理量"到"协议量"的转换功能，包含：
  1. 舵机映射：角度 → 协议值（包含 Trim、增益、极性）
  2. 推进器线性化：推力百分比 → RPM（包含死区、电压补偿）
  3. 单位强制转换：确保所有发往协议层的数据为 int16

配置结构示例：
    mappers:
      rudder:
        center_bias: 0.0   # Trim 偏移 (deg)
        gain: 1.0          # 灵敏度 (0.5~2.0)
        flip: false        # 极性翻转
      thrust:
        deadzone_percent: 5.0      # 死区百分比
        rpm_per_percent: 15.0      # 每 1% 对应的 RPM 线性斜率
        voltage_nominal: 24.0      # 标称电压 (V)
        voltage_compensation: true # 是否启用电压补偿
"""

from __future__ import annotations

import math

INT16_MIN = -32768
INT16_MAX = 32767


def clamp_int16(value: float) -> int:
    """将浮点数钳位到 int16 范围 [-32768, 32767]。

    Args:
        value: 需要转换的浮点数值

    Returns:
        int: 钳位后的 int16 值
    """
    if value > INT16_MAX:
        return INT16_MAX
    if value < INT16_MIN:
        return INT16_MIN
    return int(round(value))


def rudder_deg_to_protocol(angle_deg: float, config: dict) -> int:
    """将舵角（度）转换为协议值。

    包含 Trim 偏移、增益调节和极性翻转处理。

    Args:
        angle_deg: 期望舵角角度（度），范围通常 [-45, 45]
        config: 舵机配置字典，包含：
            - center_bias: Trim 偏移量（度），默认 0.0
            - gain: 灵敏度系数（0.5~2.0），默认 1.0
            - flip: 是否翻转极性，默认 False

    Returns:
        int: 协议要求的舵角值（int16），范围通常 [-32768, 32767]
             对应实际舵机的物理限位

    Example:
        >>> config = {"center_bias": 2.0, "gain": 1.2, "flip": False}
        >>> rudder_deg_to_protocol(10.0, config)
        14400  # (10.0 + 2.0) * 1.2 * 1000 = 14400
    """
    center_bias = float(config.get("center_bias", 0.0))
    gain = float(config.get("gain", 1.0))
    flip = bool(config.get("flip", False))

    # 应用 Trim 偏移
    adjusted_angle = angle_deg + center_bias

    # 应用增益
    scaled_angle = adjusted_angle * gain

    # 极性翻转
    if flip:
        scaled_angle = -scaled_angle

    # 映射到协议范围（假设 1° = 1000 协议单位）
    protocol_value = scaled_angle * 1000.0

    return clamp_int16(protocol_value)


def thrust_to_rpm(
    thrust_percent: float,
    config: dict,
    *,
    feedback_voltage: float | None = None,
) -> int:
    """将推力百分比转换为推进器 RPM。

    包含死区处理和电压补偿逻辑：
    - 死区跳过：当推力低于死区阈值时，直接输出最小有效 RPM
    - 电压补偿：根据回传电压调整增益，确保推力一致性

    Args:
        thrust_percent: 推力百分比（-100 ~ 100）
        config: 推进器配置字典，包含：
            - deadzone_percent: 死区百分比（如 5.0 表示 5%）
            - rpm_per_percent: 每 1% 推力对应的 RPM 线性斜率
            - voltage_nominal: 标称电压（V），默认 24.0
            - voltage_compensation: 是否启用电压补偿，默认 True
        feedback_voltage: 实际回传电压（V），可选。用于电压补偿计算。

    Returns:
        int: 协议要求的 RPM 值（int16）
             正值表示正转，负值表示反转，0 表示停止

    Example:
        >>> config = {
        ...     "deadzone_percent": 5.0,
        ...     "rpm_per_percent": 15.0,
        ...     "voltage_nominal": 24.0,
        ...     "voltage_compensation": True,
        ... }
        >>> # 1% 推力 → 跳过死区，直接输出 150 RPM
        >>> thrust_to_rpm(1.0, config)
        150
        >>> # 10% 推力 → (10 - 5 + 1) * 15 = 90 RPM
        >>> thrust_to_rpm(10.0, config)
        90
    """
    deadzone_percent = float(config.get("deadzone_percent", 5.0))
    rpm_per_percent = float(config.get("rpm_per_percent", 15.0))
    voltage_nominal = float(config.get("voltage_nominal", 24.0))
    voltage_compensation = bool(config.get("voltage_compensation", True))

    # 处理零推力
    if abs(thrust_percent) < 1e-6:
        return 0

    # 确定方向和绝对值
    direction = 1.0 if thrust_percent > 0 else -1.0
    abs_thrust = abs(thrust_percent)

    # 死区处理
    if abs_thrust < deadzone_percent:
        # 低于死区：输出最小有效 RPM（死区阈值对应的 RPM）
        rpm = deadzone_percent * rpm_per_percent
    else:
        # 高于死区：按线性关系计算
        rpm = (abs_thrust - deadzone_percent + deadzone_percent) * rpm_per_percent

    # 电压补偿
    if voltage_compensation and feedback_voltage is not None and feedback_voltage > 0:
        # 补偿因子：标称电压 / 实际电压
        # 电压低时增加 RPM 以补偿推力损失
        voltage_ratio = voltage_nominal / feedback_voltage
        # 限制补偿范围在 0.8~1.5 之间，防止过度补偿
        voltage_ratio = max(0.8, min(1.5, voltage_ratio))
        rpm *= voltage_ratio

    # 应用方向并钳位
    rpm_with_direction = direction * rpm
    return clamp_int16(rpm_with_direction)


def rudders_to_protocol_dict(
    right_deg: float | None,
    top_deg: float | None,
    left_deg: float | None,
    bottom_deg: float | None,
    config: dict,
) -> dict[str, int]:
    """批量转换四个舵面角度到协议值。

    Args:
        right_deg: 右舵角度（None 表示透传/不干预）
        top_deg: 上舵角度
        left_deg: 左舵角度
        bottom_deg: 下舵角度
        config: 舵机配置字典

    Returns:
        dict: 包含 four fins 协议值的字典，键为 fin 名称，值为 int16 协议值
              None 值会被转换为 0（表示透传）
    """
    return {
        "right": rudder_deg_to_protocol(right_deg if right_deg is not None else 0.0, config),
        "top": rudder_deg_to_protocol(top_deg if top_deg is not None else 0.0, config),
        "left": rudder_deg_to_protocol(left_deg if left_deg is not None else 0.0, config),
        "bottom": rudder_deg_to_protocol(bottom_deg if bottom_deg is not None else 0.0, config),
    }
