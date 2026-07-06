#!/usr/bin/env python3
"""PySide6 console feedback-loop scaffold.

Default mode captures a screenshot only. It does not click ESTOP, autonomy, or
mission buttons unless future scripts add explicit reviewed actions.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch", action="store_true", help="Launch the PySide6 console before screenshot")
    parser.add_argument("--screenshot-only", action="store_true", help="Capture screenshot and exit")
    parser.add_argument("--wait-seconds", type=float, default=3.0)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "results/visual_feedback/gui")
    return parser.parse_args()


def _capture_screenshot(path: Path) -> bool:
    try:
        import pyautogui  # type: ignore
    except Exception as exc:
        print(f"[WARN] pyautogui unavailable, screenshot skipped: {exc}")
        return False
    image = pyautogui.screenshot()
    image.save(path)
    return True


def _capture_qt_offscreen(path: Path, wait_seconds: float) -> bool:
    """Render the PySide6 console without a desktop session and save a widget grab."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    console_root = PROJECT_ROOT / "console_soft/auv_console_pyside6"
    if str(console_root) not in sys.path:
        sys.path.insert(0, str(console_root))

    try:
        from PySide6.QtWidgets import QApplication
        from src.ui.main_window import MainWindow
    except Exception as exc:
        print(f"[WARN] Qt offscreen capture unavailable: {exc}")
        return False

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.resize(1400, 900)
    window.show()
    deadline = time.time() + max(float(wait_seconds), 0.0)
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)
    app.processEvents()
    pixmap = window.grab()
    ok = pixmap.save(str(path))
    window.close()
    app.processEvents()
    return bool(ok)


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    proc = None
    desktop_available = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    use_external_launch = args.launch and desktop_available
    if use_external_launch:
        proc = subprocess.Popen(
            [sys.executable, str(PROJECT_ROOT / "console_soft/auv_console_pyside6/main.py")],
            cwd=str(PROJECT_ROOT / "console_soft/auv_console_pyside6"),
        )
    time.sleep(max(float(args.wait_seconds), 0.0))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = output_dir / f"console_{stamp}.png"
    captured = _capture_screenshot(screenshot_path)
    capture_backend = "pyautogui"
    if not captured and args.launch:
        captured = _capture_qt_offscreen(screenshot_path, wait_seconds=0.2)
        capture_backend = "qt_offscreen"
    report = [
        "# GUI Console Feedback Record",
        "",
        f"- Launch requested: {args.launch}",
        f"- External launch used: {use_external_launch}",
        f"- Capture backend: {capture_backend}",
        f"- Screenshot captured: {captured}",
        f"- Screenshot path: `{screenshot_path}`",
        "- Dangerous actions executed: false",
        "",
    ]
    (output_dir / f"console_{stamp}.md").write_text("\n".join(report), encoding="utf-8")
    if proc is not None and args.screenshot_only:
        proc.terminate()
    print(f"[OK] wrote feedback record in {output_dir}")


if __name__ == "__main__":
    main()
