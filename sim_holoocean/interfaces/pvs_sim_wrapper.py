"""
PythonVehicleSimulator（PVS）后端模拟器 - 轻量级 REMUS 100 AUV 动力学。

该模块提供 PythonVehicleSimulator 框架的适配层，用于在 GPU 不可用或快速原型开发时
使用简化的 6 自由度（6-DOF）刚体动力学替代 HoloOcean。

仿真器选择：
  - HoloOcean（物理引擎）：基于 UE4，高保真但需要 GPU
  - PVS（纯数学模型）：MATLAB/Simulink 级别的多体动力学，轻量级高效

REMUS 100 特性：
  - 典型运行深度：0-300m
  - 推进系统：单螺旋桨、水平舵（方向舵）、垂直舵（升降舵）
  - 自动驾驶系统：深度-航向自动驾驶仪（可选）
  - 坐标系：NED（北东地）

主要接口（与 HoloOcean 兼容）：
  open()：创建并初始化 REMUS 100 仿真模型
  step(command5)：执行一个仿真时间步
  reset_and_tick()：复位状态并执行首步
  close()：清理资源
  set_reference()：设置自动驾驶仪参考值（可选方法）

关键参数：
  - control_mode：控制方式（stepInput 或 depthHeadingAutopilot）
  - dt：仿真时间步长（秒）
  - initial_depth_m、initial_heading_deg、initial_speed_mps：初始状态
  - command_thrust_rpm_scale、max_command_rpm：推力映射参数
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PVS_ROOT = PROJECT_ROOT.parent / "PythonVehicleSimulator-master" / "src"
INTERFACES_ROOT = PROJECT_ROOT / "sim_holoocean" / "interfaces"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PVS_ROOT) not in sys.path:
    sys.path.insert(0, str(PVS_ROOT))
if str(INTERFACES_ROOT) not in sys.path:
    sys.path.insert(0, str(INTERFACES_ROOT))

from python_vehicle_simulator.lib.gnc import Rzyx, attitudeEuler
from python_vehicle_simulator.vehicles.remus100 import remus100
from common.sensor_extrinsics import base_position_to_sensor_world, base_velocity_to_sensor, load_extrinsics_map
from ocean_current_model import OceanCurrentModel



def _build_pose_matrix_ue(position_ned: np.ndarray, rpy_ned: np.ndarray) -> np.ndarray:
    """
    从 NED 位姿构造 UE4 风格的 4×4 变换矩阵。

    这是 NED → UE4 坐标系的桥梁。PVS 使用 NED，但我们需要 UE4 格式
    供上层（如 HoloOcean 桥接）使用。

    坐标系变换：
      - UE4 欧拉角 → NED 欧拉角：
          roll_ue = roll_ned
          pitch_ue = -pitch_ned
          yaw_ue = -yaw_ned
      - UE4 位置 → NED 位置：
          pos_ue = [x_ned, y_ned, -z_ned]

    参数：
        position_ned (ndarray)，形状 (3,)：NED 坐标下的位置 [x, y, z]
        rpy_ned (ndarray)，形状 (3,)：NED 欧拉角 [roll, pitch, yaw]（弧度）

    返回值：
        ndarray，形状 (4, 4)：齐次变换矩阵
          [R(3×3)  T(3×1)]
          [0(1×3)    1   ]
          其中 R 是 UE4 风格的旋转矩阵，T 是 UE4 风格的位置向量
    """
    pose = np.eye(4, dtype=float)
    roll_ue = float(rpy_ned[0])
    pitch_ue = float(-rpy_ned[1])
    yaw_ue = float(-rpy_ned[2])
    pose[:3, :3] = Rzyx(roll_ue, pitch_ue, yaw_ue)
    position_ned = np.asarray(position_ned, dtype=float).reshape(3)
    pose[:3, 3] = np.array([position_ned[0], position_ned[1], -position_ned[2]], dtype=float)
    return pose


def _body_ned_vector_to_ue(vec_ned_body: np.ndarray) -> np.ndarray:
    vec = np.asarray(vec_ned_body, dtype=float).reshape(3)
    return np.array([vec[0], vec[1], -vec[2]], dtype=float)





class PVSSimWrapper:
    """────────────────────────────────────────────────────────────────
    PythonVehicleSimulator REMUS 100 仿真模块包装器
    ────────────────────────────────────────────────────────────────

    职责：
      1. 创建和管理 REMUS 100 仿真实例（6-DOF 刚体动力学）
      2. 执行仿真时间步进（应用控制命令，更新位姿）
      3. 统一状态格式为 HoloOcean 兼容的字典
      4. 支持两种控制模式：
         - stepInput：直接接收用户命令
         - depthHeadingAutopilot：自动驾驶仪控制（参考深度、航向、推进）
      5. 维护速度、加速度、欧拉角等仿真状态

    状态向量定义：
      eta：位置和姿态 [x, y, z, roll, pitch, yaw]（NED）
      nu：速度和角速度 [u, v, w, p, q, r]
         - u, v, w：身体坐标系线速度
         - p, q, r：身体坐标系角速度
      u_actual：实际执行器状态（推力、舵角）

    流程（每时间步）：
      1. 根据 control_mode 选择控制律：
         - stepInput：使用外部命令5元组
         - 自动驾驶仪：计算错误反馈控制
      2. dynamics()：积分运动方程，更新 nu 和 u_actual
      3. attitudeEuler()：积分欧拉微分方程，更新 eta
      4. _build_state()：转换为上层格式
    """

    def __init__(self, *, config, scenario_cfg, agent_name, show_viewport=False, verbose=False):
        """
        初始化 PVS 包装器（不启动引擎）。

        参数：
            config (dict)：全局配置，包含 simulation 和 pvs 配置组
            scenario_cfg (dict)：仿真场景定义（兼容性参数，PVS 不使用）
            agent_name (str)：代理名称（返回状态时使用此键）
            show_viewport (bool)：是否显示可视化（PVS 默认无 UI，参数保留用于 API 兼容）
            verbose (bool)：冗长日志输出

        配置键（来自 config['pvs']）：
          - control_mode：str，"stepInput" 或 "depthHeadingAutopilot"
          - initial_depth_m：初始深度（米），默认 12.0
          - initial_heading_deg：初始航向（度），默认 0.0
          - initial_speed_mps：初始前进速度（m/s），默认 0.5
          - initial_rpm：初始螺旋桨转速（RPM），默认 1200
          - reference_rpm、reference_speed_rpm_slope、reference_speed_rpm_offset：自动驾驶仪参数
          - current_speed_mps、current_direction_deg：海流参数
        """
        self.config = config or {}
        self.scenario_cfg = scenario_cfg
        self.agent_name = agent_name
        self.show_viewport = bool(show_viewport)
        self.verbose = bool(verbose)

        # ────────────────────────────────────────
        # 仿真配置
        # ────────────────────────────────────────
        self.sim_cfg = dict(self.config.get("simulation", {}))
        self.pvs_cfg = dict(self.config.get("pvs", {}))
        self.dt = float(self.sim_cfg.get("dt", 1.0 / max(float(self.sim_cfg.get("ticks_per_sec", 30.0)), 1e-6)))
        self.control_mode = str(self.pvs_cfg.get("control_mode", self.sim_cfg.get("control_mode", "stepInput")))

        # ────────────────────────────────────────
        # REMUS 100 初始状态参数
        # ────────────────────────────────────────
        self.initial_depth_m = float(self.pvs_cfg.get("initial_depth_m", 12.0))
        self.initial_heading_deg = float(self.pvs_cfg.get("initial_heading_deg", 0.0))
        self.initial_speed_mps = float(self.pvs_cfg.get("initial_speed_mps", 0.5))
        self.initial_rpm = float(self.pvs_cfg.get("initial_rpm", 1200.0))

        # ────────────────────────────────────────
        # 自动驾驶仪参考值和增益参数
        # ────────────────────────────────────────
        self.reference_rpm = float(self.pvs_cfg.get("reference_rpm", self.initial_rpm))
        # 速度 (m/s) → RPM 映射：rpm = slope * speed + offset
        self.reference_speed_rpm_slope = float(self.pvs_cfg.get("reference_speed_rpm_slope", 581.0))
        self.reference_speed_rpm_offset = float(self.pvs_cfg.get("reference_speed_rpm_offset", -115.0))
        self.reference_rpm_min = float(self.pvs_cfg.get("reference_rpm_min", 300.0))
        self.reference_speed_mps = float(self.initial_speed_mps)

        # ────────────────────────────────────────
        # 命令到执行器映射
        # ────────────────────────────────────────
        # 推力百分比 → RPM：rpm = thrust_percent * scale
        self.command_thrust_rpm_scale = float(self.pvs_cfg.get("command_thrust_rpm_scale", 15.0))
        self.max_command_rpm = float(self.pvs_cfg.get("max_command_rpm", 1525.0))
        self.autonomy_motion_model = str(self.pvs_cfg.get("autonomy_motion_model", "native")).strip().lower()
        self.kinematic_max_yaw_rate_rad_s = math.radians(
            float(self.pvs_cfg.get("kinematic_max_yaw_rate_deg_s", 12.0))
        )
        self.kinematic_depth_time_constant_s = max(
            0.05,
            float(self.pvs_cfg.get("kinematic_depth_time_constant_s", 4.0)),
        )
        self.kinematic_max_speed_mps = float(
            self.pvs_cfg.get("kinematic_max_speed_mps", float("inf"))
        )

        # ────────────────────────────────────────
        # 海流和噪声参数
        # ────────────────────────────────────────
        self.current_speed_mps = float(self.pvs_cfg.get("current_speed_mps", 0.5))
        self.current_direction_deg = float(self.pvs_cfg.get("current_direction_deg", 0.0))
        self.autopilot_params = {
            "Kp_z": self.pvs_cfg.get("Kp_z"),
            "Kp_theta": self.pvs_cfg.get("Kp_theta"),
            "Kd_theta": self.pvs_cfg.get("Kd_theta"),
            "Ki_theta": self.pvs_cfg.get("Ki_theta"),
            "lam": self.pvs_cfg.get("lam"),
            "phi_b": self.pvs_cfg.get("phi_b"),
            "K_d": self.pvs_cfg.get("K_d"),
            "K_sigma": self.pvs_cfg.get("K_sigma"),
            "wn_d_z": self.pvs_cfg.get("wn_d_z"),
            "wn_d": self.pvs_cfg.get("wn_d"),
        }
        self.r_max = np.deg2rad(float(self.pvs_cfg.get("r_max_deg", 5.0)))
        self.deltaMax = np.deg2rad(float(self.pvs_cfg.get("deltaMax_deg", 15.0)))
        self.depth_anti_windup_enabled = bool(
            self.pvs_cfg.get("depth_anti_windup_enabled", False)
        )
        self.z_integral_limit = max(
            0.0,
            float(self.pvs_cfg.get("z_integral_limit", 10.0)),
        )
        self.theta_integral_limit = max(
            0.0,
            float(self.pvs_cfg.get("theta_integral_limit", 2.0)),
        )
        self.depth_anti_windup_active = False
        self.last_stern_command_raw_deg = 0.0

        # ────────────────────────────────────────
        # 三维洋流干扰模型
        # ────────────────────────────────────────
        env_cfg = self.config.get("environment", {}).get("current", {})
        self.ocean_current = OceanCurrentModel(env_cfg, dt=self.dt) if env_cfg.get("enabled", False) else None
        self._sim_time = 0.0
        self.sensor_extrinsics_truth = load_extrinsics_map(self.config.get("sensor_extrinsics_truth", {}) or {})
        self.imu_truth_extrinsic = self.sensor_extrinsics_truth["imu"]
        self.dvl_truth_extrinsic = self.sensor_extrinsics_truth["dvl"]
        self.depth_truth_extrinsic = self.sensor_extrinsics_truth["depth"]
        self.mag_truth_extrinsic = self.sensor_extrinsics_truth["mag"]
        self.dvl_measurement_frame = str(
            self.config.get("perception", {}).get("dvl_measurement_frame", "world")
        ).strip().lower()

        # ────────────────────────────────────────
        # 运行时状态（初始化为空，待 open()）
        # ────────────────────────────────────────
        self.vehicle = None  # REMUS 100 模拟对象
        # 位置和姿态：[x, y, z, roll, pitch, yaw]（NED）
        self.eta = np.array(
            [0.0, 0.0, self.initial_depth_m, 0.0, 0.0, np.deg2rad(self.initial_heading_deg)],
            dtype=float,
        )
        # 速度和角速度：[u, v, w, p, q, r]（身体坐标系）
        self.nu = np.array([self.initial_speed_mps, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=float)
        # 实际执行器状态
        self.u_actual = np.zeros(3, dtype=float)
        # 前一时步的速度（用于计算加速度）
        self.prev_nu = self.nu.copy()
        # 仿真步数计数器
        self.step_index = 0
        # 自动驾驶仪参考值（动态更新）
        self.reference_depth_m = float(self.initial_depth_m)
        self.reference_heading_deg = float(self.initial_heading_deg)
        self.reference_rpm = float(self.reference_rpm)
        self.reference_speed_mps = float(self.initial_speed_mps)


    def set_reference(
        self,
        *,
        depth_m: float,
        heading_rad: float,
        speed_mps: float | None = None,
        propeller_rpm: float | None = None,
    ) -> None:
        """
        设置自动驾驶仪的参考值（仅在自动驾驶仪模式下有效）。

        参数：
            depth_m (float)：目标深度（米）
            heading_rad (float)：目标航向（弧度，0-2π）
            speed_mps (float or None)：目标前进速度（m/s）；
                                       若为 None，参考 RPM 保持不变
            propeller_rpm (float or None)：协议已编码的推进器转速；
                                           设置时直接写入 PVS，不重复执行速度映射

        实现细节：
          1. 存储目标值到 self.reference_*
          2. 若 vehicle 已初始化，推送参考值到其自动驾驶仪逻辑
          3. 速度 → RPM 映射：rpm = slope * speed + offset，限制在 [min, max]

        用途：
          - 动态改变目标（如从深度 10m 改为 15m）
          - 支持轨迹跟踪（由上层控制律周期性调用）
        """
        self.reference_depth_m = float(depth_m)
        self.reference_heading_deg = float(math.degrees(float(heading_rad)))
        if speed_mps is not None and propeller_rpm is not None:
            raise ValueError("speed_mps and propeller_rpm are mutually exclusive")
        if propeller_rpm is not None:
            self.reference_rpm = float(
                np.clip(max(0.0, float(propeller_rpm)), 0.0, self.max_command_rpm)
            )
            if self.reference_rpm <= 1.0e-9:
                self.reference_speed_mps = 0.0
            else:
                self.reference_speed_mps = max(
                    0.0,
                    (self.reference_rpm - self.reference_speed_rpm_offset)
                    / self.reference_speed_rpm_slope,
                )
        elif speed_mps is not None:
            # @note protocol_udp currently encodes autonomy speed through
            # main-motor RPM. The optional kinematic cap keeps simulation
            # proxy setpoint motion within the mission envelope.
            self.reference_speed_mps = float(
                np.clip(
                    max(0.0, float(speed_mps)),
                    0.0,
                    self.kinematic_max_speed_mps,
                )
            )
            if self.reference_speed_mps <= 1.0e-9:
                self.reference_rpm = 0.0
            else:
                mapped_rpm = self.reference_speed_rpm_slope * self.reference_speed_mps + self.reference_speed_rpm_offset
                self.reference_rpm = float(
                    np.clip(
                        mapped_rpm,
                        self.reference_rpm_min,
                        self.max_command_rpm,
                    )
                )
        if self.vehicle is not None:
            self.vehicle.ref_z = self.reference_depth_m
            self.vehicle.ref_psi = self.reference_heading_deg
            self.vehicle.ref_n = float(self.reference_rpm)

    def _step_kinematic_autonomy(self) -> dict:
        """Advance a lightweight setpoint-driven kinematic model.

        This path is intentionally simple: it mirrors the Direction A decoupled
        closure so protocol_udp/PVS autonomy can produce observable x/y/yaw/depth
        motion even when the installed PVS package stays in step-input mode.
        """
        target_heading_rad = math.radians(float(self.reference_heading_deg))
        heading_error_rad = (target_heading_rad - float(self.eta[5]) + math.pi) % (2.0 * math.pi) - math.pi
        yaw_rate_rad_s = float(
            np.clip(
                heading_error_rad / max(self.dt, 1.0e-6),
                -self.kinematic_max_yaw_rate_rad_s,
                self.kinematic_max_yaw_rate_rad_s,
            )
        )
        self.prev_nu = self.nu.copy()
        self.eta[5] = float((float(self.eta[5]) + yaw_rate_rad_s * self.dt + math.pi) % (2.0 * math.pi) - math.pi)

        speed_mps = float(
            np.clip(
                max(0.0, float(self.reference_speed_mps)),
                0.0,
                self.kinematic_max_speed_mps,
            )
        )
        depth_error_m = float(self.reference_depth_m) - float(self.eta[2])
        depth_rate_mps = depth_error_m / self.kinematic_depth_time_constant_s

        self.nu[:] = 0.0
        self.nu[0] = speed_mps
        self.nu[2] = depth_rate_mps
        self.nu[5] = yaw_rate_rad_s

        self.eta = attitudeEuler(self.eta, self.nu, self.dt)
        self.eta[3] = 0.0
        self.eta[4] = 0.0
        self.step_index += 1
        self.u_actual[:] = 0.0
        self.u_actual[2] = float(self.reference_rpm)
        return self._build_state()

    def open(self):
        """
        创建并初始化 REMUS 100 模型对象。

        流程：
          1. 根据 control_mode 选择控制系统类型
          2. 调用 remus100() 工厂函数创建实例
          3. 初始化动力学和控制器内部状态
          4. 打印初始化日志（若 verbose=True）

        返回值：
            self（支持链式调用）

        参考初值（可选）：
          - ref_z：目标深度（米）
          - ref_psi：目标航向（度）
          - ref_n：目标 RPM
          - V_current、beta_current：海流速度和方向
        """
        mode = self.control_mode.strip().lower()
        if mode in {"depthheadingautopilot", "depth_heading_autopilot", "autopilot", "reference"}:
            control_system = "depthHeadingAutopilot"
        else:
            control_system = "stepInput"

        self.vehicle = remus100(
            controlSystem=control_system,
            r_z=self.reference_depth_m,
            r_psi=self.reference_heading_deg,
            r_rpm=self.reference_rpm,
            V_current=self.current_speed_mps,
            beta_current=self.current_direction_deg,
        )
        self.vehicle.nu = self.nu.copy()
        self.vehicle.u_actual = self.u_actual.copy()
        self._apply_autopilot_params()
        # 控制器内部状态初始化（深度和航向 PI 环自积状态）
        self.vehicle.z_d = self.reference_depth_m
        self.vehicle.z_int = 0.0
        self.vehicle.theta_int = 0.0
        self.vehicle.e_psi_int = 0.0
        self.vehicle.psi_d = np.deg2rad(self.reference_heading_deg)
        self.vehicle.r_d = 0.0
        self.vehicle.a_d = 0.0

        if self.verbose:
            print(
                f"[pvs] backend open: mode={control_system} depth={self.initial_depth_m:.2f}m "
                f"heading={self.initial_heading_deg:.1f}deg rpm={self.reference_rpm:.1f}"
            )
        return self

    def _apply_autopilot_params(self) -> None:
        """把 params.yaml/sim_params.pvs.yaml 中的 PVS v2 内环参数同步到车辆实例。"""
        if self.vehicle is None:
            return
        for name, value in self.autopilot_params.items():
            if value is not None:
                setattr(self.vehicle, name, float(value))
        self.vehicle.r_max = float(self.r_max)
        self.vehicle.deltaMax_r = float(self.deltaMax)
        self.vehicle.deltaMax_s = float(self.deltaMax)

    def __enter__(self):
        """支持 with 语句进入。"""
        return self.open()

    def __exit__(self, exc_type, exc, tb):
        """支持 with 语句退出（自动清理资源）。"""
        self.close()
        return False

    def reset_and_tick(self):
        """
        复位仿真状态并执行首个时间步。

        步骤：
          1. 重置仿真计数器和速度历史
          2. 重置洋流模型状态
          3. 调用 _build_state() 生成初始状态

        返回值：
            dict：仿真状态（兼容 HoloOcean 格式）
        """
        self.step_index = 0
        self.prev_nu = self.nu.copy()
        self._sim_time = 0.0
        if self.ocean_current is not None:
            self.ocean_current.reset()
        return self._build_state()

    def _build_rotation_matrix_ned(self) -> np.ndarray:
        """
        从 eta[3:6] (roll, pitch, yaw in NED) 构建体坐标系→NED 的旋转矩阵。

        R_b2n = Rz(yaw) · Ry(pitch) · Rx(roll)
        """
        roll, pitch, yaw = self.eta[3], self.eta[4], self.eta[5]
        cr, sr = np.cos(roll), np.sin(roll)
        cp, sp = np.cos(pitch), np.sin(pitch)
        cy, sy = np.cos(yaw), np.sin(yaw)
        R = np.array([
            [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
            [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
            [   -sp,             cp * sr,             cp * cr],
        ], dtype=np.float64)
        return R

    def _command_to_actuators(self, command5) -> np.ndarray:
        """
        将上层命令5元组映射到 REMUS 100 的执行器空间。

        输入格式：
          [right_fin_deg, top_fin_deg, left_fin_deg, bottom_fin_deg, thrust_percent]
          - 舵角：度数，范围 [-45, 45]（或其他）
          - 推力：百分比，范围 [-100, 100]

        执行器映射：
          - 方向舵（偏航控制）：rudder = 0.5 * (left - right)
          - 升降舵（俯仰控制）：stern = 0.5 * (bottom - top)
          - 推进（螺旋桨转速）：rpm = thrust_percent * scale

        输出：
          [rudder_rad, stern_rad, rpm]，单位：
            - 舵角：弧度
            - RPM：转每分钟

        参数：
            command5：长度为 5 的数组或列表

        返回值：
            ndarray (3,)：[rudder_rad, stern_rad, rpm]
        """
        cmd = np.asarray(command5, dtype=float).reshape(-1)
        if cmd.size != 5:
            raise ValueError("command must be length 5: [right,top,left,bottom,thrust]")

        rudder_deg = 0.5 * (float(cmd[2]) - float(cmd[0]))
        stern_deg = 0.5 * (float(cmd[3]) - float(cmd[1]))
        thrust_rpm = float(np.clip(float(cmd[4]) * self.command_thrust_rpm_scale, 0.0, self.max_command_rpm))
        return np.array([np.deg2rad(rudder_deg), np.deg2rad(stern_deg), thrust_rpm], dtype=float)

    def _depth_heading_autopilot_control(self) -> np.ndarray:
        """Evaluate the PVS autopilot with adapter-local integral protection."""
        previous_z_int = float(self.vehicle.z_int)
        previous_theta_int = float(self.vehicle.theta_int)
        u_control = self.vehicle.depthHeadingAutopilot(
            self.eta,
            self.nu,
            self.dt,
        )
        self.last_stern_command_raw_deg = float(np.degrees(u_control[1]))
        stern_saturated = abs(float(u_control[1])) >= self.deltaMax
        self.depth_anti_windup_active = bool(
            self.depth_anti_windup_enabled and stern_saturated
        )
        if self.depth_anti_windup_active:
            self.vehicle.z_int = previous_z_int
            self.vehicle.theta_int = previous_theta_int
        if self.depth_anti_windup_enabled:
            self.vehicle.z_int = float(
                np.clip(
                    self.vehicle.z_int,
                    -self.z_integral_limit,
                    self.z_integral_limit,
                )
            )
            self.vehicle.theta_int = float(
                np.clip(
                    self.vehicle.theta_int,
                    -self.theta_integral_limit,
                    self.theta_integral_limit,
                )
            )
        return u_control

    def _build_state(self):
        """
        从仿真状态构造兼容 HoloOcean 的状态字典。

        转换步骤：
          1. 提取 eta[0:3] → position_ned（位置）
          2. 提取 eta[3:6] → rpy_ned（欧拉角）
          3. 计算加速度 = (nu - prev_nu) / dt
          4. 坐标系转换：NED → UE4（身体轴）
          5. 打包为标准格式

        返回值：
            dict：
              {
                  agent_name: {
                      "PoseSensor": 4×4 变换矩阵 (UE4 坐标系),
                      "DVLSensor": [vx, vy, vz] 身体速度 (UE4),
                      "IMUSensor": [ax, ay, az, gx, gy, gz] 加速度和角速度 (UE4),
                      "DepthSensor": [z_ned] 深度 (米，正向下),
                  }
              }
        """
        position_ned = self.eta[:3].copy()
        rpy_ned = self.eta[3:6].copy()
        pose = _build_pose_matrix_ue(position_ned, rpy_ned)

        # 计算加速度
        accel_ned = (self.nu[:3] - self.prev_nu[:3]) / max(self.dt, 1e-6)
        gyro_ned = self.nu[3:6].copy()
        accel_sensor = self.imu_truth_extrinsic.rotation_b_to_s @ accel_ned
        gyro_sensor = self.imu_truth_extrinsic.rotation_b_to_s @ gyro_ned
        # 坐标系转换：NED body/sensor → UE4 body/sensor
        accel_ue = _body_ned_vector_to_ue(accel_sensor)
        gyro_ue = _body_ned_vector_to_ue(gyro_sensor)
        
        # DVL速度转换：从body frame到world NED frame
        # nu[0:3]是body系速度[u, v, w]，需要使用旋转矩阵转换到world系
        # 注意：Rzyx(roll, pitch, yaw)返回的是Rzyx，但根据Fossen标准：
        #   Rzyx 计算的是 R_ned_to_body（从NED到Body的旋转）
        #   我们需要的是 R_body_to_ned = Rzyx.T（转置）
        roll, pitch, yaw = rpy_ned
        R_ned_to_body = Rzyx(roll, pitch, yaw)
        R_body_to_ned = R_ned_to_body.T
        vel_body = np.array([self.nu[0], self.nu[1], self.nu[2]], dtype=float)
        vel_world_ned = R_body_to_ned @ vel_body
        if self.dvl_measurement_frame == "sensor":
            dvl_sensor = base_velocity_to_sensor(vel_body, gyro_ned, self.dvl_truth_extrinsic)
            dvl_output = _body_ned_vector_to_ue(dvl_sensor)
        else:
            dvl_output = vel_world_ned
        depth_sensor_ned = position_ned + self._build_rotation_matrix_ned() @ self.depth_truth_extrinsic.translation_b_m
        depth_m = float(depth_sensor_ned[2])
        mag_sensor_ned = base_position_to_sensor_world(
            position_ned,
            self._build_rotation_matrix_ned(),
            self.mag_truth_extrinsic,
        )
        # 注意：NED的Z轴向下为正，vel_world_ned[2]应该为正表示下沉
        
        return {
            self.agent_name: {
                "PoseSensor": pose,
                "DVLSensor": dvl_output,
                "DVLFrame": self.dvl_measurement_frame,
                "IMUSensor": np.concatenate([accel_ue, gyro_ue]),
                "DepthSensor": np.array([float(depth_m)], dtype=float),
                "MagSensorPositionNED": np.asarray(mag_sensor_ned, dtype=float),
                "MagSensorFrame": "mag_link",
            }
        }

    def step(self, command5):
        """
        执行一个仿真时间步。

        核心流程：
          1. 根据 control_mode 选择控制方式：
             - stepInput：使用外部命令，转换到执行器空间
             - depthHeadingAutopilot：调用内置自动驾驶仪，忽略外部命令
          2. 洋流干扰注入：计算对水速度 (water-relative velocity)
          3. 调用 vehicle.dynamics()：积分运动方程，更新 nu 和 u_actual
          4. 调用 attitudeEuler()：积分位姿微分方程，更新 eta
          5. 更新计数器并返回新状态

        洋流注入逻辑：
          - ν_rel = ν_body - R_n2b @ v_current_ned  (对水速度)
          - dynamics() 使用 ν_rel 计算阻尼项
          - attitudeEuler() 使用原始 ν 积分位姿 (对地运动)

        参数：
            command5 (array-like)：控制命令
              [right_fin_deg, top_fin_deg, left_fin_deg, bottom_fin_deg, thrust_percent]

        返回值：
            dict：仿真新状态

        异常：
            RuntimeError：vehicle 未初始化（未调用 open()）
        """
        if self.vehicle is None:
            raise RuntimeError("PVS wrapper is not open")

        mode = self.control_mode.strip().lower()
        if (
            self.autonomy_motion_model in {"kinematic_setpoint", "kinematic", "lightweight"}
            and mode in {"depthheadingautopilot", "depth_heading_autopilot", "autopilot", "reference"}
        ):
            return self._step_kinematic_autonomy()

        if mode in {"depthheadingautopilot", "depth_heading_autopilot", "autopilot", "reference"}:
            self._apply_autopilot_params()
            u_control = self._depth_heading_autopilot_control()
            u_control[0] = float(np.clip(u_control[0], -self.deltaMax, self.deltaMax))
            u_control[1] = float(np.clip(u_control[1], -self.deltaMax, self.deltaMax))
        else:
            self.depth_anti_windup_active = False
            self.last_stern_command_raw_deg = 0.0
            u_control = self._command_to_actuators(command5)

        # ────────────────────────────────────────
        # 洋流干扰注入
        # ────────────────────────────────────────
        if self.ocean_current is not None:
            self._sim_time = self.step_index * self.dt
            rpy_ned = self.eta[3:6].copy()

            # 获取洋流速度 (NED 世界系)
            v_current_ned = self.ocean_current.get_current_world(self._sim_time)

            # 构建 NED→体坐标系旋转矩阵
            R_n2b = self._build_rotation_matrix_ned().T  # R_b2n^T = R_n2b

            # 洋流速度转换到体坐标系
            v_current_body = R_n2b @ v_current_ned

            # 对水速度 = 体坐标系速度 - 洋流 (体坐标系)
            nu_rel = self.nu.copy()
            nu_rel[:3] = self.nu[:3] - v_current_body

            # 临时替换 vehicle.nu 以对水速度计算阻尼
            saved_nu = self.vehicle.nu.copy()
            self.vehicle.nu = nu_rel
        else:
            saved_nu = None

        self.prev_nu = self.nu.copy()
        self.nu, self.u_actual = self.vehicle.dynamics(self.eta, self.nu, self.u_actual, u_control, self.dt)
        self.u_actual[0] = float(np.clip(self.u_actual[0], -self.deltaMax, self.deltaMax))
        self.u_actual[1] = float(np.clip(self.u_actual[1], -self.deltaMax, self.deltaMax))

        # 恢复 vehicle.nu (attitudeEuler 使用原始速度积分位姿)
        if saved_nu is not None:
            self.vehicle.nu = saved_nu

        self.eta = attitudeEuler(self.eta, self.nu, self.dt)
        self.step_index += 1
        return self._build_state()

    def close(self):
        """
        清理仿真资源。

        流程：
          - 销毁 vehicle 对象
          - 释放 PVS 内部分配的内存
        """
        self.vehicle = None
