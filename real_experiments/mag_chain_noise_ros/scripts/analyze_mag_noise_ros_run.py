#!/usr/bin/env python3
"""Aggregate ROS-side magnetic noise replay runs.

Inputs are the per-mode artifacts produced by run.sh:
  - run_index.csv
  - tracking JSONL extracted from /auv/cable/tracking
  - optional noise metadata JSONL extracted from /auv/sensors/magnetic_noise_metadata
  - optional MCAP rosbag for /auv/control/setpoint command-rate statistics
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
import shutil
import sys
from typing import Any, Iterable

import numpy as np


SCRIPT_PATH = Path(__file__).resolve()
EXPERIMENT_DIR = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[3]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from thesis_plot_style import apply_thesis_style, save_figure, series_style  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-index", type=Path, default=EXPERIMENT_DIR / "data" / "run_index.csv")
    parser.add_argument("--output-dir", type=Path, default=EXPERIMENT_DIR)
    parser.add_argument(
        "--figure-dir",
        type=Path,
        default=REPO_ROOT / "docs/thesis/figures/experiments/mag_chain_noise_ros",
    )
    parser.add_argument("--warmup-s", type=float, default=4.0)
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    path = _resolve(path)
    if not path.exists() or path.stat().st_size == 0:
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            rows.append(json.loads(text))
        except json.JSONDecodeError:
            continue
    return rows


def _read_run_index(path: Path) -> list[dict[str, str]]:
    path = _resolve(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _float_or_nan(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return number if math.isfinite(number) else float("nan")


def _finite(values: Iterable[Any]) -> np.ndarray:
    arr = np.asarray([_float_or_nan(value) for value in values], dtype=np.float64)
    return arr[np.isfinite(arr)]


def _ratio(values: Iterable[Any]) -> float:
    items = [bool(value) for value in values]
    return float(sum(1 for item in items if item) / len(items)) if items else float("nan")


def _percentile(values: np.ndarray, q: float) -> float:
    return float(np.percentile(values, q)) if values.size else float("nan")


def _filter_warmup(rows: list[dict[str, Any]], warmup_s: float) -> list[dict[str, Any]]:
    times = _finite(row.get("time_s") for row in rows)
    if not rows or not times.size:
        return rows
    start = float(np.min(times))
    return [row for row in rows if _float_or_nan(row.get("time_s")) - start >= warmup_s]


def _counter_values(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = row.get(key)
        if isinstance(value, list):
            for item in value:
                counter[str(item)] += 1
        elif value is not None:
            counter[str(value)] += 1
    return dict(sorted(counter.items()))


def _topic_chunks(path_text: str) -> list[Path]:
    if not path_text or path_text == "NONE":
        return []
    path = _resolve(Path(path_text))
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.mcap"))
    return []


def _setpoint_metrics(path_text: str) -> dict[str, Any]:
    chunks = _topic_chunks(path_text)
    if not chunks:
        return {
            "setpoint_sample_count": 0,
            "control_rate_rms_per_s": float("nan"),
            "control_rate_mean_abs_per_s": float("nan"),
            "setpoint_metric_status": "no_bag",
        }
    try:
        from mcap_ros2.reader import read_ros2_messages
    except ImportError:
        return {
            "setpoint_sample_count": 0,
            "control_rate_rms_per_s": float("nan"),
            "control_rate_mean_abs_per_s": float("nan"),
            "setpoint_metric_status": "mcap_ros2_missing",
        }

    times: list[float] = []
    vectors: list[list[float]] = []
    for chunk in chunks:
        try:
            decoded_iter = read_ros2_messages(str(chunk), topics=["/auv/control/setpoint"])
            for decoded in decoded_iter:
                msg = decoded.ros_msg
                times.append(float(getattr(decoded, "log_time_ns", 0)) * 1.0e-9)
                vectors.append(
                    [
                        float(getattr(msg, "target_heading_rad", 0.0)),
                        float(getattr(msg, "target_speed_mps", 0.0)),
                        float(getattr(msg, "target_depth_m", 0.0)),
                    ]
                )
        except Exception:
            return {
                "setpoint_sample_count": len(vectors),
                "control_rate_rms_per_s": float("nan"),
                "control_rate_mean_abs_per_s": float("nan"),
                "setpoint_metric_status": "decode_failed",
            }
    if len(vectors) < 2:
        return {
            "setpoint_sample_count": len(vectors),
            "control_rate_rms_per_s": float("nan"),
            "control_rate_mean_abs_per_s": float("nan"),
            "setpoint_metric_status": "insufficient_samples",
        }
    order = np.argsort(np.asarray(times, dtype=np.float64))
    t = np.asarray(times, dtype=np.float64)[order]
    v = np.asarray(vectors, dtype=np.float64)[order]
    v[:, 0] = np.unwrap(v[:, 0])
    dt = np.diff(t)
    dv = np.diff(v, axis=0)
    mask = dt > 1.0e-6
    if not np.any(mask):
        return {
            "setpoint_sample_count": len(vectors),
            "control_rate_rms_per_s": float("nan"),
            "control_rate_mean_abs_per_s": float("nan"),
            "setpoint_metric_status": "nonpositive_dt",
        }
    rates = dv[mask] / dt[mask, None]
    rate_norm = np.linalg.norm(rates, axis=1)
    return {
        "setpoint_sample_count": len(vectors),
        "control_rate_rms_per_s": float(np.sqrt(np.mean(rate_norm * rate_norm))),
        "control_rate_mean_abs_per_s": float(np.mean(np.abs(rates))),
        "setpoint_metric_status": "ok",
    }


def _summarize_tracking(rows: list[dict[str, Any]], warmup_s: float) -> dict[str, Any]:
    kept = _filter_warmup(rows, warmup_s)
    times = _finite(row.get("time_s") for row in kept)
    cross = np.abs(_finite(row.get("cross_track_m") for row in kept))
    confidence = _finite(row.get("confidence") for row in kept)
    magnetic_confidence = _finite(row.get("magnetic_confidence") for row in kept)
    snr = _finite(row.get("magnetic_snr_db") for row in kept)
    burial_sigma = _finite(row.get("burial_sigma_m") for row in kept)
    diagnostics = [row.get("diagnostics", {}) for row in kept if isinstance(row.get("diagnostics"), dict)]
    prior_observed = [diag.get("prior_alignment_observed", False) for diag in diagnostics]
    prior_accepted = [diag.get("prior_alignment_accepted", False) for diag in diagnostics]
    return {
        "tracking_sample_count": len(kept),
        "tracking_duration_s": float(np.max(times) - np.min(times)) if times.size > 1 else 0.0,
        "cross_track_abs_mean_m": float(np.mean(cross)) if cross.size else float("nan"),
        "cross_track_abs_p95_m": _percentile(cross, 95),
        "cross_track_abs_max_m": float(np.max(cross)) if cross.size else float("nan"),
        "confidence_mean": float(np.mean(confidence)) if confidence.size else float("nan"),
        "confidence_min": float(np.min(confidence)) if confidence.size else float("nan"),
        "magnetic_confidence_mean": float(np.mean(magnetic_confidence)) if magnetic_confidence.size else float("nan"),
        "magnetic_snr_db_mean": float(np.mean(snr)) if snr.size else float("nan"),
        "magnetic_snr_db_p05": _percentile(snr, 5),
        "burial_sigma_p95_m": _percentile(burial_sigma, 95),
        "industrial_ready_ratio": _ratio(row.get("industrial_ready", False) for row in kept),
        "industrial_acceptance_pass_ratio": _ratio(row.get("industrial_acceptance_pass", False) for row in kept),
        "prior_alignment_observed_ratio": _ratio(prior_observed),
        "prior_alignment_accepted_ratio": _ratio(prior_accepted),
        "mode_counts": _counter_values(kept, "mode"),
        "acceptance_flag_counts": _counter_values(kept, "acceptance_flags"),
        "quality_flag_counts": _counter_values(kept, "quality_flags"),
    }


def _summarize_noise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    magnitude = _finite(row.get("noise_magnitude_nt") for row in rows)
    clean = _finite(row.get("clean_magnitude_nt") for row in rows)
    published = _finite(row.get("published_magnitude_nt") for row in rows)
    sample_index = [_float_or_nan(row.get("sample_index")) for row in rows]
    finite_index = [int(value) for value in sample_index if math.isfinite(value)]
    wraps = sum(1 for prev, curr in zip(finite_index, finite_index[1:]) if curr < prev)
    first = rows[0] if rows else {}
    source_npz = first.get("noise_source_npz", [])
    if isinstance(source_npz, str):
        source_npz = [source_npz]
    return {
        "noise_metadata_sample_count": len(rows),
        "noise_magnitude_mean_nt": float(np.mean(magnitude)) if magnitude.size else 0.0,
        "noise_magnitude_p95_nt": _percentile(magnitude, 95) if magnitude.size else 0.0,
        "noise_magnitude_max_nt": float(np.max(magnitude)) if magnitude.size else 0.0,
        "clean_magnitude_mean_nt": float(np.mean(clean)) if clean.size else float("nan"),
        "published_magnitude_mean_nt": float(np.mean(published)) if published.size else float("nan"),
        "replay_wrap_count": wraps,
        "noise_profile_sha256": first.get("noise_profile_sha256", ""),
        "noise_source_npz": source_npz,
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    return value


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    scalar_rows: list[dict[str, Any]] = []
    for row in rows:
        scalar = {}
        for key, value in row.items():
            if isinstance(value, (dict, list)):
                scalar[key] = json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True)
            else:
                scalar[key] = value
        scalar_rows.append(scalar)
    fieldnames: list[str] = []
    for row in scalar_rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(scalar_rows)


def _plot_summary(rows: list[dict[str, Any]], figure_dir: Path) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    apply_thesis_style(base_font_size=11)
    labels = [str(row["mode"]) for row in rows]
    x = np.arange(len(labels), dtype=float)
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.0))

    panels = [
        ("cross_track_abs_p95_m", "横偏 p95 (m)"),
        ("confidence_mean", "平均置信度"),
        ("noise_magnitude_p95_nt", "噪声幅值 p95 (nT)"),
    ]
    for ax, (key, ylabel) in zip(axes, panels):
        values = [_float_or_nan(row.get(key)) for row in rows]
        for index, value in enumerate(values):
            ax.bar(x[index], value if math.isfinite(value) else 0.0, 0.65, **series_style(index))
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=18, ha="right")
        ax.set_ylabel(ylabel)
        ax.grid(True, axis="y", alpha=0.3)
    axes[0].set_title("闭环横偏")
    axes[1].set_title("跟踪置信度")
    axes[2].set_title("观测层噪声")
    fig.suptitle("ADC-TMR 实测背景噪声 ROS 闭环对照")
    fig.tight_layout()
    written = save_figure(fig, figure_dir / "mag_chain_noise_ros_comparison")
    plt.close(fig)
    return written


def _write_report(path: Path, rows: list[dict[str, Any]], figure_paths: list[Path]) -> None:
    lines = [
        "# ADC-TMR measured replay ROS comparison",
        "",
        "This report is generated from the Linux-side ROS2 Direction A cable-loop replay.",
        "Noise is added only to `/auv/sensors/magnetic`; cable, terrain, current, and vehicle truth are unchanged.",
        "",
        "## Summary",
        "",
        "| mode | tracking samples | cross-track p95 (m) | confidence mean | mag SNR mean (dB) | noise p95 (nT) | prior observed | prior accepted | ready ratio | pass ratio | control-rate RMS |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {mode} | {samples} | {ct} | {conf} | {snr} | {noise} | {observed} | {accepted} | {ready} | {passed} | {rate} |".format(
                mode=row.get("mode", ""),
                samples=row.get("tracking_sample_count", 0),
                ct=_fmt(row.get("cross_track_abs_p95_m")),
                conf=_fmt(row.get("confidence_mean")),
                snr=_fmt(row.get("magnetic_snr_db_mean")),
                noise=_fmt(row.get("noise_magnitude_p95_nt")),
                observed=_fmt(row.get("prior_alignment_observed_ratio")),
                accepted=_fmt(row.get("prior_alignment_accepted_ratio")),
                ready=_fmt(row.get("industrial_ready_ratio")),
                passed=_fmt(row.get("industrial_acceptance_pass_ratio")),
                rate=_fmt(row.get("control_rate_rms_per_s")),
            )
        )
    lines.extend(
        [
            "",
            "## Provenance",
            "",
            "- Source experiment package: `real_experiments/mag_chain_noise_ros/`.",
            "- Default noise profile: `real_experiments/mag_chain_noise/data/noise_profile.json`.",
            "- Default measured records: `hardware_wrappers/fangkong_adc/raw_data/1780675809_291477.npz`, `hardware_wrappers/fangkong_adc/raw_data/1780676130_241387.npz`.",
            "- ROS entrypoint: `scripts/run_direction_a_decoupled_cable_sim.sh` with `AUV_MAG_NOISE_MODE`.",
            "- Summary table: `real_experiments/mag_chain_noise_ros/data/summary.csv`.",
            "",
            "## Thesis Anchors",
            "",
            "- Chapter 5 table: `tab:ch05-mag-chain-noise-ros`.",
            "- Chapter 5 figure: `fig:ch05-mag-chain-noise-ros`.",
            "- Thesis figure source: `docs/thesis/figures/experiments/mag_chain_noise_ros/_SOURCE.md`.",
            "",
            "## Boundaries",
            "",
            "- This is a semi-physical observation replay, not a full AUV wet test.",
            "- The Direction A decoupled loop is used as a ROS observation-injection gate, not as an industrial acceptance run; `industrial_ready` and `industrial_acceptance_pass` are not the conclusion metrics here.",
            "- The measured background is a dorm-room full-chain record with a strong 50 Hz environmental component; it is a stress input, not a metrology-grade laboratory noise floor.",
            "- Records shorter than the closed-loop run are explicitly looped in `measured_replay` mode.",
            "",
            "## Figures",
            "",
        ]
    )
    lines.extend(f"- `{path_item}`" for path_item in figure_paths)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fmt(value: Any) -> str:
    number = _float_or_nan(value)
    return f"{number:.4g}" if math.isfinite(number) else "nan"


def main() -> None:
    args = parse_args()
    run_index = _read_run_index(args.run_index)
    output_dir = _resolve(args.output_dir)
    data_dir = output_dir / "data"
    figure_dir = _resolve(args.figure_dir)
    rows: list[dict[str, Any]] = []
    for item in run_index:
        tracking_rows = _read_jsonl(Path(item.get("tracking_jsonl", "")))
        noise_rows = _read_jsonl(Path(item.get("noise_metadata_jsonl", "")))
        summary = {
            **item,
            **_summarize_tracking(tracking_rows, args.warmup_s),
            **_summarize_noise(noise_rows),
            **_setpoint_metrics(item.get("bag_mcap", "")),
        }
        rows.append(summary)

    data_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(data_dir / "summary.csv", rows)
    metrics = {
        "experiment_id": "mag_chain_noise_ros",
        "warmup_s": float(args.warmup_s),
        "run_count": len(rows),
        "runs": rows,
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(_json_safe(metrics), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    figure_paths = _plot_summary(rows, output_dir / "figures")
    figure_dir.mkdir(parents=True, exist_ok=True)
    copied_paths = []
    for path in figure_paths:
        target = figure_dir / path.name
        shutil.copy2(path, target)
        copied_paths.append(target)
    (figure_dir / "_SOURCE.md").write_text(
        "\n".join(
            [
                "# ADC-TMR measured replay ROS comparison figure source",
                "",
                "- Generated by `real_experiments/mag_chain_noise_ros/run.sh`.",
                "- Metrics source: `real_experiments/mag_chain_noise_ros/metrics.json`.",
                "- Summary source: `real_experiments/mag_chain_noise_ros/data/summary.csv`.",
                "- Noise enters only `/auv/sensors/magnetic`; truth geometry is unchanged.",
                "- Modes: `none`, `covariance_gaussian`, `measured_replay`.",
                "- Thesis anchors: `tab:ch05-mag-chain-noise-ros`, `fig:ch05-mag-chain-noise-ros`.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _write_report(output_dir / "report.md", rows, copied_paths)
    print(f"[mag-chain-noise-ros] wrote {output_dir / 'metrics.json'}")
    print(f"[mag-chain-noise-ros] wrote {data_dir / 'summary.csv'}")
    for path in copied_paths:
        print(f"[mag-chain-noise-ros] figure {path}")


if __name__ == "__main__":
    main()
