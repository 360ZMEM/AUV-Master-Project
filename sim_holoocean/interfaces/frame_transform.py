import numpy as np


def rotation_matrix_to_euler_ue(rot):
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
    position_ue = np.asarray(position_ue, dtype=float).reshape(3)
    return np.array([position_ue[0], position_ue[1], -position_ue[2]], dtype=float)


def ue_rpy_to_ned(rpy_ue):
    rpy_ue = np.asarray(rpy_ue, dtype=float).reshape(3)
    roll_ue, pitch_ue, yaw_ue = rpy_ue
    return np.array([roll_ue, -pitch_ue, -yaw_ue], dtype=float)


def pose_matrix_ue_to_ned(pose_ue):
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
    vec_ue = np.asarray(vec_ue, dtype=float).reshape(3)
    return np.array([vec_ue[0], vec_ue[1], -vec_ue[2]], dtype=float)
