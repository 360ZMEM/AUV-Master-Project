#!/usr/bin/env python3
"""Fit and independently validate monotonic perception probabilities."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Sequence

import numpy as np


@dataclass
class IsotonicBlock:
    x_sum: float
    y_sum: float
    weight: float
    x_min: float
    x_max: float

    @property
    def probability(self) -> float:
        return self.y_sum / self.weight

    @property
    def x_mean(self) -> float:
        return self.x_sum / self.weight


def read_labeled_csv(path: Path) -> dict[str, np.ndarray]:
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    required = {
        "detection_score",
        "track_score",
        "detected",
        "within_tolerance",
    }
    if not rows or not required.issubset(rows[0]):
        raise ValueError(
            f"{path} must contain columns: {sorted(required)}"
        )
    output = {}
    for key in required:
        values = np.asarray([float(row[key]) for row in rows], dtype=float)
        if np.any(~np.isfinite(values)):
            raise ValueError(f"{path}: non-finite {key}")
        output[key] = values
    for key in ("detected", "within_tolerance"):
        if np.any((output[key] != 0.0) & (output[key] != 1.0)):
            raise ValueError(f"{path}: {key} must be binary")
    return output


def fit_isotonic(scores: Sequence[float], labels: Sequence[float]) -> dict:
    score = np.asarray(scores, dtype=float)
    label = np.asarray(labels, dtype=float)
    order = np.argsort(score, kind="mergesort")
    score = score[order]
    label = label[order]
    blocks: list[IsotonicBlock] = []
    start = 0
    while start < score.size:
        end = start + 1
        while end < score.size and score[end] == score[start]:
            end += 1
        block_score = score[start:end]
        block_label = label[start:end]
        blocks.append(
            IsotonicBlock(
                x_sum=float(np.sum(block_score)),
                y_sum=float(np.sum(block_label)),
                weight=float(end - start),
                x_min=float(block_score[0]),
                x_max=float(block_score[-1]),
            )
        )
        while (
            len(blocks) >= 2
            and blocks[-2].probability > blocks[-1].probability
        ):
            right = blocks.pop()
            left = blocks.pop()
            blocks.append(
                IsotonicBlock(
                    x_sum=left.x_sum + right.x_sum,
                    y_sum=left.y_sum + right.y_sum,
                    weight=left.weight + right.weight,
                    x_min=left.x_min,
                    x_max=right.x_max,
                )
            )
        start = end
    if len(blocks) < 2:
        raise ValueError("isotonic calibration needs at least two score groups")
    x = [block.x_mean for block in blocks]
    y = [block.probability for block in blocks]
    return {"score": x, "probability": y}


def evaluate_curve(curve: dict, scores: np.ndarray) -> np.ndarray:
    return np.clip(
        np.interp(scores, curve["score"], curve["probability"]),
        0.0,
        1.0,
    )


def probability_metrics(
    probability: np.ndarray,
    labels: np.ndarray,
    *,
    bin_count: int = 10,
) -> dict[str, float]:
    brier = float(np.mean((probability - labels) ** 2))
    ece = 0.0
    for lower in np.linspace(0.0, 1.0, bin_count + 1)[:-1]:
        upper = lower + 1.0 / bin_count
        mask = (probability >= lower) & (
            probability <= upper if upper >= 1.0 else probability < upper
        )
        if not np.any(mask):
            continue
        ece += float(np.mean(mask)) * abs(
            float(np.mean(probability[mask])) - float(np.mean(labels[mask]))
        )
    return {"brier": brier, "ece": float(ece)}


def class_counts(labels: np.ndarray) -> dict[str, int]:
    return {
        "total": int(labels.size),
        "positive": int(np.sum(labels == 1.0)),
        "negative": int(np.sum(labels == 0.0)),
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, choices=("magnetic", "sonar"))
    parser.add_argument("--fit-csv", required=True, type=Path)
    parser.add_argument("--validation-csv", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--calibration-id", default="")
    parser.add_argument("--max-brier", type=float, default=0.20)
    parser.add_argument("--max-ece", type=float, default=0.10)
    parser.add_argument("--min-validation-samples", type=int, default=100)
    parser.add_argument("--min-validation-per-class", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fit = read_labeled_csv(args.fit_csv)
    detection_curve = fit_isotonic(
        fit["detection_score"],
        fit["detected"],
    )
    track_curve = fit_isotonic(
        fit["track_score"],
        fit["within_tolerance"],
    )
    validation_report = None
    approved = False
    if args.validation_csv is not None:
        validation = read_labeled_csv(args.validation_csv)
        detection_probability = evaluate_curve(
            detection_curve,
            validation["detection_score"],
        )
        track_probability = evaluate_curve(
            track_curve,
            validation["track_score"],
        )
        detection_metrics = probability_metrics(
            detection_probability,
            validation["detected"],
        )
        track_metrics = probability_metrics(
            track_probability,
            validation["within_tolerance"],
        )
        detection_counts = class_counts(validation["detected"])
        track_counts = class_counts(validation["within_tolerance"])
        validation_report = {
            "detection": {**detection_metrics, **detection_counts},
            "track": {**track_metrics, **track_counts},
            "sha256": file_sha256(args.validation_csv),
        }
        metric_pass = all(
            metrics["brier"] <= args.max_brier
            and metrics["ece"] <= args.max_ece
            for metrics in (detection_metrics, track_metrics)
        )
        count_pass = all(
            counts["total"] >= args.min_validation_samples
            and counts["positive"] >= args.min_validation_per_class
            and counts["negative"] >= args.min_validation_per_class
            for counts in (detection_counts, track_counts)
        )
        approved = metric_pass and count_pass

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    calibration_id = args.calibration_id or f"{args.source}-{stamp}"
    payload = {
        "schema_version": 1,
        "calibration_id": calibration_id,
        "source": args.source,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "deployment_approved": approved,
        "approval_requirements": {
            "independent_validation_required": True,
            "max_brier": args.max_brier,
            "max_ece": args.max_ece,
            "min_validation_samples": args.min_validation_samples,
            "min_validation_per_class": args.min_validation_per_class,
        },
        "fit_dataset": {
            "path": str(args.fit_csv),
            "sha256": file_sha256(args.fit_csv),
            "detection": class_counts(fit["detected"]),
            "track": class_counts(fit["within_tolerance"]),
        },
        "validation_dataset": validation_report,
        "detection": detection_curve,
        "track": track_curve,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"WROTE {args.output} deployment_approved={str(approved).lower()}"
    )
    return 0 if approved else 2


if __name__ == "__main__":
    raise SystemExit(main())
