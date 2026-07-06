#!/usr/bin/env python3
"""Foxglove public-page feedback loop scaffold.

This script intentionally does not bypass login. It opens the requested URL,
optionally waits for the operator to finish authentication, and captures a
screenshot for AI/UI review.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import subprocess
import sys
import time
import webbrowser

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--wait-login", action="store_true")
    parser.add_argument("--wait-seconds", type=float, default=5.0)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "results/visual_feedback/foxglove")
    parser.add_argument("--check-process", action="append", default=["foxglove", "zenoh"])
    return parser.parse_args()


def _process_running(pattern: str) -> bool:
    try:
        result = subprocess.run(["pgrep", "-af", pattern], check=False, capture_output=True, text=True)
    except OSError:
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def _capture_screenshot(path: Path) -> bool:
    try:
        import pyautogui  # type: ignore
    except Exception as exc:
        print(f"[WARN] pyautogui unavailable, screenshot skipped: {exc}")
        return False
    image = pyautogui.screenshot()
    image.save(path)
    return True


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    status_lines = ["# Foxglove Feedback Loop Check", ""]
    for pattern in args.check_process:
        running = _process_running(pattern)
        status_lines.append(f"- Process `{pattern}` running: {running}")

    webbrowser.open(args.url)
    if args.wait_login:
        print("[INFO] Complete Foxglove login in the browser, then press Enter here.")
        input()
    elif args.wait_seconds > 0:
        time.sleep(args.wait_seconds)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = output_dir / f"foxglove_{stamp}.png"
    captured = _capture_screenshot(screenshot_path)
    status_lines.append(f"- URL: {args.url}")
    status_lines.append(f"- Screenshot captured: {captured}")
    status_lines.append(f"- Screenshot path: `{screenshot_path}`")
    (output_dir / f"foxglove_{stamp}.md").write_text("\n".join(status_lines) + "\n", encoding="utf-8")
    print(f"[OK] wrote feedback record in {output_dir}")


if __name__ == "__main__":
    main()
