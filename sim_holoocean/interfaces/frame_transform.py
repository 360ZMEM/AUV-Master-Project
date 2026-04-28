"""
坐标系转换工具库 - UE4/HoloOcean 与 NED（北东地）坐标系之间的变换。

背景：
  - UE4 使用右手坐标系，X 向前，Y 右，Z 上
  - NED（北东地）是航空/水下领域标准，X 北，Y 东，Z 地（向下为正）
  - 这两个坐标系的原点、轴向、符号约定都不同，需要统一变换

本模块集中处理位置、姿态和体轴向量的坐标系换算，避免在各个仿真或
桥接模块中分散实现转换逻辑，确保整个系统数据一致性。

关键转换：
  1. 位置向量：(x_ue, y_ue, z_ue) → (x_ned, y_ned, z_ned)
  2. 欧拉角：(roll_ue, pitch_ue, yaw_ue) → (roll_ned, pitch_ned, yaw_ned)
  3. 旋转矩阵：UE4 风格 → 欧拉角 → NED 欧拉角
  4. 速度/加速度向量：同方向但符号调整
"""

import numpy as np


def rotation_matrix_to_euler_ue(rot):
    """
    将 3x3 UE4 风格旋转矩阵转换为欧拉角。

    参数：
        rot: ndarray，形状 (3, 3)
            UE4 旋转矩阵（行优先，对应 [X, Y, Z] 轴旋转）

    返回值：
        ndarray，形状 (3,)：[roll, pitch, yaw] 欧拉角（弧度）
    """
    sy = np.sqrt(rot[0, 0] ** 2 + rot[1, 0] ** 2)
    singular = sy < 1e-6
    if not singular:
        roll = np.arctan2(rot[2, 1], rot[2, 2])
        pitch = np.arctan2(-rot[2, 0], sy)
        yaw = np.arctan2(rot[1, 0], rot[0, 0])
    else:
        roll = np.arctan2(-rot[1, 2], rot[1, 1])
        pitch = np.arctan2(-rot[2, 0], sy)
        yaw = 0.0
    return np.array([roll, pitch, yaw], dtype=float)


def ue_position_to_ned(position_ue):
    """
    将 UE4 坐标系位置转换为 NED 坐标系位置。

    UE4: (X, Y, Z) = (前, 右, 上)
    NED: (X, Y, Z) = (北, 东, 下)

    转换规则：
      - UE4 的 X（前）→ NED 的 X（北）
      - UE4 的 Y（右）→ NED 的 Y（东）
      - UE4 的 Z（上）→ NED 的 -Z（下反向）

    参数：
        position_ue: array-like，形状 (3,)
            UE4 坐标系位置 [x_ue, y_ue, z_ue]

    返回值：
        ndarray，形状 (3,)：[x_ned, y_ned, z_ned] NED 坐标系位置
    """
    position_ue = np.asarray(position_ue, dtype=float).reshape(3)
    return np.array([position_ue[0], position_ue[1], -position_ue[2]], dtype=float)


def ue_rpy_to_ned(rpy_ue):
    """
    将 UE4 欧拉角转换为 NED 欧拉角。

    参数：
        rpy_ue: array-like，形状 (3,)
            UE4 欧拉角 [roll_ue, pitch_ue, yaw_ue]（弧度）

    返回值：
        ndarray，形状 (3,)：[roll_ned, pitch_ned, yaw_ned] NED 欧拉角（弧度）
    """
    rpy_ue = np.asarray(rpy_ue, dtype=float).reshape(3)
    roll_ue, pitch_ue, yaw_ue = rpy_ue
    return np.array([roll_ue, -pitch_ue, -yaw_ue], dtype=float)


def pose_matrix_ue_to_ned(pose_ue):
    """
    将 4x4 UE4 位姿矩阵转换为 NED 位置和姿态字典。

    输入是标准的 4x4 齐次变换矩阵：
      [R(3×3)  T(3×1)]
      [0(1×3)    1   ]

    其中：
      - R：旋转矩阵（左上 3×3）
      - T：位置向量（右上 3×1）

    参数：
        pose_ue: ndarray，形状 (4, 4)
            UE4 位姿矩阵（齐次变换）

    返回值：
        dict：包含以下键的字典：
          - position_ned: ndarray (3,)，NED 位置
          - rpy_ned: ndarray (3,)，NED 欧拉角（弧度）
          - position_ue: ndarray (3,)，原始 UE4 位置（用于调试）
          - rpy_ue: ndarray (3,)，原始 UE4 欧拉角（用于调试）
    """
    pose_ue = np.asarray(pose_ue, dtype=float)
    if pose_ue.shape != (4, 4):
        raise ValueError("pose_ue must be 4x4")
    pos_ned = ue_position_to_ned(pose_ue[:3, 3])
    rpy_ue = rotation_matrix_to_euler_ue(pose_ue[:3, :3])
    rpy_ned = ue_rpy_to_ned(rpy_ue)
    return {
        "position_ned": pos_ned,
        "rpy_ned": rpy_ned,
        "position_ue": pose_ue[:3, 3].astype(float),
        "rpy_ue": rpy_ue,
    }


def body_vector_ue_to_ned(vec_ue):
    """
    将 UE4 身体坐标系向量转换为 NED 身体坐标系向量。

    身体坐标系（固定在 AUV 上）：
      - X 轴：前（沿 AUV 运动方向）
      - Y 轴：右
      - Z 轴：上

    在 NED 坐标系中，AUV 身体轴的对应关系：
      - 身体 X（前）→ NED 身体 X（前）
      - 身体 Y（右）→ NED 身体 Y（右）
      - 身体 Z（上）→ NED 身体 -Z（下反向）

    这个转换用于速度、加速度、角速度等身体坐标系向量。

    参数：
        vec_ue: array-like，形状 (3,)
            UE4 身体坐标系向量 [vx_ue, vy_ue, vz_ue]

    返回值：
        ndarray，形状 (3,)：[vx_ned, vy_ned, vz_ned] NED 身体坐标系向量
    """
    vec_ue = np.asarray(vec_ue, dtype=float).reshape(3)
    return np.array([vec_ue[0], vec_ue[1], -vec_ue[2]], dtype=float)

