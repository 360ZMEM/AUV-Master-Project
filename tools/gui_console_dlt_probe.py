#!/usr/bin/env python3
"""Offscreen PySide6 probe for the cable DL/T runtime dashboard.

The probe injects a representative cable_monitor payload, performs only safe UI
clicks, and saves a screenshot plus a JSON result record. It must not click
ESTOP, autonomy, mission dispatch, communication connect, or task lifecycle
buttons.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONSOLE_ROOT = PROJECT_ROOT / "console_soft" / "auv_console_pyside6"


def _repo_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "results" / "visual_feedback" / "gui_pyside6_dlt_probe",
    )
    parser.add_argument("--wait-seconds", type=float, default=0.4)
    parser.add_argument("--width", type=int, default=1400)
    parser.add_argument("--height", type=int, default=900)
    return parser.parse_args()


def _sample_monitor() -> dict[str, Any]:
    return {
        "industrial_ready": True,
        "industrial_acceptance_pass": True,
        "mode": "track",
        "cross_track_m": 0.42,
        "burial_depth_m": 1.42,
        "route_progress_m": 58.7,
        "confidence": 0.956,
        "magnetic_snr_db": 87.3,
        "magnetic_confidence": 0.931,
        "acceptance_flags_text": "none",
        "dlt1278_state": "注意状态",
        "dlt1278_total_score": 24,
        "dlt1278_score_items_text": "海缆埋深不足(16分)；埋深估计精度未达 0.15m(8分)",
        "dlt1278_products_text": "tracking.jsonl, inspection_summary.json, dlt1278_report.md, operator_view/*.png",
    }


def main() -> int:
    args = parse_args()
    output_dir = _repo_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

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

    deadline = time.time() + max(float(args.wait_seconds), 0.0)
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)

    sample = _sample_monitor()
    window.update_cable_monitor_display(sample)
    app.processEvents()

    initial_tab_index = window.tab_widget.currentIndex()
    initial_tab_text = window.tab_widget.tabText(initial_tab_index)

    window.tab_widget.setCurrentIndex(1)
    app.processEvents()
    after_task_tab_text = window.tab_widget.tabText(window.tab_widget.currentIndex())

    window.tab_widget.setCurrentIndex(0)
    app.processEvents()
    before_button_selecting = bool(window.selecting_waypoint)
    QTest.mouseClick(window.btn_start_waypoint, Qt.MouseButton.LeftButton)
    app.processEvents()

    result = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "qt_platform": os.environ.get("QT_QPA_PLATFORM"),
        "dangerous_actions_executed": False,
        "clicked_controls": ["tab:任务配置", "tab:航点规划", "button:开始选点"],
        "dangerous_controls_not_clicked": [
            "紧急切断 ESTOP",
            "解除急停",
            "请求自主",
            "手动接管",
            "下发任务",
            "连接 Zenoh",
            "任务开启",
            "任务取消",
        ],
        "initial_tab_index": initial_tab_index,
        "initial_tab_text": initial_tab_text,
        "after_task_tab_text": after_task_tab_text,
        "after_return_tab_text": window.tab_widget.tabText(window.tab_widget.currentIndex()),
        "before_button_selecting_waypoint": before_button_selecting,
        "after_button_selecting_waypoint": bool(window.selecting_waypoint),
        "after_button_start_enabled": bool(window.btn_start_waypoint.isEnabled()),
        "after_button_end_enabled": bool(window.btn_end_waypoint.isEnabled()),
        "status_message": window.status_bar.currentMessage(),
        "labels": {
            "ready": window.lbl_cable_ready.text(),
            "metrics": window.lbl_cable_metrics.text(),
            "quality": window.lbl_cable_quality.text(),
            "dlt": window.lbl_cable_dlt.text(),
            "score_items": window.lbl_cable_score_items.text(),
            "flags": window.lbl_cable_flags.text(),
            "products": window.lbl_cable_products.text(),
        },
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = output_dir / f"console_dlt_probe_{stamp}.png"
    result_path = output_dir / f"console_dlt_probe_{stamp}.json"
    pixmap = window.grab()
    result["screenshot_path"] = str(screenshot_path)
    result["screenshot_saved"] = bool(pixmap.save(str(screenshot_path)))
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    window.close()
    app.processEvents()
    return 0 if result["screenshot_saved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
