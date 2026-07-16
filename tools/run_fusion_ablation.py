#!/usr/bin/env python3
"""Acoustic-magnetic cooperative fusion ablation (27 号文 §4, 组 C).

The largest remaining pure-simulation gap. No recorded bag carries a live
magnetic channel (every ``/auv/sensors/magnetic`` count is 0), so — exactly like
the thesis's existing R19 measured-noise replay — this ablation runs on a
synthetic yet reproducible cable-following trajectory and drives the *unmodified*
``algorithm/es_ekf.py`` through its ``correct_dvl`` / ``correct_depth`` /
``correct_mag`` hooks. Every arm shares one trajectory / seed / noise draw so the
comparison is fair by construction.

Ablation arms (aligned with 27 号文 §4 六配置):
  ①  imu_dvl              IMU + DVL + depth (no magnetic ranging, no sonar)
  ②  imu_dvl_mag          + magnetic weak-depth observation (default R)
  ③  imu_dvl_sonar        + sonar perception confidence (no magnetic channel)
  ④  imu_dvl_mag_sonar    magnetic + sonar (sonar confidence sharpens mag trust)
  ⑤  fusion_fixed_r       magnetic + sonar, fixed observation covariance
  ⑥  fusion_adaptive_r    magnetic + sonar, per-source adaptive covariance

Honesty contract (must stay in the thesis prose):
  * Sonar is a *perception-confidence input*, NOT an independent EKF measurement.
    It only modulates the magnetic observation's trust (R scaling) and the
    target-acquisition gate; arm ③ therefore has the same state RMSE as ① by
    construction — an expected structural result, not a bug.
  * The magnetic sub-chain uses the same linearised Biot-Savart depth-equivalent
    inversion as §3.3.3 / R19; burial inversion remains a straight-conductor,
    common-scale simplification (see 03 号文 §3.3).
  * The ``current`` scenario models a steady 0.3 m/s cross-flow *not* as extra
    measurement noise but through its physical consequence: an under-actuated AUV
    is pushed to a bounded lateral standoff, so the magnetic sensor's true slant
    distance exceeds the depth the depth-equivalent inversion assumes — a
    saturating *systematic* ranging bias. DVL is bottom-locked (measures
    ground-referenced velocity) and is therefore left unbiased by the flow.
  * Every arm reuses the shared ``experiment_contract`` bundle so ``metrics.csv`` /
    ``status.json`` / ``failure_events.csv`` stay consistent with the rest of the
    thesis experiment suite.

Usage:
    python3 tools/run_fusion_ablation.py --seeds 0,1,2 \
        --output-dir results/fusion_ablation/<ts>
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import sys

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from algorithm.es_ekf import ES_EKF, quat_to_rotmat  # noqa: E402
from tools.es_ekf_extrinsics_benchmark import (  # noqa: E402
    ekf_config,
    generate_trajectory,
    profile_by_name,
)
from tools.experiment_contract import finalize_bundle, initialize_bundle  # noqa: E402
from tools import thesis_plot_style as tps  # noqa: E402

MU0 = 4.0 * np.pi * 1e-7
CABLE_CURRENT_A = 500.0
MAG_MODEL_K = 2.0e-7 * CABLE_CURRENT_A  # |B| ~= K / distance  (matches R19)
SIGMA_MAG_BASE = 0.20  # magnetic depth-equivalent obs std (m), matches §3.3.3
SONAR_CONF_FLOOR = 0.15  # minimum trust so mag R never blows up unbounded
TARGET_ACQUIRE_CONF = 0.30  # perception gate for "target acquired"
MAG_ACQUIRE_SNR = 1.5  # magnetic magnitude / noise-std needed to hold lock


@dataclass(frozen=True)
class Arm:
    key: str
    label: str
    enable_mag: bool
    enable_sonar: bool
    adaptive_r_mode: str  # fixed | global | per_source


ARMS: tuple[Arm, ...] = (
    Arm("1_imu_dvl", "IMU+DVL", False, False, "global"),
    Arm("2_imu_dvl_mag", "+磁", True, False, "global"),
    Arm("3_imu_dvl_sonar", "+声呐", False, True, "global"),
    Arm("4_imu_dvl_mag_sonar", "+磁+声呐", True, True, "global"),
    Arm("5_fusion_fixed_r", "声磁融合(固定R)", True, True, "fixed"),
    Arm("6_fusion_adaptive_r", "声磁融合(自适应R)", True, True, "per_source"),
)


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    sonar_occlusion_windows_s: tuple[tuple[float, float], ...]
    mag_noise_scale: float  # multiplies baseline magnetic noise std
    description: str
    current_speed_mps: float = 0.0  # steady cross-flow; 0 = no current disturbance


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("baseline", "理想", (), 1.0, "清洁声磁通道"),
    Scenario("sonar_occlusion", "声呐短时不可见", ((25.0, 45.0),), 1.0,
             "侧扫声呐 20 s 遮挡，检验磁接力"),
    Scenario("mag_weak", "磁弱信号", (), 3.0, "磁背景噪声抬升 3x"),
    Scenario("em_noise", "电磁噪声增强", (), 6.0, "强电磁干扰下磁噪声抬升 6x"),
    Scenario("current", "横流扰动", (), 1.0,
             "0.3 m/s 近海横流致横向站位偏移，磁斜距系统性偏置", 0.3),
    Scenario("combined", "复合扰动", ((30.0, 50.0),), 4.0,
             "声呐遮挡 + 磁噪声抬升复合"),
)


def _crossflow_standoff_m(times: np.ndarray, current_speed_mps: float) -> np.ndarray:
    """欠驱动 AUV 在稳态横流下的横向站位偏移（m），随时间趋于饱和。

    欠驱动车体无横向推进器，只能靠航向偏置间接抵消横流，进入横流后先被推离电缆
    中心线，再由制导逐步收敛到一个\ *有界*\ 的巡航站位偏移。这里以一阶趋近 +
    小幅摆动近似该闭环残差：``d(t) = d_ss·(1-e^{-t/τ}) + 摆动``。站位偏移不进入
    DVL（底锁测地速、不受水流直接偏置），而是通过增大磁\ *斜距*\ 引入系统性观测偏置
    （见 run_arm 中 slant 计算），用于检验分源自适应 R 能否识别并压制该持续偏置。
    """
    if current_speed_mps <= 0.0:
        return np.zeros(times.size, dtype=float)
    d_ss = 8.0 * current_speed_mps  # 0.3 m/s -> 2.4 m 稳态站位偏移（近海欠驱动量级）
    tau = 20.0
    ramp = d_ss * (1.0 - np.exp(-times / tau))
    sway = 0.15 * d_ss * np.sin(0.08 * times)  # 缓慢摆动，非零均值偏置为主
    return ramp + sway


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--duration", type=float, default=120.0)
    parser.add_argument("--dt", type=float, default=0.05)
    parser.add_argument("--scenarios", default=",".join(s.key for s in SCENARIOS))
    parser.add_argument("--mag-noise-std", type=float, default=1.0e-7,
                        help="baseline magnetic field noise std in tesla. The "
                             "Biot-Savart field |B|=K/d is ~1e-5 T at 10 m depth "
                             "(K=2e-7*I, I=500 A), so a ~0.1 uT (1e-7 T) noise "
                             "floor yields ~0.1 m depth-equivalent error, matching "
                             "the §3.3.3 / R19 magnetic sub-chain scale.")
    parser.add_argument("--no-figure", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def _sonar_confidence(times: np.ndarray, windows: Sequence[tuple[float, float]]) -> np.ndarray:
    """Perception confidence in [0,1]: high normally, collapses during occlusion."""
    conf = np.full(times.size, 0.9, dtype=float)
    for start, end in windows:
        mask = (times >= start) & (times <= end)
        conf[mask] = 0.08
    return conf


def _mag_sigma_effective(base_sigma: float, sonar_conf: float, use_sonar: bool) -> float:
    """Acoustic-magnetic cooperation: sonar confidence sharpens magnetic trust.

    Higher perception confidence -> smaller effective magnetic R (more trust).
    When sonar is disabled the base sigma is used unchanged (honest: sonar is a
    confidence input, not a measurement).
    """
    if not use_sonar:
        return base_sigma
    trust = max(sonar_conf, SONAR_CONF_FLOOR)
    return base_sigma / trust


def run_arm(arm: Arm, scenario: Scenario, seed: int, duration_s: float, dt: float,
            base_mag_noise_std: float) -> dict[str, object]:
    traj = generate_trajectory(duration_s, dt)
    n = traj.times.size
    rng = np.random.default_rng(seed + 33100 + hash(scenario.key) % 997)

    acc_noise = rng.normal(0.0, 0.008, size=(n, 3))
    gyro_noise = rng.normal(0.0, 0.001, size=(n, 3))
    dvl_noise = rng.normal(0.0, 0.005, size=(n, 3))
    depth_noise = rng.normal(0.0, 0.01, size=n)
    mag_noise_std = base_mag_noise_std * scenario.mag_noise_scale
    mag_noise = rng.normal(0.0, mag_noise_std, size=(n, 3))

    sonar_conf = _sonar_confidence(traj.times, scenario.sonar_occlusion_windows_s)
    # 横流站位偏移（m），仅在 current_speed>0 的场景非零；驱动磁斜距系统性偏置。
    crossflow_standoff = _crossflow_standoff_m(traj.times, scenario.current_speed_mps)

    cfg = ekf_config(profile_by_name("none"), traj)
    cfg["feature_flags"] = {"enable_mag_correction": arm.enable_mag}
    cfg["sigma_mag_depth"] = SIGMA_MAG_BASE
    cfg["adaptive_r_mode"] = arm.adaptive_r_mode
    filt = ES_EKF(cfg)

    dvl_stride = max(1, int(round(0.2 / dt)))
    depth_stride = max(1, int(round(1.0 / dt)))
    mag_stride = max(1, int(round(0.5 / dt)))

    estimates = np.full((n, 3), np.nan, dtype=float)
    distance_err: list[float] = []
    acquired_flags: list[bool] = []

    for i, t_s in enumerate(traj.times):
        if i > 0:
            filt.predict(traj.acc_body[i] + acc_noise[i],
                         traj.gyro_body[i] + gyro_noise[i], dt)
        if i % dvl_stride == 0:
            r_nb = quat_to_rotmat(traj.q[i])
            v_body = r_nb.T @ traj.v[i]
            filt.correct_dvl_sensor(v_body + dvl_noise[i], gyro_body=traj.gyro_body[i])
        if i % depth_stride == 0:
            filt.correct_depth(float(-traj.p[i, 2] + depth_noise[i]))

        # Magnetic weak-depth observation (Biot-Savart depth-equivalent).
        # 横流下 AUV 横向站位偏移 d_lat 使磁传感到电缆的真实\ *斜距*\ 为
        # sqrt(depth^2 + d_lat^2) > depth；而深度等效反演假设电缆恰在正下方，
        # 故 |B| 偏小、反演距离偏大，形成随横流饱和的\ *系统性正偏置*\ 。
        true_depth = float(-traj.p[i, 2])
        d_lat = float(crossflow_standoff[i])
        true_slant = math.hypot(true_depth, d_lat)
        field_mag = MAG_MODEL_K / max(true_slant, 1e-6)
        measured_field = np.array([0.0, field_mag, 0.0]) + mag_noise[i]
        measured_norm = max(float(np.linalg.norm(measured_field)), 1e-12)
        mag_snr = field_mag / max(mag_noise_std, 1e-12)
        if arm.enable_mag and (i % mag_stride == 0):
            sigma_eff = _mag_sigma_effective(SIGMA_MAG_BASE, sonar_conf[i], arm.enable_sonar)
            filt.correct_mag(measured_field, sigma_mag_depth=sigma_eff)
            measured_distance = MAG_MODEL_K / measured_norm
            # 反演距离 vs 真实深度之差：既含高斯噪声，也含横流几何偏置。
            distance_err.append(measured_distance - true_depth)

        # Target acquisition gate: sonar perception OR strong magnetic lock.
        sonar_ok = arm.enable_sonar and sonar_conf[i] >= TARGET_ACQUIRE_CONF
        mag_ok = arm.enable_mag and mag_snr >= MAG_ACQUIRE_SNR
        acquired_flags.append(bool(sonar_ok or mag_ok))

        estimates[i] = filt.get_state()["p"].copy()

    # ---- metrics -----------------------------------------------------------
    valid = ~np.isnan(estimates[:, 0])
    err = estimates[valid] - traj.p[valid]
    rmse_xy = float(np.sqrt(np.mean(np.sum(err[:, :2] ** 2, axis=1)))) if err.size else float("nan")
    rmse_z = float(np.sqrt(np.mean(err[:, 2] ** 2))) if err.size else float("nan")
    rmse_3d = float(np.sqrt(np.mean(np.sum(err ** 2, axis=1)))) if err.size else float("nan")
    depth_equiv_err = (float(np.sqrt(np.mean(np.square(distance_err))))
                       if distance_err else float("nan"))
    # 磁反演距离的\ *有符号*\ 偏置：横流几何偏置为正、纯噪声近零，用于区分
    # "系统性偏置"与"随机误差"（横流场景下应显著为正）。
    depth_equiv_bias = float(np.mean(distance_err)) if distance_err else float("nan")

    acquired = np.asarray(acquired_flags, dtype=bool)
    target_loss_ratio = float(1.0 - acquired.mean()) if acquired.size else float("nan")
    # Reacquisition: after any loss segment, was the target reacquired before end?
    reacquired, loss_segments = _reacquisition_stats(acquired)
    reacq_success = (float(reacquired / loss_segments) if loss_segments else float("nan"))

    # Magnetic NIS consistency (only meaningful when mag enabled).
    mag_nis = [entry["nis"] for entry in getattr(filt, "nis_history", [])
               if entry.get("source") == "mag" and math.isfinite(float(entry["nis"]))]
    mag_nis_mean = float(np.mean(mag_nis)) if mag_nis else float("nan")
    mag_nis_p95 = float(np.percentile(mag_nis, 95)) if mag_nis else float("nan")

    return {
        "scenario": scenario.key,
        "arm": arm.key,
        "arm_label": arm.label,
        "seed": seed,
        "status": "ok",
        "rmse_xy_m": rmse_xy,
        "rmse_z_m": rmse_z,
        "rmse_3d_m": rmse_3d,
        "depth_equiv_error_m": depth_equiv_err,
        "depth_equiv_bias_m": depth_equiv_bias,
        "current_speed_mps": scenario.current_speed_mps,
        "target_loss_ratio": target_loss_ratio,
        "reacquire_success_ratio": reacq_success,
        "mag_nis_mean": mag_nis_mean,
        "mag_nis_p95": mag_nis_p95,
        "mag_updates": len(distance_err),
        "sonar_input": "confidence_only" if arm.enable_sonar else "disabled",
    }


def _reacquisition_stats(acquired: np.ndarray) -> tuple[int, int]:
    """Count loss segments and how many were reacquired before the run ends."""
    if acquired.size == 0:
        return 0, 0
    loss_segments = 0
    reacquired = 0
    i = 0
    n = acquired.size
    while i < n:
        if not acquired[i]:
            loss_segments += 1
            j = i
            while j < n and not acquired[j]:
                j += 1
            if j < n:  # recovered before end of run
                reacquired += 1
            i = j
        else:
            i += 1
    return reacquired, loss_segments


def summarize(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Mean/std per (scenario, arm) across seeds."""
    metric_keys = ["rmse_xy_m", "rmse_z_m", "rmse_3d_m", "depth_equiv_error_m",
                   "depth_equiv_bias_m", "target_loss_ratio", "reacquire_success_ratio",
                   "mag_nis_mean", "mag_nis_p95"]
    groups: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in rows:
        groups.setdefault((str(row["scenario"]), str(row["arm"])), []).append(row)
    summary: list[dict[str, object]] = []
    for (scenario, arm), items in groups.items():
        entry: dict[str, object] = {
            "scenario": scenario,
            "arm": arm,
            "arm_label": items[0]["arm_label"],
            "current_speed_mps": float(items[0].get("current_speed_mps", 0.0) or 0.0),
            "run_count": len(items),
        }
        for key in metric_keys:
            vals = [float(it[key]) for it in items if math.isfinite(float(it[key]))]
            entry[f"{key}_mean"] = float(np.mean(vals)) if vals else float("nan")
            entry[f"{key}_std"] = float(np.std(vals)) if len(vals) >= 2 else 0.0
        summary.append(entry)
    summary.sort(key=lambda e: (e["scenario"], e["arm"]))
    return summary


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _fmt(row.get(k, "")) for k in fields})


def _fmt(value: object) -> object:
    if isinstance(value, float):
        return "nan" if math.isnan(value) else f"{value:.6g}"
    return value


def plot_summary(output_dir: Path, summary: list[dict[str, object]]) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return
    tps.apply_thesis_style()  # 统一中文字体 / 黑白可辨 / 300 dpi（27 号文 P1-4）

    arms = list(dict.fromkeys(e["arm"] for e in summary))
    arm_labels = {e["arm"]: e["arm_label"] for e in summary}
    scenarios = list(dict.fromkeys(e["scenario"] for e in summary))
    lookup = {(e["scenario"], e["arm"]): e for e in summary}

    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.0))
    x = np.arange(len(scenarios))
    width = 0.8 / max(len(arms), 1)
    for i, arm in enumerate(arms):
        rmse = [lookup.get((s, arm), {}).get("rmse_3d_m_mean", float("nan")) for s in scenarios]
        axes[0].bar(x + i * width, rmse, width, label=arm_labels.get(arm, arm),
                    **tps.series_style(i))
    axes[0].set_xticks(x + width * (len(arms) - 1) / 2)
    axes[0].set_xticklabels(scenarios, rotation=20, ha="right")
    axes[0].set_ylabel("3D 状态 RMSE [m]")
    axes[0].set_title("声磁融合各配置定位误差")
    axes[0].legend(fontsize=8, ncol=2)
    axes[0].grid(axis="y", alpha=0.3)

    for i, arm in enumerate(arms):
        loss = [lookup.get((s, arm), {}).get("target_loss_ratio_mean", float("nan")) for s in scenarios]
        axes[1].bar(x + i * width, loss, width, label=arm_labels.get(arm, arm),
                    **tps.series_style(i))
    axes[1].set_xticks(x + width * (len(arms) - 1) / 2)
    axes[1].set_xticklabels(scenarios, rotation=20, ha="right")
    axes[1].set_ylabel("目标丢失时间占比")
    axes[1].set_title("声呐遮挡/磁弱下目标保持能力")
    axes[1].grid(axis="y", alpha=0.3)

    fig.tight_layout()
    tps.save_figure(fig, output_dir / "figures" / "fusion_ablation_summary")
    plt.close(fig)

    plot_adaptive_vs_fixed_r(output_dir, summary)


def plot_adaptive_vs_fixed_r(output_dir: Path, summary: list[dict[str, object]]) -> None:
    """自适应 R（臂⑥）vs 固定 R（臂⑤）成对对比（27 号文 P1-3）。

    两臂共用轨迹/种子/噪声，仅协方差策略不同：固定 R 用常量磁观测协方差，
    自适应 R 按分源 NIS 门控膨胀。横流/磁弱/复合等偏置场景下，自适应 R 应通过
    识别磁观测失配、下调其信任，换取更小的 3D RMSE 与更稳的磁 NIS。
    """
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return
    fixed_arm, adaptive_arm = "5_fusion_fixed_r", "6_fusion_adaptive_r"
    scenarios = list(dict.fromkeys(e["scenario"] for e in summary))
    lookup = {(e["scenario"], e["arm"]): e for e in summary}
    # 无两臂数据则跳过（例如仅跑单臂子集）。
    if not any((s, fixed_arm) in lookup and (s, adaptive_arm) in lookup for s in scenarios):
        return

    tps.apply_thesis_style()
    x = np.arange(len(scenarios))
    width = 0.38

    fig, axes = plt.subplots(1, 3, figsize=(15.0, 4.6))

    def _paired_bar(ax, metric: str, ylabel: str, title: str) -> None:
        fixed = [lookup.get((s, fixed_arm), {}).get(f"{metric}_mean", float("nan")) for s in scenarios]
        fixed_std = [lookup.get((s, fixed_arm), {}).get(f"{metric}_std", 0.0) for s in scenarios]
        adapt = [lookup.get((s, adaptive_arm), {}).get(f"{metric}_mean", float("nan")) for s in scenarios]
        adapt_std = [lookup.get((s, adaptive_arm), {}).get(f"{metric}_std", 0.0) for s in scenarios]
        ax.bar(x - width / 2, fixed, width, yerr=fixed_std, capsize=3,
               label="固定 R", **tps.series_style(0))
        ax.bar(x + width / 2, adapt, width, yerr=adapt_std, capsize=3,
               label="自适应 R", **tps.series_style(1))
        ax.set_xticks(x)
        ax.set_xticklabels(scenarios, rotation=20, ha="right")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.3)

    _paired_bar(axes[0], "rmse_3d_m", "3D 状态 RMSE [m]", "定位误差：固定 vs 自适应 R")
    _paired_bar(axes[1], "depth_equiv_error_m", "磁反演距离 RMSE [m]", "磁观测精度")
    _paired_bar(axes[2], "mag_nis_mean", "磁 NIS 均值", "磁观测一致性 (NIS)")
    axes[0].legend(loc="upper left", fontsize=9)

    fig.suptitle("声磁融合：自适应 R 相对固定 R 的成对增益（同源同种子）", y=1.02)
    fig.tight_layout()
    tps.save_figure(fig, output_dir / "figures" / "fusion_adaptive_vs_fixed_r")
    plt.close(fig)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    seeds = [int(s) for s in str(args.seeds).split(",") if s.strip()]
    selected = [s for s in SCENARIOS if s.key in
                {x.strip() for x in args.scenarios.split(",")}]
    if not selected:
        print(f"[fusion] no matching scenarios in {args.scenarios}", file=sys.stderr)
        return 2

    out = args.output_dir
    initialize_bundle(
        out,
        experiment_id="fusion_ablation_acoustic_magnetic",
        runner="tools/run_fusion_ablation.py",
        argv=list(argv) if argv is not None else sys.argv,
        data_layer="numerical_synthetic_trajectory",
        matrix={
            "arms": [a.key for a in ARMS],
            "scenarios": [s.key for s in selected],
            "seeds": seeds,
        },
        duration_s=args.duration,
        extra_manifest={
            "sonar_role": "perception_confidence_input_not_ekf_measurement",
            "magnetic_model": "linearised_biot_savart_depth_equivalent (§3.3.3 / R19)",
            "burial_inversion_note": "straight-conductor common-scale simplification (03 号文 §3.3)",
            "current_model": "crossflow_standoff -> magnetic_slant_distance_bias (欠驱动横向站位偏移, 见 _crossflow_standoff_m)",
        },
    )

    rows: list[dict[str, object]] = []
    for scenario in selected:
        for arm in ARMS:
            for seed in seeds:
                try:
                    row = run_arm(arm, scenario, seed, args.duration, args.dt, args.mag_noise_std)
                except Exception as exc:  # keep contract honest on failure
                    row = {
                        "scenario": scenario.key, "arm": arm.key, "arm_label": arm.label,
                        "seed": seed, "status": "error", "error": str(exc),
                    }
                rows.append(row)
                if not args.quiet and row.get("status") == "ok":
                    print(f"[fusion] {scenario.key:16s} {arm.key:22s} seed{seed} "
                          f"rmse3d={float(row['rmse_3d_m']):.3f} "
                          f"loss={float(row['target_loss_ratio']):.3f}")

    summary = summarize([r for r in rows if r.get("status") == "ok"])
    _write_csv(out / "fusion_ablation_by_run.csv", rows)
    _write_csv(out / "fusion_ablation_summary.csv", summary)
    (out / "fusion_ablation_summary.json").write_text(
        json.dumps({"schema_version": 1, "summary": summary}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    if not args.no_figure:
        plot_summary(out, summary)

    finalize_bundle(out, rows, success_statuses={"ok"})
    if not args.quiet:
        print(f"[fusion] {len(rows)} runs -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
