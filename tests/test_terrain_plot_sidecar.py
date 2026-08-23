from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from tools.plot_terrain_following_figures import (
    diagnostics_arrays,
    interpolate_pvs_feasible_reference,
    resolve_pvs_trace_path,
)
from tools.analyze_bag import BagData


def _write_trace(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["wall_time_s", "pvs_z_d_m"],
        )
        writer.writeheader()
        writer.writerows(
            [
                {"wall_time_s": 100.0, "pvs_z_d_m": 10.0},
                {"wall_time_s": 102.0, "pvs_z_d_m": 12.0},
            ]
        )


def test_interpolate_pvs_feasible_reference_uses_wall_time(
    tmp_path: Path,
) -> None:
    trace_path = tmp_path / "pvs_control_trace.csv"
    _write_trace(trace_path)

    values = interpolate_pvs_feasible_reference(
        trace_path,
        np.asarray([99.0, 100.0, 101.0, 102.0, 103.0]),
    )

    assert np.isnan(values[0])
    assert np.allclose(values[1:4], [10.0, 11.0, 12.0])
    assert np.isnan(values[4])


def test_resolve_pvs_trace_path_falls_back_to_bag_root(
    tmp_path: Path,
) -> None:
    result_root = tmp_path / "result"
    phase_dir = result_root / "pid_terrain"
    bag_root = tmp_path / "bag"
    trace_path = bag_root / "pvs_control_trace.csv"
    _write_trace(trace_path)
    phase_dir.mkdir(parents=True)
    (phase_dir / "bag_path.txt").write_text(str(bag_root), encoding="utf-8")

    assert resolve_pvs_trace_path(result_root, "pid_terrain") == trace_path


def test_diagnostics_arrays_prefers_ground_truth_depth() -> None:
    data = BagData()
    for index in range(5):
        timestamp_ns = (index + 1) * 1_000_000_000
        data.diagnostics.append(
            timestamp_ns=timestamp_ns,
            lateral_error_m=float("nan"),
            confidence=float("nan"),
            magnetic_magnitude=float("nan"),
            total_voltage_v=float("nan"),
            battery_low=False,
            anomaly_detected=False,
            depth_m=99.0,
            target_depth_m=12.0,
            depth_error_m=0.0,
            speed_mps=float("nan"),
            target_speed_mps=float("nan"),
            seabed_clearance_m=3.0,
            seabed_proximity_warning=False,
            seabed_penetration_warning=False,
            high_priority=False,
            mode="test",
            current_behavior="test",
            has_lateral_error=False,
            has_magnetic_magnitude=False,
        )
        data.truth.append(timestamp_ns, 0.0, 0.0, -(10.0 + index))
        data.altitude.append(timestamp_ns, 3.0)
        data.controller_depth_command.append(timestamp_ns, 12.0)
    data.truth_topic_used = "/auv/sensors/ground_truth"

    arrays = diagnostics_arrays(data, target_clearance_m=3.0)

    assert arrays["depth_source"] == "/auv/sensors/ground_truth"
    assert np.allclose(arrays["depth"], [10.0, 11.0, 12.0, 13.0, 14.0])
    assert np.allclose(arrays["seabed_depth"], [13.0, 14.0, 15.0, 16.0, 17.0])
