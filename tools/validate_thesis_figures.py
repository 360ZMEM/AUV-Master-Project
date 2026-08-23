#!/usr/bin/env python3
"""Validate active ThuThesis figure provenance and exported assets."""
from __future__ import annotations

import argparse
import glob
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/thesis/figures/thesis_figure_manifest.json"
INCLUDE_RE = re.compile(
    r"\\includegraphics(?:\s*\[[^\]]*\])?\s*\{([^}]+)\}",
    re.MULTILINE,
)


def load_manifest() -> dict:
    with MANIFEST.open(encoding="utf-8") as handle:
        return json.load(handle)


def active_references() -> set[Path]:
    references: set[Path] = set()
    for tex_path in sorted((ROOT / "thuthesis/data").glob("auv-chap*.tex")):
        text = tex_path.read_text(encoding="utf-8")
        for raw in INCLUDE_RE.findall(text):
            if raw.startswith("../"):
                resolved = (ROOT / "thuthesis" / raw).resolve()
            else:
                resolved = (ROOT / "docs/thesis/figures" / raw).resolve()
            references.add(resolved.relative_to(ROOT.resolve()))
    return references


def canonical_figure_path(path: Path) -> Path:
    return path.with_suffix("")


def select_figures(figures: list[dict], ids: list[str]) -> list[dict]:
    if not ids:
        return figures
    selected = [item for item in figures if item["id"] in ids]
    missing = sorted(set(ids) - {item["id"] for item in selected})
    if missing:
        raise SystemExit(f"unknown figure id(s): {', '.join(missing)}")
    return selected


def validate_manifest(
    data: dict,
    *,
    check_outputs: bool = True,
    selected_ids: list[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    figures = data.get("figures", [])
    if data.get("figure_count") != len(figures):
        errors.append(
            f"manifest figure_count={data.get('figure_count')} but has "
            f"{len(figures)} entries"
        )

    ids = [item["id"] for item in figures]
    outputs = [Path(item["output"]) for item in figures]
    for label, values in (("id", ids), ("output", outputs)):
        repeated = [value for value, count in Counter(values).items() if count > 1]
        if repeated:
            errors.append(f"duplicate {label}: {repeated}")

    references = {canonical_figure_path(path) for path in active_references()}
    declared = {canonical_figure_path(path) for path in outputs}
    missing = sorted(references - declared)
    stale = sorted(declared - references)
    if missing:
        errors.append(f"active TeX figures missing from manifest: {missing}")
    if stale:
        errors.append(f"manifest outputs not referenced by TeX: {stale}")

    for item in select_figures(figures, selected_ids or []):
        output = ROOT / item["output"]
        if check_outputs and not output.is_file():
            errors.append(f"{item['id']}: output missing: {item['output']}")
        preview = item.get("preview")
        if check_outputs and preview and not (ROOT / preview).is_file():
            errors.append(f"{item['id']}: preview missing: {preview}")
        generator = item.get("generator")
        if generator and not (ROOT / generator).is_file():
            errors.append(f"{item['id']}: generator missing: {generator}")
        for pattern in item.get("inputs", []):
            matches = glob.glob(str(ROOT / pattern))
            if not matches:
                errors.append(f"{item['id']}: input missing: {pattern}")
    return errors


def validate_png(path: Path) -> list[str]:
    errors: list[str] = []
    with Image.open(path) as image:
        width, height = image.size
        long_edge = max(width, height)
        short_edge = min(width, height)
        is_wide = long_edge / short_edge >= 2.5
        undersized = (
            long_edge < 1800 or short_edge < 600
            if is_wide
            else short_edge < 900
        )
        if undersized:
            errors.append(
                f"{path.relative_to(ROOT)}: low raster dimension {width}x{height}"
            )
    return errors


def validate_pdf(path: Path) -> list[str]:
    proc = subprocess.run(
        ["pdfinfo", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return [f"{path.relative_to(ROOT)}: pdfinfo failed: {proc.stderr.strip()}"]
    if "Pages:" not in proc.stdout:
        return [f"{path.relative_to(ROOT)}: malformed PDF metadata"]
    return []


def validate_drawio(path: Path, strict: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    tree = ET.parse(path)
    root = tree.getroot()
    graph = root.find(".//mxGraphModel")
    if graph is None:
        return [f"{path.relative_to(ROOT)}: mxGraphModel missing"], warnings

    width = float(graph.attrib.get("pageWidth", "0"))
    height = float(graph.attrib.get("pageHeight", "0"))
    if width > 1650 or height > 1000:
        errors.append(
            f"{path.relative_to(ROOT)}: canvas {width:g}x{height:g} exceeds limit"
        )

    font_sizes: set[float] = set()
    thick_edges: list[float] = []
    forbidden: set[str] = set()
    for cell in root.findall(".//mxCell"):
        style = cell.attrib.get("style", "")
        for value in re.findall(r"(?:^|;)fontSize=([0-9.]+)", style):
            font_sizes.add(float(value))
        if cell.attrib.get("edge") == "1":
            match = re.search(r"(?:^|;)strokeWidth=([0-9.]+)", style)
            if match and float(match.group(1)) > 2.0:
                thick_edges.append(float(match.group(1)))
        for token in ("gradientColor=", "shadow=1", "glass=1"):
            if token in style:
                forbidden.add(token.rstrip("="))

    if len(font_sizes) > 4:
        message = (
            f"{path.relative_to(ROOT)}: {len(font_sizes)} font sizes "
            f"{sorted(font_sizes)}"
        )
        (errors if strict else warnings).append(message)
    if thick_edges:
        message = (
            f"{path.relative_to(ROOT)}: connector stroke exceeds 2 px "
            f"({max(thick_edges):g})"
        )
        (errors if strict else warnings).append(message)
    if forbidden:
        errors.append(
            f"{path.relative_to(ROOT)}: forbidden effects {sorted(forbidden)}"
        )
    return errors, warnings


def validate_assets(
    figures: list[dict],
    strict: bool,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    seen_drawio: set[Path] = set()
    for item in figures:
        output = ROOT / item["output"]
        if output.suffix.lower() == ".pdf" and output.exists():
            errors.extend(validate_pdf(output))
        preview = item.get("preview")
        if preview and (ROOT / preview).exists():
            errors.extend(validate_png(ROOT / preview))
        if item["kind"] == "drawio":
            drawio = ROOT / item["inputs"][0]
            if drawio not in seen_drawio:
                drawio_errors, drawio_warnings = validate_drawio(drawio, strict)
                errors.extend(drawio_errors)
                warnings.extend(drawio_warnings)
                seen_drawio.add(drawio)
    return errors, warnings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", action="append", default=[])
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--check-sources", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data = load_manifest()
    selected = select_figures(data["figures"], args.id)
    errors = validate_manifest(
        data,
        check_outputs=not args.check_sources,
        selected_ids=args.id,
    )
    warnings: list[str] = []
    if not args.check_sources:
        asset_errors, warnings = validate_assets(selected, args.strict)
        errors.extend(asset_errors)

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        print(f"figure validation failed: {len(errors)} error(s)")
        return 1
    print(
        f"figure validation passed: {len(selected)} selected figures, "
        f"{len(warnings)} warning(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
