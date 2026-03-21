import numpy as np


def _skew(v):
    x, y, z = v
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]], dtype=float)


def quat_normalize(q):
    q = np.asarray(q, dtype=float)
    n = np.linalg.norm(q)
    if n < 1e-12:
        return np.array([1.0, 0.0, 0.0, 0.0], dtype=float)
    return q / n


def quat_multiply(q1, q2):
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2
    return np.array([
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    ], dtype=float)


def quat_to_rotmat(q):
    w, x, y, z = quat_normalize(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ], dtype=float)


def quat_from_rotmat(r):
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
    angle = np.linalg.norm(dtheta)
    if angle < 1e-12:
        return np.array([1.0, 0.5 * dtheta[0], 0.5 * dtheta[1], 0.5 * dtheta[2]], dtype=float)
    axis = dtheta / angle
    half = 0.5 * angle
    return quat_normalize(np.array([np.cos(half), *(np.sin(half) * axis)], dtype=float))


def quat_to_euler(q):
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
    def __init__(self, cfg):
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

        self.p = np.array(cfg.get("init_pos", [0.0, 0.0, 0.0]), dtype=float)
        self.v = np.array(cfg.get("init_vel", [0.0, 0.0, 0.0]), dtype=float)
        self.q = quat_normalize(np.array(cfg.get("init_quat_wxyz", [1.0, 0.0, 0.0, 0.0]), dtype=float))
        self.b_a = np.array(cfg.get("init_ba", [0.0, 0.0, 0.0]), dtype=float)
        self.b_g = np.array(cfg.get("init_bg", [0.0, 0.0, 0.0]), dtype=float)
        self.P = np.diag(np.array(cfg.get("init_P_diag", [1.0] * 15), dtype=float))

    def get_state(self):
        return {"p": self.p.copy(), "v": self.v.copy(), "q": self.q.copy(), "b_a": self.b_a.copy(), "b_g": self.b_g.copy()}

    def predict(self, imu_acc_body, imu_gyro_body, dt):
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
        self.p += dx[0:3]
        self.v += dx[3:6]
        self.q = quat_normalize(quat_multiply(small_angle_quat(dx[6:9]), self.q))
        self.b_a += dx[9:12]
        self.b_g += dx[12:15]

    def _correct(self, y, h, h_mat, r):
        s = h_mat @ self.P @ h_mat.T + r
        k = self.P @ h_mat.T @ np.linalg.pinv(s)
        dx = k @ (y - h)
        self._inject(dx)
        i = np.eye(15)
        ikh = i - k @ h_mat
        self.P = ikh @ self.P @ ikh.T + k @ r @ k.T

    def correct_dvl(self, dvl_vel_body):
        z = np.asarray(dvl_vel_body, dtype=float).reshape(3)
        r_nb = quat_to_rotmat(self.q)
        h = r_nb.T @ self.v
        h_mat = np.zeros((3, 15), dtype=float)
        h_mat[:, 3:6] = r_nb.T
        h_mat[:, 6:9] = -r_nb.T @ _skew(self.v)
        self._correct(z, h, h_mat, (self.sigma_dvl ** 2) * np.eye(3))

    def correct_dvl_world(self, dvl_vel_world):
        z = np.asarray(dvl_vel_world, dtype=float).reshape(3)
        h = self.v.copy()
        h_mat = np.zeros((3, 15), dtype=float)
        h_mat[:, 3:6] = np.eye(3)
        self._correct(z, h, h_mat, (self.sigma_dvl ** 2) * np.eye(3))

    def correct_depth(self, depth_m):
        z = float(depth_m)
        h = -self.p[2]
        h_mat = np.zeros((1, 15), dtype=float)
        h_mat[0, 2] = -1.0
        self._correct(np.array([z], dtype=float), np.array([h], dtype=float), h_mat, np.array([[self.sigma_depth ** 2]], dtype=float))

    def correct_gps(self, gps_xy):
        z = np.asarray(gps_xy, dtype=float).reshape(2)
        h = self.p[:2]
        h_mat = np.zeros((2, 15), dtype=float)
        h_mat[0, 0] = 1.0
        h_mat[1, 1] = 1.0
        self._correct(z, h, h_mat, (self.sigma_gps_xy ** 2) * np.eye(2))
