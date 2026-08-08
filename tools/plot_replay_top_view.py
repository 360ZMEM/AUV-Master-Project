#!/usr/bin/env python3
"""Generate a static 2D top-view image for cable replay verification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

sys.path.insert(0, str(PROJECT_ROOT / "brain_linux" / "src" / "auv_control"))
from auv_decision_ros.cable_prior_adapter import load_cable_map_from_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bag", type=Path, required=True, help="MCAP file or rosbag directory.")
    parser.add_argument("--tracking-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="3f 电缆回放俯视图")
    return parser.parse_args()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _mcap_chunks(path: Path) -> list[Path]:
    path = _resolve(path)
    if path.is_file():
        return [path]
    chunks = sorted(path.rglob("*.mcap"))
    if not chunks:
        raise SystemExit(f"no .mcap files found under: {path}")
    return chunks


def _read_tracking_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(_resolve(path).read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise SystemExit(f"invalid yaml config: {path}")
    tracking_cfg = payload.get("cable_tracking")
    if not isinstance(tracking_cfg, dict):
        raise SystemExit(f"missing cable_tracking block: {path}")
    return tracking_cfg


def _read_odom_xy(chunks: list[Path]) -> np.ndarray:
    try:
        from mcap_ros2.reader import read_ros2_messages
    except ImportError as exc:
        raise SystemExit("mcap and mcap-ros2-support are required: pip install mcap mcap-ros2-support") from exc

    rows: list[list[float]] = []
    for chunk in chunks:
        for decoded in read_ros2_messages(str(chunk), topics=["/auv/state/filtered"]):
            msg = decoded.ros_msg
            pose = getattr(msg, "pose", None)
            if pose is None:
                continue
            position = pose.pose.position
            rows.append([float(position.x), float(position.y), float(position.z)])
    if not rows:
        raise SystemExit("no /auv/state/filtered odometry found")
    return np.asarray(rows, dtype=float)


def _prior_xy(tracking_cfg: dict[str, Any]) -> np.ndarray:
    cable_map = load_cable_map_from_config(tracking_cfg, project_root=PROJECT_ROOT)
    points_xy = np.asarray(cable_map.points_xy_m, dtype=float)
    if points_xy.ndim != 2 or points_xy.shape[1] < 2:
        raise SystemExit("invalid prior points from tracking config")
    return points_xy[:, :2]


def _save_manifest(output: Path, payload: dict[str, Any]) -> None:
    output.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    bag_chunks = _mcap_chunks(args.bag)
    tracking_cfg = _read_tracking_config(args.tracking_config)
    odom_xyz = _read_odom_xy(bag_chunks)
    prior_xy = _prior_xy(tracking_cfg)

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
    plt.rcParams.update({"font.size": 12, "axes.titlesize": 14, "axes.labelsize": 12, "legend.fontsize": 10})

    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8.8, 5.8))
    ax.plot(prior_xy[:, 0], prior_xy[:, 1], color="#d4a017", linewidth=3.0, label="电缆先验")
    ax.plot(odom_xyz[:, 0], odom_xyz[:, 1], color="#1f6fd6", linewidth=2.2, alpha=0.95, label="AUV 轨迹")
    ax.scatter([odom_xyz[0, 0]], [odom_xyz[0, 1]], s=60, color="#e67e22", label="起点")
    ax.scatter([odom_xyz[-1, 0]], [odom_xyz[-1, 1]], s=70, color="#2ecc71", label="最新")

    if len(odom_xyz) >= 2:
        dx = odom_xyz[-1, 0] - odom_xyz[-2, 0]
        dy = odom_xyz[-1, 1] - odom_xyz[-2, 1]
        ax.arrow(
            odom_xyz[-1, 0],
            odom_xyz[-1, 1],
            dx,
            dy,
            width=0.25,
            head_width=1.2,
            head_length=1.8,
            color="#1f6fd6",
            length_includes_head=True,
            zorder=5,
        )

    x_min = min(float(np.min(prior_xy[:, 0])), float(np.min(odom_xyz[:, 0])))
    x_max = max(float(np.max(prior_xy[:, 0])), float(np.max(odom_xyz[:, 0])))
    y_min = min(float(np.min(prior_xy[:, 1])), float(np.min(odom_xyz[:, 1])))
    y_max = max(float(np.max(prior_xy[:, 1])), float(np.max(odom_xyz[:, 1])))

    pad_x = max(6.0, 0.08 * (x_max - x_min))
    pad_y = max(6.0, 0.10 * (y_max - y_min))
    ax.set_xlim(x_min - pad_x, x_max + pad_x)
    ax.set_ylim(y_min - pad_y, y_max + pad_y)

    scale_len = 10.0
    scale_x0 = x_min + pad_x * 0.45
    scale_y0 = y_min - pad_y * 0.35
    ax.plot([scale_x0, scale_x0 + scale_len], [scale_y0, scale_y0], color="black", linewidth=3.0)
    ax.plot([scale_x0, scale_x0], [scale_y0 - 0.7, scale_y0 + 0.7], color="black", linewidth=2.0)
    ax.plot([scale_x0 + scale_len, scale_x0 + scale_len], [scale_y0 - 0.7, scale_y0 + 0.7], color="black", linewidth=2.0)
    ax.text(scale_x0 + scale_len / 2.0, scale_y0 - 1.7, "10 m", ha="center", va="top", color="black", fontsize=11)

    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")
    ax.grid(True, alpha=0.3, color="#b0b0b0")
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("世界坐标 x（m）")
    ax.set_ylabel("世界坐标 y（m）")
    ax.set_title(args.title)
    legend = ax.legend(loc="upper left", framealpha=0.9)
    fig.tight_layout()
    fig.savefig(output, dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)

    _save_manifest(
        output,
        {
            "bag_chunks": [str(chunk) for chunk in bag_chunks],
            "tracking_config": str(_resolve(args.tracking_config)),
            "point_count": int(odom_xyz.shape[0]),
            "prior_point_count": int(prior_xy.shape[0]),
            "output": str(output),
        },
    )
    print(f"[OK] wrote {output}")


if __name__ == "__main__":
    main()
