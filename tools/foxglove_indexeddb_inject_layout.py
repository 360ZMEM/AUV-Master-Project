#!/usr/bin/env python3
"""Inject a Foxglove layout JSON into the browser IndexedDB cache.

Observed Foxglove Web storage shape on 2026-07-05:

- DB: ``foxglove-layouts``
- Store: ``layouts``
- keyPath: ``["namespace", "layout.id"]``
- Current project namespace example: ``remote-om_0eTMB6abmAEa7CFH``
- Layout data lives in ``layout.baseline.data`` and ``layout.working.data``

This is an implementation detail of Foxglove Web, so keep it as an experimental
fast iteration path. The safer production path remains importing once and
reusing the saved ``layoutId`` deep link.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
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
DEFAULT_NAMESPACE = "remote-om_0eTMB6abmAEa7CFH"
DEFAULT_LAYOUT_ID = "lay_0eTMD35mSIuRpPoy"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--layout",
        default="tmp/foxglove_layout/auv_layout.generated.json",
        help="Layout JSON path relative to repo root, or absolute path.",
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Foxglove URL to open before injection.")
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
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--layout-id", default=DEFAULT_LAYOUT_ID)
    parser.add_argument("--layout-name", default="auv_layout.generated")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--pause-for-login", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect storage only; do not write.",
    )
    parser.add_argument(
        "--screenshot",
        default="results/visual_feedback/foxglove/indexeddb_inject_layout.png",
        help="Screenshot output path after injection.",
    )
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    return parser.parse_args()


def _repo_path(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


INJECT_JS = r"""
async ({ namespace, layoutId, layoutName, layoutData, savedAt, dryRun }) => {
  function openDB(name) {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(name);
      req.onerror = () => reject(req.error);
      req.onsuccess = () => resolve(req.result);
    });
  }

  function txRequest(db, mode, callback) {
    return new Promise((resolve, reject) => {
      const tx = db.transaction("layouts", mode);
      const store = tx.objectStore("layouts");
      const req = callback(store);
      req.onerror = () => reject(req.error);
      req.onsuccess = () => resolve(req.result);
    });
  }

  const db = await openDB("foxglove-layouts");
  const storeNames = [...db.objectStoreNames];
  const current = await txRequest(db, "readonly", (store) => store.get([namespace, layoutId]));
  const before = {
    storeNames,
    found: Boolean(current),
    keyPath: db.transaction("layouts", "readonly").objectStore("layouts").keyPath,
    existingName: current?.layout?.name,
    existingConfigCount: current?.layout?.working?.data?.configById
      ? Object.keys(current.layout.working.data.configById).length
      : null,
  };

  if (dryRun) {
    db.close();
    return { dryRun: true, before };
  }

  const layoutRecord = current ?? {
    namespace,
    layout: {
      id: layoutId,
      orgId: namespace.replace(/^remote-/, ""),
      name: layoutName,
      folderName: undefined,
      permission: "CREATOR_WRITE",
      syncInfo: { status: "tracked" },
    },
  };

  layoutRecord.namespace = namespace;
  layoutRecord.layout.id = layoutId;
  layoutRecord.layout.name = layoutName || layoutRecord.layout.name || layoutId;
  layoutRecord.layout.baseline = { data: layoutData, savedAt };
  layoutRecord.layout.working = { data: layoutData, savedAt };
  layoutRecord.layout.lastViewedAt = savedAt;
  layoutRecord.layout.syncInfo = layoutRecord.layout.syncInfo || { status: "tracked" };

  await txRequest(db, "readwrite", (store) => store.put(layoutRecord));
  const after = await txRequest(db, "readonly", (store) => store.get([namespace, layoutId]));
  db.close();

  return {
    dryRun: false,
    before,
    after: {
      found: Boolean(after),
      name: after?.layout?.name,
      configCount: after?.layout?.working?.data?.configById
        ? Object.keys(after.layout.working.data.configById).length
        : null,
      savedAt: after?.layout?.working?.savedAt,
    },
  };
}
"""


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

    layout_data = json.loads(layout_path.read_text(encoding="utf-8"))
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
            print("[WARN] Foxglove did not reach networkidle; continuing with IndexedDB access.")
        result = page.evaluate(
            INJECT_JS,
            {
                "namespace": args.namespace,
                "layoutId": args.layout_id,
                "layoutName": args.layout_name,
                "layoutData": layout_data,
                "savedAt": _iso_now(),
                "dryRun": args.dry_run,
            },
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))

        if not args.dry_run:
            page.reload(wait_until="domcontentloaded", timeout=args.timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=min(args.timeout_ms, 10_000))
            except PlaywrightTimeoutError:
                print("[WARN] Foxglove did not reach networkidle after reload; taking screenshot anyway.")
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"[OK] injected layout: {layout_path}")
            print(f"[OK] screenshot: {screenshot_path}")
        context.close()
        if browser is not None:
            browser.close()


if __name__ == "__main__":
    try:
        main()
    except PlaywrightTimeoutError as exc:
        raise SystemExit(f"Playwright timeout: {exc}") from exc
