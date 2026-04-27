"""UE4/HoloOcean 与 NED 坐标系之间的变换工具。

该模块集中处理位置、姿态和体轴向量的坐标系换算，避免在各个仿真或
桥接模块中分散实现转换逻辑。
"""

import numpy as np


def rotation_matrix_to_euler_ue(rot):
    """将 UE 风格旋转矩阵转换为欧拉角。"""
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
    """将 UE 坐标系位置转换为 NED 坐标系位置。"""
    position_ue = np.asarray(position_ue, dtype=float).reshape(3)
    return np.array([position_ue[0], position_ue[1], -position_ue[2]], dtype=float)


def ue_rpy_to_ned(rpy_ue):
    """将 UE 欧拉角转换为 NED 欧拉角。"""
    rpy_ue = np.asarray(rpy_ue, dtype=float).reshape(3)
    roll_ue, pitch_ue, yaw_ue = rpy_ue
    return np.array([roll_ue, -pitch_ue, -yaw_ue], dtype=float)


def pose_matrix_ue_to_ned(pose_ue):
    """将 4x4 UE 位姿矩阵转换为 NED 位置和姿态字典。"""
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
    """将 UE 体轴向量转换为 NED 体轴向量。"""
    vec_ue = np.asarray(vec_ue, dtype=float).reshape(3)
    return np.array([vec_ue[0], vec_ue[1], -vec_ue[2]], dtype=float)
