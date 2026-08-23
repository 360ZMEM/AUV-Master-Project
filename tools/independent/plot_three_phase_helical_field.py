#!/usr/bin/env python3
"""Simulate the qualitative leakage field of a balanced helical three-phase cable.

The conductor centerlines are discretized into finite current elements and the
field is evaluated with the Biot-Savart law. The plotted central region is kept
away from both finite-length ends. No project simulation code or data is used.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import patheffects
from matplotlib.colors import LogNorm
from matplotlib.patches import Circle

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import thesis_plot_style as tps  # noqa: E402


MU0 = 4.0 * np.pi * 1.0e-7
PHASE_OFFSETS = np.array([0.0, 2.0 * np.pi / 3.0, -2.0 * np.pi / 3.0])
CURRENT_PHASORS = np.exp(1j * np.array([0.0, -2.0 * np.pi / 3.0, 2.0 * np.pi / 3.0]))
PHASE_COLORS = (tps.PROPOSED, tps.BASELINE_1, tps.BASELINE_2)


def configure_plot_style() -> None:
    tps.apply_thesis_style(layout="full")


def default_output_dir() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "thesis"
        / "figures"
        / "magnetics"
    )


def build_helical_segments(
    core_radius: float,
    pitch: float,
    total_length: float,
    points_per_pitch: int,
) -> list[tuple[np.ndarray, np.ndarray]]:
    count = int(np.ceil(total_length / pitch * points_per_pitch))
    s = np.linspace(-total_length / 2.0, total_length / 2.0, count + 1)
    wave_number = 2.0 * np.pi / pitch
    segments: list[tuple[np.ndarray, np.ndarray]] = []
    for phase in PHASE_OFFSETS:
        path = np.column_stack(
            (
                core_radius * np.cos(wave_number * s + phase),
                core_radius * np.sin(wave_number * s + phase),
                s,
            )
        )
        midpoints = 0.5 * (path[1:] + path[:-1])
        line_elements = np.diff(path, axis=0)
        segments.append((midpoints, line_elements))
    return segments


def field_per_ampere(
    observations: np.ndarray,
    segments: tuple[np.ndarray, np.ndarray],
    chunk_size: int = 192,
) -> np.ndarray:
    midpoints, line_elements = segments
    field = np.empty_like(observations, dtype=float)
    coefficient = MU0 / (4.0 * np.pi)
    for start in range(0, observations.shape[0], chunk_size):
        stop = min(start + chunk_size, observations.shape[0])
        displacement = observations[start:stop, None, :] - midpoints[None, :, :]
        distance_sq = np.einsum("ijk,ijk->ij", displacement, displacement)
        inverse_distance_cubed = np.power(distance_sq, -1.5)
        contributions = np.cross(line_elements[None, :, :], displacement)
        field[start:stop] = coefficient * np.einsum(
            "ijk,ij->ik", contributions, inverse_distance_cubed
        )
    return field


def evaluate_phase_fields(
    observations: np.ndarray,
    segments: list[tuple[np.ndarray, np.ndarray]],
) -> list[np.ndarray]:
    return [field_per_ampere(observations, phase_segments) for phase_segments in segments]


def draw_current_symbol(
    ax: plt.Axes,
    center: tuple[float, float],
    positive: bool,
    color: str,
    label: str,
    label_offset: tuple[float, float],
) -> None:
    circle = Circle(center, 0.25, facecolor="white", edgecolor=color, lw=1.5, zorder=8)
    ax.add_patch(circle)
    if positive:
        ax.plot(*center, ".", color=color, ms=7, zorder=9)
    else:
        x, y = center
        ax.plot([x - 0.10, x + 0.10], [y - 0.10, y + 0.10], color=color, lw=1.2, zorder=9)
        ax.plot([x - 0.10, x + 0.10], [y + 0.10, y - 0.10], color=color, lw=1.2, zorder=9)
    annotation = ax.annotate(
        label,
        xy=center,
        xytext=(center[0] + label_offset[0], center[1] + label_offset[1]),
        color="white",
        fontsize=8.5,
        weight="bold",
        ha="center",
        va="center",
        arrowprops={"arrowstyle": "-", "color": "white", "lw": 1.0},
        zorder=10,
    )
    outline = [patheffects.withStroke(linewidth=2.2, foreground="#222222")]
    annotation.set_path_effects(outline)
    if annotation.arrow_patch is not None:
        annotation.arrow_patch.set_path_effects(outline)


def make_figure() -> tuple[plt.Figure, float]:
    configure_plot_style()

    core_radius = 0.06
    pitch = 1.0
    total_length = 7.0 * pitch
    observation_height = 0.35
    segments = build_helical_segments(core_radius, pitch, total_length, points_per_pitch=320)

    fig = plt.figure(
        figsize=tps.figure_size("full", height=4.8),
        layout="constrained",
    )
    grid = fig.add_gridspec(2, 2, height_ratios=(1.12, 0.78), width_ratios=(1.22, 0.78))
    geometry_ax = fig.add_subplot(grid[0, 0], projection="3d")
    section_ax = fig.add_subplot(grid[0, 1])
    axial_ax = fig.add_subplot(grid[1, :])

    # Panel (a): conductor geometry and normalized instantaneous field direction.
    s_plot = np.linspace(-1.5 * pitch, 1.5 * pitch, 700)
    wave_number = 2.0 * np.pi / pitch
    for name, phase, color in zip(("A 相芯线", "B 相芯线", "C 相芯线"), PHASE_OFFSETS, PHASE_COLORS):
        x = core_radius * np.cos(wave_number * s_plot + phase)
        y = core_radius * np.sin(wave_number * s_plot + phase)
        geometry_ax.plot(s_plot / pitch, x / core_radius, y / core_radius, color=color, lw=2.0, label=name)
        label_s = 1.46 * pitch
        geometry_ax.text(
            label_s / pitch,
            np.cos(wave_number * label_s + phase),
            np.sin(wave_number * label_s + phase),
            name[0],
            color=color,
            fontsize=8.5,
            weight="bold",
        )

    arrow_s = np.linspace(-1.35 * pitch, 1.35 * pitch, 11)
    arrow_observations = np.column_stack(
        (np.zeros_like(arrow_s), np.full_like(arrow_s, observation_height), arrow_s)
    )
    arrow_phase_fields = evaluate_phase_fields(arrow_observations, segments)
    instantaneous_field = sum(
        phasor.real * phase_field
        for phasor, phase_field in zip(CURRENT_PHASORS, arrow_phase_fields)
    )
    instantaneous_norm = np.linalg.norm(instantaneous_field, axis=1)
    unit_field = instantaneous_field / instantaneous_norm[:, None]
    geometry_ax.plot(
        arrow_s / pitch,
        np.zeros_like(arrow_s),
        np.full_like(arrow_s, observation_height / core_radius),
        color="#555555",
        lw=1.0,
        ls="--",
        label="AUV 观测线",
    )
    geometry_ax.quiver(
        arrow_s / pitch,
        np.zeros_like(arrow_s),
        np.full_like(arrow_s, observation_height / core_radius),
        0.24 * unit_field[:, 2],
        0.55 * unit_field[:, 0],
        0.55 * unit_field[:, 1],
        color="#7d2131",
        linewidth=1.0,
        arrow_length_ratio=0.28,
        normalize=False,
    )
    geometry_ax.set_xlabel(r"沿缆位置 $s/p$", labelpad=-2)
    geometry_ax.set_ylabel(r"$x/a$", labelpad=-1)
    geometry_ax.set_zlabel(r"$y/a$", labelpad=-1)
    geometry_ax.set_title("(a) 三相芯线沿电缆方向螺旋绞合", loc="left", pad=0)
    geometry_ax.set_xlim(-1.5, 1.5)
    geometry_ax.set_ylim(-1.5, 1.5)
    geometry_ax.set_zlim(-1.5, 6.3)
    geometry_ax.set_yticks((-1.0, 0.0, 1.0))
    geometry_ax.set_zticks((0.0, 2.0, 4.0, 6.0))
    geometry_ax.set_box_aspect((3.0, 1.4, 2.0), zoom=1.28)
    geometry_ax.view_init(elev=18.0, azim=-66.0)
    geometry_ax.text2D(
        0.02,
        0.96,
        "蓝/橙/绿：A/B/C 相芯线\n灰虚线：AUV 观测线    红箭头：瞬时磁场方向",
        transform=geometry_ax.transAxes,
        color="#333333",
        fontsize=7.0,
        ha="left",
        va="top",
    )

    # Panel (b): a Biot-Savart cross-section at the balanced-current snapshot.
    normalized_axis = np.linspace(-5.0, 5.0, 31)
    x_norm, y_norm = np.meshgrid(normalized_axis, normalized_axis)
    section_observations = np.column_stack(
        (
            (core_radius * x_norm).ravel(),
            (core_radius * y_norm).ravel(),
            np.zeros(x_norm.size),
        )
    )
    section_phase_fields = evaluate_phase_fields(section_observations, segments)
    section_field = sum(
        phasor.real * phase_field
        for phasor, phase_field in zip(CURRENT_PHASORS, section_phase_fields)
    )
    section_field = section_field.reshape(x_norm.shape + (3,))
    section_magnitude_ut = np.linalg.norm(section_field, axis=2) * 1.0e6
    section_projection = section_field[:, :, :2]
    projection_norm = np.linalg.norm(section_projection, axis=2)

    conductor_centers = np.column_stack((np.cos(PHASE_OFFSETS), np.sin(PHASE_OFFSETS)))
    core_mask = np.zeros_like(x_norm, dtype=bool)
    for center in conductor_centers:
        core_mask |= (x_norm - center[0]) ** 2 + (y_norm - center[1]) ** 2 < 0.32**2
    section_magnitude_ut = np.ma.array(section_magnitude_ut, mask=core_mask)
    projection_norm = np.where(projection_norm > 0.0, projection_norm, 1.0)
    ux = np.ma.array(section_projection[:, :, 0] / projection_norm, mask=core_mask)
    uy = np.ma.array(section_projection[:, :, 1] / projection_norm, mask=core_mask)

    finite_values = section_magnitude_ut.compressed()
    lower = max(np.percentile(finite_values, 6.0), 1.0e-4)
    upper = np.percentile(finite_values, 97.5)
    contour = section_ax.contourf(
        x_norm,
        y_norm,
        section_magnitude_ut,
        levels=np.geomspace(lower, upper, 17),
        norm=LogNorm(vmin=lower, vmax=upper),
        cmap="cividis",
        extend="both",
    )
    stride = 2
    section_ax.quiver(
        x_norm[::stride, ::stride],
        y_norm[::stride, ::stride],
        ux[::stride, ::stride],
        uy[::stride, ::stride],
        color="#222222",
        pivot="mid",
        scale=20,
        width=0.004,
        headwidth=3.4,
    )
    current_values = CURRENT_PHASORS.real
    label_offsets = ((0.78, 0.62), (-0.78, 0.72), (-0.78, -0.72))
    for index, (center, current, color, label_offset) in enumerate(
        zip(conductor_centers, current_values, PHASE_COLORS, label_offsets)
    ):
        draw_current_symbol(
            section_ax,
            (float(center[0]), float(center[1])),
            current > 0.0,
            color,
            f"{'ABC'[index]} 相",
            label_offset,
        )
    section_ax.text(
        0.03,
        0.97,
        "此时：A 相 = +1.0 $I_m$（· 流出）\n"
        "B、C 相 = -0.5 $I_m$（× 流入）\n"
        r"电流之和 $i_A+i_B+i_C=0$",
        ha="left",
        va="top",
        transform=section_ax.transAxes,
        fontsize=7.0,
        bbox={"facecolor": "white", "edgecolor": "#777777", "alpha": 0.88, "pad": 2.5},
    )
    section_ax.add_patch(
        Circle((0.0, 0.0), 1.45, facecolor="none", edgecolor="#666666", ls="--", lw=0.9)
    )
    section_ax.set_aspect("equal")
    section_ax.set_xlim(-5.0, 5.0)
    section_ax.set_ylim(-5.0, 5.0)
    section_ax.set_xlabel(r"横向 $x/a$")
    section_ax.set_ylabel(r"竖向 $y/a$")
    section_ax.set_title("(b) 三相电流和为零，外部仍有漏磁", loc="left")
    colorbar = fig.colorbar(contour, ax=section_ax, orientation="horizontal", pad=0.03, shrink=0.88)
    candidate_ticks = np.array((0.2, 0.5, 1.0, 2.0, 5.0))
    colorbar_ticks = candidate_ticks[(candidate_ticks >= lower) & (candidate_ticks <= upper)]
    colorbar.set_ticks(colorbar_ticks)
    colorbar.set_ticklabels(tuple(f"{tick:g}" for tick in colorbar_ticks))
    colorbar.set_label(r"颜色：磁场强度 $|\mathbf{B}|$（$\mu$T）；黑箭头：方向")

    # Panel (c): vector components rotate while the three-axis RMS norm is stable.
    axial_s = np.linspace(-1.5 * pitch, 1.5 * pitch, 301)
    axial_observations = np.column_stack(
        (np.zeros_like(axial_s), np.full_like(axial_s, observation_height), axial_s)
    )
    axial_phase_fields = evaluate_phase_fields(axial_observations, segments)
    field_phasor = sum(
        phasor * phase_field
        for phasor, phase_field in zip(CURRENT_PHASORS, axial_phase_fields)
    )
    field_rms = np.sqrt(np.sum(np.abs(field_phasor) ** 2, axis=1) / 2.0)
    normalization = float(np.mean(field_rms))
    instantaneous = np.real(field_phasor) / normalization
    line_styles = ("-", "--", "-.")
    for index, (component, color, line_style) in enumerate(
        zip((r"瞬时 $B_x$", r"瞬时 $B_y$", r"瞬时 $B_s$"), PHASE_COLORS, line_styles)
    ):
        axial_ax.plot(
            axial_s / pitch,
            instantaneous[:, index],
            color=color,
            ls=line_style,
            lw=1.4,
            alpha=0.86,
            label=component,
        )
    normalized_rms = field_rms / normalization
    axial_ax.plot(
        axial_s / pitch,
        normalized_rms,
        color="#111111",
        lw=2.5,
        label="三轴 RMS 合成强度（定位量）",
    )
    max_deviation_percent = float(np.max(np.abs(normalized_rms - 1.0)) * 100.0)
    axial_ax.axhline(0.0, color="#666666", lw=0.7)
    axial_ax.axhline(1.0, color="#111111", lw=0.7, ls=":")
    axial_ax.set_xlim(-1.5, 1.5)
    axial_ax.set_ylim(-1.45, 1.45)
    axial_ax.set_xlabel(r"沿电缆位置 $s/p$（横轴每增加 1，前进一个绞距）")
    axial_ax.set_ylabel("相对磁场值")
    axial_ax.set_title(
        "(c) 彩色分量随绞距振荡，黑色三轴合成强度近似不变",
        loc="left",
    )
    axial_ax.grid(True, alpha=0.25)
    axial_ax.legend(loc="lower left", ncol=4)

    return fig, max_deviation_percent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=default_output_dir())
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    figure, max_deviation_percent = make_figure()
    for output in tps.save_figure(
        figure,
        args.output_dir / "three_phase_helical_field",
    ):
        print(output)
    print(f"central-window RMS max deviation: {max_deviation_percent:.3f}%")
    plt.close(figure)


if __name__ == "__main__":
    main()
