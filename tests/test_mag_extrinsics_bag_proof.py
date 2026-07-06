from __future__ import annotations

from pathlib import Path

from tools.verify_mag_extrinsics_bag_proof import _summarize


def _status_row(**overrides):
    row = {
        "schema_version": "mag_extrinsics_status.v1",
        "uses_estimated_extrinsics": True,
        "estimated_extrinsics_source": "results/mag_extrinsics/estimated_extrinsics.yaml",
        "truth_extrinsics_exported": False,
        "simulator_position_present": True,
        "sensor_position_ned_hash_sha256_16": "1234567890abcdef",
    }
    row.update(overrides)
    return row


def test_mag_extrinsics_bag_proof_passes_minimal_deployable_contract() -> None:
    summary = _summarize(
        chunks=[Path("bag_0.mcap")],
        magnetic_topic="/auv/sensors/magnetic",
        status_topic="/auv/sensors/magnetic_extrinsics_status",
        magnetic_messages=[object() for _ in range(50)],
        status_payloads=[_status_row(), _status_row()],
    )

    assert summary["validation_status"] == "pass"
    assert summary["checks"]["status_is_lower_rate_than_magnetic"] is True
    assert summary["checks"]["raw_sim_sensor_position_not_republished"] is True
    assert summary["simulator_position_hash_count"] == 2


def test_mag_extrinsics_bag_proof_limits_raw_position_or_truth_export() -> None:
    summary = _summarize(
        chunks=[Path("bag_0.mcap")],
        magnetic_topic="/auv/sensors/magnetic",
        status_topic="/auv/sensors/magnetic_extrinsics_status",
        magnetic_messages=[object() for _ in range(10)],
        status_payloads=[
            _status_row(
                truth_extrinsics_exported=True,
                sensor_position_ned=[1.0, 2.0, 3.0],
            )
        ],
    )

    assert summary["validation_status"] == "limited"
    assert "truth_extrinsics_not_exported" in summary["failed_checks"]
    assert "raw_sim_sensor_position_not_republished" in summary["failed_checks"]
