#!/usr/bin/env python3
"""Locate, regenerate, export, validate, and preview thesis figures.

The Draw.io editing loop deliberately separates ``generate`` from ``export``:
``generate`` rewrites generated .drawio sources, while ``export`` preserves any
manual Draw.io edits and only refreshes publication PDF/PNG outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
ARCH = ROOT / "docs/thesis/figures/architecture"
PREVIEW = ROOT / ".auv_data/thesis-figure-workflow"


@dataclass(frozen=True)
class Figure:
    id: str
    stem: str
    tex: str
    label: str
    source: str = "drawio"
    generator: str = "docs/thesis/figures/architecture/generate_architecture_diagrams.py"

    @property
    def source_path(self) -> Path:
        if self.source == "drawio":
            return ARCH / f"{self.stem}.drawio"
        return ROOT / self.generator

    @property
    def pdf(self) -> Path:
        return ARCH / f"{self.stem}.pdf"

    @property
    def png(self) -> Path:
        return ARCH / f"{self.stem}.png"


FIGURES = {
    f.id: f
    for f in [
        Figure("F01", "auv_thesis_technical_route", "thuthesis/data/auv-chap01.tex", "fig:ch01-technical-route"),
        Figure("F02", "auv_system_autonomy_functional_loop", "thuthesis/data/auv-chap02.tex", "fig:ch02-autonomy-loop"),
        Figure("F03", "auv_v2_dual_brain_async_hardware", "thuthesis/data/auv-chap02.tex", "fig:ch02-dual-brain-async"),
        Figure("F04", "auv_v2_five_layer_functional_architecture", "thuthesis/data/auv-chap02.tex", "fig:ch02-five-layer-architecture"),
        Figure("F05", "auv_system_verification_deployment_ladder", "thuthesis/data/auv-chap02.tex", "fig:ch02-verification-ladder"),
        Figure("F06", "auv_v2_emergency_transition", "thuthesis/data/auv-chap02.tex", "fig:ch02-emergency-arbitration"),
        Figure("F07", "auv_v2_mission_lifecycle_flow", "thuthesis/data/auv-chap02.tex", "fig:ch02-mission-lifecycle"),
        Figure("F08", "auv_v2_uncertainty_highway", "thuthesis/data/auv-chap03.tex", "fig:ch03-uncertainty-highway"),
        Figure("F09", "cable_acoustic_magnetic_perception_pipeline", "thuthesis/data/auv-chap03.tex", "fig:ch03-cable-perception-pipeline", "python", "tools/render_cable_perception_pipeline_figure.py"),
        Figure("F10", "auv_v2_mission_state_machine", "thuthesis/data/auv-chap04.tex", "fig:ch04-mission-state-machine"),
        Figure("F11", "auv_v2_behavior_tree_illustration", "thuthesis/data/auv-chap04.tex", "fig:ch04-behavior-tree-core"),
        Figure("F12", "../magnetics/fwhm_depth_principle", "thuthesis/data/auv-chap02.tex", "fig:ch02-fwhm-depth-principle", "python", "tools/independent/plot_fwhm_depth_principle.py"),
        Figure("F13", "cable_active_crossing_observability", "thuthesis/data/auv-chap02.tex", "fig:ch02-active-crossing", "python", "tools/render_cable_active_crossing_figure.py"),
    ]
}


def run(command: list[str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def selected(ids: list[str]) -> list[Figure]:
    if not ids or ids == ["all"]:
        return list(FIGURES.values())
    result: list[Figure] = []
    for raw in ids:
        key = raw.upper()
        if key not in FIGURES:
            raise SystemExit(f"unknown figure {raw}; choose F01..F13 or all")
        result.append(FIGURES[key])
    return result


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def locate(figures: list[Figure]) -> None:
    for f in figures:
        print(f"{f.id}  {f.label}")
        print(f"  source: {f.source_path.relative_to(ROOT)} ({f.source})")
        print(f"  output: {f.pdf.relative_to(ROOT)}")
        print(f"  TeX:    {f.tex}")


def generate(figures: list[Figure]) -> None:
    drawio = [f for f in figures if f.source == "drawio"]
    python_figs = [f for f in figures if f.source == "python"]
    if drawio:
        # The shared generator is intentionally run once; it owns the generated
        # Draw.io XML. Use export directly after manual Draw.io refinement.
        run([sys.executable, str(ROOT / drawio[0].generator)])
    for f in python_figs:
        run([sys.executable, str(f.source_path)])


def export(figures: list[Figure]) -> None:
    if shutil.which("drawio") is None:
        raise SystemExit("drawio CLI is not on PATH")
    for f in figures:
        if f.source != "drawio":
            run([sys.executable, str(f.source_path)])
            continue
        if not f.source_path.is_file():
            raise SystemExit(f"missing source: {f.source_path}")
        run(["drawio", "--export", "--crop", "--format", "pdf", "--output", str(f.pdf), str(f.source_path)])
        run(["drawio", "--export", "--crop", "--format", "png", "--scale", "2", "--output", str(f.png), str(f.source_path)])


def check(figures: list[Figure]) -> None:
    errors: list[str] = []
    drawio = [f for f in figures if f.source == "drawio"]
    if drawio:
        run([sys.executable, str(ARCH / "validate_drawio_architecture.py"), "--strict-publication"])
    for f in figures:
        tex = ROOT / f.tex
        for path, role in ((f.source_path, "source"), (f.pdf, "PDF"), (f.png, "PNG")):
            if not path.is_file():
                errors.append(f"{f.id}: missing {role} {path.relative_to(ROOT)}")
        if tex.is_file() and f.label not in tex.read_text(encoding="utf-8"):
            errors.append(f"{f.id}: label {f.label} not found in {f.tex}")
        if f.source == "drawio" and f.source_path.is_file():
            try:
                ET.parse(f.source_path)
            except ET.ParseError as exc:
                errors.append(f"{f.id}: invalid Draw.io XML: {exc}")
        if f.pdf.is_file():
            info = subprocess.run(["pdfinfo", str(f.pdf)], text=True, capture_output=True, check=True).stdout
            pages = next((line.split(":", 1)[1].strip() for line in info.splitlines() if line.startswith("Pages:")), "?")
            if pages != "1":
                errors.append(f"{f.id}: expected one PDF page, got {pages}")
        if f.source_path.is_file() and f.pdf.is_file() and f.pdf.stat().st_mtime < f.source_path.stat().st_mtime:
            errors.append(f"{f.id}: PDF is older than editable source; run export")
        if f.pdf.is_file():
            print(f"OK {f.id}: pdf={digest(f.pdf)} png={digest(f.png) if f.png.is_file() else 'missing'}")
    if errors:
        raise SystemExit("\n".join(f"ERROR {item}" for item in errors))


def preview(figures: list[Figure]) -> None:
    PREVIEW.mkdir(parents=True, exist_ok=True)
    images: list[str] = []
    for f in figures:
        if not f.png.is_file():
            raise SystemExit(f"missing {f.png}; run export first")
        images.append(str(f.png))
    output = PREVIEW / ("contact-sheet-" + "-".join(f.id for f in figures) + ".png")
    run(["convert", *images, "-thumbnail", "900x620", "-background", "white", "-gravity", "center", "-extent", "920x660", "+append", str(output)])
    print(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("locate", "generate", "export", "check", "preview", "cycle"))
    parser.add_argument("figures", nargs="*", default=["all"], help="F01..F13 or all")
    args = parser.parse_args()
    figures = selected(args.figures)
    if args.command == "locate":
        locate(figures)
    elif args.command == "generate":
        generate(figures)
    elif args.command == "export":
        export(figures)
    elif args.command == "check":
        check(figures)
    elif args.command == "preview":
        preview(figures)
    else:
        locate(figures)
        export(figures)
        check(figures)
        preview(figures)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
