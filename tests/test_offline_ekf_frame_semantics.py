#!/usr/bin/env python3
"""Local smoke test for offline benchmark frame semantics.

This test intentionally avoids MCAP/ROS dependencies. It reproduces the
HoloOcean smoke case where ROS ground truth PoseStamped stores z-up
(`z=-12`) while depth is positive-down (`depth=12`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.offline_ekf_benchmark import (  # noqa: E402
    DeadReckoningEngine,
    StandardEKFEngine,
    _ned_to_ros_up,
    _position_to_ned,
    compute_rmse_z,
)


def main() -> None:
    truth_ros_up = np.array([0.0, 0.0, -12.0], dtype=float)
    truth_ned = _position_to_ned(truth_ros_up, "ros-up")
    estimated_depth_ned = np.array([[0.0, 0.0, 12.0]], dtype=float)

    old_error = compute_rmse_z(estimated_depth_ned, truth_ros_up.reshape(1, 3))
    fixed_error = compute_rmse_z(estimated_depth_ned, truth_ned.reshape(1, 3))

    assert abs(old_error - 24.0) < 1e-9, old_error
    assert fixed_error < 1e-9, fixed_error

    dr = DeadReckoningEngine(truth_ned)
    dr.update_depth(12.0, 0)
    dr.record_state(0)
    _, dr_pos = dr.get_position_history()
    assert compute_rmse_z(dr_pos, truth_ned.reshape(1, 3)) < 1e-9

    std = StandardEKFEngine({
        "init_pos": truth_ned.tolist(),
        "init_vel": [0.0, 0.0, 0.0],
    })
    std.update_depth(12.0, 0)
    std_pos = std.get_position().reshape(1, 3)
    assert compute_rmse_z(std_pos, truth_ned.reshape(1, 3)) < 1e-6

    es_internal_init = _ned_to_ros_up(truth_ned)
    assert np.allclose(es_internal_init, np.array([0.0, 0.0, -12.0]))

    print(f"old_unfixed_z_error_m={old_error:.3f}")
    print(f"fixed_z_error_m={fixed_error:.3f}")
    print("offline_ekf_frame_semantics: PASS")


if __name__ == "__main__":
    main()
