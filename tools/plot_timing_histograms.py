#!/usr/bin/env python3
"""Plot PC104 packet timing and MPC solver wall-time histograms."""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np


DEFAULT_PC104_BUNDLE = Path(
    "results/control/pc104_udp_timing_hostrelay_sockreturn_zero_30s_20260810_221904"
)
DEFAULT_MPC_BUNDLE = Path(
    "results/control/r22_native_closed_loop_full_3seed_60s_h8_20260810"
)


@dataclass(frozen=True)
class SeriesSummary:
    name: str
    sample_count: int
    mean_ms: float
    std_ms: float
    p50_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate histograms for the raw PC104 UDP timing samples and "
            "per-step MPC solver wall-time samples."
        )
    )
    parser.add_argument("--pc104-bundle", type=Path, default=DEFAULT_PC104_BUNDLE)
    parser.add_argument("--mpc-bundle", type=Path, default=DEFAULT_MPC_BUNDLE)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def finite(values: Iterable[float]) -> np.ndarray:
    array = np.asarray(list(values), dtype=float)
    return array[np.isfinite(array)]


def to_float(value: str | None) -> float:
    if value is None or value == "":
        return float("nan")
    try:
        return float(value)
    except ValueError:
        return float("nan")


def quantile(values: np.ndarray, q: float) -> float:
    if values.size == 0:
        return float("nan")
    return float(np.quantile(values, q))


def summarize(name: str, values_ms: np.ndarray) -> SeriesSummary:
    values_ms = finite(values_ms)
    return SeriesSummary(
        name=name,
        sample_count=int(values_ms.size),
        mean_ms=float(np.mean(values_ms)) if values_ms.size else float("nan"),
        std_ms=float(np.std(values_ms)) if values_ms.size else float("nan"),
        p50_ms=quantile(values_ms, 0.50),
        p90_ms=quantile(values_ms, 0.90),
        p95_ms=quantile(values_ms, 0.95),
        p99_ms=quantile(values_ms, 0.99),
        max_ms=float(np.max(values_ms)) if values_ms.size else float("nan"),
    )


def read_pc104_samples(bundle: Path) -> dict[str, np.ndarray]:
    path = bundle / "udp_timing_samples.csv"
    downlink_intervals: list[float] = []
    uplink_intervals: list[float] = []
    uplink_frame_gaps: list[float] = []
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            event_type = row.get("event_type", "")
            if event_type == "downlink_send":
                downlink_intervals.append(to_float(row.get("send_interval_ms")))
            elif event_type == "uplink_recv":
                uplink_intervals.append(to_float(row.get("uplink_interarrival_ms")))
                uplink_frame_gaps.append(to_float(row.get("uplink_frame_gap")))
    return {
        "pc104_downlink_send_interval_ms": finite(downlink_intervals),
        "pc104_uplink_interarrival_ms": finite(uplink_intervals),
        "pc104_uplink_frame_gap": finite(uplink_frame_gaps),
    }


def infer_mpc_mode(path: Path) -> str:
    stem = path.stem
    if stem.endswith("__ua"):
        return "ua"
    if stem.endswith("__baseline"):
        return "baseline"
    return "unknown"


def read_mpc_solver_samples(bundle: Path) -> tuple[dict[str, np.ndarray], int]:
    trace_dir = bundle / "traces"
    values_by_mode: dict[str, list[float]] = {"baseline": [], "ua": [], "all": []}
    trace_count = 0
    for path in sorted(trace_dir.glob("*.csv")):
        mode = infer_mpc_mode(path)
        trace_count += 1
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            if "solver_wall_time_ms" not in (reader.fieldnames or []):
                continue
            for row in reader:
                value = to_float(row.get("solver_wall_time_ms"))
                if math.isfinite(value):
                    values_by_mode.setdefault(mode, []).append(value)
                    values_by_mode["all"].append(value)
    return {name: finite(values) for name, values in values_by_mode.items()}, trace_count


def write_summary_csv(path: Path, summaries: list[SeriesSummary]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "name",
                "sample_count",
                "mean_ms",
                "std_ms",
                "p50_ms",
                "p90_ms",
                "p95_ms",
                "p99_ms",
                "max_ms",
            ],
        )
        writer.writeheader()
        for item in summaries:
            writer.writerow(item.__dict__)


def hist_edges(values: np.ndarray, bin_count: int = 30) -> np.ndarray:
    values = finite(values)
    if values.size == 0:
        return np.linspace(0.0, 1.0, bin_count + 1)
    lo = max(0.0, float(np.min(values)))
    hi = float(np.max(values))
    if hi <= lo:
        hi = lo + 1.0
    return np.linspace(lo, hi, bin_count + 1)


def plot_pc104(series: dict[str, np.ndarray], output_dir: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.0), constrained_layout=True)
    configs = [
        ("pc104_uplink_interarrival_ms", "PC104 $AUV uplink inter-arrival", "#228be6"),
        ("pc104_downlink_send_interval_ms", "Zero-thrust $CKTH send interval", "#20c997"),
    ]
    for axis, (key, title, color) in zip(axes, configs, strict=True):
        values = series[key]
        axis.hist(values, bins=hist_edges(values), color=color, alpha=0.82)
        axis.axvline(np.quantile(values, 0.95), color="#f59f00", linestyle="--", linewidth=1.5, label="p95")
        axis.set_title(title)
        axis.set_xlabel("interval (ms)")
        axis.set_ylabel("count")
        axis.grid(True, alpha=0.25)
        axis.legend()
    fig.suptitle("PC104 host-relay packet timing, 30 s")
    fig.savefig(output_dir / "pc104_packet_interval_histograms.png", dpi=180)
    fig.savefig(output_dir / "pc104_packet_interval_histograms.pdf")
    plt.close(fig)


def plot_mpc(series: dict[str, np.ndarray], output_dir: Path) -> None:
    fig, axis = plt.subplots(figsize=(8.5, 4.8), constrained_layout=True)
    colors = {"baseline": "#228be6", "ua": "#845ef7"}
    all_values = series.get("all", np.asarray([], dtype=float))
    edges = hist_edges(all_values, bin_count=36)
    for mode in ("baseline", "ua"):
        values = series.get(mode, np.asarray([], dtype=float))
        if values.size == 0:
            continue
        axis.hist(values, bins=edges, alpha=0.58, label=f"{mode} (n={values.size})", color=colors[mode])
        axis.axvline(np.quantile(values, 0.95), color=colors[mode], linestyle="--", linewidth=1.4)
    axis.axvline(50.0, color="#fa5252", linestyle="-.", linewidth=1.6, label="20 Hz budget 50 ms")
    axis.axvline(100.0, color="#f59f00", linestyle=":", linewidth=1.6, label="10 Hz budget 100 ms")
    axis.set_title("R22 native closed-loop MPC solver wall time")
    axis.set_xlabel("solver wall time (ms)")
    axis.set_ylabel("control-step count")
    axis.grid(True, alpha=0.25)
    axis.legend()
    fig.savefig(output_dir / "mpc_solver_wall_time_histogram.png", dpi=180)
    fig.savefig(output_dir / "mpc_solver_wall_time_histogram.pdf")
    plt.close(fig)


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    pc104_series = read_pc104_samples(args.pc104_bundle)
    mpc_series, trace_count = read_mpc_solver_samples(args.mpc_bundle)
    plot_pc104(pc104_series, output_dir)
    plot_mpc(mpc_series, output_dir)

    summaries = [
        summarize("pc104_uplink_interarrival_ms", pc104_series["pc104_uplink_interarrival_ms"]),
        summarize("pc104_downlink_send_interval_ms", pc104_series["pc104_downlink_send_interval_ms"]),
        summarize("mpc_solver_wall_time_all_ms", mpc_series["all"]),
        summarize("mpc_solver_wall_time_baseline_ms", mpc_series["baseline"]),
        summarize("mpc_solver_wall_time_ua_ms", mpc_series["ua"]),
    ]
    write_summary_csv(output_dir / "timing_histogram_summary.csv", summaries)

    metadata = {
        "pc104_bundle": str(args.pc104_bundle),
        "pc104_raw_samples_csv": str(args.pc104_bundle / "udp_timing_samples.csv"),
        "mpc_bundle": str(args.mpc_bundle),
        "mpc_trace_count": trace_count,
        "mpc_trace_glob": str(args.mpc_bundle / "traces" / "*.csv"),
        "summary_csv": str(output_dir / "timing_histogram_summary.csv"),
        "plots": [
            str(output_dir / "pc104_packet_interval_histograms.png"),
            str(output_dir / "pc104_packet_interval_histograms.pdf"),
            str(output_dir / "mpc_solver_wall_time_histogram.png"),
            str(output_dir / "mpc_solver_wall_time_histogram.pdf"),
        ],
        "one_way_latency_claim": False,
        "round_trip_latency_claim": False,
    }
    (output_dir / "timing_histogram_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n"
    )

    lines = [
        "# PC104 and MPC Timing Histograms",
        "",
        f"- PC104 raw packet samples: `{args.pc104_bundle / 'udp_timing_samples.csv'}`.",
        f"- MPC raw solver traces: `{args.mpc_bundle / 'traces/*.csv'}` (`{trace_count}` files).",
        f"- PC104 uplink p95 inter-arrival: `{summaries[0].p95_ms:.3f} ms`.",
        f"- PC104 downlink p95 send interval: `{summaries[1].p95_ms:.3f} ms`.",
        f"- MPC all-sample p95 wall time: `{summaries[2].p95_ms:.3f} ms`.",
        "",
        "Boundary: these histograms use host/container arrival timestamps and solver wall-clock durations. They do not by themselves provide one-way Jetson--PC104 physical latency.",
    ]
    (output_dir / "report.md").write_text("\n".join(lines) + "\n")
    print(
        "[timing-hist] "
        f"pc104_n={summaries[0].sample_count} mpc_n={summaries[2].sample_count} "
        f"mpc_p95={summaries[2].p95_ms:.3f}ms -> {output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
