"""Raw cable-perception measurement generators for proxy simulation.

These helpers may use simulator truth to generate noisy sensor measurements.
They deliberately do not produce confidence or probability values; those are
computed by the same perception-quality estimators used by the physical stack.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def _dense_polyline(points_ned: np.ndarray, spacing_m: float) -> np.ndarray:
    points = np.asarray(points_ned, dtype=float).reshape(-1, 3)
    if points.shape[0] < 2:
        return points.copy()
    dense: list[np.ndarray] = []
    spacing = max(float(spacing_m), 0.05)
    for start, end in zip(points[:-1], points[1:]):
        length = float(np.linalg.norm(end - start))
        count = max(2, int(math.ceil(length / spacing)) + 1)
        segment = np.linspace(start, end, count, endpoint=True)
        if dense:
            segment = segment[1:]
        dense.extend(segment)
    return np.asarray(dense, dtype=float)


def _cumulative_arclength(points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    if points.shape[0] == 0:
        return np.zeros(0, dtype=float)
    if points.shape[0] == 1:
        return np.zeros(1, dtype=float)
    step = np.linalg.norm(np.diff(points, axis=0), axis=1)
    return np.concatenate(([0.0], np.cumsum(step)))


def _line_residual_sigma(points: np.ndarray) -> float:
    points = np.asarray(points, dtype=float)
    if points.shape[0] < 3:
        return float("inf")
    center = np.mean(points, axis=0)
    centered = points - center
    scatter = centered.T @ centered / max(points.shape[0], 1)
    _, vectors = np.linalg.eigh(scatter)
    tangent = vectors[:, -1]
    normal = np.array([-tangent[1], tangent[0]])
    residual = centered @ normal
    return max(
        1.4826
        * float(np.median(np.abs(residual - np.median(residual)))),
        1e-4,
    )


def _select_local_visible_branch(
    *,
    dense_ned: np.ndarray,
    visible: np.ndarray,
    body_points: np.ndarray,
    max_arc_m: float,
    min_points: int,
) -> np.ndarray:
    """Select a local straight detector branch from visible polyline points."""
    visible_indices = np.flatnonzero(visible)
    if (
        visible_indices.size < max(int(min_points), 1)
        or not math.isfinite(max_arc_m)
        or max_arc_m <= 0.0
    ):
        return visible_indices

    full_arc = _cumulative_arclength(dense_ned)
    split_at = np.flatnonzero(np.diff(visible_indices) > 1) + 1
    runs = np.split(visible_indices, split_at)
    best_indices = visible_indices
    best_score = float("-inf")

    body_by_dense_index = {
        int(dense_index): body_index
        for body_index, dense_index in enumerate(visible_indices)
    }
    min_points = max(int(min_points), 3)

    for run in runs:
        if run.size < min_points:
            continue
        run_arc = full_arc[run]
        starts = range(run.size)
        for start in starts:
            start_arc = run_arc[start]
            stop = int(np.searchsorted(run_arc, start_arc + max_arc_m, side="right"))
            candidate = run[start:stop]
            if candidate.size < min_points:
                continue
            local_body = body_points[
                [body_by_dense_index[int(index)] for index in candidate]
            ]
            visible_length_m = float(
                np.sum(np.linalg.norm(np.diff(local_body, axis=0), axis=1))
            )
            residual_sigma = _line_residual_sigma(local_body)
            score = (
                math.log1p(candidate.size)
                + math.log1p(max(visible_length_m, 0.0))
                - math.log1p(residual_sigma / 0.1)
            )
            if score > best_score:
                best_score = score
                best_indices = candidate
    return best_indices


def build_magnetic_block_payload(
    *,
    field_amplitude_t: np.ndarray,
    block_end_time_s: float,
    magnetic_sigma_t: np.ndarray,
    config: dict[str, Any] | None,
    rng: np.random.Generator,
) -> dict[str, Any]:
    """Generate an FK2301-like 2 kHz waveform block around the cable field."""
    cfg = dict(config or {})
    sample_rate_hz = max(float(cfg.get("sample_rate_hz", 2000.0)), 200.0)
    duration_s = max(float(cfg.get("duration_s", 0.2)), 0.18)
    target_frequency_hz = float(cfg.get("target_frequency_hz", 45.0))
    mains_frequency_hz = float(cfg.get("mains_frequency_hz", 50.0))
    sample_count = max(16, int(round(sample_rate_hz * duration_s)))
    time_offset_s = (
        np.arange(sample_count, dtype=float) - float(sample_count - 1)
    ) / sample_rate_hz
    absolute_time_s = float(block_end_time_s) + time_offset_s

    target_signal_scale = float(cfg.get("target_signal_scale", 0.002))
    amplitude_nt = (
        np.asarray(field_amplitude_t, dtype=float).reshape(3)
        * 1.0e9
        * target_signal_scale
    )
    noise_std_nt = np.maximum(
        np.asarray(magnetic_sigma_t, dtype=float).reshape(3) * 1.0e9,
        1.0e-6,
    )
    dc_nt = np.asarray(
        cfg.get("background_dc_nt", [24000.0, 1200.0, 41000.0]),
        dtype=float,
    ).reshape(3)
    mains_amplitude_nt = np.asarray(
        cfg.get("mains_amplitude_nt", [30.0, 20.0, 25.0]),
        dtype=float,
    ).reshape(3)
    target_phase = 2.0 * math.pi * target_frequency_hz * absolute_time_s
    mains_phase = 2.0 * math.pi * mains_frequency_hz * absolute_time_s
    samples_nt = (
        dc_nt[None, :]
        + np.cos(target_phase)[:, None] * amplitude_nt[None, :]
        + np.cos(mains_phase + 0.37)[:, None] * mains_amplitude_nt[None, :]
        + rng.normal(0.0, noise_std_nt, size=(sample_count, 3))
    )

    clipping_limit_nt = float(cfg.get("clipping_limit_nt", 100000.0))
    clipped = np.any(np.abs(samples_nt) >= clipping_limit_nt, axis=1)
    samples_nt = np.clip(samples_nt, -clipping_limit_nt, clipping_limit_nt)
    return {
        "sample_rate_hz": sample_rate_hz,
        "sample_count": sample_count,
        "time_offset_s": time_offset_s.tolist(),
        "x_nt": samples_nt[:, 0].tolist(),
        "y_nt": samples_nt[:, 1].tolist(),
        "z_nt": samples_nt[:, 2].tolist(),
        "clipping_ratio": float(np.mean(clipped)),
        "data_completeness": 1.0,
        "dropped_sample_count": 0,
        "calibration_valid": True,
        "calibration_id": "sim_proxy_magnetic_measurement_v1",
        "sample_clock_verified": True,
        "status": "acquiring",
        "measurement_domain": "simulation_proxy",
        "target_signal_scale": target_signal_scale,
    }


def build_sonar_observation_payload(
    *,
    cable_points_ned: np.ndarray,
    position_ned: np.ndarray,
    heading_rad: float,
    sonar_config: dict[str, Any],
    quality_config: dict[str, Any] | None,
    rng: np.random.Generator,
) -> dict[str, Any]:
    """Generate noisy body-frame cable line points for a cable sonar detector."""
    cfg = dict(quality_config or {})
    spacing_m = float(cfg.get("point_spacing_m", 0.35))
    dense = _dense_polyline(cable_points_ned, spacing_m)
    position = np.asarray(position_ned, dtype=float).reshape(3)
    relative = dense - position[None, :]

    cosine = math.cos(float(heading_rad))
    sine = math.sin(float(heading_rad))
    forward = cosine * relative[:, 0] + sine * relative[:, 1]
    starboard = -sine * relative[:, 0] + cosine * relative[:, 1]
    horizontal_range = np.hypot(forward, starboard)
    bearing = np.arctan2(starboard, forward)

    max_range_m = float(sonar_config.get("max_range_m", 30.0))
    field_of_view_deg = float(cfg.get("field_of_view_deg", 140.0))
    half_fov_rad = math.radians(field_of_view_deg) * 0.5
    visible = (
        (forward > 0.05)
        & (horizontal_range <= max_range_m)
        & (np.abs(bearing) <= half_fov_rad)
    )
    body_points = np.column_stack((forward[visible], starboard[visible]))
    selected_visible_indices = np.flatnonzero(visible)
    local_line_max_arc_m = float(cfg.get("local_line_max_arc_m", 0.0))
    if body_points.size and local_line_max_arc_m > 0.0:
        selected_visible_indices = _select_local_visible_branch(
            dense_ned=dense,
            visible=visible,
            body_points=body_points,
            max_arc_m=local_line_max_arc_m,
            min_points=int(cfg.get("local_line_min_points", 8)),
        )
        selected_mask = np.zeros_like(visible, dtype=bool)
        selected_mask[selected_visible_indices] = True
        body_points = np.column_stack(
            (forward[selected_mask], starboard[selected_mask])
        )

    base_noise = max(float(sonar_config.get("base_noise_sigma", 0.01)), 1.0e-6)
    peak_gain = max(float(sonar_config.get("peak_gain", 0.9)), 1.0e-6)
    contrast_to_noise = peak_gain / base_noise
    point_noise_std_m = max(
        float(cfg.get("minimum_point_noise_std_m", 0.02)),
        float(cfg.get("noise_to_geometry_scale_m", 0.3))
        * base_noise
        / peak_gain,
    )
    if body_points.size:
        body_points = body_points + rng.normal(
            0.0,
            point_noise_std_m,
            size=body_points.shape,
        )

    maximum_points = max(int(cfg.get("maximum_points", 120)), 8)
    if body_points.shape[0] > maximum_points:
        indices = np.linspace(
            0,
            body_points.shape[0] - 1,
            maximum_points,
        ).astype(int)
        body_points = body_points[indices]
    visible_length_m = 0.0
    if body_points.shape[0] >= 2:
        visible_length_m = float(
            np.sum(np.linalg.norm(np.diff(body_points, axis=0), axis=1))
        )
    detector_score = math.log1p(max(contrast_to_noise, 0.0))
    ambiguity_margin = float(
        np.clip(
            peak_gain / (peak_gain + 3.0 * base_noise),
            0.0,
            1.0,
        )
    )
    valid = bool(body_points.shape[0] >= 8 and contrast_to_noise >= 1.0)
    flags: list[str] = []
    if not valid:
        flags.append("detector_invalid")
    output_mask = np.zeros_like(visible, dtype=bool)
    output_mask[selected_visible_indices] = True
    truncated = bool(
        np.any(
            output_mask
            & (
                (horizontal_range >= 0.95 * max_range_m)
                | (np.abs(bearing) >= 0.95 * half_fov_rad)
            )
        )
    )
    return {
        "valid": valid,
        "detector_score": detector_score,
        "point_x_m": body_points[:, 0].tolist(),
        "point_y_m": body_points[:, 1].tolist(),
        "point_weight": np.ones(body_points.shape[0], dtype=float).tolist(),
        "contrast_to_noise_ratio": contrast_to_noise,
        "visible_length_m": visible_length_m,
        "ambiguity_margin": ambiguity_margin,
        "field_of_view_truncated": truncated,
        "detector_id": "sim_proxy_cable_sonar_v1",
        "quality_flags": flags,
        "measurement_domain": "simulation_proxy",
        "point_noise_std_m": point_noise_std_m,
    }
