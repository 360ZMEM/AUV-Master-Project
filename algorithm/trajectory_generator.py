import numpy as np


class TrajectoryGenerator:
    def __init__(self, traj_cfg):
        self.kind = traj_cfg.get("kind", "cable_like_3d")
        self.duration = float(traj_cfg.get("duration", 80.0))
        self.dt = float(traj_cfg.get("dt", 0.1))

        self.start = np.array(traj_cfg.get("start", [0.0, 0.0, -12.0]), dtype=float)
        self.surge_speed = float(traj_cfg.get("surge_speed", 1.1))
        self.length = float(traj_cfg.get("length", 88.0))

        self.lateral_amplitude = float(traj_cfg.get("lateral_amplitude", 1.2))
        self.lateral_wavenumber = float(traj_cfg.get("lateral_wavenumber", 0.08))
        self.depth_base = float(traj_cfg.get("depth_base", self.start[2]))
        self.depth_amplitude = float(traj_cfg.get("depth_amplitude", 0.35))
        self.depth_wavenumber = float(traj_cfg.get("depth_wavenumber", 0.05))

        self.circle_radius = float(traj_cfg.get("circle_radius", 10.0))
        self.circle_omega = float(traj_cfg.get("circle_omega", 0.08))
        self.min_turn_radius = float(traj_cfg.get("min_turn_radius", 6.0))

    def sample(self, t):
        x, y, z = self._xyz(t)
        yaw = self._tangent_yaw(t)
        return {"x": x, "y": y, "z": z, "target_yaw": yaw}

    def generate(self):
        times = np.arange(0.0, self.duration + self.dt, self.dt)
        points = np.zeros((len(times), 3), dtype=float)
        yaws = np.zeros(len(times), dtype=float)

        for index, t in enumerate(times):
            x, y, z = self._xyz(t)
            points[index] = [x, y, z]
            yaws[index] = self._tangent_yaw(t)

        curvature, radius = self.curvature_profile(times)
        return {
            "t": times,
            "points": points,
            "target_yaw": yaws,
            "curvature": curvature,
            "turn_radius": radius,
        }

    def curvature_profile(self, times):
        curvature = np.zeros(len(times), dtype=float)
        radius = np.full(len(times), np.inf, dtype=float)
        for index, t in enumerate(times):
            x_dot, y_dot = self._xy_dot(t)
            x_ddot, y_ddot = self._xy_ddot(t)
            speed_sq = x_dot * x_dot + y_dot * y_dot
            denom = np.power(speed_sq, 1.5)
            numer = abs(x_dot * y_ddot - y_dot * x_ddot)
            if denom > 1e-9:
                curvature[index] = numer / denom
                if curvature[index] > 1e-9:
                    radius[index] = 1.0 / curvature[index]
        return curvature, radius

    def validate_turn_radius(self, radius):
        min_radius_actual = float(np.nanmin(radius[np.isfinite(radius)])) if np.any(np.isfinite(radius)) else np.inf
        passed = min_radius_actual >= self.min_turn_radius
        return {
            "min_radius_actual": min_radius_actual,
            "min_radius_required": self.min_turn_radius,
            "passed": bool(passed),
        }

    def _xyz(self, t):
        if self.kind == "cable_like_3d":
            x = self.start[0] + self.surge_speed * t
            x = min(x, self.start[0] + self.length)
            dx = x - self.start[0]
            y = self.start[1] + self.lateral_amplitude * np.sin(self.lateral_wavenumber * dx)
            z = self.depth_base + self.depth_amplitude * np.sin(self.depth_wavenumber * dx)
            return float(x), float(y), float(z)

        if self.kind == "circle_3d":
            angle = self.circle_omega * t
            x = self.start[0] + self.circle_radius * np.cos(angle)
            y = self.start[1] + self.circle_radius * np.sin(angle)
            z = self.depth_base + self.depth_amplitude * np.sin(self.depth_wavenumber * t)
            return float(x), float(y), float(z)

        raise ValueError(f"Unsupported trajectory kind: {self.kind}")

    def _xy_dot(self, t):
        if self.kind == "cable_like_3d":
            x = self.start[0] + self.surge_speed * t
            saturated = x >= self.start[0] + self.length
            if saturated:
                return 0.0, 0.0
            x_dot = self.surge_speed
            dx = x - self.start[0]
            y_dot = self.lateral_amplitude * self.lateral_wavenumber * np.cos(self.lateral_wavenumber * dx) * x_dot
            return float(x_dot), float(y_dot)

        angle = self.circle_omega * t
        x_dot = -self.circle_radius * self.circle_omega * np.sin(angle)
        y_dot = self.circle_radius * self.circle_omega * np.cos(angle)
        return float(x_dot), float(y_dot)

    def _xy_ddot(self, t):
        if self.kind == "cable_like_3d":
            x = self.start[0] + self.surge_speed * t
            saturated = x >= self.start[0] + self.length
            if saturated:
                return 0.0, 0.0
            x_dot = self.surge_speed
            dx = x - self.start[0]
            x_ddot = 0.0
            y_ddot = -self.lateral_amplitude * (self.lateral_wavenumber ** 2) * np.sin(self.lateral_wavenumber * dx) * (x_dot ** 2)
            return float(x_ddot), float(y_ddot)

        angle = self.circle_omega * t
        x_ddot = -self.circle_radius * (self.circle_omega ** 2) * np.cos(angle)
        y_ddot = -self.circle_radius * (self.circle_omega ** 2) * np.sin(angle)
        return float(x_ddot), float(y_ddot)

    def _tangent_yaw(self, t):
        x_dot, y_dot = self._xy_dot(t)
        if abs(x_dot) < 1e-9 and abs(y_dot) < 1e-9:
            return 0.0
        return float(np.arctan2(y_dot, x_dot))
