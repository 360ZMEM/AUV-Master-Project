#!/usr/bin/env python3
"""Plot magnetometer lever-arm calibration validation artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _read_residuals(path: Path) -> tuple[list[float], list[float]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return (
        [float(row["time_s"]) for row in rows],
        [float(row["residual_m"]) for row in rows],
    )


def main() -> None:
    args = parse_args()
    input_dir = _resolve(args.input_dir)
    output_dir = _resolve(args.output_dir) if args.output_dir else input_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as exc:
        raise SystemExit(f"matplotlib unavailable: {exc}") from exc

    # 图内统一中文：注入文泉驿正黑（容器内唯一 CJK 字体），负号用 ASCII
    import os
    import matplotlib.font_manager as fm

    _zh_font = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
    if os.path.exists(_zh_font):
        fm.fontManager.addfont(_zh_font)
        plt.rcParams["font.family"] = fm.FontProperties(fname=_zh_font).get_name()
    else:
        plt.rcParams["font.sans-serif"] = ["WenQuanYi Zen Hei", "SimHei"] + plt.rcParams["font.sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams.update({"font.size": 12, "axes.titlesize": 14, "axes.labelsize": 12, "legend.fontsize": 11})

    summary = json.loads((input_dir / "validation_summary.json").read_text(encoding="utf-8"))
    times, residuals = _read_residuals(input_dir / "residuals.csv")

    plt.figure(figsize=(7, 4))
    plt.plot(times, residuals, linewidth=2, label="平移残差（m）")
    plt.xlabel("时间（s）")
    plt.ylabel("残差（m）")
    plt.title("磁力计杆臂标定残差")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "01_mag_extrinsics_residual.png", dpi=180)
    plt.close()

    labels = ["标定前", "标定后"]
    translation_errors = [
        float(summary["initial_translation_error_m"]),
        float(summary["estimated_translation_error_m"]),
    ]
    rotation_errors = [
        float(summary["initial_rotation_error_deg"]),
        float(summary["estimated_rotation_error_deg"]),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(8, 4))
    axes[0].bar(labels, translation_errors, color=["tab:orange", "tab:blue"])
    axes[0].set_title("平移误差")
    axes[0].set_ylabel("m")
    axes[0].grid(True, axis="y", alpha=0.3)

    axes[1].bar(labels, rotation_errors, color=["tab:orange", "tab:blue"])
    axes[1].set_title("旋转误差")
    axes[1].set_ylabel("deg")
    axes[1].grid(True, axis="y", alpha=0.3)

    fig.suptitle("磁力计外参误差下降")
    fig.tight_layout()
    fig.savefig(output_dir / "02_mag_extrinsics_error_reduction.png", dpi=180)
    plt.close(fig)

    manifest = {
        "input_dir": str(input_dir),
        "generated": [
            "01_mag_extrinsics_residual.png",
            "02_mag_extrinsics_error_reduction.png",
        ],
    }
    (output_dir / "plot_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote magnetometer extrinsics plots to {output_dir}")


if __name__ == "__main__":
    main()
