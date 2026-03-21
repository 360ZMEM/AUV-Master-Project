import numpy as np


def compute_metrics(history, eval_cfg):
    pos = np.asarray(history["pos"], dtype=float)
    ref = np.asarray(history["ref"], dtype=float)

    if pos.size == 0 or ref.size == 0:
        sat_count = int(np.sum(history.get("saturated_any", [])))
        sat_total = len(history.get("saturated_any", []))
        sat_ratio = sat_count / max(sat_total, 1)
        return {
            "rms": float("nan"),
            "mean_error": float("nan"),
            "trajectory_length": 0.0,
            "axis_ratio": float("inf"),
            "sat_ratio": sat_ratio,
            "safety_event_count": int(history.get("safety_event_count", 0)),
            "pass_rms": False,
            "pass_axis_ratio": False,
        }

    if pos.ndim == 1:
        pos = pos.reshape(1, -1)
    if ref.ndim == 1:
        ref = ref.reshape(1, -1)

    n = min(len(pos), len(ref))
    pos = pos[:n]
    ref = ref[:n]

    err = np.linalg.norm(ref - pos, axis=1)
    rms = float(np.sqrt(np.mean(err * err)))

    trajectory_length = float(np.sum(np.linalg.norm(np.diff(ref, axis=0), axis=1)))
    mean_error = float(np.mean(err))
    axis_ratio = mean_error / max(trajectory_length, 1e-9)

    sat_count = int(np.sum(history["saturated_any"]))
    sat_ratio = sat_count / max(len(history["saturated_any"]), 1)

    return {
        "rms": rms,
        "mean_error": mean_error,
        "trajectory_length": trajectory_length,
        "axis_ratio": axis_ratio,
        "sat_ratio": sat_ratio,
        "safety_event_count": int(history["safety_event_count"]),
        "pass_rms": rms <= float(eval_cfg["rms_threshold_m"]),
        "pass_axis_ratio": axis_ratio <= float(eval_cfg["axis_ratio_threshold"]),
    }
