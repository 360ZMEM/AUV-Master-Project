import numpy as np

MU0 = 4.0e-7 * np.pi


class CablePath:
    def __init__(self, control_points):
        points = np.asarray(control_points, dtype=float)
        if points.ndim != 2 or points.shape[1] != 3 or points.shape[0] < 2:
            raise ValueError("CABLE_PATH must be N x 3 with N >= 2")
        self.points = points

    def segments(self):
        for i in range(len(self.points) - 1):
            yield self.points[i], self.points[i + 1]

    def closest_point_and_distance(self, p):
        p = np.asarray(p, dtype=float).reshape(3)
        min_dist = np.inf
        best_point = self.points[0]
        for a, b in self.segments():
            ab = b - a
            denom = float(np.dot(ab, ab))
            if denom <= 1e-12:
                q = a
            else:
                t = np.clip(float(np.dot(p - a, ab) / denom), 0.0, 1.0)
                q = a + t * ab
            d = float(np.linalg.norm(p - q))
            if d < min_dist:
                min_dist = d
                best_point = q
        return best_point, min_dist


def compute_biot_savart_hvdc(auv_pos_ned, cable: CablePath, current_amp=500.0, epsilon=1e-3):
    p = np.asarray(auv_pos_ned, dtype=float).reshape(3)
    b_total = np.zeros(3, dtype=float)

    coeff = MU0 * float(current_amp) / (4.0 * np.pi)
    for a, c in cable.segments():
        dl = c - a
        mid = 0.5 * (a + c)
        r = p - mid
        r_norm = float(np.linalg.norm(r))
        if r_norm < epsilon:
            continue
        b_total += coeff * np.cross(dl, r) / (r_norm ** 3)
    return b_total


def inject_gaussian_noise(vec, sigma):
    vec = np.asarray(vec, dtype=float)
    sigma_arr = np.asarray(sigma, dtype=float)
    if sigma_arr.ndim == 0:
        sigma_arr = np.full_like(vec, float(sigma_arr))
    return vec + np.random.normal(0.0, sigma_arr, size=vec.shape)


def inject_sonar_cable_peak(n_bins, max_range_m, cable_distance_m, base_noise_sigma=0.01, peak_gain=1.0, peak_width_bins=3.0):
    n_bins = int(n_bins)
    if n_bins <= 0:
        raise ValueError("n_bins must be > 0")

    sonar = np.random.normal(0.0, float(base_noise_sigma), size=n_bins)
    cable_distance_m = max(0.0, float(cable_distance_m))
    max_range_m = max(1e-6, float(max_range_m))

    idx_center = int(np.clip(round((cable_distance_m / max_range_m) * (n_bins - 1)), 0, n_bins - 1))
    idx = np.arange(n_bins, dtype=float)
    peak = float(peak_gain) * np.exp(-0.5 * ((idx - idx_center) / max(float(peak_width_bins), 1e-6)) ** 2)
    sonar += peak
    return sonar
