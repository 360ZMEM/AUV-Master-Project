#!/usr/bin/env python3
"""Render active ThuThesis figures from the provenance manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/thesis/figures/thesis_figure_manifest.json"
DRAWIO_GENERATOR = (
    ROOT / "docs/thesis/figures/architecture/generate_architecture_diagrams.py"
)


def load_figures() -> list[dict]:
    with MANIFEST.open(encoding="utf-8") as handle:
        return json.load(handle)["figures"]


def drawio_binary() -> str | None:
    candidates = [
        shutil.which("drawio"),
        "/Applications/draw.io.app/Contents/MacOS/draw.io",
        shutil.which("draw.io"),
    ]
    return next((candidate for candidate in candidates if candidate), None)


def run(command: list[str]) -> None:
    print("+", shlex.join(command))
    environment = os.environ.copy()
    environment.setdefault("AUV_DATA_ROOT", str(ROOT))
    subprocess.run(command, cwd=ROOT, check=True, env=environment)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_source_hashes(item: dict) -> None:
    """Verify external source data before a platform-specific render."""
    for source in item.get("source_sha256", []):
        path = Path(source["path"])
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file():
            raise SystemExit(f"{item['id']}: source missing: {path}")
        digest = sha256_file(path)
        if digest != source["sha256"]:
            raise SystemExit(
                f"{item['id']}: SHA256 mismatch for {path}: "
                f"expected {source['sha256']}, got {digest}"
            )
        print(f"{item['id']}: verified {digest}  {path}")


def resolve_command(command: str) -> list[str]:
    """Use the active interpreter when a platform-local venv is unavailable."""
    parts = shlex.split(command)
    if parts and parts[0] == ".venv/bin/python" and not (ROOT / parts[0]).exists():
        parts[0] = sys.executable
    return parts


def export_drawio(item: dict, executable: str) -> None:
    source = ROOT / item["inputs"][0]
    output = ROOT / item["output"]
    preview = ROOT / item["preview"]
    svg = output.with_suffix(".svg")
    output.parent.mkdir(parents=True, exist_ok=True)
    run([executable, "--export", "--format", "pdf", "--output", str(output), str(source)])
    run([executable, "--export", "--format", "svg", "--output", str(svg), str(source)])
    run(
        [
            executable,
            "--export",
            "--format",
            "png",
            "--scale",
            "2",
            "--output",
            str(preview),
            str(source),
        ]
    )


def select_figures(figures: list[dict], ids: list[str]) -> list[dict]:
    if not ids:
        return figures
    selected = [item for item in figures if item["id"] in ids]
    missing = sorted(set(ids) - {item["id"] for item in selected})
    if missing:
        raise SystemExit(f"unknown figure id(s): {', '.join(missing)}")
    return selected


def preflight(figures: list[dict]) -> int:
    print(f"platform: {platform.system()} {platform.machine()}")
    failures = 0
    for item in figures:
        state = item["reproducibility"]
        missing = [
            value
            for value in item.get("inputs", [])
            if "*" not in value and not (ROOT / value).exists()
        ]
        suffix = f"; missing={missing}" if missing else ""
        print(f"{item['id']}: {state}{suffix}")
        failures += bool(missing)
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", action="append", default=[])
    parser.add_argument(
        "--render",
        choices=("mac", "linux", "drawio"),
        help="render the selected platform class",
    )
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    figures = select_figures(load_figures(), args.id)
    if args.check or not args.render:
        return 1 if preflight(figures) else 0

    selected: list[dict] = []
    for item in figures:
        if args.render == "drawio" and item["kind"] == "drawio":
            selected.append(item)
        elif args.render == "mac" and item["reproducibility"] in {
            "mac_full",
            "mac_render_only",
        }:
            selected.append(item)
        elif args.render == "linux" and item["reproducibility"] == "linux_required":
            selected.append(item)

    drawio_items = [item for item in selected if item["kind"] == "drawio"]
    if drawio_items:
        executable = drawio_binary()
        if not executable:
            raise SystemExit("draw.io CLI not found")
        if any(item["generator"] == str(DRAWIO_GENERATOR.relative_to(ROOT))
               for item in drawio_items):
            run([str(ROOT / ".venv/bin/python"), str(DRAWIO_GENERATOR)])
        for item in drawio_items:
            export_drawio(item, executable)

    commands: list[str] = []
    for item in selected:
        if item["kind"] == "drawio" or not item.get("command"):
            continue
        verify_source_hashes(item)
        if item["command"] not in commands:
            commands.append(item["command"])
    for command in commands:
        run(resolve_command(command))

    print(f"rendered {len(selected)} manifest entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
