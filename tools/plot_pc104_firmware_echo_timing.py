#!/usr/bin/env python3
"""Plot packet cadence and firmware-echo timing from a PC104 timing bundle."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import thesis_plot_style as tps


@dataclass(frozen=True)
class SeriesSummary:
    name: str
    sample_count: int
    mean_ms: float
    std_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    p999_ms: float
    max_ms: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def to_float(value: str | None) -> float:
    if value is None or not str(value).strip():
        return float("nan")
    try:
        return float(value)
    except ValueError:
        return float("nan")


def finite(values: Iterable[float]) -> np.ndarray:
    array = np.asarray(list(values), dtype=float)
    return array[np.isfinite(array)]


def summarize(name: str, values: np.ndarray) -> SeriesSummary:
    values = finite(values)
    if values.size == 0:
        return SeriesSummary(name, 0, *(float("nan"),) * 7)
    return SeriesSummary(
        name=name,
        sample_count=int(values.size),
        mean_ms=float(np.mean(values)),
        std_ms=float(np.std(values)),
        p50_ms=float(np.quantile(values, 0.50)),
        p95_ms=float(np.quantile(values, 0.95)),
        p99_ms=float(np.quantile(values, 0.99)),
        p999_ms=float(np.quantile(values, 0.999)),
        max_ms=float(np.max(values)),
    )


def read_samples(path: Path) -> tuple[dict[str, np.ndarray], dict[str, int]]:
    series: dict[str, list[float]] = {
        "elapsed_s": [],
        "uplink_elapsed_s": [],
        "pc104_uptime_ms": [],
        "downlink_send_interval_ms": [],
        "uplink_interarrival_ms": [],
        "pc104_uptime_delta_ms": [],
        "first_echo_rtt_ms": [],
        "receive_to_first_pack_ms": [],
        "echo_event_interval_ms": [],
        "echo_observation_age_ms": [],
    }
    counts = {
        "downlink_count": 0,
        "uplink_count": 0,
        "parse_error_count": 0,
        "duplicate_uplink_count": 0,
        "forward_gap_count": 0,
        "estimated_lost_frames": 0,
        "valid_pc104_time_count": 0,
        "valid_echo_uplink_count": 0,
        "unique_echo_event_count": 0,
        "paired_echo_event_count": 0,
        "valid_dvl_time_count": 0,
    }
    seen_echo: set[tuple[str, str]] = set()
    previous_echo_rx_uptime_ms: float | None = None

    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            event_type = row.get("event_type", "")
            if event_type == "downlink_send":
                counts["downlink_count"] += 1
                series["downlink_send_interval_ms"].append(
                    to_float(row.get("send_interval_ms"))
                )
                continue
            if event_type == "uplink_parse_error":
                counts["parse_error_count"] += 1
                continue
            if event_type != "uplink_recv" or row.get("parse_ok") != "1":
                continue

            counts["uplink_count"] += 1
            series["uplink_interarrival_ms"].append(
                to_float(row.get("uplink_interarrival_ms"))
            )
            series["pc104_uptime_delta_ms"].append(
                to_float(row.get("pc104_uptime_delta_ms"))
            )
            gap = to_float(row.get("uplink_frame_gap"))
            if math.isfinite(gap):
                if int(gap) == 0:
                    counts["duplicate_uplink_count"] += 1
                elif int(gap) > 1:
                    counts["forward_gap_count"] += 1
                    counts["estimated_lost_frames"] += int(gap) - 1
            if row.get("pc104_time_valid") == "1":
                counts["valid_pc104_time_count"] += 1
                series["uplink_elapsed_s"].append(to_float(row.get("elapsed_s")))
                series["pc104_uptime_ms"].append(to_float(row.get("pc104_uptime_ms")))
            if row.get("pc104_dvl_bi_time_valid") == "1":
                counts["valid_dvl_time_count"] += 1
            if row.get("pc104_downlink_echo_valid") != "1":
                continue

            counts["valid_echo_uplink_count"] += 1
            series["echo_observation_age_ms"].append(
                to_float(row.get("pc104_downlink_echo_age_ms"))
            )
            echo_key = (
                row.get("pc104_downlink_echo_frame", ""),
                row.get("pc104_downlink_recv_uptime_ms", ""),
            )
            explicit_first = row.get("pc104_downlink_echo_event_first")
            is_first = explicit_first == "1" if explicit_first not in (None, "") else echo_key not in seen_echo
            if not is_first:
                continue

            seen_echo.add(echo_key)
            counts["unique_echo_event_count"] += 1
            rtt_ms = to_float(row.get("downlink_echo_rtt_ms"))
            receive_to_pack_ms = to_float(row.get("pc104_downlink_recv_to_pack_ms"))
            explicit_paired = row.get("pc104_downlink_echo_event_paired")
            is_paired = (
                explicit_paired == "1"
                if explicit_paired not in (None, "")
                else math.isfinite(rtt_ms) and math.isfinite(receive_to_pack_ms)
            )
            if not is_paired:
                continue

            counts["paired_echo_event_count"] += 1
            series["elapsed_s"].append(to_float(row.get("elapsed_s")))
            series["first_echo_rtt_ms"].append(rtt_ms)
            series["receive_to_first_pack_ms"].append(receive_to_pack_ms)
            rx_uptime_ms = to_float(row.get("pc104_downlink_recv_uptime_ms"))
            if previous_echo_rx_uptime_ms is not None and math.isfinite(rx_uptime_ms):
                delta_ms = rx_uptime_ms - previous_echo_rx_uptime_ms
                if delta_ms >= 0.0:
                    series["echo_event_interval_ms"].append(delta_ms)
            if math.isfinite(rx_uptime_ms):
                previous_echo_rx_uptime_ms = rx_uptime_ms

    return {name: finite(values) for name, values in series.items()}, counts


def fit_pc104_clock(series: dict[str, np.ndarray]) -> dict[str, float | int]:
    host_s = finite(series["uplink_elapsed_s"])
    pc104_ms = finite(series["pc104_uptime_ms"])
    count = min(host_s.size, pc104_ms.size)
    if count < 2:
        return {
            "sample_count": int(count),
            "pc104_seconds_per_host_second": float("nan"),
            "rate_offset_ppm": float("nan"),
            "absolute_residual_p95_ms": float("nan"),
            "absolute_residual_p99_ms": float("nan"),
            "absolute_residual_max_ms": float("nan"),
        }
    host_s = host_s[:count] - host_s[0]
    pc104_s = pc104_ms[:count] / 1000.0
    pc104_s = pc104_s - pc104_s[0]
    host_per_pc104, intercept = np.polyfit(pc104_s, host_s, 1)
    predicted_host_s = host_per_pc104 * pc104_s + intercept
    absolute_residual_ms = np.abs(host_s - predicted_host_s) * 1000.0
    pc104_per_host = 1.0 / float(host_per_pc104)
    return {
        "sample_count": int(count),
        "pc104_seconds_per_host_second": pc104_per_host,
        "rate_offset_ppm": (pc104_per_host - 1.0) * 1.0e6,
        "absolute_residual_p95_ms": float(np.quantile(absolute_residual_ms, 0.95)),
        "absolute_residual_p99_ms": float(np.quantile(absolute_residual_ms, 0.99)),
        "absolute_residual_max_ms": float(np.max(absolute_residual_ms)),
    }


def histogram(axis, values: np.ndarray, *, title: str, xlabel: str, index: int) -> None:
    values = finite(values)
    style = tps.series_style(index)
    if values.size:
        bin_count = min(45, max(12, int(round(math.sqrt(values.size)))))
        axis.hist(values, bins=bin_count, alpha=0.72, **style)
        p95 = float(np.quantile(values, 0.95))
        axis.axvline(
            p95,
            color=tps.ACCENT_COLORS[(index + 3) % len(tps.ACCENT_COLORS)],
            linestyle="--",
            linewidth=1.6,
            label=f"p95={p95:.2f} ms",
        )
        axis.legend()
    axis.set_title(title)
    axis.set_xlabel(xlabel)
    axis.set_ylabel("样本数")


def plot_packet_cadence(series: dict[str, np.ndarray], output_dir: Path) -> list[Path]:
    fig, axes = plt.subplots(1, 3, figsize=(12.8, 3.8), constrained_layout=True)
    histogram(
        axes[0],
        series["downlink_send_interval_ms"],
        title="$CKTH$ 安全下行发送间隔",
        xlabel="间隔 / ms",
        index=0,
    )
    histogram(
        axes[1],
        series["uplink_interarrival_ms"],
        title="$AUV$ 上行到达间隔",
        xlabel="间隔 / ms",
        index=1,
    )
    histogram(
        axes[2],
        series["pc104_uptime_delta_ms"],
        title="PC104 上行打包时间增量",
        xlabel="增量 / ms",
        index=2,
    )
    fig.suptitle("PC104/VxWorks 双脑 UDP 周期统计")
    paths = tps.save_figure(fig, output_dir / "pc104_packet_cadence")
    plt.close(fig)
    return paths


def plot_firmware_echo(series: dict[str, np.ndarray], output_dir: Path) -> list[Path]:
    fig, axes = plt.subplots(2, 2, figsize=(10.8, 7.2), constrained_layout=True)
    histogram(
        axes[0, 0],
        series["first_echo_rtt_ms"],
        title="唯一接收事件的首次回显 RTT",
        xlabel="RTT / ms",
        index=0,
    )
    histogram(
        axes[0, 1],
        series["receive_to_first_pack_ms"],
        title="PC104 接收到首次打包",
        xlabel="内部处理时间 / ms",
        index=1,
    )
    histogram(
        axes[1, 0],
        series["echo_event_interval_ms"],
        title="PC104 已记录下行事件间隔",
        xlabel="事件间隔 / ms",
        index=2,
    )

    elapsed = series["elapsed_s"]
    rtt = series["first_echo_rtt_ms"]
    axis = axes[1, 1]
    if elapsed.size and rtt.size:
        style = tps.line_style(0)
        style["marker"] = "."
        style["markersize"] = 3
        axis.plot(elapsed, rtt, label="首次回显 RTT", **style)
        p95 = float(np.quantile(rtt, 0.95))
        axis.axhline(
            p95,
            color=tps.ACCENT_COLORS[3],
            linestyle="--",
            linewidth=1.5,
            label=f"p95={p95:.2f} ms",
        )
        axis.legend()
    axis.set_title("首次回显 RTT 随实验时间变化")
    axis.set_xlabel("实验时间 / s")
    axis.set_ylabel("RTT / ms")

    fig.suptitle("PC104 固件接收时间戳回显统计")
    paths = tps.save_figure(fig, output_dir / "pc104_firmware_echo_timing")
    plt.close(fig)
    return paths


def write_outputs(
    output_dir: Path,
    bundle: Path,
    series: dict[str, np.ndarray],
    counts: dict[str, int],
    plot_paths: list[Path],
) -> None:
    summaries = [
        summarize("downlink_send_interval_ms", series["downlink_send_interval_ms"]),
        summarize("uplink_interarrival_ms", series["uplink_interarrival_ms"]),
        summarize("pc104_uptime_delta_ms", series["pc104_uptime_delta_ms"]),
        summarize("first_echo_rtt_ms", series["first_echo_rtt_ms"]),
        summarize("receive_to_first_pack_ms", series["receive_to_first_pack_ms"]),
        summarize("echo_event_interval_ms", series["echo_event_interval_ms"]),
    ]
    summary_csv = output_dir / "firmware_echo_summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(summaries[0]).keys()))
        writer.writeheader()
        for item in summaries:
            writer.writerow(asdict(item))

    clock_fit = fit_pc104_clock(series)
    payload = {
        "source_bundle": str(bundle),
        "source_samples": str(bundle / "udp_timing_samples.csv"),
        "counts": counts,
        "series": {item.name: asdict(item) for item in summaries},
        "pc104_to_host_clock_fit": clock_fit,
        "plots": [str(path) for path in plot_paths],
        "firmware_echo_application_rtt_claim": summaries[3].sample_count > 0,
        "one_way_latency_claim": False,
        "strict_physical_round_trip_claim": False,
        "boundary": (
            "First-echo RTT includes container scheduling, Docker Desktop, host "
            "relay, bidirectional Ethernet, firmware receive, and periodic uplink "
            "scheduling. It is not a synchronized one-way physical latency."
        ),
    }
    (output_dir / "firmware_echo_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    first_rtt = summaries[3]
    recv_to_pack = summaries[4]
    lines = [
        "# PC104 firmware echo timing",
        "",
        f"- Source bundle: `{bundle}`",
        f"- Downlink/uplink frames: `{counts['downlink_count']}`/`{counts['uplink_count']}`",
        f"- Parse errors: `{counts['parse_error_count']}`",
        f"- Forward sequence gaps / estimated lost uplinks: "
        f"`{counts['forward_gap_count']}`/`{counts['estimated_lost_frames']}`",
        f"- Unique/paired firmware receive events: "
        f"`{counts['unique_echo_event_count']}`/`{counts['paired_echo_event_count']}`",
        f"- First-echo RTT p50/p95/p99/p99.9: `{first_rtt.p50_ms:.3f}`/"
        f"`{first_rtt.p95_ms:.3f}`/`{first_rtt.p99_ms:.3f}`/"
        f"`{first_rtt.p999_ms:.3f} ms`",
        f"- PC104 receive-to-first-pack p50/p95/p99/p99.9: "
        f"`{recv_to_pack.p50_ms:.3f}`/`{recv_to_pack.p95_ms:.3f}`/"
        f"`{recv_to_pack.p99_ms:.3f}`/`{recv_to_pack.p999_ms:.3f} ms`",
        f"- Valid DVL device timestamps: `{counts['valid_dvl_time_count']}`",
        f"- PC104 relative clock rate offset: `{clock_fit['rate_offset_ppm']:.3f} ppm`",
        f"- Clock-fit absolute residual p95: "
        f"`{clock_fit['absolute_residual_p95_ms']:.3f} ms`",
        "",
        "Boundary: first-echo RTT is an application-path round trip. It is not "
        "a synchronized one-way physical latency.",
        "",
    ]
    (output_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    bundle = args.bundle.resolve()
    samples_path = bundle / "udp_timing_samples.csv"
    if not samples_path.is_file():
        raise SystemExit(f"missing timing samples: {samples_path}")
    output_dir = (args.output_dir or (bundle / "figures")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    tps.apply_thesis_style(base_font_size=11)
    series, counts = read_samples(samples_path)
    plot_paths = [
        *plot_packet_cadence(series, output_dir),
        *plot_firmware_echo(series, output_dir),
    ]
    write_outputs(output_dir, bundle, series, counts, plot_paths)
    print(
        "[pc104-echo-plot] "
        f"uplink={counts['uplink_count']} paired_echo={counts['paired_echo_event_count']} "
        f"-> {output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
