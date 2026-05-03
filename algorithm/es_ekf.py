import numpy as np


def _skew(v):
    """构造三维向量的反对称矩阵，用于叉乘线性化。"""
    x, y, z = v
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]], dtype=float)


def quat_normalize(q):
    """将四元数归一化为单位长度。"""
    q = np.asarray(q, dtype=float)
    n = np.linalg.norm(q)
    if n < 1e-12:
        return np.array([1.0, 0.0, 0.0, 0.0], dtype=float)
    return q / n


def quat_multiply(q1, q2):
    """计算两个四元数的乘积。"""
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2
    return np.array([
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    ], dtype=float)


def quat_to_rotmat(q):
    """把四元数转换为方向余弦矩阵。"""
    w, x, y, z = quat_normalize(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ], dtype=float)


def quat_from_rotmat(r):
    """从旋转矩阵恢复四元数。"""
    tr = np.trace(r)
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2
        w = 0.25 * s
        x = (r[2, 1] - r[1, 2]) / s
        y = (r[0, 2] - r[2, 0]) / s
        z = (r[1, 0] - r[0, 1]) / s
    elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
        s = np.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
        w = (r[2, 1] - r[1, 2]) / s
        x = 0.25 * s
        y = (r[0, 1] + r[1, 0]) / s
        z = (r[0, 2] + r[2, 0]) / s
    elif r[1, 1] > r[2, 2]:
        s = np.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
        w = (r[0, 2] - r[2, 0]) / s
        x = (r[0, 1] + r[1, 0]) / s
        y = 0.25 * s
        z = (r[1, 2] + r[2, 1]) / s
    else:
        s = np.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
        w = (r[1, 0] - r[0, 1]) / s
        x = (r[0, 2] + r[2, 0]) / s
        y = (r[1, 2] + r[2, 1]) / s
        z = 0.25 * s
    return quat_normalize(np.array([w, x, y, z], dtype=float))


def small_angle_quat(dtheta):
    """将小角度误差向量转换为四元数增量。"""
    angle = np.linalg.norm(dtheta)
    if angle < 1e-12:
        return np.array([1.0, 0.5 * dtheta[0], 0.5 * dtheta[1], 0.5 * dtheta[2]], dtype=float)
    axis = dtheta / angle
    half = 0.5 * angle
    return quat_normalize(np.array([np.cos(half), *(np.sin(half) * axis)], dtype=float))


def quat_to_euler(q):
    """将四元数转换为欧拉角，顺序为 roll、pitch、yaw。"""
    w, x, y, z = quat_normalize(q)
    sinr_cosp = 2 * (w * x + y * z)
    cosr_cosp = 1 - 2 * (x * x + y * y)
    roll = np.arctan2(sinr_cosp, cosr_cosp)

    sinp = 2 * (w * y - z * x)
    pitch = np.sign(sinp) * np.pi / 2 if abs(sinp) >= 1 else np.arcsin(sinp)

    siny_cosp = 2 * (w * z + x * y)
    cosy_cosp = 1 - 2 * (y * y + z * z)
    yaw = np.arctan2(siny_cosp, cosy_cosp)
    return np.array([roll, pitch, yaw], dtype=float)


class ES_EKF:
    """扩展状态卡尔曼滤波器，用于 AUV 位姿与速度估计。

    状态向量包含位置、速度、姿态四元数、加速度零偏和陀螺零偏，
    支持 IMU 预测以及 DVL、深度、GPS 观测修正。

    增强特性：
    - 支持自动初始化：首次收到 DVL 或深度观测时自动对齐位置
    - 可配置初始化策略：固定位置 / 观测对齐 / 混合模式
    - 支持零偏预校准：使用静止期间IMU样本估计初始零偏，减少预测漂移
    """

    def __init__(self, cfg):
        """从滤波配置初始化状态、协方差和噪声参数。"""
        self.g = float(cfg.get("gravity", 9.81))
        self.g_n = np.array([0.0, 0.0, -self.g], dtype=float)
        self.imu_acc_is_linear = bool(cfg.get("imu_acc_is_linear", True))

        self.sigma_acc = float(cfg.get("sigma_acc", 0.08))
        self.sigma_gyro = float(cfg.get("sigma_gyro", 0.01))
        self.sigma_ba = float(cfg.get("sigma_ba", 0.001))
        self.sigma_bg = float(cfg.get("sigma_bg", 0.0005))

        self.sigma_dvl = float(cfg.get("sigma_dvl", 0.03))
        self.sigma_depth = float(cfg.get("sigma_depth", 0.05))
        self.sigma_gps_xy = float(cfg.get("sigma_gps_xy", 0.5))

        self.auto_init = bool(cfg.get("auto_init", True))
        self.use_first_dvl_for_init = bool(cfg.get("use_first_dvl_for_init", True))
        self.use_first_depth_for_init = bool(cfg.get("use_first_depth_for_init", True))

        init_P = cfg.get("init_P_diag", [1.0] * 15)
        if len(init_P) == 15:
            init_P = list(init_P)
        self._init_P_diag = np.array(init_P, dtype=float)
        self.P = np.diag(self._init_P_diag)

        self._init_pos = np.array(cfg.get("init_pos", [0.0, 0.0, 0.0]), dtype=float)
        self._init_vel = np.array(cfg.get("init_vel", [0.0, 0.0, 0.0]), dtype=float)
        self._init_quat = quat_normalize(np.array(cfg.get("init_quat_wxyz", [1.0, 0.0, 0.0, 0.0]), dtype=float))

        self.p = self._init_pos.copy()
        self.v = self._init_vel.copy()
        self.q = self._init_quat.copy()
        self.b_a = np.array(cfg.get("init_ba", [0.0, 0.0, 0.0]), dtype=float)
        self.b_g = np.array(cfg.get("init_bg", [0.0, 0.0, 0.0]), dtype=float)

        self._initialized = False
        self._init_info = None

        # 零偏预校准机制：使用静止期间的IMU样本估计初始零偏
        self.enable_bias_calibration = bool(cfg.get("enable_bias_calibration", True))
        self.bias_calibration_samples = int(cfg.get("bias_calibration_samples", 50))  # 用于校准的样本数
        self._bias_calibration_buffer_acc = []  # 加速度校准缓冲区
        self._bias_calibration_buffer_gyro = []  # 陀螺仪校准缓冲区
        self._bias_calibration_done = False

    def add_bias_calibration_sample(self, acc_body, gyro_body):
        """添加IMU样本用于零偏预校准。

        在滤波器首次predict之前调用，收集静止期间的IMU样本来估计零偏。
        当收集到足够样本后自动完成校准。

        Args:
            acc_body (array-like): 机体系加速度测量
            gyro_body (array-like): 机体系角速度测量
        """
        if self._bias_calibration_done or not self.enable_bias_calibration:
            return

        acc = np.asarray(acc_body, dtype=float).reshape(3)
        gyro = np.asarray(gyro_body, dtype=float).reshape(3)

        self._bias_calibration_buffer_acc.append(acc)
        self._bias_calibration_buffer_gyro.append(gyro)

        # 当收集到足够样本时，计算零偏估计
        if len(self._bias_calibration_buffer_acc) >= self.bias_calibration_samples:
            # 加速度零偏：静止时加速度应等于重力向量（机体系）
            # 假设初始姿态为水平，重力沿Z轴向下，因此b_a = mean(acc) - [0, 0, -g]
            mean_acc = np.mean(self._bias_calibration_buffer_acc, axis=0)
            self.b_a = mean_acc - self.g_n  # 估计加速度零偏

            # 陀螺零偏：静止时角速度应为零
            self.b_g = np.mean(self._bias_calibration_buffer_gyro, axis=0)

            self._bias_calibration_done = True
            self._bias_calibration_info = {
                "samples_used": len(self._bias_calibration_buffer_acc),
                "mean_acc_before_calibration": mean_acc.tolist(),
                "estimated_ba": self.b_a.tolist(),
                "estimated_bg": self.b_g.tolist(),
            }

            # 清空缓冲区
            self._bias_calibration_buffer_acc.clear()
            self._bias_calibration_buffer_gyro.clear()

    def is_bias_calibration_done(self):
        """检查零偏预校准是否已完成。"""
        return self._bias_calibration_done

    def get_bias_calibration_info(self):
        """获取零偏预校准信息。"""
        return getattr(self, '_bias_calibration_info', None)

    def is_initialized(self):
        """检查滤波器是否已完成初始化。"""
        return self._initialized

    def initialize_from_observation(self, pos=None, vel=None, quat=None):
        """从观测值初始化滤波器状态。

        当首次收到可靠的传感器观测（DVL 或深度）时调用，
        将滤波器状态对齐到观测值，消除初始位置偏移。

        Args:
            pos (array-like, optional): 观测到的位置 [x, y, z]
            vel (array-like, optional): 观测到的速度 [vx, vy, vz]
            quat (array-like, optional): 观测到的姿态四元数 [w, x, y, z]
        """
        if pos is not None:
            self.p = np.array(pos, dtype=float).copy()
        if vel is not None:
            self.v = np.array(vel, dtype=float).copy()
        if quat is not None:
            self.q = quat_normalize(np.array(quat, dtype=float))

        self._initialized = True

    def _auto_initialize(self, pos=None, vel=None, source="observation"):
        """内部自动初始化辅助方法。

        当 auto_init=True 且滤波器未初始化时，从首次观测中自动对齐状态。
        该方法记录初始化信息以供后续查询。

        Args:
            pos (array-like, optional): 观测到的位置
            vel (array-like, optional): 观测到的速度
            source (str): 初始化来源标识 ("dvl" 或 "depth")
        """
        if self._initialized:
            return

        init_pos = self.p.copy()
        init_vel = self.v.copy()

        if pos is not None:
            self.p = np.array(pos, dtype=float).copy()
        if vel is not None:
            self.v = np.array(vel, dtype=float).copy()

        self.P = np.diag(self._init_P_diag)

        self._initialized = True
        self._init_info = {
            "source": source,
            "initial_pos_config": self._init_pos.tolist(),
            "aligned_pos": self.p.tolist(),
            "initial_vel_config": self._init_vel.tolist(),
            "aligned_vel": self.v.tolist(),
            "position_offset": (self.p - self._init_pos).tolist(),
        }

    def _try_auto_init_from_dvl(self, dvl_vel_body):
        """尝试从首次DVL观测自动初始化。

        如果 auto_init=True 且 use_first_dvl_for_init=True 且未初始化，
        则从DVL速度推断初始状态。

        关键改进：
          1. 对齐速度：将 self.v 对齐到 DVL 测量的世界系速度
          2. 消除 init_vel=[0,0,0] 导致的初始运动积分误差跳变

        Args:
            dvl_vel_body (array-like): 机体系DVL速度（若调用 correct_dvl_world 则传入世界系）
        """
        if self._initialized or not self.auto_init or not self.use_first_dvl_for_init:
            return

        vel = np.asarray(dvl_vel_body, dtype=float).reshape(3)
        self._auto_initialize(pos=self._init_pos.copy(), vel=vel, source="dvl")

    def _try_auto_init_from_depth(self, depth_m):
        """尝试从首次深度观测自动初始化。

        如果 auto_init=True 且 use_first_depth_for_init=True 且未初始化，
        则从深度观测中对齐Z轴位置。

        Args:
            depth_m (float): 深度观测值（米）
        """
        if self._initialized or not self.auto_init or not self.use_first_depth_for_init:
            return

        new_pos = self.p.copy()
        new_pos[2] = -depth_m
        self._auto_initialize(pos=new_pos, source="depth")

    def get_state(self):
        """返回当前滤波状态的拷贝，避免外部直接修改内部状态。"""
        return {"p": self.p.copy(), "v": self.v.copy(), "q": self.q.copy(), "b_a": self.b_a.copy(), "b_g": self.b_g.copy()}

    def predict(self, imu_acc_body, imu_gyro_body, dt):
        """使用 IMU 预测状态并推进协方差。

        Args:
            imu_acc_body (array-like): 机体系加速度测量。
            imu_gyro_body (array-like): 机体系角速度测量。
            dt (float): 预测周期，单位秒。
        """
        dt = float(dt)
        acc_m = np.asarray(imu_acc_body, dtype=float)
        gyr_m = np.asarray(imu_gyro_body, dtype=float)

        omega = gyr_m - self.b_g
        dq = small_angle_quat(omega * dt)
        self.q = quat_normalize(quat_multiply(self.q, dq))

        r_nb = quat_to_rotmat(self.q)
        a_n = r_nb @ (acc_m - self.b_a)
        if not self.imu_acc_is_linear:
            a_n = a_n + self.g_n

        self.p = self.p + self.v * dt + 0.5 * a_n * dt * dt
        self.v = self.v + a_n * dt

        f = np.zeros((15, 15), dtype=float)
        f[0:3, 3:6] = np.eye(3)
        f[3:6, 6:9] = -r_nb @ _skew(acc_m - self.b_a)
        f[3:6, 9:12] = -r_nb
        f[6:9, 6:9] = -_skew(omega)
        f[6:9, 12:15] = -np.eye(3)

        phi = np.eye(15) + f * dt
        qd = np.zeros((15, 15), dtype=float)
        qd[3:6, 3:6] = (self.sigma_acc ** 2) * np.eye(3) * dt * dt
        qd[6:9, 6:9] = (self.sigma_gyro ** 2) * np.eye(3) * dt * dt
        qd[9:12, 9:12] = (self.sigma_ba ** 2) * np.eye(3) * dt
        qd[12:15, 12:15] = (self.sigma_bg ** 2) * np.eye(3) * dt
        self.P = phi @ self.P @ phi.T + qd

    def _inject(self, dx):
        """将误差状态注入到名义状态中。"""
        self.p += dx[0:3]
        self.v += dx[3:6]
        self.q = quat_normalize(quat_multiply(small_angle_quat(dx[6:9]), self.q))
        self.b_a += dx[9:12]
        self.b_g += dx[12:15]

    def _correct(self, y, h, h_mat, r):
        """执行 EKF 观测更新。

        Args:
            y (np.ndarray): 观测值。
            h (np.ndarray): 预测观测值。
            h_mat (np.ndarray): 观测雅可比。
            r (np.ndarray): 观测噪声协方差。
        """
        s = h_mat @ self.P @ h_mat.T + r
        k = self.P @ h_mat.T @ np.linalg.pinv(s)
        dx = k @ (y - h)
        self._inject(dx)
        i = np.eye(15)
        ikh = i - k @ h_mat
        self.P = ikh @ self.P @ ikh.T + k @ r @ k.T

    def correct_dvl(self, dvl_vel_body):
        """使用机体系 DVL 速度修正滤波状态。"""
        self._try_auto_init_from_dvl(dvl_vel_body)
        z = np.asarray(dvl_vel_body, dtype=float).reshape(3)
        r_nb = quat_to_rotmat(self.q)
        h = r_nb.T @ self.v
        h_mat = np.zeros((3, 15), dtype=float)
        h_mat[:, 3:6] = r_nb.T
        h_mat[:, 6:9] = -r_nb.T @ _skew(self.v)
        self._correct(z, h, h_mat, (self.sigma_dvl ** 2) * np.eye(3))

    def correct_dvl_world(self, dvl_vel_world):
        """使用世界系 DVL 速度修正滤波状态。"""
        self._try_auto_init_from_dvl(dvl_vel_world)
        z = np.asarray(dvl_vel_world, dtype=float).reshape(3)
        h = self.v.copy()
        h_mat = np.zeros((3, 15), dtype=float)
        h_mat[:, 3:6] = np.eye(3)
        self._correct(z, h, h_mat, (self.sigma_dvl ** 2) * np.eye(3))

    def correct_depth(self, depth_m):
        """使用深度观测修正位置的 Z 轴分量。"""
        self._try_auto_init_from_depth(depth_m)
        z = float(depth_m)
        h = -self.p[2]
        h_mat = np.zeros((1, 15), dtype=float)
        h_mat[0, 2] = -1.0
        self._correct(np.array([z], dtype=float), np.array([h], dtype=float), h_mat, np.array([[self.sigma_depth ** 2]], dtype=float))

    def correct_gps(self, gps_xy):
        """使用 GPS 平面位置观测修正滤波状态。"""
        z = np.asarray(gps_xy, dtype=float).reshape(2)
        h = self.p[:2]
        h_mat = np.zeros((2, 15), dtype=float)
        h_mat[0, 0] = 1.0
        h_mat[1, 1] = 1.0
        self._correct(z, h, h_mat, (self.sigma_gps_xy ** 2) * np.eye(2))
