#!/usr/bin/env python3
"""Open the real PySide6 console and activate its ESTOP button on a timer."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CONSOLE = ROOT / "console_soft/auv_console_pyside6"
sys.path.insert(0, str(CONSOLE))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from main import apply_console_theme
from src.ui.main_window import MainWindow


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delay", type=float, default=12.0)
    parser.add_argument("--hold", type=float, default=35.0)
    parser.add_argument("--screenshot", required=True)
    parser.add_argument(
        "--config",
        default=str(CONSOLE / "console_config.defense.yaml"),
    )
    args = parser.parse_args()

    os.environ.setdefault("AUV_CONSOLE_THEME", "dark")
    app = QApplication(sys.argv[:1])
    apply_console_theme(app, "dark")
    window = MainWindow(config_file=args.config)
    window.resize(1600, 1000)
    window.show()

    screenshot = Path(args.screenshot).resolve()
    screenshot.parent.mkdir(parents=True, exist_ok=True)

    def activate() -> None:
        # Use the actual button signal path used by an operator click.
        window.btn_estop.click()
        QTimer.singleShot(900, lambda: window.grab().save(str(screenshot)))

    QTimer.singleShot(max(0, int(args.delay * 1000)), activate)
    QTimer.singleShot(max(1000, int((args.delay + args.hold) * 1000)), window.close)
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
