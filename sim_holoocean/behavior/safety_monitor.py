"""
仿真侧安全监视器 - 边界和深度约束的实时应用。

该模块在仿真主循环中执行地域和深度的安全约束，避免 AUV 穿出人工环境边界。

主要功能：
  1. 环境边界检查（XY 平面）：如果靠近边界，降低推力以防冲出
  2. 深度约束（Z 轴）：如果深度不足，自动下潜；如果过深，自动上浮
  3. 安全裕度：配置可调的边界外推和深度缓冲区
  4. 事件记录：返回每步触发的安全事件列表（用于调试和统计）

工作流程：
  receive position (北东地坐标) → 检查XY/Z约束 → 调整命令 → 返回安全命令 + 事件列表

配置示例（来自 sim_params.yaml 的 'limits' 部分）：
  limits:
    env_min: [-100, -100, -50]      # 环境下界（北、东、地）
    env_max: [100, 100, 0]          # 环境上界（Z=0 表示水面）
    safety_margin_xy: 10.0          # XY 边界内推距离（米）
    safety_margin_z: 5.0            # Z 边界内推距离（米）
    fin_deg_max: 30.0               # 舵角限幅（度）
    thrust_min: -100.0              # 推力下限（百分比）
    thrust_max: 100.0               # 推力上限（百分比）
"""

import numpy as np


def apply_safety(command, position, limits_cfg):
    """
    对命令应用实时安全约束。

    逻辑：
      1️⃣ 边界裕度计算：为环境XY边界减去安全裕度
      2️⃣ XY边界检查：如果AUV靠近边界，推力降低至 60%
      3️⃣ 深度检查：
         - 水深不足（pos[2] > z_max_safe，即 Z 值向上越界）→ 增加俯角命令
         - 过深（pos[2] < z_min_safe，即 Z 值向下越界）→ 增加仰角命令
      4️⃣ 二次限幅：确保调整后的命令仍在允许范围内
      5️⃣ 返回：安全命令向量 + 事件列表

    坐标系说明（NED - 北东地）：
      - pos[0]：北向位置（米）
      - pos[1]：东向位置（米）
      - pos[2]：地向位置（米，正向为向下）

    参数：
        command (array-like)：当前控制命令 [right, top, left, bottom, thrust]
        position (array-like)：AUV 当前位置 [north, east, down]
        limits_cfg (dict)：来自 sim_params.yaml 的限制配置：
          - env_min (list[3])：环境最小坐标
          - env_max (list[3])：环境最大坐标
          - safety_margin_xy (float)：XY 方向安全裕度
          - safety_margin_z (float)：Z 方向安全裕度
          - fin_deg_max (float)：舵角最大值
          - thrust_min, thrust_max (float)：推力范围

    返回值：
        tuple：(安全命令, 事件列表)
          - 安全命令 (ndarray[5])：经过安全处理的命令向量
          - 事件列表 (list[str])：本步骤触发的安全事件，包括：
            - "near_xy_boundary_thrust_reduce"：XY 边界推力限制
            - "too_shallow_pitch_down"：水深不足，需要下潜
            - "too_deep_pitch_up"：过深，需要上浮

    示例：
        >>> cfg = {'env_min': [-100, -100, -50], 'env_max': [100, 100, 0],
        ...        'safety_margin_xy': 10, 'safety_margin_z': 5,
        ...        'fin_deg_max': 30, 'thrust_min': -100, 'thrust_max': 100}
        >>> cmd = [0, 0, 0, 0, 50]
        >>> pos = [-95, -95, -10]  # 接近北西边界，中等深度
        >>> safe_cmd, events = apply_safety(cmd, pos, cfg)
        >>> print(events)  # ['near_xy_boundary_thrust_reduce']
        >>> print(safe_cmd[4])  # 30.0 (推力从 50 降至 30)
    """
    # ────────────────────────────────────────────────
    # 初始化和坐标转换
    # ────────────────────────────────────────────────
    cmd = np.array(command, dtype=float)
    pos = np.array(position, dtype=float)
    events = []

    # 环境边界（NED 坐标）
    env_min = np.array(limits_cfg["env_min"], dtype=float)
    env_max = np.array(limits_cfg["env_max"], dtype=float)
    margin_xy = float(limits_cfg["safety_margin_xy"])
    margin_z = float(limits_cfg["safety_margin_z"])

    # ────────────────────────────────────────────────
    # 计算安全区域边界
    # ────────────────────────────────────────────────
    x_min_safe = env_min[0] + margin_xy
    x_max_safe = env_max[0] - margin_xy
    y_min_safe = env_min[1] + margin_xy
    y_max_safe = env_max[1] - margin_xy
    z_min_safe = env_min[2] + margin_z
    z_max_safe = env_max[2] - margin_z

    # ────────────────────────────────────────────────
    # 检查 1️⃣：XY 平面边界
    # ────────────────────────────────────────────────
    near_xy_boundary = (
        pos[0] <= x_min_safe
        or pos[0] >= x_max_safe
        or pos[1] <= y_min_safe
        or pos[1] >= y_max_safe
    )
    if near_xy_boundary:
        # 接近 XY 边界时，推力降低至原来的 60%
        cmd[4] *= 0.6
        events.append("near_xy_boundary_thrust_reduce")

    # ────────────────────────────────────────────────
    # 检查 2️⃣：Z 轴深度约束
    # ────────────────────────────────────────────────
    if pos[2] > z_max_safe:
        # ⚠️ 浅层警告：Z 值过低（接近水面或已超过）
        # 增加俯角命令（right, left 增加正命令）使 AUV 下潜
        cmd[0] += 6.0   # 右舵增加俯仰
        cmd[2] -= 6.0   # 左舵抵消滚动
        events.append("too_shallow_pitch_down")
    elif pos[2] < z_min_safe:
        # ⚠️ 深度警告：Z 值过高（下潜过深）
        # 减少俯角或增加仰角以获得上浮分量
        cmd[0] -= 6.0   # 右舵减少俯仰
        cmd[2] += 6.0   # 左舵抵消滚动
        events.append("too_deep_pitch_up")

    # ────────────────────────────────────────────────
    # 二次限幅：确保调整后命令仍然有效
    # ────────────────────────────────────────────────
    cmd[:4] = np.clip(cmd[:4], -float(limits_cfg["fin_deg_max"]), float(limits_cfg["fin_deg_max"]))
    cmd[4] = np.clip(cmd[4], float(limits_cfg["thrust_min"]), float(limits_cfg["thrust_max"]))
    return cmd, events
