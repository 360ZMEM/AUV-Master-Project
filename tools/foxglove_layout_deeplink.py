#!/usr/bin/env python3
"""Generate Foxglove layout links and local import hints.

Foxglove Web does not publicly support loading arbitrary exported layout JSON
through a base64 query parameter. The practical no-file-picker path is to import
the layout once, then reuse the saved layoutId in a shareable link.
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from urllib.parse import quote, urlencode


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WEB_BASE = "https://app.foxglove.dev/guanwen/p/prj_0eTMB6alu9ojy3u3/view"
DEFAULT_LAYOUT_ID = "lay_0eTMD35mSIuRpPoy"
DEFAULT_WS_URL = "ws://localhost:8765"
DEFAULT_HOST_REPO_ROOT = "/Users/auv_user/coding/AUV-Master-Project"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Foxglove layout deep links")
    parser.add_argument(
        "--layout",
        default="tmp/foxglove_layout/auv_layout.generated.json",
        help="Layout JSON path relative to the repo root",
    )
    parser.add_argument(
        "--web-base",
        default=DEFAULT_WEB_BASE,
        help="Foxglove web project view URL without query string",
    )
    parser.add_argument(
        "--layout-id",
        default=DEFAULT_LAYOUT_ID,
        help="Saved Foxglove layoutId after one-time import",
    )
    parser.add_argument(
        "--ws-url",
        default=DEFAULT_WS_URL,
        help="Foxglove WebSocket URL",
    )
    parser.add_argument(
        "--host-repo-root",
        default=DEFAULT_HOST_REPO_ROOT,
        help="Repo root path on the host machine used by the browser file picker",
    )
    parser.add_argument(
        "--write-url-file",
        default="tmp/foxglove_layout/open_auv_layout.url",
        help="Write the recommended deep link to this text file",
    )
    parser.add_argument(
        "--print-base64-experiment",
        action="store_true",
        help="Also print an unsupported base64 layout URL for diagnostics",
    )
    return parser.parse_args()


def _repo_path(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def _host_path(repo_path: Path, host_repo_root: str) -> str:
    rel = repo_path.resolve().relative_to(REPO_ROOT)
    return str(Path(host_repo_root) / rel)


def _layout_base64url(layout_path: Path) -> str:
    data = json.loads(layout_path.read_text(encoding="utf-8"))
    compact = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(compact).decode("ascii").rstrip("=")


def main() -> None:
    args = parse_args()
    layout_path = _repo_path(args.layout)
    if not layout_path.exists():
        raise SystemExit(f"layout not found: {layout_path}")

    query = {
        "layoutId": args.layout_id,
        "ds": "foxglove-websocket",
        "ds.url": args.ws_url,
    }
    recommended_url = f"{args.web_base}?{urlencode(query)}"

    url_file = _repo_path(args.write_url_file)
    url_file.parent.mkdir(parents=True, exist_ok=True)
    url_file.write_text(recommended_url + "\n", encoding="utf-8")

    print("[recommended]")
    print(recommended_url)
    print()
    print("[url_file]")
    print(url_file)
    print()
    print("[one_time_import_host_path]")
    print(_host_path(layout_path, args.host_repo_root))

    if args.print_base64_experiment:
        encoded = _layout_base64url(layout_path)
        experiment_query = {
            "ds": "foxglove-websocket",
            "ds.url": args.ws_url,
            "layout": encoded,
        }
        print()
        print("[unsupported_base64_experiment]")
        print(f"{args.web_base}?{urlencode(experiment_query, quote_via=quote)}")


if __name__ == "__main__":
    main()
