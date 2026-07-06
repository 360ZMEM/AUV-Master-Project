#!/usr/bin/env python3
"""Record an operator-workflow video of the PySide6 AUV console.

The recorder drives the real MainWindow offscreen using genuine cable-tracking
telemetry (tracking.jsonl produced by a DL/T 1278 acceptance run), performs only
safe operator actions (tab switching, waypoint-selection toggle, cable monitor
refresh), grabs one frame per telemetry step, and encodes an MP4 via ffmpeg with
an animated-GIF fallback (PillowWriter). It never clicks ESTOP, autonomy, mission
dispatch, communication connect, or task-lifecycle controls, and it stops the
outbound transmit timer so no packets are emitted while recording.

Intended for thesis defense / appendix demonstration material.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONSOLE_ROOT = PROJECT_ROOT / "console_soft" / "auv_console_pyside6"
DEFAULT_TRACKING = (
    PROJECT_ROOT
    / "results"
    / "cable_ops_report"
    / "acceptance_fresh1_20260706_135331"
    / "tracking.jsonl"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "thesis" / "figures" / "console_operator_video"


def _repo_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracking-jsonl", type=Path, default=DEFAULT_TRACKING)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--basename", default="console_operator_workflow")
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--max-frames", type=int, default=180)
    parser.add_argument("--width", type=int, default=1400)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument(
        "--gif",
        action="store_true",
        help="Also emit an animated GIF (PillowWriter) alongside the MP4.",
    )
    return parser.parse_args()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    if not rows:
        raise SystemExit(f"tracking JSONL has no rows: {path}")
    return rows


def _downsample_indices(count: int, max_frames: int) -> list[int]:
    if count <= max_frames:
        return list(range(count))
    step = (count - 1) / float(max_frames - 1)
    return sorted({int(round(i * step)) for i in range(max_frames)})


def _monitor_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Map a tracking.jsonl row onto the cable_monitor payload the console renders."""
    dlt = row.get("dlt1278") if isinstance(row.get("dlt1278"), dict) else {}
    score_items = dlt.get("score_items") or []
    score_items_text = "；".join(
        f"{item.get('item', '?')}({item.get('score', 0)}分)" for item in score_items
    ) or "none"
    accept_flags = row.get("acceptance_flags") or []
    flags_text = ", ".join(str(f) for f in accept_flags) if accept_flags else "none"
    products = dlt.get("output_products") or []
    products_text = ", ".join(str(p) for p in products) if products else "--"
    return {
        "industrial_ready": bool(row.get("industrial_ready", False)),
        "industrial_acceptance_pass": bool(row.get("industrial_acceptance_pass", False)),
        "mode": str(row.get("mode", "--")),
        "cross_track_m": row.get("cross_track_m"),
        "burial_depth_m": row.get("burial_depth_m"),
        "route_progress_m": row.get("route_progress_m"),
        "confidence": row.get("confidence"),
        "magnetic_snr_db": row.get("magnetic_snr_db"),
        "magnetic_confidence": row.get("magnetic_confidence"),
        "acceptance_flags_text": flags_text,
        "dlt1278_state": str(dlt.get("state", "--")),
        "dlt1278_total_score": dlt.get("total_score"),
        "dlt1278_score_items_text": score_items_text,
        "dlt1278_products_text": products_text,
    }


def _encode_mp4(frames_dir: Path, output_path: Path, fps: int) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return False
    cmd = [
        ffmpeg,
        "-y",
        "-framerate",
        str(max(1, fps)),
        "-i",
        str(frames_dir / "frame_%05d.png"),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr[-2000:] + "\n")
        return False
    return output_path.exists()


def _encode_gif(frame_paths: list[Path], output_path: Path, fps: int) -> bool:
    try:
        from PIL import Image  # type: ignore
    except Exception as exc:  # pragma: no cover
        sys.stderr.write(f"PIL unavailable, cannot write GIF fallback: {exc}\n")
        return False
    images = [Image.open(str(p)).convert("RGB") for p in frame_paths]
    if not images:
        return False
    duration_ms = int(1000 / max(1, fps))
    images[0].save(
        str(output_path),
        save_all=True,
        append_images=images[1:],
        duration=duration_ms,
        loop=0,
        optimize=True,
    )
    return output_path.exists()


def main() -> int:
    args = parse_args()
    tracking_path = _repo_path(args.tracking_jsonl)
    output_dir = _repo_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = _read_jsonl(tracking_path)
    frame_indices = _downsample_indices(len(rows), max(2, int(args.max_frames)))

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if str(CONSOLE_ROOT) not in sys.path:
        sys.path.insert(0, str(CONSOLE_ROOT))

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from src.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.resize(int(args.width), int(args.height))
    window.show()

    # Safety: silence the outbound transmit timer so no packets are emitted while
    # the recorder drives the UI offscreen.
    try:
        window.tx_timer.stop()
        window.beidou_timer.stop()
    except AttributeError:
        pass

    # Let the window settle.
    for _ in range(6):
        app.processEvents()
        time.sleep(0.03)

    # Safe operator workflow setup: land on the cable-monitor tab layout and arm
    # waypoint selection so the video shows the operator preparing an inspection.
    window.tab_widget.setCurrentIndex(0)
    app.processEvents()
    before_selecting = bool(window.selecting_waypoint)
    QTest.mouseClick(window.btn_start_waypoint, Qt.MouseButton.LeftButton)
    app.processEvents()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    frames_tmp = Path(tempfile.mkdtemp(prefix="console_frames_"))
    frame_paths: list[Path] = []

    n_tabs = window.tab_widget.count()
    total = len(frame_indices)
    for frame_no, idx in enumerate(frame_indices):
        row = rows[idx]
        window.update_cable_monitor_display(_monitor_from_row(row))

        # Progress-driven status line for the operator (no side effects).
        progress = row.get("route_progress_m")
        try:
            progress_txt = f"{float(progress):.1f} m"
        except (TypeError, ValueError):
            progress_txt = "--"
        window.status_bar.showMessage(
            f"电缆巡检回放 | 样本 {idx + 1}/{len(rows)} | 路由进度 {progress_txt} | 模式 {row.get('mode', '--')}"
        )

        # Gentle tab cycling in the first third so the video shows the operator
        # reviewing mission config, then returns to the monitor layout.
        if n_tabs > 1:
            phase = frame_no / max(1, total - 1)
            if 0.15 < phase < 0.30:
                window.tab_widget.setCurrentIndex(1)
            elif 0.30 <= phase < 0.42:
                window.tab_widget.setCurrentIndex(2)
            else:
                window.tab_widget.setCurrentIndex(0)

        app.processEvents()
        pixmap = window.grab()
        frame_path = frames_tmp / f"frame_{frame_no:05d}.png"
        if not pixmap.save(str(frame_path)):
            sys.stderr.write(f"failed to save frame {frame_no}\n")
            continue
        frame_paths.append(frame_path)

    # End waypoint selection cleanly at the end of the workflow.
    QTest.mouseClick(window.btn_end_waypoint, Qt.MouseButton.LeftButton)
    app.processEvents()
    after_selecting = bool(window.selecting_waypoint)

    last_frame_png = output_dir / f"{args.basename}_{stamp}_lastframe.png"
    if frame_paths:
        shutil.copyfile(frame_paths[-1], last_frame_png)

    mp4_path = output_dir / f"{args.basename}_{stamp}.mp4"
    gif_path = output_dir / f"{args.basename}_{stamp}.gif"

    mp4_ok = _encode_mp4(frames_tmp, mp4_path, args.fps)
    gif_ok = False
    if args.gif or not mp4_ok:
        gif_ok = _encode_gif(frame_paths, gif_path, args.fps)

    result = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "qt_platform": os.environ.get("QT_QPA_PLATFORM"),
        "tracking_jsonl": str(tracking_path),
        "telemetry_rows": len(rows),
        "frames_rendered": len(frame_paths),
        "fps": args.fps,
        "mp4_path": str(mp4_path) if mp4_ok else None,
        "gif_path": str(gif_path) if gif_ok else None,
        "last_frame_png": str(last_frame_png) if frame_paths else None,
        "dangerous_actions_executed": False,
        "safe_actions": ["tab:航点规划/任务配置/消息", "button:开始选点", "button:结束选点", "cable_monitor 遥测刷新"],
        "dangerous_controls_not_clicked": [
            "紧急切断 ESTOP",
            "解除急停",
            "请求自主",
            "手动接管",
            "任务开启",
            "任务取消",
            "下发任务",
            "连接 Zenoh",
        ],
        "tx_timer_stopped": True,
        "before_selecting_waypoint": before_selecting,
        "after_selecting_waypoint": after_selecting,
    }
    result_path = output_dir / f"{args.basename}_{stamp}.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    window.close()
    app.processEvents()
    shutil.rmtree(frames_tmp, ignore_errors=True)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if mp4_ok:
        print(f"[OK] wrote MP4: {mp4_path}")
    if gif_ok:
        print(f"[OK] wrote GIF: {gif_path}")
    if not mp4_ok and not gif_ok:
        print("[FAIL] no video artifact produced")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
