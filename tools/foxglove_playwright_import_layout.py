#!/usr/bin/env python3
"""Import a Foxglove layout JSON through Playwright without an OS file picker.

This uses the standard Playwright file chooser interception path:

1. Open Foxglove Web with a persistent browser profile.
2. Open the layout menu.
3. Click "Import from file" / "从文件导入".
4. Feed the JSON file directly to the file chooser.

The script does not bypass login. Use ``--pause-for-login`` the first time with a
fresh Playwright profile, then reuse the same ``--user-data-dir``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = (
    "https://app.foxglove.dev/guanwen/p/prj_0eTMB6alu9ojy3u3/view"
    "?layoutId=lay_0eTMD35mSIuRpPoy"
    "&ds=foxglove-websocket"
    "&ds.url=ws%3A%2F%2Flocalhost%3A8765"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--layout",
        default="tmp/foxglove_layout/auv_layout.generated.json",
        help="Layout JSON path relative to repo root, or absolute path.",
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Foxglove URL to open before import.")
    parser.add_argument(
        "--user-data-dir",
        default="tmp/foxglove_playwright_profile",
        help="Persistent Playwright profile directory. Reuse it to keep login state.",
    )
    parser.add_argument(
        "--storage-state",
        default=None,
        help="Optional Playwright auth/storage state JSON. When set, uses this login state instead of the persistent profile.",
    )
    parser.add_argument("--headless", action="store_true", help="Run browser headless.")
    parser.add_argument(
        "--pause-for-login",
        action="store_true",
        help="Pause after opening Foxglove so the operator can log in once.",
    )
    parser.add_argument(
        "--screenshot",
        default="results/visual_feedback/foxglove/playwright_import_layout.png",
        help="Screenshot output path.",
    )
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    return parser.parse_args()


def _repo_path(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def _first_available(page, selectors: list[str], timeout_ms: int):
    last_error: Exception | None = None
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout_ms)
            return locator
        except Exception as exc:  # Playwright has multiple selector timeout paths.
            last_error = exc
    raise RuntimeError(f"none of the selectors matched: {selectors}") from last_error


def main() -> None:
    args = parse_args()
    layout_path = _repo_path(args.layout).resolve()
    user_data_dir = _repo_path(args.user_data_dir)
    storage_state_path = _repo_path(args.storage_state).resolve() if args.storage_state else None
    screenshot_path = _repo_path(args.screenshot)

    if not layout_path.exists():
        raise SystemExit(f"layout not found: {layout_path}")
    if storage_state_path is not None and not storage_state_path.exists():
        raise SystemExit(f"storage state not found: {storage_state_path}")

    user_data_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = None
        if storage_state_path is not None:
            browser = p.chromium.launch(headless=args.headless, args=["--disable-dev-shm-usage"])
            context = browser.new_context(
                storage_state=str(storage_state_path),
                viewport={"width": 1600, "height": 1000},
            )
        else:
            context = p.chromium.launch_persistent_context(
                str(user_data_dir),
                headless=args.headless,
                viewport={"width": 1600, "height": 1000},
                args=["--disable-dev-shm-usage"],
            )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout_ms)

        if args.pause_for_login:
            print("[INFO] Finish Foxglove login in the Playwright browser, then press Enter.")
            input()
            page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout_ms)

        try:
            page.wait_for_load_state("networkidle", timeout=min(args.timeout_ms, 10_000))
        except PlaywrightTimeoutError:
            print("[WARN] Foxglove did not reach networkidle; continuing with DOM-based readiness.")

        layout_button = _first_available(
            page,
            [
                "button:has-text('auv_')",
                "button:has-text('layout.generated')",
                "button:has-text('默认')",
                "button:has-text('Default')",
                "[role=button]:has-text('layout.generated')",
                "[role=button]:has-text('默认')",
                "[role=button]:has-text('Default')",
            ],
            args.timeout_ms,
        )
        layout_button.click()

        import_item = _first_available(
            page,
            [
                "[role=menuitem]:has-text('从文件导入')",
                "[role=menuitem]:has-text('Import from file')",
                "text=/Import from file|从文件导入/",
            ],
            args.timeout_ms,
        )

        with page.expect_file_chooser(timeout=args.timeout_ms) as chooser_info:
            import_item.click()
        chooser = chooser_info.value
        chooser.set_files(str(layout_path))

        page.wait_for_timeout(2000)
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"[OK] imported layout: {layout_path}")
        print(f"[OK] screenshot: {screenshot_path}")
        context.close()
        if browser is not None:
            browser.close()


if __name__ == "__main__":
    try:
        main()
    except PlaywrightTimeoutError as exc:
        raise SystemExit(f"Playwright timeout: {exc}") from exc
