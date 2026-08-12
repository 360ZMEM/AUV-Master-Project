from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from tools.analyze_tmr_recording import analyze, sliding_lockin


def test_sliding_lockin_preserves_global_phase_and_amplitude() -> None:
    sample_rate = 2000.0
    frequency = 45.0
    amplitude_ut = 0.125
    phase_rad = 0.37
    time_s = np.arange(int(2.0 * sample_rate)) / sample_rate
    signal = amplitude_ut * np.cos(
        2.0 * np.pi * frequency * time_s - phase_rad
    )
    values = np.column_stack([signal, signal, signal])

    result = sliding_lockin(
        values,
        sample_rate_hz=sample_rate,
        start_timestamp=1000.0,
        frequency_hz=frequency,
        window_sec=1.0,
        hop_sec=0.05,
        window_name="rect",
        detrend_mode="constant",
    )

    amplitudes = np.asarray(result["amplitude_ut"])
    phases = np.asarray(result["phase_rad"])
    assert np.allclose(amplitudes, amplitude_ut, atol=1e-10)
    assert np.allclose(phases, phase_rad, atol=1e-10)
    assert abs(float(result["enbw_hz"]) - 1.0) < 1e-12


def test_headless_analysis_writes_machine_readable_bundle(
    tmp_path: Path,
) -> None:
    sample_rate = 2000
    frequency = 45.0
    sample_count = 4000
    time_s = np.arange(sample_count) / sample_rate
    magnetic_ut = np.column_stack(
        [
            0.1 * np.cos(2.0 * np.pi * frequency * time_s),
            0.2 * np.cos(2.0 * np.pi * frequency * time_s + 0.2),
            0.3 * np.cos(2.0 * np.pi * frequency * time_s - 0.4),
        ]
    )
    sensitivity = np.asarray([20.02, 19.98, 19.96])
    voltage = magnetic_ut * (sensitivity / 1000.0)
    input_path = tmp_path / "synthetic.npz"
    np.savez(
        input_path,
        voltage=voltage,
        sample_rate_hz=np.asarray(sample_rate),
        channels=np.asarray([0, 1, 2]),
        start_timestamp=np.asarray(1234.5),
        sensitivity_mv_per_ut=sensitivity,
        experiment_metadata_json=np.str_(
            json.dumps(
                {
                    "excitation_hz": 45.0,
                    "reference_hz": 45.0,
                    "frequency_provenance": "synthetic test metadata",
                }
            )
        ),
    )
    output_dir = tmp_path / "analysis"
    args = argparse.Namespace(
        input=input_path,
        output_dir=output_dir,
        data_source_id="synthetic_45hz",
        frequency=45.0,
        excitation_hz=45.0,
        frequency_source="recorded_metadata",
        reference_type="software",
        window="hann",
        window_sec=1.0,
        hop_sec=0.05,
        detrend="linear",
        bandpass_low=None,
        bandpass_high=None,
        threshold_nt=None,
        dpi=50,
    )

    summary = analyze(args)

    assert summary["window_count"] == 21
    assert summary["frequency_contract"]["excitation_hz"] == 45.0
    assert summary["frequency_contract"]["reference_hz"] == 45.0
    assert abs(summary["axis_summary"]["x"]["amplitude"]["p50_nt"] - 100.0) < 0.1
    for name in (
        "analysis_summary.json",
        "lockin_timeseries.csv",
        "spectrum.csv",
        "report.md",
        "lockin_amplitude.png",
        "lockin_amplitude.pdf",
        "spectrum_near_reference.png",
        "spectrum_near_reference.pdf",
        "lockin_iq.png",
        "lockin_iq.pdf",
    ):
        assert (output_dir / name).is_file()
    parsed = json.loads(
        (output_dir / "analysis_summary.json").read_text(encoding="utf-8")
    )
    assert parsed["processing"]["window_name"] == "hann"
    assert (
        parsed["frequency_contract"]["frequency_provenance"]
        == "synthetic test metadata"
    )
