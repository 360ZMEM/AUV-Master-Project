#!/usr/bin/env python3
"""Generate PID/PVS inner-loop reference tracking figures.

The script uses the PVS remus100 native depthHeadingAutopilot through
tools.pid_tuner_pvs.PVSControlSim. It produces step and sine tracking plots
for the tuned PVS-only profiles documented in the thesis notes.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def _apply_zh_style() -> None:
    """图内统一中文：注入文泉驿正黑（容器内唯一可用 CJK 字体），并上调字号适配 A4。"""
    import os
    import matplotlib.font_manager as fm

    zh_font = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
    if os.path.exists(zh_font):
        fm.fontManager.addfont(zh_font)
        plt.rcParams["font.family"] = fm.FontProperties(fname=zh_font).get_name()
    else:
        plt.rcParams["font.sans-serif"] = ["WenQuanYi Zen Hei", "SimHei"] + plt.rcParams["font.sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False  # 负号用 ASCII，避免中文字体缺 U+2212 变方块
    plt.rcParams.update({"font.size": 12, "axes.titlesize": 14, "axes.labelsize": 12, "legend.fontsize": 11})


_apply_zh_style()


def _resolve_project_root() -> Path:
    cur = Path(__file__).resolve()
    for parent in cur.parents:
        if (parent / "algorithm").exists() and (parent / "tools").exists():
            return parent
    raise RuntimeError("Cannot find project root")


PROJECT_ROOT = _resolve_project_root()
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from tools.pid_tuner_pvs import PVSControlSim, _wrap  # noqa: E402


@dataclass(frozen=True)
class Profile:
    name: str
    depth_params: tuple[float, float, float, float]
    yaw_params: tuple[float, float, float, float]
    wn_d_z: float = 0.02
    wn_d: float = 0.1
    r_max_deg: float = 5.0
    delta_max_deg: float = 15.0


@dataclass(frozen=True)
class Case:
    name: str
    kind: str
    channel: str
    duration_s: float
    profile: Profile


# 用户指定的放宽后底层限制：舵限 ±20deg，航向角速率 12deg/s，航向参考模型带宽 0.6。
# 深度 LP 滤波带宽 wn_d_z 随 step/sine 任务分别取值。
STEP_PROFILE = Profile(
    name="step_tuned_v2",
    depth_params=(1.0, 12.0, 2.0, 2.0),
    yaw_params=(0.08, 0.4, 0.1, 0.01),
    wn_d_z=0.15,
    wn_d=0.6,
    r_max_deg=12.0,
    delta_max_deg=20.0,
)

SINE_PROFILE = Profile(
    name="sine_tuned_v2",
    depth_params=(1.0, 6.0, 2.0, 1.5),
    yaw_params=(0.1, 0.4, 0.1, 0.01),
    wn_d_z=0.4,
    wn_d=0.6,
    r_max_deg=12.0,
    delta_max_deg=20.0,
)

COMPARISON_PROFILES = [
    Profile("pvs_default_baseline", (1.0, 15.0, 2.0, 1.0), (0.05, 0.2, 0.3, 0.03)),
    STEP_PROFILE,
    SINE_PROFILE,
]


def _target(kind: str, channel: str, t: float) -> tuple[float, float]:
    if kind == "step":
        depth = 5.0 if channel == "depth" and t >= 3.0 else 0.0
        yaw = math.radians(30.0) if channel == "yaw" and t >= 3.0 else 0.0
        return depth, yaw
    if kind == "sine":
        depth = 2.5 + 0.75 * math.sin(0.12 * t) if channel == "depth" else 0.0
        yaw = math.radians(10.0) * math.sin(0.12 * t) if channel == "yaw" else 0.0
        return depth, yaw
    raise ValueError(f"unknown target kind: {kind}")


def simulate(case: Case, dt: float = 0.02) -> dict[str, np.ndarray | dict[str, float]]:
    sim = PVSControlSim(dt=dt)
    sim.reset(u_init=1.5)
    kp_z, kp_theta, kd_theta, ki_theta = case.profile.depth_params
    lam, phi_b, k_d, k_sigma = case.profile.yaw_params
    sim.set_controller_params(
        Kp_z=kp_z,
        Kp_theta=kp_theta,
        Kd_theta=kd_theta,
        Ki_theta=ki_theta,
        lam=lam,
        phi_b=phi_b,
        K_d=k_d,
        K_sigma=k_sigma,
        wn_d_z=case.profile.wn_d_z,
        wn_d=case.profile.wn_d,
        r_max_deg=case.profile.r_max_deg,
        deltaMax_deg=case.profile.delta_max_deg,
    )

    n_steps = int(case.duration_s / dt)
    t = np.zeros(n_steps)
    depth = np.zeros(n_steps)
    target_depth = np.zeros(n_steps)
    feasible_depth = np.zeros(n_steps)
    yaw = np.zeros(n_steps)
    target_yaw = np.zeros(n_steps)
    feasible_yaw = np.zeros(n_steps)
    stern_deg = np.zeros(n_steps)
    rudder_deg = np.zeros(n_steps)

    for i in range(n_steps):
        now = i * dt
        z_ref, psi_ref = _target(case.kind, case.channel, now)
        sim.step_custom_control(target_z=z_ref, target_psi=psi_ref, target_u=1.5)
        state = sim.get_state()
        t[i] = now
        depth[i] = state["depth"]
        target_depth[i] = z_ref
        # PVS 内部可行参考：深度 LP 滤波状态 z_d 与航向参考模型 psi_d。
        feasible_depth[i] = float(sim.vehicle.z_d)
        yaw[i] = math.degrees(state["yaw"])
        target_yaw[i] = math.degrees(psi_ref)
        feasible_yaw[i] = math.degrees(float(sim.vehicle.psi_d))
        rudder_deg[i] = math.degrees(float(sim.u_actual[0]))
        stern_deg[i] = math.degrees(float(sim.u_actual[1]))

    depth_error = depth - target_depth
    yaw_error = np.array([math.degrees(_wrap(math.radians(a - b))) for a, b in zip(yaw, target_yaw)])
    # 公平口径：相对 PVS 可行参考(滤波/速率受限后)的跟踪误差。
    depth_error_feasible = depth - feasible_depth
    yaw_error_feasible = np.array(
        [math.degrees(_wrap(math.radians(a - b))) for a, b in zip(yaw, feasible_yaw)]
    )
    mask = t >= (20.0 if case.kind == "sine" else 3.0)

    if case.channel == "depth":
        err = depth_error[mask]
        err_f = depth_error_feasible[mask]
        metrics = {
            "rmse": float(np.sqrt(np.mean(err**2))),
            "rmse_feasible": float(np.sqrt(np.mean(err_f**2))),
            "mae": float(np.mean(np.abs(err))),
            "maxe": float(np.max(np.abs(err))),
            "final_err": float(depth_error[-1]),
        }
        if case.kind == "step":
            metrics.update(
                {
                    "final": float(depth[-1]),
                    "overshoot": float(max(0.0, np.max(depth[mask]) - 5.0)),
                }
            )
    else:
        err = yaw_error[mask]
        err_f = yaw_error_feasible[mask]
        metrics = {
            "rmse": float(np.sqrt(np.mean(err**2))),
            "rmse_feasible": float(np.sqrt(np.mean(err_f**2))),
            "mae": float(np.mean(np.abs(err))),
            "maxe": float(np.max(np.abs(err))),
            "final_err": float(yaw_error[-1]),
        }
        if case.kind == "step":
            metrics.update(
                {
                    "final": float(yaw[-1]),
                    "overshoot": float(max(0.0, np.max(yaw[mask]) - 30.0)),
                }
            )

    return {
        "t": t,
        "depth": depth,
        "target_depth": target_depth,
        "feasible_depth": feasible_depth,
        "yaw": yaw,
        "target_yaw": target_yaw,
        "feasible_yaw": feasible_yaw,
        "depth_error": depth_error,
        "yaw_error": yaw_error,
        "stern_deg": stern_deg,
        "rudder_deg": rudder_deg,
        "metrics": metrics,
    }


def _plot_tracking(case: Case, result: dict[str, np.ndarray | dict[str, float]], output: Path) -> None:
    t = result["t"]
    assert isinstance(t, np.ndarray)
    metrics = result["metrics"]
    assert isinstance(metrics, dict)

    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    if case.channel == "depth":
        actual = result["depth"]
        target = result["target_depth"]
        feasible = result["feasible_depth"]
        error = result["depth_error"]
        control = result["stern_deg"]
        ylabel = "深度（m）"
        error_label = "深度误差（m）"
        control_label = "艉舵（deg）"
    else:
        actual = result["yaw"]
        target = result["target_yaw"]
        feasible = result["feasible_yaw"]
        error = result["yaw_error"]
        control = result["rudder_deg"]
        ylabel = "艏向（deg）"
        error_label = "艏向误差（deg）"
        control_label = "方向舵（deg）"

    for arr in (actual, target, feasible, error, control):
        assert isinstance(arr, np.ndarray)

    axes[0].plot(t, target, "--", label="指令", linewidth=2, color="#7f7f7f")
    axes[0].plot(t, feasible, ":", label="可行参考", linewidth=2, color="#9467bd")
    axes[0].plot(t, actual, label="响应", linewidth=1.8, color="#1f77b4")
    axes[0].set_ylabel(ylabel)
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(loc="best")
    axes[0].set_title(f"内层 PID/PVS 跟踪 — {case.name}（{case.profile.name}）")

    axes[1].plot(t, error, color="#d62728", linewidth=1.5)
    axes[1].axhline(0.0, color="black", linewidth=0.8)
    axes[1].set_ylabel(error_label)
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(t, control, color="#2ca02c", linewidth=1.4)
    axes[2].set_ylabel(control_label)
    axes[2].set_xlabel("时间（s）")
    axes[2].grid(True, alpha=0.3)

    text = ", ".join(f"{k}={v:.3f}" for k, v in metrics.items())
    fig.text(0.01, 0.01, text, fontsize=9)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(output, dpi=160)
    plt.close(fig)


def _comparison_metrics(kind: str, channel: str) -> list[tuple[str, float]]:
    values = []
    for profile in COMPARISON_PROFILES:
        case = Case(
            name=f"{kind}_{channel}",
            kind=kind,
            channel=channel,
            duration_s=80.0 if kind == "sine" else 60.0,
            profile=profile,
        )
        result = simulate(case)
        metrics = result["metrics"]
        assert isinstance(metrics, dict)
        values.append((profile.name, metrics["rmse"]))
    return values


def _plot_summary(output: Path) -> None:
    cases = [
        ("step", "depth", "阶跃深度 RMSE（m）"),
        ("step", "yaw", "阶跃艏向 RMSE（deg）"),
        ("sine", "depth", "正弦深度 RMSE（m）"),
        ("sine", "yaw", "正弦艏向 RMSE（deg）"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    for ax, (kind, channel, title) in zip(axes.ravel(), cases):
        values = _comparison_metrics(kind, channel)
        labels = [v[0] for v in values]
        rmse = [v[1] for v in values]
        ax.bar(range(len(labels)), rmse, color=["#7f7f7f", "#1f77b4", "#ff7f0e"])
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=25, ha="right", fontsize=8)
        ax.set_title(title)
        ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)


def _write_report(output_dir: Path, figures: dict[str, Path], results: dict[str, dict[str, float]]) -> None:
    lines = [
        "# PID/PVS Inner-Loop Tracking Figures",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Profiles",
        "",
        "Shared relaxed plant limits (runtime, not source edit): "
        f"deltaMax={STEP_PROFILE.delta_max_deg} deg, r_max={STEP_PROFILE.r_max_deg} deg/s, wn_d={STEP_PROFILE.wn_d}.",
        "",
        f"- step depth: `Kp_z={STEP_PROFILE.depth_params[0]}, Kp_theta={STEP_PROFILE.depth_params[1]}, Kd_theta={STEP_PROFILE.depth_params[2]}, Ki_theta={STEP_PROFILE.depth_params[3]}, wn_d_z={STEP_PROFILE.wn_d_z}`",
        f"- step yaw: `lam={STEP_PROFILE.yaw_params[0]}, phi_b={STEP_PROFILE.yaw_params[1]}, K_d={STEP_PROFILE.yaw_params[2]}, K_sigma={STEP_PROFILE.yaw_params[3]}`",
        f"- sine depth: `Kp_z={SINE_PROFILE.depth_params[0]}, Kp_theta={SINE_PROFILE.depth_params[1]}, Kd_theta={SINE_PROFILE.depth_params[2]}, Ki_theta={SINE_PROFILE.depth_params[3]}, wn_d_z={SINE_PROFILE.wn_d_z}`",
        f"- sine yaw: `lam={SINE_PROFILE.yaw_params[0]}, phi_b={SINE_PROFILE.yaw_params[1]}, K_d={SINE_PROFILE.yaw_params[2]}, K_sigma={SINE_PROFILE.yaw_params[3]}`",
        "",
        "## Metrics",
        "",
        "| case | metrics |",
        "| --- | --- |",
    ]
    for name, metrics in results.items():
        rendered = ", ".join(f"{k}={v:.3f}" for k, v in metrics.items())
        lines.append(f"| `{name}` | {rendered} |")
    lines.extend(["", "## Figures", "", "| figure | path |", "| --- | --- |"])
    for name, path in figures.items():
        lines.append(f"| `{name}` | `{path}` |")
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("/auv_data/results/control/pid_pvs_tuning"),
        help="Directory where a timestamped run folder will be created.",
    )
    args = parser.parse_args()

    run_dir = args.output_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    figures_dir = run_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    cases = [
        Case("depth_step", "step", "depth", 60.0, STEP_PROFILE),
        Case("yaw_step", "step", "yaw", 60.0, STEP_PROFILE),
        Case("depth_sine", "sine", "depth", 80.0, SINE_PROFILE),
        Case("yaw_sine", "sine", "yaw", 80.0, SINE_PROFILE),
    ]

    figures: dict[str, Path] = {}
    results: dict[str, dict[str, float]] = {}
    for idx, case in enumerate(cases, start=1):
        result = simulate(case)
        metrics = result["metrics"]
        assert isinstance(metrics, dict)
        results[case.name] = metrics
        path = figures_dir / f"{idx:02d}_pid_pvs_{case.name}.png"
        _plot_tracking(case, result, path)
        figures[case.name] = path

    summary_path = figures_dir / "05_pid_pvs_profile_comparison.png"
    _plot_summary(summary_path)
    figures["profile_comparison"] = summary_path

    _write_report(run_dir, figures, results)
    print(run_dir)


if __name__ == "__main__":
    main()
