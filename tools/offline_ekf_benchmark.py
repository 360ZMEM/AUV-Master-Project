#!/usr/bin/env python3
"""
基于 MCAP 回放的 AUV 定位算法离线基准测试工具。

从录制好的 .mcap 数据包中读取传感器原始数据，分别喂给三种定位算法
(Raw DR, Standard EKF, ES-EKF)，计算相对于包内"地面真值"的偏差，
并生成对比报告和可视化图表。

该工具完全独立于 ROS2 运行环境，仅依赖 Python 标准库及:
  - mcap, mcap-ros2-support
  - numpy
  - matplotlib
  - pyyaml

使用示例:
  python3 tools/offline_ekf_benchmark.py --input log/experiment_01.mcap --output-dir ./results

架构:
  [Part 1] MCAP Ingestion       - 数据解析层
  [Part 2] Algorithm Engines    - 三种定位算法实现
  [Part 3] Metrics              - 评估指标计算
  [Part 4] Visualization        - 图表生成
  [Part 5] Report               - 报告生成
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from common.env_utils import get_output_dir

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = PROJECT_ROOT / "tools"
SIM_DIR = PROJECT_ROOT / "sim_holoocean"
ALGO_DIR = PROJECT_ROOT / "algorithm"

for p in (str(TOOLS_DIR), str(SIM_DIR), str(ALGO_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

plt = None
read_ros2_messages = None

DEFAULT_IMU_TOPIC = "/auv/sensors/imu"
DEFAULT_DVL_TOPIC = "/auv/sensors/dvl"
DEFAULT_DEPTH_TOPIC = "/auv/sensors/depth"
DEFAULT_TRUTH_TOPICS = (
    "/auv/sensors/ground_truth",
    "/auv/state/truth",
    "/auv/visual/truth_marker",
)
DEFAULT_EKF_CONFIG = str(PROJECT_ROOT / "brain_linux" / "config" / "params.yaml")


# =============================================================================
# [Part 0] Runtime Dependency Checks
# =============================================================================

def ensure_runtime_dependencies() -> None:
    global plt, read_ros2_messages
    if plt is None:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as _plt
        except ImportError as exc:
            raise SystemExit(
                "matplotlib is required. Install: pip install matplotlib"
            ) from exc
        plt = _plt

    if read_ros2_messages is None:
        try:
            from mcap_ros2.reader import read_ros2_messages as _reader
        except ImportError as exc:
            raise SystemExit(
                "mcap and mcap-ros2-support are required. Install: "
                "pip install mcap mcap-ros2-support"
            ) from exc
        read_ros2_messages = _reader


def configure_matplotlib() -> None:
    assert plt is not None
    plt.rcParams["font.family"] = "serif"
    plt.rcParams["font.serif"] = ["Times New Roman", "Liberation Serif", "DejaVu Serif"]
    plt.rcParams["mathtext.fontset"] = "stix"
    plt.rcParams["font.size"] = 11
    plt.rcParams["axes.labelsize"] = 11
    plt.rcParams["axes.titlesize"] = 12
    plt.rcParams["legend.fontsize"] = 9
    plt.rcParams["xtick.labelsize"] = 10
    plt.rcParams["ytick.labelsize"] = 10
    plt.rcParams["figure.figsize"] = (8.0, 5.0)
    plt.rcParams["axes.grid"] = True
    plt.rcParams["grid.alpha"] = 0.35
    plt.rcParams["grid.linestyle"] = "--"
    plt.rcParams["lines.linewidth"] = 1.6
    plt.rcParams["savefig.bbox"] = "tight"


# =============================================================================
# [Part 1] MCAP Data Ingestion Layer
# =============================================================================

@dataclass
class ImuSample:
    ts_ns: int
    acc: np.ndarray  # (3,) body frame
    gyro: np.ndarray  # (3,) body frame


@dataclass
class DvlSample:
    ts_ns: int
    vel: np.ndarray  # (3,) frame depends on --dvl-frame


@dataclass
class DepthSample:
    ts_ns: int
    depth_m: float


@dataclass
class TruthSample:
    ts_ns: int
    pos: np.ndarray  # (3,) NED
    quat_wxyz: np.ndarray | None = None  # (4,) optional


def nested_attr(obj: Any, path: tuple[str, ...]) -> Any:
    value = obj
    for name in path:
        if not hasattr(value, name):
            raise AttributeError(".".join(path))
        value = getattr(value, name)
    return value


def extract_position_xyz(msg: Any) -> tuple[float, float, float]:
    position_paths = (
        ("pose", "pose", "position"),
        ("pose", "position"),
        ("position",),
    )
    for path in position_paths:
        try:
            position = nested_attr(msg, path)
        except AttributeError:
            continue
        if all(hasattr(position, axis) for axis in ("x", "y", "z")):
            return float(position.x), float(position.y), float(position.z)
    if hasattr(msg, "position_ned"):
        values = list(getattr(msg, "position_ned"))
        if len(values) >= 3:
            return float(values[0]), float(values[1]), float(values[2])
    if all(hasattr(msg, axis) for axis in ("x", "y", "z")):
        return float(msg.x), float(msg.y), float(msg.z)
    raise ValueError(f"Unsupported position message type: {type(msg).__name__}")


def extract_orientation_wxyz(msg: Any) -> tuple[float, float, float, float] | None:
    try:
        quat = nested_attr(msg, ("pose", "pose", "orientation"))
        return float(quat.w), float(quat.x), float(quat.y), float(quat.z)
    except AttributeError:
        pass
    try:
        quat = nested_attr(msg, ("pose", "orientation"))
        return float(quat.w), float(quat.x), float(quat.y), float(quat.z)
    except AttributeError:
        pass
    return None


def select_timestamp_ns(message_wrapper: Any) -> int:
    publish_time_ns = int(getattr(message_wrapper, "publish_time_ns", 0))
    if publish_time_ns > 0:
        return publish_time_ns
    return int(message_wrapper.log_time_ns)


def _quat_to_euler(q: np.ndarray) -> np.ndarray:
    q = q / np.linalg.norm(q)
    w, x, y, z = q
    sinr_cosp = 2 * (w * x + y * z)
    cosr_cosp = 1 - 2 * (x * x + y * y)
    roll = np.arctan2(sinr_cosp, cosr_cosp)
    sinp = 2 * (w * y - z * x)
    pitch = np.sign(sinp) * np.pi / 2 if abs(sinp) >= 1 else np.arcsin(sinp)
    siny_cosp = 2 * (w * z + x * y)
    cosy_cosp = 1 - 2 * (y * y + z * z)
    yaw = np.arctan2(siny_cosp, cosy_cosp)
    return np.array([roll, pitch, yaw], dtype=float)


def _euler_to_quat(rpy: np.ndarray) -> np.ndarray:
    cr = math.cos(rpy[0] * 0.5)
    sr = math.sin(rpy[0] * 0.5)
    cp = math.cos(rpy[1] * 0.5)
    sp = math.sin(rpy[1] * 0.5)
    cy = math.cos(rpy[2] * 0.5)
    sy = math.sin(rpy[2] * 0.5)
    w = cr * cp * cy + sr * sp * sy
    x = sr * cp * cy - cr * sp * sy
    y = cr * sp * cy + sr * cp * sy
    z = cr * cp * sy - sr * sp * cy
    q = np.array([w, x, y, z], dtype=float)
    return q / np.linalg.norm(q)


def load_frame_transform_module():
    module_path = SIM_DIR / "interfaces" / "frame_transform.py"
    if not module_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("frame_transform", str(module_path))
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_mcap_sensor_data(
    mcap_path: Path,
    imu_topic: str,
    dvl_topic: str,
    depth_topic: str,
    truth_topics: list[str],
    dvl_frame: str,
    apply_coord_transform: bool,
    verbose: bool = False,
) -> tuple[list[ImuSample], list[DvlSample], list[DepthSample], list[TruthSample]]:
    ft = load_frame_transform_module()
    topics_to_read = {imu_topic, dvl_topic, depth_topic, *truth_topics}
    imu_samples: list[ImuSample] = []
    dvl_samples: list[DvlSample] = []
    depth_samples: list[DepthSample] = []
    truth_samples: list[TruthSample] = []
    truth_topic_found: str | None = None

    for decoded in read_ros2_messages(str(mcap_path), topics=topics_to_read):
        topic = decoded.channel.topic
        ts_ns = select_timestamp_ns(decoded)
        msg = decoded.ros_msg

        if topic == imu_topic:
            acc = np.array([
                msg.linear_acceleration.x,
                msg.linear_acceleration.y,
                msg.linear_acceleration.z,
            ], dtype=float)
            gyro = np.array([
                msg.angular_velocity.x,
                msg.angular_velocity.y,
                msg.angular_velocity.z,
            ], dtype=float)
            if apply_coord_transform and ft is not None:
                acc = ft.body_vector_ue_to_ned(acc)
                gyro = ft.body_vector_ue_to_ned(gyro)
            imu_samples.append(ImuSample(ts_ns, acc, gyro))
            continue

        if topic == dvl_topic:
            vel = np.array([
                msg.twist.linear.x,
                msg.twist.linear.y,
                msg.twist.linear.z,
            ], dtype=float)
            if dvl_frame == "body" and apply_coord_transform and ft is not None:
                vel = ft.body_vector_ue_to_ned(vel)
            dvl_samples.append(DvlSample(ts_ns, vel))
            continue

        if topic == depth_topic:
            depth_val = float(getattr(msg, "data", 0.0))
            depth_samples.append(DepthSample(ts_ns, depth_val))
            continue

        if topic in truth_topics:
            x, y, z = extract_position_xyz(msg)
            pos = np.array([x, y, z], dtype=float)
            quat = extract_orientation_wxyz(msg)
            quat_arr = np.array(quat, dtype=float) if quat is not None else None
            if apply_coord_transform and ft is not None:
                pos = ft.ue_position_to_ned(pos)
                if quat_arr is not None:
                    rpy_ue = _quat_to_euler(quat_arr)
                    rpy_ned = ft.ue_rpy_to_ned(rpy_ue)
                    quat_arr = _euler_to_quat(rpy_ned)
            truth_samples.append(TruthSample(ts_ns, pos, quat_arr))
            if truth_topic_found is None:
                truth_topic_found = topic
            continue

    imu_samples.sort(key=lambda s: s.ts_ns)
    dvl_samples.sort(key=lambda s: s.ts_ns)
    depth_samples.sort(key=lambda s: s.ts_ns)
    truth_samples.sort(key=lambda s: s.ts_ns)

    if verbose:
        print(f"[INFO] Loaded from {mcap_path.name}:")
        print(f"  IMU samples:    {len(imu_samples)}  (topic: {imu_topic})")
        print(f"  DVL samples:    {len(dvl_samples)}  (topic: {dvl_topic}, frame: {dvl_frame})")
        print(f"  Depth samples:  {len(depth_samples)}  (topic: {depth_topic})")
        print(f"  Truth samples:  {len(truth_samples)}  (topic: {truth_topic_found})")

    return imu_samples, dvl_samples, depth_samples, truth_samples


# =============================================================================
# [Part 2] Algorithm Engines
# =============================================================================

class DeadReckoningEngine:
    """纯航位推算：DVL 速度 + IMU 航向积分，无反馈修正。"""

    def __init__(self, init_pos: np.ndarray, init_yaw: float = 0.0):
        self.p = init_pos.copy()
        self.yaw = float(init_yaw)
        self.history_ts: list[int] = []
        self.history_p: list[np.ndarray] = []
        self._last_imu_ts: int | None = None
        self._last_dvl_ts: int | None = None
        self._last_dvl_vel: np.ndarray | None = None
        self._dt_predict: float = 0.02

    def predict(self, acc_body: np.ndarray, gyro_body: np.ndarray, dt: float) -> None:
        self.yaw += float(gyro_body[2]) * dt
        self._dt_predict = dt

    def update_dvl(self, vel: np.ndarray, ts_ns: int) -> None:
        self._last_dvl_vel = vel.copy()
        self._last_dvl_ts = ts_ns
        if self._last_imu_ts is not None and ts_ns > self._last_imu_ts:
            dt = (ts_ns - self._last_imu_ts) / 1e9
        else:
            dt = self._dt_predict
        if self._last_dvl_vel is not None and dt > 0:
            vx = self._last_dvl_vel[0] * math.cos(self.yaw) - self._last_dvl_vel[1] * math.sin(self.yaw)
            vy = self._last_dvl_vel[0] * math.sin(self.yaw) + self._last_dvl_vel[1] * math.cos(self.yaw)
            vz = self._last_dvl_vel[2]
            self.p[0] += vx * dt
            self.p[1] += vy * dt
            self.p[2] += vz * dt

    def update_depth(self, depth_m: float, ts_ns: int) -> None:
        self.p[2] = depth_m

    def record_state(self, ts_ns: int) -> None:
        self.history_ts.append(ts_ns)
        self.history_p.append(self.p.copy())

    def get_position_history(self) -> tuple[np.ndarray, np.ndarray]:
        if not self.history_ts:
            return np.array([]), np.empty((0, 3))
        return np.array(self.history_ts, dtype=np.int64), np.array(self.history_p, dtype=float)


class StandardEKFEngine:
    """标准 16 状态 EKF（全状态更新，非误差状态）。

    状态向量 (16 维):
      [px, py, pz, vx, vy, vz, qw, qx, qy, qz, ba_x, ba_y, ba_z, bg_x, bg_y, bg_z]
    由于四元数有 4 个元素，全状态 EKF 使用 16 维状态和 16x16 协方差矩阵。
    为处理四元数过参数化问题，在协方差传播后对姿态部分做 QR 修正。
    """

    def __init__(self, cfg: dict):
        self.g = float(cfg.get("gravity", 9.81))
        self.g_n = np.array([0.0, 0.0, -self.g], dtype=float)
        self.imu_acc_is_linear = bool(cfg.get("imu_acc_is_linear", True))

        self.sigma_acc = float(cfg.get("sigma_acc", 0.08))
        self.sigma_gyro = float(cfg.get("sigma_gyro", 0.01))
        self.sigma_ba = float(cfg.get("sigma_ba", 0.001))
        self.sigma_bg = float(cfg.get("sigma_bg", 0.0005))
        self.sigma_dvl = float(cfg.get("sigma_dvl", 0.03))
        self.sigma_depth = float(cfg.get("sigma_depth", 0.05))

        p0 = np.array(cfg.get("init_pos", [0.0, 0.0, 0.0]), dtype=float)
        v0 = np.array(cfg.get("init_vel", [0.0, 0.0, 0.0]), dtype=float)
        q0 = self._quat_normalize(np.array(cfg.get("init_quat_wxyz", [1.0, 0.0, 0.0, 0.0]), dtype=float))
        ba0 = np.array(cfg.get("init_ba", [0.0, 0.0, 0.0]), dtype=float)
        bg0 = np.array(cfg.get("init_bg", [0.0, 0.0, 0.0]), dtype=float)

        self.state = np.concatenate([p0, v0, q0, ba0, bg0])  # 16 维

        init_P = list(cfg.get("init_P_diag", [1.0] * 15))
        if len(init_P) == 15:
            init_P.insert(6, init_P[6])
        self.P = np.diag(np.array(init_P, dtype=float))  # 16x16

        self.history_ts: list[int] = []
        self.history_p: list[np.ndarray] = []
        self.innovation_ts: list[int] = []
        self.innovation_history: list[float] = []
        self.innovation_gate_history: list[float] = []

    @staticmethod
    def _skew(v: np.ndarray) -> np.ndarray:
        return np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]], dtype=float)

    @staticmethod
    def _quat_normalize(q: np.ndarray) -> np.ndarray:
        n = np.linalg.norm(q)
        return q / n if n > 1e-12 else np.array([1.0, 0.0, 0.0, 0.0], dtype=float)

    @staticmethod
    def _quat_multiply(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
        w1, x1, y1, z1 = q1
        w2, x2, y2, z2 = q2
        return np.array([
            w1*w2 - x1*x2 - y1*y2 - z1*z2,
            w1*x2 + x1*w2 + y1*z2 - z1*y2,
            w1*y2 - x1*z2 + y1*w2 + z1*x2,
            w1*z2 + x1*y2 - y1*x2 + z1*w2,
        ], dtype=float)

    @staticmethod
    def _quat_to_rotmat(q: np.ndarray) -> np.ndarray:
        q = np.asarray(q, dtype=float)
        q = q / np.linalg.norm(q)
        w, x, y, z = q
        return np.array([
            [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
            [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
            [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)],
        ], dtype=float)

    @staticmethod
    def _small_angle_quat(dtheta: np.ndarray) -> np.ndarray:
        angle = np.linalg.norm(dtheta)
        if angle < 1e-12:
            return np.array([1.0, 0.5*dtheta[0], 0.5*dtheta[1], 0.5*dtheta[2]], dtype=float)
        axis = dtheta / angle
        half = 0.5 * angle
        return np.array([math.cos(half), *(math.sin(half)*axis)], dtype=float)

    def get_position(self) -> np.ndarray:
        return self.state[0:3].copy()

    def _quat_part(self) -> np.ndarray:
        return self.state[6:10]

    def predict(self, acc_body: np.ndarray, gyro_body: np.ndarray, dt: float) -> None:
        dt = float(dt)
        acc_m = np.asarray(acc_body, dtype=float)
        gyr_m = np.asarray(gyro_body, dtype=float)

        ba = self.state[10:13]
        bg = self.state[13:16]
        q = self._quat_part()

        omega = gyr_m - bg
        dq = self._small_angle_quat(omega * dt)
        q_new = self._quat_normalize(self._quat_multiply(q, dq))
        self.state[6:10] = q_new

        r_nb = self._quat_to_rotmat(q_new)
        a_n = r_nb @ (acc_m - ba)
        if not self.imu_acc_is_linear:
            a_n = a_n + self.g_n

        p = self.state[0:3]
        v = self.state[3:6]
        self.state[0:3] = p + v * dt + 0.5 * a_n * dt * dt
        self.state[3:6] = v + a_n * dt

        # 16x16 状态转移矩阵 F
        F = np.zeros((16, 16), dtype=float)
        F[0:3, 3:6] = np.eye(3)
        F[3:6, 6:9] = -r_nb @ self._skew(acc_m - ba)
        F[3:6, 10:13] = -r_nb
        F[6:9, 6:9] = -self._skew(omega)
        F[6:9, 13:16] = -np.eye(3)

        phi = np.eye(16) + F * dt

        Q = np.zeros((16, 16), dtype=float)
        Q[3:6, 3:6] = (self.sigma_acc ** 2) * np.eye(3) * dt * dt
        Q[6:9, 6:9] = (self.sigma_gyro ** 2) * np.eye(3) * dt * dt
        Q[10:13, 10:13] = (self.sigma_ba ** 2) * np.eye(3) * dt
        Q[13:16, 13:16] = (self.sigma_bg ** 2) * np.eye(3) * dt

        self.P = phi @ self.P @ phi.T + Q

        # 处理四元数过参数化: 将 q 行/列的协方差投影到切空间
        self._quaternion_covariance_correction()

    def _quaternion_covariance_correction(self) -> None:
        # 将 16x16 P 中四元数部分(6:10, 6:10)的秩修正为 3
        q_cov = self.P[6:10, 6:10].copy()
        q = self._quat_part()
        proj = np.eye(4) - np.outer(q, q)
        q_cov_corrected = proj @ q_cov @ proj
        self.P[6:10, 6:10] = q_cov_corrected
        # 同时修正交叉项
        for i in list(range(6)) + list(range(10, 16)):
            self.P[i, 6:10] = self.P[i, 6:10] @ proj.T
            self.P[6:10, i] = proj @ self.P[6:10, i]

    def update_dvl(self, vel: np.ndarray, ts_ns: int = 0) -> None:
        z = np.asarray(vel, dtype=float).reshape(3)
        h = self.state[3:6]
        y = z - h
        H = np.zeros((3, 16), dtype=float)
        H[:, 3:6] = np.eye(3)
        R = (self.sigma_dvl ** 2) * np.eye(3)

        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.pinv(S)
        dx = K @ y
        self.state += dx
        I_KH = np.eye(16) - K @ H
        self.P = I_KH @ self.P @ I_KH.T + K @ R @ K.T

        self.innovation_ts.append(ts_ns)
        self.innovation_history.append(float(np.linalg.norm(y)))
        self.innovation_gate_history.append(float(3.0 * self.sigma_dvl))

    def update_depth(self, depth_m: float, ts_ns: int = 0) -> None:
        z = np.array([depth_m], dtype=float)
        h = self.state[2]
        y = z - np.array([h], dtype=float)
        H = np.zeros((1, 16), dtype=float)
        H[0, 2] = 1.0
        R = np.array([[self.sigma_depth ** 2]], dtype=float)

        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.pinv(S)
        dx = K @ y
        self.state += dx
        I_KH = np.eye(16) - K @ H
        self.P = I_KH @ self.P @ I_KH.T + K @ R @ K.T

        self.innovation_ts.append(ts_ns)
        self.innovation_history.append(float(np.abs(y[0])))
        self.innovation_gate_history.append(float(3.0 * self.sigma_depth))

    def record_state(self, ts_ns: int) -> None:
        self.history_ts.append(ts_ns)
        self.history_p.append(self.get_position())


class EseKfEngine:
    """ES-EKF 包装器：复用 algorithm/es_ekf.py 中的 ES_EKF 类。"""

    def __init__(self, cfg: dict, auto_init: bool = True):
        cfg = cfg.copy()
        cfg["auto_init"] = auto_init
        cfg["use_first_dvl_for_init"] = auto_init
        cfg["use_first_depth_for_init"] = auto_init
        cfg["enable_bias_calibration"] = True  # 启用零偏预校准
        cfg["bias_calibration_samples"] = 50  # 使用前50个IMU样本进行校准
        ES_EKF_CLASS = self._load_es_ekf_class()
        self.filter = ES_EKF_CLASS(cfg)
        self.history_ts: list[int] = []
        self.history_p: list[np.ndarray] = []
        self.innovation_ts: list[int] = []
        self.innovation_history: list[float] = []
        self.innovation_gate_history: list[float] = []
        self._init_info_logged = False
        self._bias_calibration_pending = True  # 标志位：零偏预校准是否还在进行中

    @staticmethod
    def _load_es_ekf_class():
        module_path = ALGO_DIR / "es_ekf.py"
        spec = importlib.util.spec_from_file_location("es_ekf_offline", str(module_path))
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Failed to load ES-EKF module: {module_path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.ES_EKF

    def get_position(self) -> np.ndarray:
        s = self.filter.get_state()
        return s["p"].copy()

    def predict(self, acc_body: np.ndarray, gyro_body: np.ndarray, dt: float) -> None:
        # 在首次predict之前，执行零偏预校准
        if self._bias_calibration_pending:
            self.filter.add_bias_calibration_sample(acc_body, gyro_body)
            if self.filter.is_bias_calibration_done():
                self._bias_calibration_pending = False
                bias_info = self.filter.get_bias_calibration_info()
                if bias_info:
                    print(f"  [ES-EKF] Bias pre-calibration completed:")
                    print(f"    Estimated acc bias (b_a): [{bias_info['estimated_ba'][0]:.6f}, {bias_info['estimated_ba'][1]:.6f}, {bias_info['estimated_ba'][2]:.6f}]")
                    print(f"    Estimated gyro bias (b_g): [{bias_info['estimated_bg'][0]:.6f}, {bias_info['estimated_bg'][1]:.6f}, {bias_info['estimated_bg'][2]:.6f}]")
        
        self.filter.predict(acc_body, gyro_body, dt)

    def update_dvl(self, vel: np.ndarray, ts_ns: int = 0) -> None:
        was_initialized = self.filter.is_initialized()
        h_before = self.filter.get_state()
        self.filter.correct_dvl_world(vel)
        h_after = self.filter.get_state()
        innovation = np.linalg.norm(h_after["p"] - h_before["p"])
        self.innovation_ts.append(ts_ns)
        self.innovation_history.append(float(innovation))
        self.innovation_gate_history.append(float(3.0 * self.filter.sigma_dvl))
        if not was_initialized and self.filter.is_initialized():
            self._log_init_event("dvl")

    def update_depth(self, depth_m: float, ts_ns: int = 0) -> None:
        was_initialized = self.filter.is_initialized()
        h_before = self.filter.get_state()
        self.filter.correct_depth(-depth_m)
        h_after = self.filter.get_state()
        innovation = abs(h_after["p"][2] - h_before["p"][2])
        self.innovation_ts.append(ts_ns)
        self.innovation_history.append(float(innovation))
        self.innovation_gate_history.append(float(3.0 * self.filter.sigma_depth))
        if not was_initialized and self.filter.is_initialized():
            self._log_init_event("depth")

    def _log_init_event(self, source: str) -> None:
        """记录滤波器初始化事件。"""
        if self._init_info_logged:
            return
        self._init_info_logged = True
        init_info = getattr(self.filter, '_init_info', None)
        if init_info is not None:
            aligned_pos = init_info.get('aligned_pos', [0.0, 0.0, 0.0])
            pos_offset = init_info.get('position_offset', [0.0, 0.0, 0.0])
            print(f"  [ES-EKF] Auto-initialized from first {source} frame")
            print(f"    Aligned position: [{aligned_pos[0]:.4f}, {aligned_pos[1]:.4f}, {aligned_pos[2]:.4f}]")
            print(f"    Position offset from config: [{pos_offset[0]:.4f}, {pos_offset[1]:.4f}, {pos_offset[2]:.4f}]")
        else:
            state = self.filter.get_state()
            print(f"  [ES-EKF] Initialized from first {source} frame")
            print(f"    Position: [{state['p'][0]:.4f}, {state['p'][1]:.4f}, {state['p'][2]:.4f}]")

    def record_state(self, ts_ns: int) -> None:
        self.history_ts.append(ts_ns)
        self.history_p.append(self.get_position())


# =============================================================================
# [Part 3] Metrics Computation
# =============================================================================

def compute_rmse(estimated: np.ndarray, truth: np.ndarray) -> float:
    if estimated.size == 0 or truth.size == 0:
        return float("nan")
    errors = np.linalg.norm(estimated - truth, axis=1)
    return float(np.sqrt(np.mean(errors ** 2)))


def compute_rmse_xy(estimated: np.ndarray, truth: np.ndarray) -> float:
    if estimated.size == 0 or truth.size == 0:
        return float("nan")
    errors = np.linalg.norm(estimated[:, :2] - truth[:, :2], axis=1)
    return float(np.sqrt(np.mean(errors ** 2)))


def compute_rmse_z(estimated: np.ndarray, truth: np.ndarray) -> float:
    if estimated.size == 0 or truth.size == 0:
        return float("nan")
    errors = np.abs(estimated[:, 2] - truth[:, 2])
    return float(np.sqrt(np.mean(errors ** 2)))


def compute_cep(estimated_xy: np.ndarray, truth_xy: np.ndarray) -> float:
    if estimated_xy.size == 0 or truth_xy.size == 0:
        return float("nan")
    lateral_errors = np.linalg.norm(estimated_xy[:, :2] - truth_xy[:, :2], axis=1)
    return float(np.median(lateral_errors))


def compute_max_drift(estimated_xy: np.ndarray, truth_xy: np.ndarray) -> float:
    if estimated_xy.size == 0 or truth_xy.size == 0:
        return float("nan")
    return float(np.max(np.linalg.norm(estimated_xy[:, :2] - truth_xy[:, :2], axis=1)))


def compute_dr_error_trend(dr_p: np.ndarray, truth_p: np.ndarray, truth_t: np.ndarray) -> tuple[np.ndarray, bool]:
    if dr_p.size < 2 or truth_p.size < 2:
        return np.array([]), False
    errors = np.linalg.norm(dr_p[:, :2] - truth_p[:, :2], axis=1)
    if len(errors) < 3:
        return errors, False
    first_half = np.mean(errors[:len(errors)//2])
    second_half = np.mean(errors[len(errors)//2:])
    is_increasing = second_half > first_half * 1.1
    return errors, bool(is_increasing)


# =============================================================================
# [Part 4] Visualization
# =============================================================================

def plot_trajectory_xy(
    truth_xy: np.ndarray,
    dr_xy: np.ndarray,
    std_ekf_xy: np.ndarray,
    es_ekf_xy: np.ndarray,
    output_path: Path,
    dpi: int = 300,
) -> None:
    assert plt is not None
    fig, ax = plt.subplots(1, 1, figsize=(8.0, 7.0), dpi=dpi)

    all_x = np.concatenate([truth_xy[:, 0], dr_xy[:, 0], std_ekf_xy[:, 0], es_ekf_xy[:, 0]])
    all_y = np.concatenate([truth_xy[:, 1], dr_xy[:, 1], std_ekf_xy[:, 1], es_ekf_xy[:, 1]])
    pad_x = max(0.5, 0.05 * (all_x.max() - all_x.min() + 1e-9))
    pad_y = max(0.5, 0.05 * (all_y.max() - all_y.min() + 1e-9))

    ax.plot(truth_xy[:, 0], truth_xy[:, 1], "k--", linewidth=1.3, label="Ground Truth", zorder=5)
    ax.plot(dr_xy[:, 0], dr_xy[:, 1], color="#d62728", linewidth=1.6, label="Raw DR", zorder=4)
    ax.plot(std_ekf_xy[:, 0], std_ekf_xy[:, 1], color="#1f77b4", linewidth=1.6, label="Std EKF", zorder=3)
    ax.plot(es_ekf_xy[:, 0], es_ekf_xy[:, 1], color="#2ca02c", linewidth=1.6, label="ES-EKF", zorder=2)

    for traj, color, marker in [(truth_xy, "k", "s"), (dr_xy, "#d62728", "o"), (std_ekf_xy, "#1f77b4", "^"), (es_ekf_xy, "#2ca02c", "d")]:
        if traj.shape[0] > 0:
            ax.scatter(traj[0, 0], traj[0, 1], color=color, marker=marker, s=60, zorder=6, edgecolors="white", linewidth=0.5)
            ax.scatter(traj[-1, 0], traj[-1, 1], color=color, marker="*", s=120, zorder=7, edgecolors="white", linewidth=0.5)

    ax.set_xlim(all_x.min() - pad_x, all_x.max() + pad_x)
    ax.set_ylim(all_y.min() - pad_y, all_y.max() + pad_y)
    ax.set_xlabel("X [m] (North)")
    ax.set_ylabel("Y [m] (East)")
    ax.set_title("AUV Trajectory Comparison (XY Plane)")
    ax.legend(loc="best", frameon=True)
    ax.set_aspect("equal")

    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def plot_error_time(
    truth_t: np.ndarray,
    truth_xyz: np.ndarray,
    dr_xyz: np.ndarray,
    std_ekf_xyz: np.ndarray,
    es_ekf_xyz: np.ndarray,
    output_path: Path,
    dpi: int = 300,
) -> None:
    assert plt is not None
    fig, ax = plt.subplots(1, 1, figsize=(9.0, 4.5), dpi=dpi)

    def _error_curve(est_xyz: np.ndarray) -> np.ndarray:
        if est_xyz.size == 0:
            return np.full(truth_t.shape, np.nan)
        return np.linalg.norm(est_xyz - truth_xyz, axis=1)

    ax.plot(truth_t, _error_curve(dr_xyz), color="#d62728", linewidth=1.6, label="Raw DR")
    ax.plot(truth_t, _error_curve(std_ekf_xyz), color="#1f77b4", linewidth=1.6, label="Std EKF")
    ax.plot(truth_t, _error_curve(es_ekf_xyz), color="#2ca02c", linewidth=1.6, label="ES-EKF")

    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Position Error [m]")
    ax.set_title("Position Error vs. Time")
    ax.legend(loc="best", frameon=True)
    ax.set_ylim(bottom=0)

    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def plot_innovation_residual(
    global_start_ns: int,
    innovations: list[float],
    innovation_ts: list[int],
    gate_bounds: list[float],
    output_path: Path,
    dpi: int = 300,
) -> None:
    assert plt is not None
    if not innovations or not innovation_ts:
        return
    t = (np.array(innovation_ts, dtype=np.float64) - float(global_start_ns)) / 1e9
    innov = np.array(innovations, dtype=float)
    gates = np.array(gate_bounds, dtype=float)

    fig, ax = plt.subplots(1, 1, figsize=(9.0, 4.5), dpi=dpi)
    ax.plot(t, innov, color="#ff7f0e", linewidth=1.2, label="Innovation Norm", zorder=2)
    ax.plot(t, gates, color="#7f7f7f", linestyle="--", linewidth=1.0, label="3-sigma Gate", zorder=1)
    ax.fill_between(t, -gates, gates, color="#d3d3d3", alpha=0.3, zorder=0)
    ax.axhline(0, color="#333333", linewidth=0.5, zorder=0)

    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Innovation")
    ax.set_title("ES-EKF Innovation Residual vs. 3-sigma Gate")
    ax.legend(loc="best", frameon=True)

    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def plot_error_components(
    truth_t: np.ndarray,
    truth_xyz: np.ndarray,
    dr_xyz: np.ndarray,
    std_ekf_xyz: np.ndarray,
    es_ekf_xyz: np.ndarray,
    output_path: Path,
    dpi: int = 300,
) -> None:
    assert plt is not None
    fig, (ax_xy, ax_z) = plt.subplots(2, 1, figsize=(9.0, 6.0), dpi=dpi, sharex=True)

    def _error_xy(est_xyz: np.ndarray) -> np.ndarray:
        if est_xyz.size == 0:
            return np.full(truth_t.shape, np.nan)
        return np.linalg.norm(est_xyz[:, :2] - truth_xyz[:, :2], axis=1)

    def _error_z(est_xyz: np.ndarray) -> np.ndarray:
        if est_xyz.size == 0:
            return np.full(truth_t.shape, np.nan)
        return np.abs(est_xyz[:, 2] - truth_xyz[:, 2])

    ax_xy.plot(truth_t, _error_xy(dr_xyz), color="#d62728", linewidth=1.4, label="Raw DR")
    ax_xy.plot(truth_t, _error_xy(std_ekf_xyz), color="#1f77b4", linewidth=1.4, label="Std EKF")
    ax_xy.plot(truth_t, _error_xy(es_ekf_xyz), color="#2ca02c", linewidth=1.4, label="ES-EKF")
    ax_xy.set_ylabel("XY Error [m]")
    ax_xy.set_title("Horizontal (XY) Position Error")
    ax_xy.legend(loc="best", frameon=True)
    ax_xy.set_ylim(bottom=0)

    ax_z.plot(truth_t, _error_z(dr_xyz), color="#d62728", linewidth=1.4, label="Raw DR")
    ax_z.plot(truth_t, _error_z(std_ekf_xyz), color="#1f77b4", linewidth=1.4, label="Std EKF")
    ax_z.plot(truth_t, _error_z(es_ekf_xyz), color="#2ca02c", linewidth=1.4, label="ES-EKF")
    ax_z.set_xlabel("Time [s]")
    ax_z.set_ylabel("Z Error [m]")
    ax_z.set_title("Depth (Z) Position Error")
    ax_z.legend(loc="best", frameon=True)
    ax_z.set_ylim(bottom=0)

    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


# =============================================================================
# [Part 5] Report Generation
# =============================================================================

def generate_benchmark_report(
    input_file: Path,
    duration_s: float,
    imu_hz: float,
    dvl_hz: float,
    truth_hz: float,
    metrics: dict[str, dict[str, float]],
    latencies: dict[str, float],
    dr_error_increasing: bool,
    output_path: Path,
) -> None:
    lines: list[str] = []
    lines.append("# AUV 定位算法离线基准测试报告\n")
    lines.append("## 测试信息\n")
    lines.append(f"- **输入文件**: `{input_file}`")
    lines.append(f"- **数据时长**: {duration_s:.1f} s")
    lines.append(f"- **IMU 频率**: {imu_hz:.1f} Hz")
    lines.append(f"- **DVL 频率**: {dvl_hz:.1f} Hz")
    lines.append(f"- **Ground Truth 频率**: {truth_hz:.1f} Hz\n")
    lines.append("## 评估指标\n")
    lines.append("| 算法 | XY RMSE (m) | Z RMSE (m) | 3D RMSE (m) | CEP50 (m) | Max Drift (m) | 平均耗时 (μs/frame) |")
    lines.append("|------|-------------|------------|-------------|-----------|---------------|---------------------|")

    for algo_key in ("raw_dr", "std_ekf", "es_ekf"):
        m = metrics.get(algo_key, {})
        lat = latencies.get(algo_key, float("nan"))
        algo_name = {"raw_dr": "Raw DR", "std_ekf": "Std EKF", "es_ekf": "ES-EKF"}.get(algo_key, algo_key)
        lines.append(
            f"| {algo_name} "
            f"| {m.get('rmse_xy', float('nan')):.3f} "
            f"| {m.get('rmse_z', float('nan')):.3f} "
            f"| {m.get('rmse_3d', float('nan')):.3f} "
            f"| {m.get('cep50', float('nan')):.3f} "
            f"| {m.get('max_drift', float('nan')):.3f} "
            f"| {lat:.1f} |"
        )

    lines.append("\n## 结论\n")
    lines.append(f"- **Raw DR 误差随时间线性增长**: {'是' if dr_error_increasing else '否'}")

    es_rmse = metrics.get("es_ekf", {}).get("rmse_3d", float("inf"))
    dr_rmse = metrics.get("raw_dr", {}).get("rmse_3d", float("inf"))
    if es_rmse < dr_rmse * 0.5:
        lines.append("- **ES-EKF RMSE 显著低于 Raw DR**: 是 (ES-EKF RMSE < 50% of DR RMSE)")
    else:
        lines.append(f"- **ES-EKF RMSE 显著低于 Raw DR**: 否 (ES-EKF RMSE = {es_rmse:.3f}m, DR RMSE = {dr_rmse:.3f}m)")

    std_rmse = metrics.get("std_ekf", {}).get("rmse_3d", float("nan"))
    if not math.isnan(std_rmse) and not math.isnan(es_rmse):
        if es_rmse < std_rmse:
            lines.append(f"- **ES-EKF vs Std EKF**: ES-EKF RMSE ({es_rmse:.3f}m) 优于 Std EKF ({std_rmse:.3f}m)")
        else:
            lines.append(f"- **ES-EKF vs Std EKF**: Std EKF RMSE ({std_rmse:.3f}m) 优于 ES-EKF ({es_rmse:.3f}m)")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# =============================================================================
# [Main] CLI & Pipeline
# =============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="基于 MCAP 回放的 AUV 定位算法离线基准测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--input", type=Path, default=None, help="输入 .mcap 文件路径 (运行 EKF 基准测试时必需)")
    parser.add_argument("--output-dir", type=Path, default=None, help="输出目录，默认为 <input>.benchmark/")
    parser.add_argument("--imu-topic", default=DEFAULT_IMU_TOPIC, help=f"IMU topic (默认: {DEFAULT_IMU_TOPIC})")
    parser.add_argument("--dvl-topic", default=DEFAULT_DVL_TOPIC, help=f"DVL topic (默认: {DEFAULT_DVL_TOPIC})")
    parser.add_argument("--depth-topic", default=DEFAULT_DEPTH_TOPIC, help=f"Depth topic (默认: {DEFAULT_DEPTH_TOPIC})")
    parser.add_argument("--truth-topics", default=",".join(DEFAULT_TRUTH_TOPICS), help=f"真值 topic 列表 (逗号分隔, 默认: {','.join(DEFAULT_TRUTH_TOPICS)})")
    parser.add_argument("--dvl-frame", choices=["body", "world"], default="world", help="DVL 速度坐标系 (默认: world)")
    parser.add_argument("--no-coordinate-transform", action="store_true", help="跳过 UE4->NED 坐标系转换 (假设数据已是 NED)")
    parser.add_argument("--ekf-config", type=Path, default=Path(DEFAULT_EKF_CONFIG), help=f"EKF 参数 YAML (默认: {DEFAULT_EKF_CONFIG})")
    parser.add_argument("--verbose", action="store_true", help="打印详细信息")
    parser.add_argument("--dpi", type=int, default=300, help="图表 DPI (默认: 300)")
    parser.add_argument("--skip-assertions", action="store_true", help="跳过逻辑断言验证")
    parser.add_argument("--dvl-downsample-hz", type=float, default=None, help="DVL降采样频率 (默认: None=不降采样，5.0=模拟真实声学DVL)")
    
    # 控制基准测试选项
    parser.add_argument("--run-control-benchmark", action="store_true", 
                        help="运行控制算法基准测试 (PID/MPC)")
    parser.add_argument("--control-type", type=str, choices=["pid", "mpc", "both"], default="both",
                        help="要测试的控制器类型 (默认: both)")
    parser.add_argument("--skip-ekf-benchmark", action="store_true",
                        help="跳过 EKF 定位基准测试，仅运行控制测试")
    
    return parser.parse_args()


def load_ekf_config(config_path: Path) -> dict:
    import yaml
    if not config_path.exists():
        print(f"[WARN] EKF config not found: {config_path}, using defaults")
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if isinstance(data, dict):
        return data.get("ekf", data)
    return {}


def _resample_to_truth(
    truth_ts: np.ndarray,
    est_ts: np.ndarray,
    est_p: np.ndarray,
) -> np.ndarray:
    if est_p.ndim != 2 or est_p.shape[1] != 3:
        return np.empty((0, 3))
    if est_ts.size < 2:
        return np.empty((0, 3))
    truth_t = truth_ts.astype(float)
    est_t = est_ts.astype(float)
    resampled = np.column_stack([
        np.interp(truth_t, est_t, est_p[:, i])
        for i in range(3)
    ])
    return resampled


def _compute_sample_rate(ts_list: list[int], duration_s: float) -> float:
    if duration_s <= 0 or len(ts_list) < 2:
        return 0.0
    return len(ts_list) / duration_s


def main() -> None:
    args = parse_args()
    ensure_runtime_dependencies()
    configure_matplotlib()

    # 如果仅运行控制测试，跳过 EKF 基准测试
    if args.skip_ekf_benchmark:
        if args.run_control_benchmark:
            _run_control_benchmarks(
                output_dir=get_output_dir('results/control'),
                control_type=args.control_type,
                dpi=args.dpi,
                verbose=args.verbose,
            )
            print("\n" + "=" * 60)
            print("  控制基准测试完成")
            print("=" * 60)
            return
        else:
            raise SystemExit("请指定 --run-control-benchmark 以运行控制测试")

    if args.input is None:
        raise SystemExit("运行 EKF 基准测试需要指定 --input 参数")

    if not args.input.exists():
        raise SystemExit(f"Input file not found: {args.input}")

    output_dir = args.output_dir if args.output_dir else get_output_dir(f"results/ekf_benchmark/{args.input.stem}")
    output_dir.mkdir(parents=True, exist_ok=True)

    ekf_cfg = load_ekf_config(args.ekf_config)
    truth_topic_list = [t.strip() for t in args.truth_topics.split(",") if t.strip()]
    apply_transform = not args.no_coordinate_transform

    print("=" * 60)
    print("  AUV Offline EKF Benchmark")
    print("=" * 60)

    print("\n[1/6] Reading MCAP sensor data ...")
    imu_samples, dvl_samples, depth_samples, truth_samples = read_mcap_sensor_data(
        mcap_path=args.input,
        imu_topic=args.imu_topic,
        dvl_topic=args.dvl_topic,
        depth_topic=args.depth_topic,
        truth_topics=truth_topic_list,
        dvl_frame=args.dvl_frame,
        apply_coord_transform=apply_transform,
        verbose=args.verbose,
    )

    if not truth_samples:
        raise SystemExit("No ground truth samples found in the MCAP file.")
    if not imu_samples:
        raise SystemExit("No IMU samples found in the MCAP file.")

    truth_ts = np.array([s.ts_ns for s in truth_samples], dtype=np.int64)
    truth_pos = np.array([s.pos for s in truth_samples], dtype=float)
    global_start_ns = truth_ts[0]
    duration_s = (truth_ts[-1] - global_start_ns) / 1e9

    imu_hz = _compute_sample_rate([s.ts_ns for s in imu_samples], duration_s)
    dvl_hz = _compute_sample_rate([s.ts_ns for s in dvl_samples], duration_s)
    truth_hz = _compute_sample_rate([s.ts_ns for s in truth_samples], duration_s)

    print(f"\n  Duration: {duration_s:.1f} s")
    print(f"  IMU: {imu_hz:.1f} Hz, DVL: {dvl_hz:.1f} Hz, Truth: {truth_hz:.1f} Hz")

    # DVL 降采样：模拟真实声学 DVL 频率（5-10 Hz）
    if args.dvl_downsample_hz is not None and args.dvl_downsample_hz > 0:
        dvl_interval_ns = int(1e9 / args.dvl_downsample_hz)
        downsampled_dvl = []
        last_dvl_ts_ns = -int(1e18)  # 负无穷大
        for s in dvl_samples:
            if s.ts_ns - last_dvl_ts_ns >= dvl_interval_ns:
                downsampled_dvl.append(s)
                last_dvl_ts_ns = s.ts_ns
        original_dvl_count = len(dvl_samples)
        dvl_samples = downsampled_dvl
        dvl_hz = _compute_sample_rate([s.ts_ns for s in dvl_samples], duration_s)
        print(f"  DVL downsampled: {original_dvl_count} -> {len(dvl_samples)} samples ({dvl_hz:.1f} Hz)")

    print("\n[2/6] Initializing algorithm engines ...")
    init_pos = truth_pos[0].copy()
    init_yaw = 0.0
    if truth_samples[0].quat_wxyz is not None:
        rpy = _quat_to_euler(truth_samples[0].quat_wxyz)
        init_yaw = float(rpy[2])

    dr_engine = DeadReckoningEngine(init_pos, init_yaw)

    ekf_cfg_aligned = ekf_cfg.copy()
    ekf_cfg_aligned["init_pos"] = init_pos.tolist()
    ekf_cfg_aligned["init_vel"] = ekf_cfg.get("init_vel", [0.0, 0.0, 0.0])
    ekf_cfg_aligned["auto_init"] = True
    ekf_cfg_aligned["use_first_dvl_for_init"] = True
    ekf_cfg_aligned["use_first_depth_for_init"] = True

    std_ekf_engine = StandardEKFEngine(ekf_cfg_aligned)
    es_ekf_engine = EseKfEngine(ekf_cfg_aligned, auto_init=True)

    if args.verbose:
        print("  Dead Reckoning engine: OK")
        print("  Standard EKF engine:   OK")
        print("  ES-EKF engine:         OK")

    print("\n[3/6] Running parallel filtering ...")
    imu_idx = 0
    dvl_idx = 0
    depth_idx = 0
    last_imu_ts: int | None = None

    imu_timestamps_ns = [s.ts_ns for s in imu_samples]
    dvl_timestamps_ns = [s.ts_ns for s in dvl_samples]
    depth_timestamps_ns = [s.ts_ns for s in depth_samples]
    truth_timestamps_ns = [s.ts_ns for s in truth_samples]

    all_event_ts = sorted(set(
        imu_timestamps_ns + dvl_timestamps_ns + depth_timestamps_ns + truth_timestamps_ns
    ))

    perf_dr: list[float] = []
    perf_std: list[float] = []
    perf_es: list[float] = []

    for event_ts in all_event_ts:
        while imu_idx < len(imu_samples) and imu_samples[imu_idx].ts_ns <= event_ts:
            imu = imu_samples[imu_idx]
            dt = (imu.ts_ns - last_imu_ts) / 1e9 if last_imu_ts is not None else 0.02
            last_imu_ts = imu.ts_ns

            t0 = time.perf_counter()
            dr_engine.predict(imu.acc, imu.gyro, dt)
            perf_dr.append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            std_ekf_engine.predict(imu.acc, imu.gyro, dt)
            perf_std.append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            es_ekf_engine.predict(imu.acc, imu.gyro, dt)
            perf_es.append(time.perf_counter() - t0)

            imu_idx += 1

        while dvl_idx < len(dvl_samples) and dvl_samples[dvl_idx].ts_ns <= event_ts:
            dvl = dvl_samples[dvl_idx]
            t0 = time.perf_counter()
            dr_engine.update_dvl(dvl.vel, dvl.ts_ns)
            perf_dr.append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            std_ekf_engine.update_dvl(dvl.vel, dvl.ts_ns)
            perf_std.append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            es_ekf_engine.update_dvl(dvl.vel, dvl.ts_ns)
            perf_es.append(time.perf_counter() - t0)

            dvl_idx += 1

        while depth_idx < len(depth_samples) and depth_samples[depth_idx].ts_ns <= event_ts:
            depth = depth_samples[depth_idx]
            t0 = time.perf_counter()
            dr_engine.update_depth(depth.depth_m, depth.ts_ns)
            perf_dr.append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            std_ekf_engine.update_depth(depth.depth_m, depth.ts_ns)
            perf_std.append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            es_ekf_engine.update_depth(depth.depth_m, depth.ts_ns)
            perf_es.append(time.perf_counter() - t0)

            depth_idx += 1

        if event_ts in truth_timestamps_ns:
            dr_engine.record_state(event_ts)
            std_ekf_engine.record_state(event_ts)
            es_ekf_engine.record_state(event_ts)

    total_events = len(perf_dr) + len(perf_std) + len(perf_es)
    print(f"  Processed {len(all_event_ts)} events, {total_events} algorithm steps")

    print("\n[4/6] Computing metrics ...")
    truth_ts_aligned = np.array(dr_engine.history_ts, dtype=np.int64)
    dr_pos = np.array(dr_engine.history_p, dtype=float) if dr_engine.history_p else np.empty((0, 3))
    std_pos = np.array(std_ekf_engine.history_p, dtype=float) if std_ekf_engine.history_p else np.empty((0, 3))
    es_pos = np.array(es_ekf_engine.history_p, dtype=float) if es_ekf_engine.history_p else np.empty((0, 3))

    truth_ts_float = (truth_ts_aligned - global_start_ns) / 1e9
    truth_pos_at_alg = _resample_to_truth(truth_ts_aligned, truth_ts, truth_pos)

    dr_valid = dr_pos.shape[0] > 0 and truth_pos_at_alg.shape[0] > 0
    std_valid = std_pos.shape[0] > 0 and truth_pos_at_alg.shape[0] > 0
    es_valid = es_pos.shape[0] > 0 and truth_pos_at_alg.shape[0] > 0

    metrics: dict[str, dict[str, float]] = {}

    if dr_valid:
        metrics["raw_dr"] = {
            "rmse_xy": compute_rmse_xy(dr_pos, truth_pos_at_alg),
            "rmse_z": compute_rmse_z(dr_pos, truth_pos_at_alg),
            "rmse_3d": compute_rmse(dr_pos, truth_pos_at_alg),
            "cep50": compute_cep(dr_pos, truth_pos_at_alg),
            "max_drift": compute_max_drift(dr_pos, truth_pos_at_alg),
        }
    else:
        metrics["raw_dr"] = {k: float("nan") for k in ("rmse_xy", "rmse_z", "rmse_3d", "cep50", "max_drift")}

    if std_valid:
        metrics["std_ekf"] = {
            "rmse_xy": compute_rmse_xy(std_pos, truth_pos_at_alg),
            "rmse_z": compute_rmse_z(std_pos, truth_pos_at_alg),
            "rmse_3d": compute_rmse(std_pos, truth_pos_at_alg),
            "cep50": compute_cep(std_pos, truth_pos_at_alg),
            "max_drift": compute_max_drift(std_pos, truth_pos_at_alg),
        }
    else:
        metrics["std_ekf"] = {k: float("nan") for k in ("rmse_xy", "rmse_z", "rmse_3d", "cep50", "max_drift")}

    if es_valid:
        metrics["es_ekf"] = {
            "rmse_xy": compute_rmse_xy(es_pos, truth_pos_at_alg),
            "rmse_z": compute_rmse_z(es_pos, truth_pos_at_alg),
            "rmse_3d": compute_rmse(es_pos, truth_pos_at_alg),
            "cep50": compute_cep(es_pos, truth_pos_at_alg),
            "max_drift": compute_max_drift(es_pos, truth_pos_at_alg),
        }
    else:
        metrics["es_ekf"] = {k: float("nan") for k in ("rmse_xy", "rmse_z", "rmse_3d", "cep50", "max_drift")}

    dr_errors, dr_error_increasing = compute_dr_error_trend(dr_pos, truth_pos_at_alg, truth_ts_float)

    latencies: dict[str, float] = {}
    latencies["raw_dr"] = (np.mean(perf_dr) * 1e6) if perf_dr else float("nan")
    latencies["std_ekf"] = (np.mean(perf_std) * 1e6) if perf_std else float("nan")
    latencies["es_ekf"] = (np.mean(perf_es) * 1e6) if perf_es else float("nan")

    for algo_name, m in metrics.items():
        print(f"  {algo_name:8s}: RMSE_XY={m['rmse_xy']:.3f}m  RMSE_Z={m['rmse_z']:.3f}m  RMSE_3D={m['rmse_3d']:.3f}m  CEP50={m['cep50']:.3f}m")

    print("\n[5/6] Generating plots ...")

    if dr_valid and std_valid and es_valid:
        plot_trajectory_xy(
            truth_pos_at_alg, dr_pos, std_pos, es_pos,
            output_path=output_dir / "trajectory_xy.png", dpi=args.dpi,
        )
        print("  Saved: trajectory_xy.png")

        plot_error_time(
            truth_ts_float, truth_pos_at_alg, dr_pos, std_pos, es_pos,
            output_path=output_dir / "error_time.png", dpi=args.dpi,
        )
        print("  Saved: error_time.png")

        plot_error_components(
            truth_ts_float, truth_pos_at_alg, dr_pos, std_pos, es_pos,
            output_path=output_dir / "error_components.png", dpi=args.dpi,
        )
        print("  Saved: error_components.png")

        if es_ekf_engine.innovation_history:
            plot_innovation_residual(
                global_start_ns,
                es_ekf_engine.innovation_history,
                es_ekf_engine.innovation_ts,
                es_ekf_engine.innovation_gate_history,
                output_path=output_dir / "innovation_residual.png", dpi=args.dpi,
            )
            print("  Saved: innovation_residual.png")
    else:
        print("  [WARN] Not all algorithms produced valid results; some plots skipped.")

        if dr_valid:
            fig, ax = plt.subplots(1, 1, figsize=(7.0, 5.0), dpi=args.dpi)
            ax.plot(dr_pos[:, 0], dr_pos[:, 1], color="#d62728", linewidth=1.6, label="Raw DR")
            if truth_pos_at_alg.shape[0] > 0:
                ax.plot(truth_pos_at_alg[:, 0], truth_pos_at_alg[:, 1], "k--", linewidth=1.3, label="Truth")
            ax.set_xlabel("X [m]"); ax.set_ylabel("Y [m]")
            ax.set_title("Raw DR Trajectory"); ax.legend(); ax.set_aspect("equal")
            fig.savefig(output_dir / "trajectory_xy_dr_only.png", dpi=args.dpi)
            plt.close(fig)

    print("\n[6/6] Generating benchmark report ...")
    report_path = output_dir / "benchmark_results.md"
    generate_benchmark_report(
        input_file=args.input,
        duration_s=duration_s,
        imu_hz=imu_hz,
        dvl_hz=dvl_hz,
        truth_hz=truth_hz,
        metrics=metrics,
        latencies=latencies,
        dr_error_increasing=dr_error_increasing,
        output_path=report_path,
    )
    print(f"  Saved: benchmark_results.md")

    if not args.skip_assertions:
        print("\n[VALIDATION] Running logical assertions ...")
        assertions_passed = True

        if dr_valid:
            if not dr_error_increasing:
                print("  [WARN] Assertion: Raw DR error should increase over time - FAILED")
                assertions_passed = False
            else:
                print("  [OK] Assertion: Raw DR error increases over time - PASSED")

        if dr_valid and es_valid:
            dr_rmse_3d = metrics["raw_dr"]["rmse_3d"]
            es_rmse_3d = metrics["es_ekf"]["rmse_3d"]
            if not math.isnan(dr_rmse_3d) and not math.isnan(es_rmse_3d):
                if es_rmse_3d < dr_rmse_3d * 0.5:
                    print(f"  [OK] Assertion: ES-EKF RMSE ({es_rmse_3d:.3f}m) << DR RMSE ({dr_rmse_3d:.3f}m) - PASSED")
                else:
                    print(f"  [WARN] Assertion: ES-EKF RMSE should be significantly lower than DR RMSE - FAILED")
                    print(f"         ES-EKF RMSE = {es_rmse_3d:.3f}m, DR RMSE = {dr_rmse_3d:.3f}m")
                    assertions_passed = False

        if assertions_passed:
            print("  All assertions PASSED.")
        else:
            print("  Some assertions FAILED. Check results for details.")

    print("\n" + "=" * 60)
    print(f"  EKF Benchmark complete. Results in: {output_dir}")
    print("=" * 60)

    # =========================================================================
    # [Optional] Control Benchmark Tests
    # =========================================================================
    if args.run_control_benchmark:
        _run_control_benchmarks(
            output_dir=output_dir,
            control_type=args.control_type,
            dpi=args.dpi,
            verbose=args.verbose,
        )


def _run_control_benchmarks(
    output_dir: Path,
    control_type: str = "both",
    dpi: int = 300,
    verbose: bool = False,
) -> None:
    """运行控制算法基准测试 (PID/MPC)。

    Args:
        output_dir: 主输出目录
        control_type: 控制器类型 ('pid', 'mpc', 'both')
        dpi: 图表 DPI
        verbose: 是否打印详细信息
    """
    import datetime as _datetime
    from pathlib import Path as _Path

    try:
        import control_benchmark_module as ctrl_mod
    except ImportError:
        print("\n[WARN] control_benchmark_module 未找到，跳过控制基准测试")
        return

    control_output_dir = get_output_dir('results/control/benchmark')
    control_output_dir.mkdir(parents=True, exist_ok=True)

    if verbose:
        print(f"\n{'='*60}")
        print("  控制算法基准测试")
        print(f"{'='*60}")
        print(f"\n[控制基准] 输出目录: {control_output_dir}")

    if control_type in ("pid", "both"):
        print(f"\n[控制基准] 运行 PID 测试...")
        try:
            pid_dir = control_output_dir / 'pid'
            pid_dir.mkdir(exist_ok=True)
            pid_results, pid_report, pid_figs = ctrl_mod.run_pid_benchmark(
                output_dir=pid_dir, verbose=verbose
            )
            print(f"  PID 测试完成: {pid_report}")
        except Exception as e:
            print(f"  [WARN] PID 测试失败: {e}")

    if control_type in ("mpc", "both"):
        print(f"\n[控制基准] 运行 MPC 测试...")
        try:
            mpc_dir = control_output_dir / 'mpc'
            mpc_dir.mkdir(exist_ok=True)
            mpc_results, mpc_report, mpc_figs = ctrl_mod.run_mpc_benchmark(
                output_dir=mpc_dir, verbose=verbose
            )
            print(f"  MPC 测试完成: {mpc_report}")
        except Exception as e:
            print(f"  [WARN] MPC 测试失败: {e}")

    # 生成综合摘要报告
    _generate_control_summary_report(control_output_dir, control_type)

    print(f"\n[控制基准] 所有测试完成，结果在: {control_output_dir}")


def _generate_control_summary_report(
    output_dir: Path,
    control_type: str,
) -> None:
    """生成控制测试综合摘要报告。

    Args:
        output_dir: 控制测试输出目录
        control_type: 控制器类型
    """
    import datetime as _datetime

    report = []
    report.append("# 控制算法基准测试综合报告\n")
    report.append(f"**日期**: {_datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    report.append(f"**输出目录**: `{output_dir}`\n")

    report.append("\n---\n")
    report.append("\n## 1. 测试概述\n")
    report.append("本次基准测试评估了 AUV 控制算法的性能，包括:\n")

    if control_type in ("pid", "both"):
        report.append("- **PID 控制器**: 级联 PI-PID 结构 (深度) + PID (航向)")
        report.append("  - 详细报告: [pid/pid_control_report.md](pid/pid_control_report.md)\n")

    if control_type in ("mpc", "both"):
        report.append("- **MPC 控制器**: 模型预测控制 + PVS 内环")
        report.append("  - 详细报告: [mpc/mpc_control_report.md](mpc/mpc_control_report.md)\n")

    report.append("\n## 2. 测试场景\n")
    report.append("| 测试 | 描述 | 时长 |")
    report.append("|------|------|------|")
    report.append("| 1    | 深度阶跃：0 → 5 m | 40 s |")
    report.append("| 2    | 航向阶跃：0 → 30° | 40 s |")
    report.append("| 3    | 电缆跟踪：正弦深度 + 余弦航向 | 60 s |")

    report.append("\n## 3. 输出文件\n")
    report.append("### 3.1 PID 控制器\n")
    if (output_dir / 'pid' / 'figures').exists():
        fig_dir = output_dir / 'pid' / 'figures'
        for f in sorted(fig_dir.glob('*.png')):
            report.append(f"- [{f.name}](pid/figures/{f.name})")
    else:
        report.append("- 无 PID 图表 (测试可能失败)")

    report.append("\n### 3.2 MPC 控制器\n")
    if (output_dir / 'mpc' / 'figures').exists():
        fig_dir = output_dir / 'mpc' / 'figures'
        for f in sorted(fig_dir.glob('*.png')):
            report.append(f"- [{f.name}](mpc/figures/{f.name})")
    else:
        report.append("- 无 MPC 图表 (测试可能失败)")

    report.append("\n## 4. 性能对比\n")
    report.append("请参考各子报告获取详细性能指标 (RMSE, 最大误差, 上升时间等)。\n")

    report.append("\n## 5. 结论\n")
    report.append("- 控制基准测试提供了 PID 和 MPC 控制器在标准测试场景下的性能对比")
    report.append("- 所有图表和报告可用于论文和性能分析")

    summary_path = output_dir / 'control_benchmark_summary.md'
    summary_path.write_text('\n'.join(report) + '\n', encoding='utf-8')
    print(f"  综合摘要报告: {summary_path}")


if __name__ == "__main__":
    main()
