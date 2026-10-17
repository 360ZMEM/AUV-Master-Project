"""Check that task progress cannot mask unsafe Hold commands."""

import csv
import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "tools/audit_v2_inspection_task_liveness.py"
SPEC = importlib.util.spec_from_file_location("inspection_task_liveness", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write_run(path, *, hold_rpm=0, finish=False, final_x=4):
    path.mkdir()
    columns = ["time_s", "x_m", "y_m", "mode", "stage", "reason",
               "target_speed_mps", "thrust_percent", "rpm",
               "endpoint_complete", "depth_valid"]
    samples = [
        [0, 0, 0, "search", "unavailable", "search", .3, 10, 180, False, False],
        [1, 1, 0, "confirm", "unavailable", "scan", .3, 10, 180, False, False],
        [2, 2, 0, "track", "inspect_along_cable", "track", .3, 10, 180, False, False],
        [3, 3, 0, "hold", "", "fault", 0, 0, hold_rpm, False, False],
        [4, final_x, 0, "track" if finish else "hold",
         "inspect_along_cable" if finish else "", "resume" if finish else "fault",
         0 if finish else 0, 0, 0, finish, False],
    ]
    with (path / "trace.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(samples)
    (path / "trace_summary.json").write_text(json.dumps({
        "source": "trace.csv", "ticks": len(samples), "completed": finish,
        "route_observed_lateral_max_m": 0.5,
        "recovery_status_observed": not finish,
        "native_pvs": True, "ros_dds": True, "protocol_encoded": True,
    }))


def test_recoverable_hold_can_complete(tmp_path):
    path = tmp_path / "recover"
    _write_run(path, finish=True)
    result = MODULE.audit_run(path, max_sample_gap_s=1.0,
                              min_inspection_x_progress_m=1.0)
    assert result["software_route_complete"] is True
    assert result["hold_command_violation_count"] == 0
    assert result["field_release_authorized"] is False


def test_nonzero_hold_rpm_rejects_withdrawal_and_completion(tmp_path):
    path = tmp_path / "bad"
    _write_run(path, hold_rpm=50, finish=True)
    result = MODULE.audit_run(path, max_sample_gap_s=1.0,
                              min_inspection_x_progress_m=1.0)
    assert result["software_route_complete"] is False
    assert result["hold_command_violation_count"] == 1
    assert result["software_withdrawal_trace_passed"] is False


def test_endpoint_flag_without_route_progress_is_rejected(tmp_path):
    path = tmp_path / "short"
    _write_run(path, finish=True, final_x=2.1)
    result = MODULE.audit_run(path, max_sample_gap_s=1.0,
                              min_inspection_x_progress_m=1.0)
    assert result["endpoint_count"] == 1
    assert result["inspection_x_progress_m"] < 1.0
    assert result["software_route_complete"] is False
