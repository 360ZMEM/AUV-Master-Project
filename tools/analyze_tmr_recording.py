#!/usr/bin/env python3
"""Headless TMR/SK2301 lock-in analysis with explicit frequency provenance."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np


WINDOWS = ("rect", "hann", "blackmanharris")
AXIS_NAMES = ("x", "y", "z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze a raw TMR/SK2301 NPZ without a GUI."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--data-source-id")
    parser.add_argument("--frequency", type=float, default=45.0)
    parser.add_argument("--excitation-hz", type=float, default=None)
    parser.add_argument(
        "--frequency-source",
        choices=[
            "recorded_metadata",
            "hardware_reference",
            "analysis_config",
            "legacy_inference",
        ],
        default="analysis_config",
    )
    parser.add_argument(
        "--reference-type",
        choices=["software", "external_current", "mains", "unknown"],
        default="software",
    )
    parser.add_argument("--window", choices=WINDOWS, default="hann")
    parser.add_argument("--window-sec", type=float, default=1.0)
    parser.add_argument("--hop-sec", type=float, default=0.05)
    parser.add_argument(
        "--detrend", choices=["none", "constant", "linear"], default="linear"
    )
    parser.add_argument("--bandpass-low", type=float)
    parser.add_argument("--bandpass-high", type=float)
    parser.add_argument("--threshold-nt", type=float)
    parser.add_argument("--dpi", type=int, default=200)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_recording(path: Path) -> dict[str, Any]:
    with np.load(path, allow_pickle=False) as archive:
        required = {
            "voltage",
            "sample_rate_hz",
            "channels",
            "start_timestamp",
        }
        missing = required.difference(archive.files)
        if missing:
            raise ValueError(f"NPZ missing required fields: {sorted(missing)}")
        voltage = np.asarray(archive["voltage"], dtype=np.float64)
        if voltage.ndim != 2 or voltage.shape[0] < 2:
            raise ValueError("voltage must be a non-empty 2-D array")
        channels = [int(value) for value in archive["channels"].tolist()]
        sensitivity = (
            np.asarray(archive["sensitivity_mv_per_ut"], dtype=np.float64)
            if "sensitivity_mv_per_ut" in archive.files
            else np.asarray([20.02, 19.98, 19.96], dtype=np.float64)
        )
        sample_rate_hz = float(np.asarray(archive["sample_rate_hz"]))
        start_timestamp = float(np.asarray(archive["start_timestamp"]))
        calibration_name = (
            str(archive["calibration_name"])
            if "calibration_name" in archive.files
            else None
        )
        experiment_metadata = (
            json.loads(str(np.asarray(archive["experiment_metadata_json"]).item()))
            if "experiment_metadata_json" in archive.files
            else None
        )
    if sensitivity.size < voltage.shape[1] or np.any(sensitivity <= 0):
        raise ValueError("invalid sensitivity_mv_per_ut")
    magnetic_ut = voltage / (sensitivity[: voltage.shape[1]] / 1000.0)
    return {
        "voltage": voltage,
        "magnetic_ut": magnetic_ut,
        "sample_rate_hz": sample_rate_hz,
        "channels": channels,
        "start_timestamp": start_timestamp,
        "sensitivity_mv_per_ut": sensitivity[: voltage.shape[1]],
        "calibration_name": calibration_name,
        "experiment_metadata": experiment_metadata,
    }


def detrend_signal(values: np.ndarray, mode: str) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    if mode == "none":
        return arr.copy()
    if mode == "constant":
        return arr - np.mean(arr, axis=0, keepdims=True)
    if mode != "linear":
        raise ValueError(f"unknown detrend mode: {mode}")
    x = np.arange(arr.shape[0], dtype=np.float64)
    x_centered = x - np.mean(x)
    denominator = float(np.sum(x_centered**2))
    centered = arr - np.mean(arr, axis=0, keepdims=True)
    slopes = (x_centered[:, None] * centered).sum(axis=0) / denominator
    return centered - x_centered[:, None] * slopes[None, :]


def window_values(name: str, size: int) -> np.ndarray:
    if size < 2:
        raise ValueError("window requires at least two samples")
    if name == "rect":
        return np.ones(size, dtype=np.float64)
    if name == "hann":
        return np.hanning(size)
    if name == "blackmanharris":
        n = np.arange(size, dtype=np.float64)
        phase = 2.0 * np.pi * n / (size - 1)
        return (
            0.35875
            - 0.48829 * np.cos(phase)
            + 0.14128 * np.cos(2.0 * phase)
            - 0.01168 * np.cos(3.0 * phase)
        )
    raise ValueError(f"unknown window: {name}")


def fft_bandpass(
    values: np.ndarray,
    sample_rate_hz: float,
    low_hz: float | None,
    high_hz: float | None,
) -> np.ndarray:
    if low_hz is None and high_hz is None:
        return np.asarray(values, dtype=np.float64).copy()
    nyquist = sample_rate_hz / 2.0
    low = 0.0 if low_hz is None else float(low_hz)
    high = nyquist if high_hz is None else float(high_hz)
    if not 0.0 <= low < high <= nyquist:
        raise ValueError(
            f"bandpass must satisfy 0 <= low < high <= {nyquist:g}"
        )
    arr = np.asarray(values, dtype=np.float64)
    frequencies = np.fft.rfftfreq(arr.shape[0], d=1.0 / sample_rate_hz)
    spectrum = np.fft.rfft(arr, axis=0)
    spectrum[(frequencies < low) | (frequencies > high), :] = 0.0
    return np.fft.irfft(spectrum, n=arr.shape[0], axis=0)


def sliding_lockin(
    values_ut: np.ndarray,
    *,
    sample_rate_hz: float,
    start_timestamp: float,
    frequency_hz: float,
    window_sec: float,
    hop_sec: float,
    window_name: str,
    detrend_mode: str,
) -> dict[str, np.ndarray | float | int]:
    window_samples = int(round(window_sec * sample_rate_hz))
    hop_samples = int(round(hop_sec * sample_rate_hz))
    if window_samples < 2 or hop_samples < 1:
        raise ValueError("window/hop produce invalid sample counts")
    if window_samples > values_ut.shape[0]:
        raise ValueError("window is longer than recording")
    weights = window_values(window_name, window_samples)
    weight_sum = float(np.sum(weights))
    coherent_gain = weight_sum / window_samples
    enbw_hz = (
        sample_rate_hz * float(np.sum(weights**2)) / (weight_sum**2)
    )
    starts = np.arange(
        0,
        values_ut.shape[0] - window_samples + 1,
        hop_samples,
        dtype=int,
    )
    channel_count = values_ut.shape[1]
    i_values = np.empty((starts.size, channel_count), dtype=np.float64)
    q_values = np.empty_like(i_values)
    amplitudes = np.empty_like(i_values)
    phases = np.empty_like(i_values)
    relative_center_s = (
        starts.astype(np.float64) + window_samples / 2.0
    ) / sample_rate_hz

    local = np.arange(window_samples, dtype=np.float64)
    for row_index, start in enumerate(starts):
        segment = detrend_signal(
            values_ut[start : start + window_samples],
            detrend_mode,
        )
        # Global sample time keeps I/Q coherent across overlapping windows.
        phase = (
            2.0
            * np.pi
            * frequency_hz
            * (start + local)
            / sample_rate_hz
        )
        cosine = np.cos(phase)
        sine = np.sin(phase)
        weighted = segment * weights[:, None]
        i_row = 2.0 * (weighted * cosine[:, None]).sum(axis=0) / weight_sum
        q_row = 2.0 * (weighted * sine[:, None]).sum(axis=0) / weight_sum
        i_values[row_index] = i_row
        q_values[row_index] = q_row
        amplitudes[row_index] = np.hypot(i_row, q_row)
        phases[row_index] = np.arctan2(q_row, i_row)

    return {
        "start_sample": starts,
        "relative_center_s": relative_center_s,
        "timestamp": start_timestamp + relative_center_s,
        "i_ut": i_values,
        "q_ut": q_values,
        "amplitude_ut": amplitudes,
        "phase_rad": phases,
        "vector_amplitude_ut": np.linalg.norm(amplitudes, axis=1),
        "window_samples": window_samples,
        "hop_samples": hop_samples,
        "coherent_gain": coherent_gain,
        "enbw_hz": enbw_hz,
    }


def amplitude_spectral_density(
    values_ut: np.ndarray,
    sample_rate_hz: float,
    detrend_mode: str,
) -> tuple[np.ndarray, np.ndarray]:
    arr = detrend_signal(values_ut, detrend_mode)
    weights = np.hanning(arr.shape[0])
    transformed = np.fft.rfft(arr * weights[:, None], axis=0)
    psd = np.abs(transformed) ** 2 / (
        sample_rate_hz * float(np.sum(weights**2))
    )
    if psd.shape[0] > 2:
        psd[1:-1] *= 2.0
    return (
        np.fft.rfftfreq(arr.shape[0], d=1.0 / sample_rate_hz),
        np.sqrt(psd),
    )


def percentile_summary(
    values_ut: np.ndarray,
    threshold_nt: float | None,
) -> dict[str, float | int | None]:
    values_nt = np.asarray(values_ut, dtype=float) * 1000.0
    return {
        "count": int(values_nt.size),
        "mean_nt": float(np.mean(values_nt)),
        "std_nt": float(np.std(values_nt)),
        "p50_nt": float(np.percentile(values_nt, 50)),
        "p95_nt": float(np.percentile(values_nt, 95)),
        "p99_nt": float(np.percentile(values_nt, 99)),
        "max_nt": float(np.max(values_nt)),
        "threshold_nt": threshold_nt,
        "threshold_exceed_ratio": (
            float(np.mean(values_nt > threshold_nt))
            if threshold_nt is not None
            else None
        ),
    }


def write_lockin_csv(
    path: Path,
    result: dict[str, np.ndarray | float | int],
    channel_count: int,
) -> None:
    fields = ["start_sample", "relative_center_s", "timestamp"]
    for index in range(channel_count):
        axis = AXIS_NAMES[index] if index < len(AXIS_NAMES) else f"ch{index}"
        fields.extend(
            [
                f"{axis}_i_ut",
                f"{axis}_q_ut",
                f"{axis}_amplitude_ut",
                f"{axis}_phase_rad",
            ]
        )
    fields.append("vector_amplitude_ut")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        starts = np.asarray(result["start_sample"])
        for row_index in range(starts.size):
            row: dict[str, object] = {
                "start_sample": int(starts[row_index]),
                "relative_center_s": float(
                    np.asarray(result["relative_center_s"])[row_index]
                ),
                "timestamp": float(
                    np.asarray(result["timestamp"])[row_index]
                ),
                "vector_amplitude_ut": float(
                    np.asarray(result["vector_amplitude_ut"])[row_index]
                ),
            }
            for index in range(channel_count):
                axis = (
                    AXIS_NAMES[index]
                    if index < len(AXIS_NAMES)
                    else f"ch{index}"
                )
                row[f"{axis}_i_ut"] = float(
                    np.asarray(result["i_ut"])[row_index, index]
                )
                row[f"{axis}_q_ut"] = float(
                    np.asarray(result["q_ut"])[row_index, index]
                )
                row[f"{axis}_amplitude_ut"] = float(
                    np.asarray(result["amplitude_ut"])[row_index, index]
                )
                row[f"{axis}_phase_rad"] = float(
                    np.asarray(result["phase_rad"])[row_index, index]
                )
            writer.writerow(row)


def write_spectrum_csv(
    path: Path,
    frequencies: np.ndarray,
    asd_ut_per_sqrt_hz: np.ndarray,
) -> None:
    fields = ["frequency_hz"] + [
        f"{AXIS_NAMES[index] if index < len(AXIS_NAMES) else f'ch{index}'}_asd_ut_per_sqrt_hz"
        for index in range(asd_ut_per_sqrt_hz.shape[1])
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row_index, frequency in enumerate(frequencies):
            row: dict[str, object] = {"frequency_hz": float(frequency)}
            for index, field in enumerate(fields[1:]):
                row[field] = float(asd_ut_per_sqrt_hz[row_index, index])
            writer.writerow(row)


def save_figures(
    output_dir: Path,
    *,
    result: dict[str, np.ndarray | float | int],
    frequencies: np.ndarray,
    asd_ut_per_sqrt_hz: np.ndarray,
    frequency_hz: float,
    dpi: int,
) -> None:
    time_s = np.asarray(result["relative_center_s"])
    amplitude_nt = np.asarray(result["amplitude_ut"]) * 1000.0
    fig, ax = plt.subplots(figsize=(9.0, 4.5))
    for index in range(amplitude_nt.shape[1]):
        axis = AXIS_NAMES[index] if index < len(AXIS_NAMES) else f"ch{index}"
        ax.plot(time_s, amplitude_nt[:, index], label=axis.upper())
    ax.set_xlabel("Time [s]")
    ax.set_ylabel(f"{frequency_hz:g} Hz amplitude [nT]")
    ax.set_title("TMR coherent lock-in amplitude")
    ax.legend()
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"lockin_amplitude.{suffix}", dpi=dpi)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9.0, 4.5))
    mask = (frequencies >= max(0.1, frequency_hz - 20.0)) & (
        frequencies <= frequency_hz + 20.0
    )
    for index in range(asd_ut_per_sqrt_hz.shape[1]):
        axis = AXIS_NAMES[index] if index < len(AXIS_NAMES) else f"ch{index}"
        ax.semilogy(
            frequencies[mask],
            asd_ut_per_sqrt_hz[mask, index] * 1e6,
            label=axis.upper(),
        )
    ax.axvline(frequency_hz, color="k", linestyle="--", linewidth=0.8)
    ax.set_xlabel("Frequency [Hz]")
    ax.set_ylabel("ASD [pT/sqrt(Hz)]")
    ax.set_title("TMR amplitude spectral density")
    ax.legend()
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"spectrum_near_reference.{suffix}", dpi=dpi)
    plt.close(fig)

    i_nt = np.asarray(result["i_ut"]) * 1000.0
    q_nt = np.asarray(result["q_ut"]) * 1000.0
    fig, ax = plt.subplots(figsize=(5.5, 5.0))
    for index in range(i_nt.shape[1]):
        axis = AXIS_NAMES[index] if index < len(AXIS_NAMES) else f"ch{index}"
        ax.scatter(i_nt[:, index], q_nt[:, index], s=8, alpha=0.45, label=axis.upper())
    ax.set_xlabel("I [nT]")
    ax.set_ylabel("Q [nT]")
    ax.set_title("Coherent I/Q distribution")
    ax.legend()
    ax.set_aspect("equal", adjustable="datalim")
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"lockin_iq.{suffix}", dpi=dpi)
    plt.close(fig)


def analyze(args: argparse.Namespace) -> dict[str, Any]:
    input_path = args.input.resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if args.frequency <= 0:
        raise ValueError("frequency must be positive")
    if (args.bandpass_low is None) != (args.bandpass_high is None):
        raise ValueError("bandpass-low and bandpass-high must be used together")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    recording = load_recording(input_path)
    recorded_metadata = recording["experiment_metadata"]
    frequency_provenance = (
        f"CLI --frequency {args.frequency:g}; source={args.frequency_source}"
    )
    if args.frequency_source == "recorded_metadata":
        if not isinstance(recorded_metadata, dict):
            raise ValueError(
                "frequency_source=recorded_metadata requires "
                "experiment_metadata_json in the NPZ"
            )
        recorded_reference = float(recorded_metadata["reference_hz"])
        if not math.isclose(
            recorded_reference,
            args.frequency,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "CLI reference frequency does not match recorded metadata: "
                f"{args.frequency} != {recorded_reference}"
            )
        recorded_excitation = recorded_metadata.get("excitation_hz")
        if recorded_excitation is not None:
            recorded_excitation = float(recorded_excitation)
        if (
            recorded_excitation is None
            and args.excitation_hz is not None
        ) or (
            recorded_excitation is not None
            and (
                args.excitation_hz is None
                or not math.isclose(
                    recorded_excitation,
                    args.excitation_hz,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
            )
        ):
            raise ValueError(
                "CLI excitation frequency does not match recorded metadata: "
                f"{args.excitation_hz} != {recorded_excitation}"
            )
        frequency_provenance = str(
            recorded_metadata.get(
                "frequency_provenance",
                "NPZ experiment_metadata_json",
            )
        )
    sample_rate_hz = float(recording["sample_rate_hz"])
    magnetic_ut = np.asarray(recording["magnetic_ut"])
    filtered_ut = fft_bandpass(
        detrend_signal(magnetic_ut, args.detrend),
        sample_rate_hz,
        args.bandpass_low,
        args.bandpass_high,
    )
    result = sliding_lockin(
        filtered_ut,
        sample_rate_hz=sample_rate_hz,
        start_timestamp=float(recording["start_timestamp"]),
        frequency_hz=args.frequency,
        window_sec=args.window_sec,
        hop_sec=args.hop_sec,
        window_name=args.window,
        detrend_mode=args.detrend,
    )
    frequencies, asd = amplitude_spectral_density(
        magnetic_ut, sample_rate_hz, args.detrend
    )
    write_lockin_csv(
        output_dir / "lockin_timeseries.csv",
        result,
        magnetic_ut.shape[1],
    )
    write_spectrum_csv(output_dir / "spectrum.csv", frequencies, asd)
    save_figures(
        output_dir,
        result=result,
        frequencies=frequencies,
        asd_ut_per_sqrt_hz=asd,
        frequency_hz=args.frequency,
        dpi=args.dpi,
    )

    nearest_index = int(np.argmin(np.abs(frequencies - args.frequency)))
    axis_summary: dict[str, Any] = {}
    amplitudes = np.asarray(result["amplitude_ut"])
    i_values = np.asarray(result["i_ut"])
    q_values = np.asarray(result["q_ut"])
    for index in range(amplitudes.shape[1]):
        axis = AXIS_NAMES[index] if index < len(AXIS_NAMES) else f"ch{index}"
        axis_summary[axis] = {
            "amplitude": percentile_summary(
                amplitudes[:, index], args.threshold_nt
            ),
            "i_mean_nt": float(np.mean(i_values[:, index]) * 1000.0),
            "q_mean_nt": float(np.mean(q_values[:, index]) * 1000.0),
            "target_asd_pt_per_sqrt_hz": float(
                asd[nearest_index, index] * 1e6
            ),
        }
    summary: dict[str, Any] = {
        "schema_version": 1,
        "data_source_id": args.data_source_id or input_path.stem,
        "data_layer": "offline_analysis",
        "input": {
            "path": str(input_path),
            "sha256": sha256_file(input_path),
            "sample_rate_hz": sample_rate_hz,
            "sample_count": int(magnetic_ut.shape[0]),
            "duration_s": float(magnetic_ut.shape[0] / sample_rate_hz),
            "channels": recording["channels"],
            "sensitivity_mv_per_ut": np.asarray(
                recording["sensitivity_mv_per_ut"]
            ).tolist(),
            "start_timestamp": recording["start_timestamp"],
            "calibration_name": recording["calibration_name"],
            "embedded_experiment_metadata": recorded_metadata,
        },
        "frequency_contract": {
            "excitation_hz": args.excitation_hz,
            "reference_hz": args.frequency,
            "frequency_source": args.frequency_source,
            "reference_type": args.reference_type,
            "frequency_provenance": frequency_provenance,
        },
        "processing": {
            "detrend": args.detrend,
            "window_name": args.window,
            "window_sec": args.window_sec,
            "hop_sec": args.hop_sec,
            "window_samples": result["window_samples"],
            "hop_samples": result["hop_samples"],
            "coherent_gain": result["coherent_gain"],
            "enbw_hz": result["enbw_hz"],
            "bandpass_low_hz": args.bandpass_low,
            "bandpass_high_hz": args.bandpass_high,
            "bandpass_method": (
                "whole-record FFT mask"
                if args.bandpass_low is not None
                else None
            ),
        },
        "window_count": int(amplitudes.shape[0]),
        "axis_summary": axis_summary,
        "vector_amplitude": percentile_summary(
            np.asarray(result["vector_amplitude_ut"]),
            args.threshold_nt,
        ),
        "target_frequency_bin_hz": float(frequencies[nearest_index]),
        "limitations": [
            "No independent hardware reference phase is available unless supplied externally.",
            "Whole-record FFT bandpass is an offline diagnostic and is not a causal online filter.",
            "Detection probability requires an independently defined background threshold.",
        ],
    }
    (output_dir / "analysis_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    excitation_label = (
        "null (background)"
        if args.excitation_hz is None
        else f"{args.excitation_hz:g} Hz"
    )
    report = [
        "# TMR/SK2301 Headless Analysis",
        "",
        f"- Data source: `{summary['data_source_id']}`",
        f"- Input: `{input_path}`",
        f"- Samples: `{summary['input']['sample_count']}` at `{sample_rate_hz:g} Hz`",
        f"- Excitation: `{excitation_label}`",
        f"- Lock-in reference: `{args.frequency:g} Hz`",
        f"- Window: `{args.window}`, `{args.window_sec:g} s`; hop `{args.hop_sec:g} s`",
        f"- ENBW: `{float(result['enbw_hz']):.6g} Hz`",
        f"- Windows: `{summary['window_count']}`",
        "",
        "| axis | p50 [nT] | p95 [nT] | p99 [nT] | ASD at reference [pT/sqrt(Hz)] |",
        "|---|---:|---:|---:|---:|",
    ]
    for axis, values in axis_summary.items():
        amplitude = values["amplitude"]
        report.append(
            f"| {axis.upper()} | {amplitude['p50_nt']:.6g} | "
            f"{amplitude['p95_nt']:.6g} | {amplitude['p99_nt']:.6g} | "
            f"{values['target_asd_pt_per_sqrt_hz']:.6g} |"
        )
    (output_dir / "report.md").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    args = parse_args()
    summary = analyze(args)
    print(
        f"[tmr-analysis] wrote {args.output_dir} "
        f"({summary['window_count']} windows)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
