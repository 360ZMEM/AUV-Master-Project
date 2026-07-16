"""Magnetic observation noise sources for ROS-side semi-physical replay.

The helpers in this module are deliberately ROS-independent so the ADC-TMR
record conversion can be tested without starting rclpy.  All public samples are
returned in Tesla and are intended to be added only to magnetic measurements,
not to cable, terrain, current, or vehicle truth.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np


VALID_NOISE_MODES = {"none", "covariance_gaussian", "measured_replay"}


@dataclass(frozen=True)
class MagneticNoiseSample:
    vector_t: np.ndarray
    metadata: dict[str, Any]


@dataclass(frozen=True)
class MagneticNoiseDataset:
    samples_t: np.ndarray
    sample_rate_hz: float
    source_files: list[str]
    segment_lengths: list[int]
    profile_path: str
    profile_sha256: str
    axis_rms_t: list[float]
    covariance_t2: list[list[float]]

    @property
    def sample_count(self) -> int:
        return int(self.samples_t.shape[0])

    @property
    def duration_s(self) -> float:
        if self.sample_rate_hz <= 0.0:
            return 0.0
        return float(self.sample_count / self.sample_rate_hz)

    def source_for_index(self, sample_index: int) -> tuple[str, int]:
        if not self.segment_lengths:
            return "", 0
        clamped = int(sample_index) % max(self.sample_count, 1)
        cumulative = np.cumsum(np.asarray(self.segment_lengths, dtype=int))
        segment = int(np.searchsorted(cumulative, clamped, side="right"))
        segment_start = int(cumulative[segment - 1]) if segment > 0 else 0
        local_index = clamped - segment_start
        return self.source_files[segment], local_index


def parse_path_sequence(value: object) -> list[str]:
    """Normalize ROS string-array, JSON-string, or comma-list path parameters."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    return [part.strip() for part in text.split(",") if part.strip()]


def resolve_project_path(path: str | Path, project_root: Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (project_root / candidate).resolve()


def file_sha256(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _as_axis_vector(values: Iterable[float], *, default: list[float]) -> np.ndarray:
    items = [float(item) for item in values]
    if not items:
        items = list(default)
    if len(items) < 3:
        items = [items[index % len(items)] for index in range(3)]
    return np.asarray(items[:3], dtype=np.float64)


def voltage_to_magnetic_t(voltage: np.ndarray, sensitivity_mv_per_ut: Iterable[float]) -> np.ndarray:
    arr = np.asarray(voltage, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] < 3:
        raise ValueError("ADC voltage must be a two-dimensional array with at least three axes")
    sensitivity = _as_axis_vector(sensitivity_mv_per_ut, default=[20.02, 19.98, 19.96])
    if np.any(sensitivity <= 0.0):
        raise ValueError("sensitivity_mv_per_ut values must be positive")
    magnetic_ut = arr[:, :3] / (sensitivity[None, :] / 1000.0)
    return magnetic_ut * 1.0e-6


def detrend_samples(samples_t: np.ndarray, mode: str) -> np.ndarray:
    arr = np.asarray(samples_t, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != 3:
        raise ValueError("magnetic noise samples must have shape (N, 3)")
    finite = np.isfinite(arr)
    if not np.all(finite):
        median = np.nanmedian(np.where(finite, arr, np.nan), axis=0)
        arr = np.where(finite, arr, median[None, :])
    mode_text = str(mode).strip().lower()
    if mode_text == "none":
        return arr.copy()
    centered = arr - np.mean(arr, axis=0)
    if mode_text == "mean":
        return centered
    if mode_text != "linear":
        raise ValueError("mag_noise_detrend must be one of: linear, mean, none")
    if arr.shape[0] < 2:
        return centered
    t = np.linspace(-1.0, 1.0, arr.shape[0], dtype=np.float64)
    slope = np.sum(centered * t[:, None], axis=0) / max(float(np.sum(t * t)), 1.0e-12)
    return centered - t[:, None] * slope[None, :]


def load_magnetic_noise_dataset(
    *,
    npz_paths: list[str | Path],
    project_root: Path,
    profile_path: str | Path = "",
    detrend_mode: str = "linear",
    fallback_sensitivity_mv_per_ut: Iterable[float] = (20.02, 19.98, 19.96),
    axis_order: Iterable[int] = (0, 1, 2),
    axis_signs: Iterable[float] = (1.0, 1.0, 1.0),
    scale: float = 1.0,
) -> MagneticNoiseDataset:
    if not npz_paths:
        raise ValueError("measured magnetic noise replay requires at least one NPZ path")
    order = [int(item) for item in axis_order]
    signs = _as_axis_vector(axis_signs, default=[1.0, 1.0, 1.0])
    if len(order) != 3 or any(index < 0 or index > 2 for index in order):
        raise ValueError("mag_noise_axis_order must contain three indices in [0, 2]")

    source_files: list[str] = []
    segment_lengths: list[int] = []
    arrays: list[np.ndarray] = []
    sample_rate_hz: float | None = None
    fallback = list(float(item) for item in fallback_sensitivity_mv_per_ut)
    for item in npz_paths:
        path = resolve_project_path(item, project_root)
        with np.load(path, allow_pickle=False) as archive:
            if "voltage" not in archive or "sample_rate_hz" not in archive:
                raise ValueError(f"ADC noise record missing voltage/sample_rate_hz: {path}")
            voltage = np.asarray(archive["voltage"], dtype=np.float64)
            record_rate = float(np.asarray(archive["sample_rate_hz"]).item())
            sensitivity = (
                np.asarray(archive["sensitivity_mv_per_ut"], dtype=np.float64).tolist()
                if "sensitivity_mv_per_ut" in archive
                else fallback
            )
        if sample_rate_hz is None:
            sample_rate_hz = record_rate
        elif abs(record_rate - sample_rate_hz) > 1.0e-6:
            raise ValueError(
                f"magnetic noise replay records must share one sample rate: "
                f"{record_rate} != {sample_rate_hz}"
            )
        field_t = voltage_to_magnetic_t(voltage, sensitivity)[:, order] * signs[None, :]
        field_t = detrend_samples(field_t, detrend_mode) * float(scale)
        arrays.append(field_t)
        source_files.append(str(path))
        segment_lengths.append(int(field_t.shape[0]))

    samples_t = np.vstack(arrays)
    if samples_t.size == 0:
        raise ValueError("magnetic noise replay records contain no samples")
    covariance_t2 = np.cov(samples_t, rowvar=False)
    covariance_t2 = np.atleast_2d(covariance_t2).astype(np.float64)
    covariance_t2 = 0.5 * (covariance_t2 + covariance_t2.T)
    profile = resolve_project_path(profile_path, project_root) if str(profile_path).strip() else Path("")
    return MagneticNoiseDataset(
        samples_t=samples_t,
        sample_rate_hz=float(sample_rate_hz or 1.0),
        source_files=source_files,
        segment_lengths=segment_lengths,
        profile_path=str(profile) if str(profile) else "",
        profile_sha256=file_sha256(profile) if str(profile) else "",
        axis_rms_t=[float(value) for value in np.sqrt(np.mean(samples_t * samples_t, axis=0))],
        covariance_t2=covariance_t2.tolist(),
    )


class MagneticNoiseSource:
    mode = "none"

    def describe(self) -> dict[str, Any]:
        return {"noise_mode": self.mode}

    def sample(self, elapsed_s: float) -> MagneticNoiseSample:
        return MagneticNoiseSample(np.zeros(3, dtype=np.float64), self.describe())


class NullMagneticNoiseSource(MagneticNoiseSource):
    mode = "none"


class MeasuredMagNoiseReplay(MagneticNoiseSource):
    mode = "measured_replay"

    def __init__(self, dataset: MagneticNoiseDataset, *, seed: int | None = None) -> None:
        self.dataset = dataset
        if seed is None:
            self.start_index = 0
        else:
            rng = np.random.default_rng(int(seed))
            self.start_index = int(rng.integers(0, max(dataset.sample_count, 1)))

    def describe(self) -> dict[str, Any]:
        return {
            "noise_mode": self.mode,
            "noise_profile_path": self.dataset.profile_path,
            "noise_profile_sha256": self.dataset.profile_sha256,
            "noise_source_npz": self.dataset.source_files,
            "record_sample_rate_hz": self.dataset.sample_rate_hz,
            "record_sample_count": self.dataset.sample_count,
            "record_duration_s": self.dataset.duration_s,
            "axis_rms_t": self.dataset.axis_rms_t,
            "looped_replay": True,
        }

    def sample(self, elapsed_s: float) -> MagneticNoiseSample:
        raw_index = int(math.floor(max(0.0, float(elapsed_s)) * self.dataset.sample_rate_hz))
        sample_index = int((self.start_index + raw_index) % self.dataset.sample_count)
        source, local_index = self.dataset.source_for_index(sample_index)
        vector_t = self.dataset.samples_t[sample_index].copy()
        metadata = {
            **self.describe(),
            "sample_index": sample_index,
            "source_local_sample_index": local_index,
            "current_noise_source_npz": source,
            "replay_phase": sample_index / max(float(self.dataset.sample_count), 1.0),
            "elapsed_s": float(elapsed_s),
        }
        return MagneticNoiseSample(vector_t, metadata)


class CovarianceGaussianMagNoise(MagneticNoiseSource):
    mode = "covariance_gaussian"

    def __init__(self, dataset: MagneticNoiseDataset, *, seed: int | None = None) -> None:
        self.dataset = dataset
        self.rng = np.random.default_rng(seed)
        covariance = np.asarray(dataset.covariance_t2, dtype=np.float64)
        eigval, eigvec = np.linalg.eigh(0.5 * (covariance + covariance.T))
        eigval = np.clip(eigval, 0.0, None)
        self.sqrt_covariance = eigvec @ np.diag(np.sqrt(eigval))
        self.sample_index = 0

    def describe(self) -> dict[str, Any]:
        return {
            "noise_mode": self.mode,
            "noise_profile_path": self.dataset.profile_path,
            "noise_profile_sha256": self.dataset.profile_sha256,
            "noise_source_npz": self.dataset.source_files,
            "record_sample_rate_hz": self.dataset.sample_rate_hz,
            "record_sample_count": self.dataset.sample_count,
            "record_duration_s": self.dataset.duration_s,
            "axis_rms_t": self.dataset.axis_rms_t,
            "covariance_t2": self.dataset.covariance_t2,
        }

    def sample(self, elapsed_s: float) -> MagneticNoiseSample:
        vector_t = self.rng.standard_normal(3) @ self.sqrt_covariance.T
        metadata = {
            **self.describe(),
            "sample_index": self.sample_index,
            "replay_phase": float("nan"),
            "elapsed_s": float(elapsed_s),
        }
        self.sample_index += 1
        return MagneticNoiseSample(vector_t, metadata)


def make_magnetic_noise_source(
    *,
    mode: str,
    project_root: Path,
    npz_paths: list[str | Path],
    profile_path: str | Path = "",
    seed: int | None = None,
    detrend_mode: str = "linear",
    fallback_sensitivity_mv_per_ut: Iterable[float] = (20.02, 19.98, 19.96),
    axis_order: Iterable[int] = (0, 1, 2),
    axis_signs: Iterable[float] = (1.0, 1.0, 1.0),
    scale: float = 1.0,
) -> MagneticNoiseSource:
    mode_text = str(mode).strip().lower()
    if mode_text not in VALID_NOISE_MODES:
        raise ValueError(f"mag_noise_mode must be one of {sorted(VALID_NOISE_MODES)}")
    if mode_text == "none":
        return NullMagneticNoiseSource()
    dataset = load_magnetic_noise_dataset(
        npz_paths=npz_paths,
        project_root=project_root,
        profile_path=profile_path,
        detrend_mode=detrend_mode,
        fallback_sensitivity_mv_per_ut=fallback_sensitivity_mv_per_ut,
        axis_order=axis_order,
        axis_signs=axis_signs,
        scale=scale,
    )
    if mode_text == "measured_replay":
        return MeasuredMagNoiseReplay(dataset, seed=seed)
    return CovarianceGaussianMagNoise(dataset, seed=seed)
