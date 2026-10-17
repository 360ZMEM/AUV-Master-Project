#!/usr/bin/env python3
"""Capture one live ROS 2 cross-scan and render FWHM/truth evidence."""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import MagneticField
from std_msgs.msg import String

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))
from tools import thesis_plot_style as tps  # noqa: E402


class LiveFwhmCapture(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__("fwhm_live_evidence_capture")
        self.args = args
        self.started = time.monotonic()
        self.latest_xy: np.ndarray | None = None
        self.latest_phase = "WAITING"
        self.latest_diag: dict = {}
        self.final_diag: dict | None = None
        self.track_seen_at: float | None = None
        self.samples: list[dict[str, float]] = []
        self.quality: list[dict[str, float | str]] = []
        self.create_subscription(Odometry, "/auv/state/filtered", self._on_odom, 50)
        self.create_subscription(MagneticField, "/auv/sensors/magnetic", self._on_mag, 100)
        self.create_subscription(String, "/auv/cable/tracking", self._on_tracking, 20)

    def _elapsed(self) -> float:
        return time.monotonic() - self.started

    def _on_odom(self, msg: Odometry) -> None:
        self.latest_xy = np.asarray(
            [msg.pose.pose.position.x, msg.pose.pose.position.y], dtype=float
        )

    def _scan_geometry(self) -> tuple[np.ndarray, np.ndarray] | None:
        center = self.latest_diag.get("cross_scan_center_xy_m")
        points = self.latest_diag.get("cross_scan_waypoints_xy_m")
        if not isinstance(center, list) or len(center) < 2:
            return None
        if not isinstance(points, list) or len(points) < 2:
            return None
        first = np.asarray(points[0][:2], dtype=float)
        second = np.asarray(points[1][:2], dtype=float)
        direction = second - first
        norm = float(np.linalg.norm(direction))
        if norm <= 1.0e-9:
            return None
        return np.asarray(center[:2], dtype=float), direction / norm

    def _on_mag(self, msg: MagneticField) -> None:
        if self.latest_phase.lower() != "confirm" or self.latest_xy is None:
            return
        geometry = self._scan_geometry()
        if geometry is None:
            return
        center, normal = geometry
        vector_t = np.asarray(
            [msg.magnetic_field.x, msg.magnetic_field.y, msg.magnetic_field.z], dtype=float
        )
        if not np.all(np.isfinite(vector_t)):
            return
        self.samples.append(
            {
                "elapsed_s": self._elapsed(),
                "north_m": float(self.latest_xy[0]),
                "east_m": float(self.latest_xy[1]),
                "scan_x_m": float(np.dot(self.latest_xy - center, normal)),
                "magnetic_envelope_nt": float(np.linalg.norm(vector_t) * 1.0e9),
                "center_north_m": float(center[0]),
                "center_east_m": float(center[1]),
                "normal_north": float(normal[0]),
                "normal_east": float(normal[1]),
            }
        )

    @staticmethod
    def _number(value, default=float("nan")) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def _on_tracking(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except (TypeError, ValueError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        diag = payload.get("diagnostics")
        diag = diag if isinstance(diag, dict) else {}
        self.latest_diag = diag
        self.latest_phase = str(diag.get("mission_phase", payload.get("mode", "WAITING")))
        self.quality.append(
            {
                "elapsed_s": self._elapsed(),
                "phase": self.latest_phase,
                "validity": self._number(diag.get("fwhm_validity_score")),
                "confidence": self._number(diag.get("fwhm_confidence")),
                "coverage": self._number(diag.get("fwhm_coverage_score")),
            }
        )
        if bool(diag.get("fwhm_valid", False)):
            self.final_diag = dict(diag)
        if self.latest_phase.lower() == "track" and self.track_seen_at is None:
            self.track_seen_at = time.monotonic()

    def complete(self) -> bool:
        if self._elapsed() >= self.args.duration:
            return True
        return self.track_seen_at is not None and time.monotonic() - self.track_seen_at >= 3.0


def _save_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _truth_profile_nt(scan_x: np.ndarray, true_center_x: float, z_m: float, current_a: float) -> np.ndarray:
    mu0 = 4.0e-7 * math.pi
    radius = np.sqrt((scan_x - true_center_x) ** 2 + z_m**2)
    return mu0 * abs(current_a) / (2.0 * math.pi * radius) * 1.0e9


def render(output_dir: Path, capture: LiveFwhmCapture) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = capture.samples
    diag = capture.final_diag or capture.latest_diag
    if len(samples) < 10 or not bool(diag.get("fwhm_valid", False)):
        raise RuntimeError(
            f"insufficient live FWHM evidence: samples={len(samples)} valid={diag.get('fwhm_valid')}"
        )

    _save_csv(output_dir / "fwhm_live_samples.csv", samples)
    _save_csv(output_dir / "fwhm_quality_timeline.csv", capture.quality)

    x = np.asarray([row["scan_x_m"] for row in samples], dtype=float)
    b = np.asarray([row["magnetic_envelope_nt"] for row in samples], dtype=float)
    order = np.argsort(x)
    x, b = x[order], b[order]
    center = np.asarray([samples[-1]["center_north_m"], samples[-1]["center_east_m"]])
    normal = np.asarray([samples[-1]["normal_north"], samples[-1]["normal_east"]])
    cable_point = np.asarray([center[0], capture.args.true_cable_y_m])
    true_center_x = float(np.dot(cable_point - center, normal))
    grid = np.linspace(float(np.min(x)), float(np.max(x)), 500)
    truth = _truth_profile_nt(
        grid, true_center_x, capture.args.vertical_separation_m, capture.args.current_a
    )

    left = float(diag["fwhm_left_x_m"])
    right = float(diag["fwhm_right_x_m"])
    peak = float(diag["fwhm_peak_x_m"])
    half = float(diag["fwhm_half_level_nt"])
    width = float(diag["fwhm_width_m"])
    vertical_est = float(diag["fwhm_vertical_separation_m"])
    burial_est = float(diag["fwhm_burial_depth_m"])
    burial_sigma = float(diag["fwhm_burial_depth_sigma_m"])

    tps.apply_thesis_style(layout="full")
    fig, axes = plt.subplots(2, 2, figsize=tps.figure_size("full", height=6.3), constrained_layout=True)
    ax = axes[0, 0]
    stride = max(1, len(x) // 500)
    ax.scatter(x[::stride], b[::stride], s=8, color=tps.PROPOSED, alpha=0.58, label="本次巡检实测样本")
    ax.plot(grid, truth, color=tps.REFERENCE, lw=1.6, label="仿真真值磁场")
    ax.axhline(half, color=tps.WARNING, ls="--", lw=1.2, label="背景修正半高")
    ax.axvline(left, color=tps.BASELINE_2, ls=":", lw=1.2)
    ax.axvline(right, color=tps.BASELINE_2, ls=":", lw=1.2)
    ax.axvline(peak, color=tps.PROPOSED, ls="-.", lw=1.0, label="实测峰值位置")
    ax.annotate(f"FWHM = {width:.3f} m", xy=((left + right) / 2.0, half), xytext=(0, 14), textcoords="offset points", ha="center")
    ax.set_xlabel("横扫法向坐标 (m)"); ax.set_ylabel("磁场包络 (nT)")
    ax.set_title("空间磁场剖面与双侧半高交点"); ax.legend(loc="best", fontsize=7)

    ax = axes[0, 1]
    names = ["垂直距离", "埋深"]
    truth_values = [capture.args.vertical_separation_m, capture.args.true_burial_m]
    estimate_values = [vertical_est, burial_est]
    idx = np.arange(2); bar_w = 0.34
    ax.bar(idx - bar_w / 2, truth_values, bar_w, color=tps.REFERENCE, label="真值")
    ax.bar(idx + bar_w / 2, estimate_values, bar_w, color=tps.PROPOSED, label="FWHM 估计")
    ax.errorbar(1 + bar_w / 2, burial_est, yerr=burial_sigma, color=tps.WARNING, capsize=4, fmt="none", label="埋深 1σ")
    ax.set_xticks(idx); ax.set_xticklabels(names); ax.set_ylabel("距离 (m)")
    ax.set_title("几何真值与反演结果")
    ax.set_ylim(0.0, max(truth_values + estimate_values) * 1.18)
    ax.text(0, max(truth_values[0], estimate_values[0]) + 0.12, f"误差 {vertical_est-truth_values[0]:+.4f} m", ha="center")
    ax.text(1, max(truth_values[1], estimate_values[1]) + burial_sigma + 0.08, f"误差 {burial_est-truth_values[1]:+.4f} m", ha="center")
    ax.legend(loc="best", fontsize=7)

    ax = axes[1, 0]
    q_t = np.asarray([float(row["elapsed_s"]) for row in capture.quality])
    for key, label, index in (("validity", "有效性", 0), ("confidence", "FWHM 置信度", 1), ("coverage", "覆盖率", 2)):
        values = np.asarray([float(row[key]) for row in capture.quality])
        finite = np.isfinite(values)
        if np.any(finite):
            ax.plot(q_t[finite], values[finite], label=label, **tps.line_style(index))
    ax.axhline(0.55, color=tps.WARNING, ls="--", lw=1.1, label="发布阈值")
    ax.set_ylim(-0.03, 1.05); ax.set_xlabel("任务时间 (s)"); ax.set_ylabel("评分 / 覆盖率")
    ax.set_title("质量门控只解释是否可发布"); ax.legend(loc="lower right", fontsize=7)

    ax = axes[1, 1]
    metrics = [float(diag["fwhm_validity_score"]), float(diag["fwhm_confidence"]), float(diag["fwhm_coverage_score"]), float(diag["fwhm_symmetry_score"])]
    labels = ["有效性", "置信度", "覆盖率", "对称性"]
    bars = ax.bar(labels, metrics, color=[tps.PROPOSED, tps.BASELINE_1, tps.BASELINE_2, tps.NEUTRAL], edgecolor=tps.REFERENCE)
    ax.set_ylim(0, 1.08); ax.set_ylabel("0–1")
    ax.set_title("FWHM 结果的可审计质量分解")
    for bar, value in zip(bars, metrics):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.02, f"{value:.3f}", ha="center", fontsize=8)

    tps.add_panel_labels(axes)
    tps.save_figure(fig, output_dir / "fwhm_live_truth_comparison")
    plt.close(fig)

    summary = {
        "schema": "auv.fwhm_live_evidence.v1",
        "source": "live_ros2_topics",
        "sample_count": len(samples),
        "truth": {
            "cable_y_m": capture.args.true_cable_y_m,
            "vertical_separation_m": capture.args.vertical_separation_m,
            "altitude_m": capture.args.altitude_m,
            "burial_depth_m": capture.args.true_burial_m,
            "current_a": capture.args.current_a,
        },
        "estimate": {
            "fwhm_width_m": width,
            "vertical_separation_m": vertical_est,
            "burial_depth_m": burial_est,
            "burial_sigma_m": burial_sigma,
            "burial_error_m": burial_est - capture.args.true_burial_m,
            "validity": float(diag["fwhm_validity_score"]),
            "confidence": float(diag["fwhm_confidence"]),
            "coverage": float(diag["fwhm_coverage_score"]),
            "symmetry": float(diag["fwhm_symmetry_score"]),
            "reason_codes": list(diag.get("fwhm_reason_codes", [])),
        },
        "artifacts": {
            "samples_csv": "fwhm_live_samples.csv",
            "quality_csv": "fwhm_quality_timeline.csv",
            "figure_png": "fwhm_live_truth_comparison.png",
            "figure_pdf": "fwhm_live_truth_comparison.pdf",
        },
    }
    (output_dir / "fwhm_live_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--duration", type=float, default=180.0)
    parser.add_argument("--true-cable-y-m", type=float, default=0.0)
    parser.add_argument("--vertical-separation-m", type=float, default=4.0)
    parser.add_argument("--altitude-m", type=float, default=3.0)
    parser.add_argument("--true-burial-m", type=float, default=1.0)
    parser.add_argument("--current-a", type=float, default=600.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rclpy.init()
    node = LiveFwhmCapture(args)
    try:
        while rclpy.ok() and not node.complete():
            rclpy.spin_once(node, timeout_sec=0.1)
        summary = render(Path(args.output_dir), node)
        print(json.dumps(summary, ensure_ascii=False))
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
