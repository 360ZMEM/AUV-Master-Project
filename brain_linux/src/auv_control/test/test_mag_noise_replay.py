from __future__ import annotations

import numpy as np

from auv_decision_ros.mag_noise_replay import (
    MeasuredMagNoiseReplay,
    load_magnetic_noise_dataset,
    parse_path_sequence,
)


def test_parse_path_sequence_accepts_ros_string_and_array_forms() -> None:
    assert parse_path_sequence(["a.npz", "b.npz"]) == ["a.npz", "b.npz"]
    assert parse_path_sequence("a.npz,b.npz") == ["a.npz", "b.npz"]
    assert parse_path_sequence('["a.npz", "b.npz"]') == ["a.npz", "b.npz"]


def test_measured_noise_dataset_converts_voltage_to_tesla(tmp_path) -> None:
    record = tmp_path / "noise.npz"
    np.savez(
        record,
        voltage=np.array([[0.001, 0.002, 0.003], [0.004, 0.005, 0.006]], dtype=float),
        sample_rate_hz=np.array(10),
        channels=np.array([0, 1, 2]),
        sensitivity_mv_per_ut=np.array([1.0, 1.0, 1.0], dtype=float),
    )

    dataset = load_magnetic_noise_dataset(
        npz_paths=[record],
        project_root=tmp_path,
        detrend_mode="none",
    )

    assert dataset.sample_rate_hz == 10.0
    assert dataset.sample_count == 2
    assert np.allclose(
        dataset.samples_t,
        np.array([[1.0e-6, 2.0e-6, 3.0e-6], [4.0e-6, 5.0e-6, 6.0e-6]]),
    )


def test_measured_noise_replay_loops_with_source_metadata(tmp_path) -> None:
    record = tmp_path / "noise.npz"
    np.savez(
        record,
        voltage=np.array([[0.001, 0.002, 0.003], [0.004, 0.005, 0.006]], dtype=float),
        sample_rate_hz=np.array(10),
        channels=np.array([0, 1, 2]),
        sensitivity_mv_per_ut=np.array([1.0, 1.0, 1.0], dtype=float),
    )
    dataset = load_magnetic_noise_dataset(
        npz_paths=[record],
        project_root=tmp_path,
        detrend_mode="none",
    )
    source = MeasuredMagNoiseReplay(dataset, seed=None)

    first = source.sample(0.0)
    second = source.sample(0.1)
    looped = source.sample(0.2)

    assert np.allclose(first.vector_t, dataset.samples_t[0])
    assert np.allclose(second.vector_t, dataset.samples_t[1])
    assert np.allclose(looped.vector_t, dataset.samples_t[0])
    assert first.metadata["sample_index"] == 0
    assert first.metadata["source_local_sample_index"] == 0
    assert first.metadata["current_noise_source_npz"] == str(record)
    assert first.metadata["looped_replay"] is True
