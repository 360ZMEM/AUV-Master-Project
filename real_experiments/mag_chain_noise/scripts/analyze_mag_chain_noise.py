#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

try:
    import yaml
except ImportError as exc:  # pragma: no cover - dependency is declared in fangkong_adc
    raise SystemExit("PyYAML is required. Install hardware_wrappers/fangkong_adc/requirements.txt") from exc


SCRIPT_PATH = Path(__file__).resolve()
EXPERIMENT_DIR = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[3]
FANGKONG_ROOT = REPO_ROOT / "hardware_wrappers" / "fangkong_adc"
sys.path.insert(0, str(FANGKONG_ROOT))

from core.calibration import voltage_to_magnetic_field  # noqa: E402
from core.lockin import compute_lockin  # noqa: E402


MU0 = 4.0 * math.pi * 1e-7


@dataclass
class RecordMetrics:
    file: str
    group: str
    sample_rate_hz: int
    sample_count: int
    duration_s: float
    rms_demeaned_vector_nt: float
    rms_detrended_vector_nt: float
    axis_rms_detrended_nt: list[float]
    lockin_45_vector_nt: float
    lockin_50_vector_nt: float
    lockin_50_to_45_ratio: float
    spectral_peak_hz: float
    spectral_peak_asd_nt_sqrt_hz: float
    high_band_median_asd_nt_sqrt_hz: float
    high_band_rms_vector_nt: float
    max_abs_axis_corr: float
    lag1_corr_median: float


@dataclass
class InjectionMetrics:
    noise_file: str
    windows: int
    duration_s: float
    clean_peak_nt: float
    clean_median_nt: float
    replay_rmse_nt: float
    replay_bias_nt: float
    replay_p95_abs_error_nt: float
    gaussian_rmse_nt: float
    gaussian_p95_abs_error_nt: float
    replay_error_to_peak_percent: float
    gaussian_error_to_peak_percent: float


def _resolve(path_text: str, base: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (base / path).resolve()


def _load_config(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid config: {path}")
    return data


def _load_magnetic_nt(path: Path, fallback_sensitivity: list[float]) -> tuple[np.ndarray, int, list[int]]:
    archive = np.load(path, allow_pickle=False)
    voltage = np.asarray(archive["voltage"], dtype=np.float64)
    sample_rate_hz = int(archive["sample_rate_hz"])
    channels = archive["channels"].astype(int).tolist()
    sensitivity = (
        archive["sensitivity_mv_per_ut"].astype(float).tolist()
        if "sensitivity_mv_per_ut" in archive
        else fallback_sensitivity
    )
    magnetic_ut = voltage_to_magnetic_field(voltage, sensitivity)
    return magnetic_ut * 1000.0, sample_rate_hz, channels


def _vector_lockin_nt(samples_nt: np.ndarray, sample_rate_hz: int, frequency_hz: float) -> float:
    results = compute_lockin(samples_nt, sample_rate_hz, list(range(samples_nt.shape[1])), frequency_hz)
    return float(np.linalg.norm([item.amplitude for item in results]))


def _linear_detrend(samples: np.ndarray) -> np.ndarray:
    arr = np.asarray(samples, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError("samples must be a 2D array")
    finite = np.isfinite(arr)
    if not np.all(finite):
        med = np.nanmedian(np.where(finite, arr, np.nan), axis=0)
        arr = np.where(finite, arr, med[None, :])
    if arr.shape[0] < 2:
        return arr - np.mean(arr, axis=0)
    t = np.linspace(-1.0, 1.0, arr.shape[0], dtype=np.float64)
    centered = arr - np.mean(arr, axis=0)
    slope = np.sum(centered * t[:, None], axis=0) / max(float(np.sum(t**2)), 1e-12)
    return centered - t[:, None] * slope[None, :]


def _same_covariance_gaussian(noise_nt: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    covariance = np.cov(noise_nt, rowvar=False)
    covariance = 0.5 * (covariance + covariance.T)
    eigval, eigvec = np.linalg.eigh(covariance)
    eigval = np.clip(eigval, 0.0, None)
    transform = eigvec @ np.diag(np.sqrt(eigval))
    standard = rng.normal(size=noise_nt.shape)
    return np.einsum("ni,ji->nj", standard, transform, optimize=False)


def _sliding_vector_lockin_nt(
    samples_nt: np.ndarray,
    sample_rate_hz: int,
    frequency_hz: float,
    window_sec: float,
    hop_sec: float,
) -> tuple[np.ndarray, np.ndarray]:
    window = int(round(window_sec * sample_rate_hz))
    hop = max(1, int(round(hop_sec * sample_rate_hz)))
    if window <= 1 or samples_nt.shape[0] < window:
        return np.empty(0, dtype=float), np.empty(0, dtype=float)
    times: list[float] = []
    amplitudes: list[float] = []
    pos = 0
    while pos + window <= samples_nt.shape[0]:
        segment = samples_nt[pos : pos + window]
        results = compute_lockin(segment, sample_rate_hz, list(range(samples_nt.shape[1])), frequency_hz)
        amplitudes.append(float(np.linalg.norm([item.amplitude for item in results])))
        times.append(float((pos + 0.5 * window) / sample_rate_hz))
        pos += hop
    return np.asarray(times, dtype=float), np.asarray(amplitudes, dtype=float)


def _welch_vector_asd(
    samples_nt: np.ndarray,
    sample_rate_hz: int,
    segment_sec: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    nperseg = min(samples_nt.shape[0], max(256, int(round(segment_sec * sample_rate_hz))))
    freqs, psd = signal.welch(
        samples_nt,
        fs=sample_rate_hz,
        window="hann",
        nperseg=nperseg,
        axis=0,
        scaling="density",
    )
    axis_asd = np.sqrt(psd)
    vector_asd = np.sqrt(np.sum(psd, axis=1))
    return freqs, axis_asd, vector_asd


def _axis_lag1_corr(samples: np.ndarray) -> float:
    vals = []
    for idx in range(samples.shape[1]):
        x = samples[:, idx]
        if x.size < 3 or np.std(x[:-1]) < 1e-12 or np.std(x[1:]) < 1e-12:
            continue
        vals.append(float(np.corrcoef(x[:-1], x[1:])[0, 1]))
    return float(np.median(vals)) if vals else float("nan")


def _group_for(path: Path, default_background: set[str], known_45hz: set[str], joint_record: str) -> str:
    if path.name == joint_record:
        return "biot_savart_joint"
    if path.name in default_background:
        return "default_background"
    if path.name in known_45hz:
        return "known_45hz_excited"
    return "context_record"


def _compute_record_metrics(
    path: Path,
    group: str,
    cfg: dict[str, Any],
) -> RecordMetrics:
    analysis = cfg["analysis"]
    magnetic_nt, sample_rate_hz, _channels = _load_magnetic_nt(path, analysis["sensitivity_mv_per_ut"])
    demeaned = magnetic_nt - np.mean(magnetic_nt, axis=0)
    detrended = _linear_detrend(magnetic_nt)
    rms_demeaned_axis = np.sqrt(np.mean(demeaned**2, axis=0))
    rms_detrended_axis = np.sqrt(np.mean(detrended**2, axis=0))

    freqs, _axis_asd, vector_asd = _welch_vector_asd(
        detrended,
        sample_rate_hz,
        float(analysis["welch_segment_sec"]),
    )
    peak_lo, peak_hi = [float(v) for v in analysis["spectral_peak_band_hz"]]
    peak_mask = (freqs >= peak_lo) & (freqs <= min(peak_hi, sample_rate_hz / 2.0))
    peak_idx = int(np.argmax(vector_asd[peak_mask]))
    peak_freq = float(freqs[peak_mask][peak_idx])
    peak_asd = float(vector_asd[peak_mask][peak_idx])

    high_lo, high_hi = [float(v) for v in analysis["high_frequency_band_hz"]]
    high_mask = (freqs >= high_lo) & (freqs <= min(high_hi, sample_rate_hz / 2.0))
    high_asd = vector_asd[high_mask]
    high_freqs = freqs[high_mask]
    high_band_median_asd = float(np.median(high_asd)) if high_asd.size else float("nan")
    integrate = getattr(np, "trapezoid", np.trapz)
    high_band_rms = float(math.sqrt(integrate(high_asd**2, high_freqs))) if high_asd.size > 1 else float("nan")

    corr = np.corrcoef(detrended, rowvar=False)
    max_abs_corr = float(np.max(np.abs(corr[np.triu_indices(detrended.shape[1], 1)])))

    lockin_45 = _vector_lockin_nt(
        detrended,
        sample_rate_hz,
        float(analysis["reference_frequency_hz"]),
    )
    lockin_50 = _vector_lockin_nt(
        detrended,
        sample_rate_hz,
        float(analysis["mains_frequency_hz"]),
    )
    return RecordMetrics(
        file=path.name,
        group=group,
        sample_rate_hz=sample_rate_hz,
        sample_count=int(magnetic_nt.shape[0]),
        duration_s=float(magnetic_nt.shape[0] / sample_rate_hz),
        rms_demeaned_vector_nt=float(np.sqrt(np.sum(rms_demeaned_axis**2))),
        rms_detrended_vector_nt=float(np.sqrt(np.sum(rms_detrended_axis**2))),
        axis_rms_detrended_nt=[float(v) for v in rms_detrended_axis],
        lockin_45_vector_nt=lockin_45,
        lockin_50_vector_nt=lockin_50,
        lockin_50_to_45_ratio=float(lockin_50 / max(lockin_45, 1e-12)),
        spectral_peak_hz=peak_freq,
        spectral_peak_asd_nt_sqrt_hz=peak_asd,
        high_band_median_asd_nt_sqrt_hz=high_band_median_asd,
        high_band_rms_vector_nt=high_band_rms,
        max_abs_axis_corr=max_abs_corr,
        lag1_corr_median=_axis_lag1_corr(detrended),
    )


def _wire_field_nt(
    lateral_m: np.ndarray,
    height_m: float,
    current_peak_a: float,
) -> np.ndarray:
    k_nt_m = MU0 * current_peak_a / (2.0 * math.pi) * 1e9
    rho2 = np.maximum(lateral_m**2 + height_m**2, 1e-12)
    # Wire along local y; field lies in x-z plane.
    bx = k_nt_m * height_m / rho2
    by = np.zeros_like(bx)
    bz = -k_nt_m * lateral_m / rho2
    return np.column_stack([bx, by, bz])


def _simulate_injection_for_record(
    path: Path,
    cfg: dict[str, Any],
    rng: np.random.Generator,
) -> tuple[InjectionMetrics, dict[str, np.ndarray]]:
    analysis = cfg["analysis"]
    sim = cfg["simulation"]
    magnetic_nt, sample_rate_hz, _channels = _load_magnetic_nt(path, analysis["sensitivity_mv_per_ut"])
    noise_nt = _linear_detrend(magnetic_nt)
    t = np.arange(noise_nt.shape[0], dtype=float) / sample_rate_hz
    lateral = np.linspace(-0.5 * float(sim["lateral_span_m"]), 0.5 * float(sim["lateral_span_m"]), noise_nt.shape[0])
    envelope_nt = _wire_field_nt(lateral, float(sim["wire_height_m"]), float(sim["current_peak_a"]))
    clean_nt = envelope_nt * np.sin(2.0 * math.pi * float(analysis["reference_frequency_hz"]) * t)[:, None]
    gaussian_noise = _same_covariance_gaussian(noise_nt, rng)
    replay_signal = clean_nt + noise_nt
    gaussian_signal = clean_nt + gaussian_noise

    lock_t, clean_amp = _sliding_vector_lockin_nt(
        clean_nt,
        sample_rate_hz,
        float(analysis["reference_frequency_hz"]),
        float(analysis["lockin_window_sec"]),
        float(analysis["lockin_hop_sec"]),
    )
    _, replay_amp = _sliding_vector_lockin_nt(
        replay_signal,
        sample_rate_hz,
        float(analysis["reference_frequency_hz"]),
        float(analysis["lockin_window_sec"]),
        float(analysis["lockin_hop_sec"]),
    )
    _, gaussian_amp = _sliding_vector_lockin_nt(
        gaussian_signal,
        sample_rate_hz,
        float(analysis["reference_frequency_hz"]),
        float(analysis["lockin_window_sec"]),
        float(analysis["lockin_hop_sec"]),
    )
    if clean_amp.size == 0:
        raise ValueError(f"{path.name} is too short for the configured lock-in window")

    replay_error = replay_amp - clean_amp
    gaussian_error = gaussian_amp - clean_amp
    clean_peak = float(np.max(clean_amp))
    metrics = InjectionMetrics(
        noise_file=path.name,
        windows=int(clean_amp.size),
        duration_s=float(noise_nt.shape[0] / sample_rate_hz),
        clean_peak_nt=clean_peak,
        clean_median_nt=float(np.median(clean_amp)),
        replay_rmse_nt=float(np.sqrt(np.mean(replay_error**2))),
        replay_bias_nt=float(np.mean(replay_error)),
        replay_p95_abs_error_nt=float(np.percentile(np.abs(replay_error), 95)),
        gaussian_rmse_nt=float(np.sqrt(np.mean(gaussian_error**2))),
        gaussian_p95_abs_error_nt=float(np.percentile(np.abs(gaussian_error), 95)),
        replay_error_to_peak_percent=float(100.0 * np.sqrt(np.mean(replay_error**2)) / max(clean_peak, 1e-12)),
        gaussian_error_to_peak_percent=float(100.0 * np.sqrt(np.mean(gaussian_error**2)) / max(clean_peak, 1e-12)),
    )
    series = {
        "time_s": lock_t,
        "clean_amp_nt": clean_amp,
        "replay_amp_nt": replay_amp,
        "gaussian_amp_nt": gaussian_amp,
        "replay_error_nt": replay_error,
        "gaussian_error_nt": gaussian_error,
    }
    return metrics, series


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def _plot_background_spectra(
    output_dir: Path,
    record_paths: list[Path],
    cfg: dict[str, Any],
) -> None:
    analysis = cfg["analysis"]
    fig, ax = plt.subplots(figsize=(8.0, 4.6))
    for path in record_paths:
        magnetic_nt, sample_rate_hz, _channels = _load_magnetic_nt(path, analysis["sensitivity_mv_per_ut"])
        detrended = _linear_detrend(magnetic_nt)
        freqs, _axis_asd, vector_asd = _welch_vector_asd(
            detrended,
            sample_rate_hz,
            float(analysis["welch_segment_sec"]),
        )
        ax.semilogy(freqs, vector_asd, linewidth=1.0, alpha=0.85, label=path.stem)
    ax.axvline(float(analysis["reference_frequency_hz"]), color="#1f77b4", linestyle="--", linewidth=1.0, label="45 Hz target")
    ax.axvline(float(analysis["mains_frequency_hz"]), color="#d62728", linestyle="--", linewidth=1.0, label="50 Hz mains")
    ax.set_xlim(0.0, 120.0)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Vector ASD (nT/sqrt(Hz))")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(output_dir / "background_lockin_spectrum.png", dpi=220)
    fig.savefig(output_dir / "background_lockin_spectrum.pdf")
    plt.close(fig)


def _plot_record_metric_summary(output_dir: Path, records: list[RecordMetrics]) -> None:
    labels = [Path(item.file).stem for item in records]
    x = np.arange(len(records), dtype=float)
    lock45 = np.asarray([item.lockin_45_vector_nt for item in records], dtype=float)
    lock50 = np.asarray([item.lockin_50_vector_nt for item in records], dtype=float)
    rms = np.asarray([item.rms_detrended_vector_nt for item in records], dtype=float)
    fig, ax = plt.subplots(figsize=(10.0, 4.8))
    ax.semilogy(x, rms, "o-", label="detrended RMS")
    ax.semilogy(x, lock45, "s-", label="45 Hz lock-in")
    ax.semilogy(x, lock50, "^-", label="50 Hz lock-in")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=75, ha="right", fontsize=7)
    ax.set_ylabel("Vector magnitude (nT)")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "noise_record_metric_summary.png", dpi=220)
    fig.savefig(output_dir / "noise_record_metric_summary.pdf")
    plt.close(fig)


def _plot_injection(output_dir: Path, series: dict[str, np.ndarray], metrics: InjectionMetrics) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(8.0, 5.6), sharex=True)
    axes[0].plot(series["time_s"], series["clean_amp_nt"], label="clean Biot-Savart", linewidth=1.6)
    axes[0].plot(series["time_s"], series["replay_amp_nt"], label="measured-noise replay", linewidth=1.2)
    axes[0].plot(series["time_s"], series["gaussian_amp_nt"], label="same-covariance Gaussian", linewidth=1.0, alpha=0.75)
    axes[0].set_ylabel("45 Hz lock-in amplitude (nT)")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(fontsize=8)
    axes[1].plot(series["time_s"], series["replay_error_nt"], label="replay error", linewidth=1.2)
    axes[1].plot(series["time_s"], series["gaussian_error_nt"], label="Gaussian error", linewidth=1.0, alpha=0.75)
    axes[1].axhline(0.0, color="black", linewidth=0.8)
    axes[1].set_xlabel("Time (s)")
    axes[1].set_ylabel("Amplitude error (nT)")
    axes[1].grid(True, alpha=0.25)
    axes[1].legend(fontsize=8)
    fig.suptitle(f"Noise-injected Biot-Savart replay: {metrics.noise_file}")
    fig.tight_layout()
    fig.savefig(output_dir / "noise_injected_biot_savart_replay.png", dpi=220)
    fig.savefig(output_dir / "noise_injected_biot_savart_replay.pdf")
    plt.close(fig)


def _copy_thesis_figures(output_dir: Path) -> None:
    thesis_dir = REPO_ROOT / "docs" / "thesis" / "figures" / "hardware" / "mag_chain_noise"
    thesis_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "background_lockin_spectrum.png",
        "noise_record_metric_summary.png",
        "noise_injected_biot_savart_replay.png",
    ):
        src = output_dir / "figures" / name
        if src.exists():
            shutil.copy2(src, thesis_dir / name)


def _load_biot_savart_summary(cfg: dict[str, Any]) -> dict[str, Any] | None:
    item = cfg.get("biot_savart_reference", {})
    summary_path = _resolve(str(item.get("summary_json", "")), EXPERIMENT_DIR)
    if not summary_path.exists():
        return None
    return json.loads(summary_path.read_text(encoding="utf-8"))


def _write_report(
    output_dir: Path,
    record_metrics: list[RecordMetrics],
    injection_metrics: list[InjectionMetrics],
    noise_profile: dict[str, Any],
    biot_summary: dict[str, Any] | None,
    cfg: dict[str, Any],
) -> None:
    background = [item for item in record_metrics if item.group == "default_background"]
    best_injection = injection_metrics[0] if injection_metrics else None
    lines = [
        "# ADC-TMR full-chain noise integration replay",
        "",
        "## Scope",
        "",
        "This experiment uses the local `hardware_wrappers/fangkong_adc/raw_data` NPZ captures.",
        "It is a dorm-room full-chain background/noise replay, not a calibrated lab noise-floor certification.",
        "The 45 Hz target is kept separate from the 50 Hz mains component so the result can support the thesis simulation-to-hardware narrative.",
        "",
        "## One-command reproduction",
        "",
        "```bash",
        "real_experiments/mag_chain_noise/run.sh",
        "```",
        "",
        "## Background records used for the default replay",
        "",
        "| file | duration (s) | RMS after detrend (nT) | 45 Hz lock-in (nT) | 50 Hz lock-in (nT) | peak (Hz) | max axis corr |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in background:
        lines.append(
            f"| `{item.file}` | {item.duration_s:.3f} | {item.rms_detrended_vector_nt:.3f} | "
            f"{item.lockin_45_vector_nt:.3f} | {item.lockin_50_vector_nt:.3f} | "
            f"{item.spectral_peak_hz:.2f} | {item.max_abs_axis_corr:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Derived replay profile",
            "",
            f"- background records: {noise_profile['background_record_count']}",
            f"- total background duration: {noise_profile['total_background_duration_s']:.3f} s",
            f"- median 45 Hz vector lock-in: {noise_profile['median_lockin_45_vector_nt']:.3f} nT",
            f"- median 50 Hz vector lock-in: {noise_profile['median_lockin_50_vector_nt']:.3f} nT",
            f"- median high-band vector ASD: {noise_profile['median_high_band_asd_nt_sqrt_hz']:.3f} nT/sqrt(Hz)",
            f"- vector RMS after linear detrend: {noise_profile['concatenated_detrended_vector_rms_nt']:.3f} nT",
            "",
            "## Noise-injected Biot-Savart semi-physical replay",
            "",
        ]
    )
    if best_injection is not None:
        lines.extend(
            [
                f"Reference plot uses `{best_injection.noise_file}`.",
                "",
                "| noise file | windows | clean peak (nT) | replay RMSE (nT) | Gaussian RMSE (nT) | replay error/peak |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for item in injection_metrics:
            lines.append(
                f"| `{item.noise_file}` | {item.windows} | {item.clean_peak_nt:.1f} | "
                f"{item.replay_rmse_nt:.3f} | {item.gaussian_rmse_nt:.3f} | "
                f"{item.replay_error_to_peak_percent:.3f}% |"
            )
    if biot_summary is not None:
        complex_free = biot_summary.get("complex_iq_free_scale", {})
        complex_fixed = biot_summary.get("complex_iq_fixed_current", {})
        constants = biot_summary.get("constants", {})
        lines.extend(
            [
                "",
                "## Existing Biot-Savart joint inversion audit",
                "",
                f"- aligned lock-in/pose pairs: {biot_summary.get('aligned_count')}",
                f"- lock-in frequency: {constants.get('lockin_frequency_hz')} Hz",
                f"- peak current used by fixed model: {constants.get('current_peak_a'):.6f} A",
                f"- complex I/Q free-scale R2: {complex_free.get('complex_r2'):.4f}",
                f"- complex I/Q fixed-current R2: {complex_fixed.get('complex_r2'):.4f}",
                f"- free-scale equivalent current: {complex_free.get('equivalent_current_a'):.4f} A",
            ]
        )
    lines.extend(
        [
            "",
            "## Thesis-use boundary",
            "",
            "- Use this as a semi-physical replay and full-chain background-noise support.",
            "- Do not write it as a calibrated laboratory noise-floor or complete AUV field acceptance test.",
            "- Keep the 50 Hz mains component as an environmental interference term; the controlled target remains 45 Hz.",
            "",
        ]
    )
    (output_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze ADC-TMR full-chain noise captures and replay them into a 45 Hz Biot-Savart signal.")
    parser.add_argument("--config", type=Path, default=EXPERIMENT_DIR / "config.yaml")
    args = parser.parse_args()

    cfg = _load_config(args.config.resolve())
    raw_dir = _resolve(cfg["raw_data_dir"], EXPERIMENT_DIR)
    output_dir = _resolve(cfg.get("output_dir", "."), EXPERIMENT_DIR)
    data_dir = output_dir / "data"
    figures_dir = output_dir / "figures"
    data_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    default_background = set(cfg["records"]["default_background"])
    known_45hz = set(cfg["records"].get("known_45hz_excited", []))
    joint_record = str(cfg["records"].get("biot_savart_joint_record", ""))
    record_paths = sorted(raw_dir.glob(cfg["records"].get("include_glob", "*.npz")))
    if not record_paths:
        raise SystemExit(f"No NPZ records found under {raw_dir}")

    record_metrics = [
        _compute_record_metrics(
            path,
            _group_for(path, default_background, known_45hz, joint_record),
            cfg,
        )
        for path in record_paths
    ]
    background_paths = [raw_dir / name for name in cfg["records"]["default_background"]]
    missing = [str(path) for path in background_paths if not path.exists()]
    if missing:
        raise SystemExit(f"Missing configured background records: {missing}")

    rng = np.random.default_rng(int(cfg["simulation"]["gaussian_seed"]))
    injection_results: list[InjectionMetrics] = []
    injection_series: dict[str, np.ndarray] | None = None
    for path in background_paths:
        metrics, series = _simulate_injection_for_record(path, cfg, rng)
        injection_results.append(metrics)
        if injection_series is None:
            injection_series = series

    background_metrics = [item for item in record_metrics if item.group == "default_background"]
    background_arrays = []
    for path in background_paths:
        magnetic_nt, _sample_rate_hz, _channels = _load_magnetic_nt(path, cfg["analysis"]["sensitivity_mv_per_ut"])
        background_arrays.append(_linear_detrend(magnetic_nt))
    concat_background = np.vstack(background_arrays)
    axis_rms = np.sqrt(np.mean(concat_background**2, axis=0))
    noise_profile = {
        "background_record_count": len(background_metrics),
        "total_background_duration_s": float(sum(item.duration_s for item in background_metrics)),
        "default_background_records": [item.file for item in background_metrics],
        "median_lockin_45_vector_nt": float(np.median([item.lockin_45_vector_nt for item in background_metrics])),
        "median_lockin_50_vector_nt": float(np.median([item.lockin_50_vector_nt for item in background_metrics])),
        "median_high_band_asd_nt_sqrt_hz": float(np.median([item.high_band_median_asd_nt_sqrt_hz for item in background_metrics])),
        "concatenated_detrended_axis_rms_nt": [float(v) for v in axis_rms],
        "concatenated_detrended_vector_rms_nt": float(np.sqrt(np.sum(axis_rms**2))),
        "notes": [
            "Dorm-room background/noise captures; 50 Hz mains is an environmental interference term.",
            "Use 45 Hz for controlled target injection to stay separated from the 50 Hz mains component.",
            "This is a full-chain replay profile, not a metrology-grade laboratory noise floor.",
        ],
    }

    biot_summary = _load_biot_savart_summary(cfg)
    metrics = {
        "record_metrics": [asdict(item) for item in record_metrics],
        "noise_profile": noise_profile,
        "noise_injection_metrics": [asdict(item) for item in injection_results],
        "biot_savart_joint_inversion": None,
    }
    if biot_summary is not None:
        metrics["biot_savart_joint_inversion"] = {
            "aligned_count": biot_summary.get("aligned_count"),
            "lockin_frequency_hz": biot_summary.get("constants", {}).get("lockin_frequency_hz"),
            "current_peak_a": biot_summary.get("constants", {}).get("current_peak_a"),
            "complex_iq_free_scale_r2": biot_summary.get("complex_iq_free_scale", {}).get("complex_r2"),
            "complex_iq_fixed_current_r2": biot_summary.get("complex_iq_fixed_current", {}).get("complex_r2"),
            "complex_iq_free_scale_equivalent_current_a": biot_summary.get("complex_iq_free_scale", {}).get("equivalent_current_a"),
        }

    (output_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (data_dir / "noise_profile.json").write_text(json.dumps(noise_profile, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(data_dir / "record_metrics.csv", [asdict(item) for item in record_metrics])
    _write_csv(data_dir / "noise_injection_metrics.csv", [asdict(item) for item in injection_results])

    _plot_background_spectra(figures_dir, background_paths, cfg)
    _plot_record_metric_summary(figures_dir, record_metrics)
    if injection_series is not None and injection_results:
        _plot_injection(figures_dir, injection_series, injection_results[0])
    _copy_thesis_figures(output_dir)
    _write_report(output_dir, record_metrics, injection_results, noise_profile, biot_summary, cfg)

    print(f"[mag-chain-noise] records: {len(record_metrics)}")
    print(f"[mag-chain-noise] background records: {len(background_metrics)}")
    print(f"[mag-chain-noise] total background duration: {noise_profile['total_background_duration_s']:.3f} s")
    print(f"[mag-chain-noise] median 45 Hz lock-in: {noise_profile['median_lockin_45_vector_nt']:.3f} nT")
    print(f"[mag-chain-noise] median 50 Hz lock-in: {noise_profile['median_lockin_50_vector_nt']:.3f} nT")
    if injection_results:
        first = injection_results[0]
        print(
            "[mag-chain-noise] replay injection: "
            f"{first.noise_file}, RMSE={first.replay_rmse_nt:.3f} nT, "
            f"peak error={first.replay_error_to_peak_percent:.3f}%"
        )
    if metrics["biot_savart_joint_inversion"] is not None:
        ref = metrics["biot_savart_joint_inversion"]
        print(
            "[mag-chain-noise] Biot-Savart audit: "
            f"aligned={ref['aligned_count']}, "
            f"free_R2={ref['complex_iq_free_scale_r2']:.4f}, "
            f"fixed_R2={ref['complex_iq_fixed_current_r2']:.4f}"
        )
    print(f"[mag-chain-noise] report: {output_dir / 'report.md'}")


if __name__ == "__main__":
    main()
