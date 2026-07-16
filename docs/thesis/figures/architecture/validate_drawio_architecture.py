"""Static validation for thesis and supporting Draw.io sources."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DIRS = (
    ROOT / "docs" / "thesis" / "figures" / "architecture",
    ROOT / "docs" / "internals" / "figures" / "architecture",
    ROOT / "AUV-Master-Mag" / "docs" / "figure",
)
FORBIDDEN_TEXT = ("图注：", "caption_auto")
TITLE_IDS = {"t1"}
PUBLICATION_FONT_FAMILY = "Songti SC"


def validate(path: Path, strict_publication: bool) -> list[str]:
    errors: list[str] = []
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        return [f"XML parse failed: {exc}"]

    cells = root.findall(".//mxCell")
    ids = [cell.get("id") for cell in cells if cell.get("id")]
    counts = Counter(ids)
    duplicates = sorted(cell_id for cell_id, count in counts.items() if count > 1)
    if duplicates:
        errors.append(f"duplicate ids: {', '.join(duplicates)}")

    known = set(ids)
    for cell in cells:
        if cell.get("edge") != "1":
            continue
        geometry = cell.find("mxGeometry")
        point_roles = {
            point.get("as")
            for point in geometry.findall("mxPoint")
        } if geometry is not None else set()
        for endpoint in ("source", "target"):
            target = cell.get(endpoint)
            if not target and f"{endpoint}Point" not in point_roles:
                errors.append(f"edge {cell.get('id')} missing {endpoint}")
            elif target and target not in known:
                errors.append(f"edge {cell.get('id')} has unknown {endpoint}={target}")
        if geometry is None:
            errors.append(f"edge {cell.get('id')} missing mxGeometry")

    if strict_publication:
        for cell in cells:
            value = cell.get("value", "")
            cell_id = cell.get("id", "")
            if cell_id in TITLE_IDS:
                errors.append(f"publication title cell remains: {cell_id}")
            if any(token in value or token in cell_id for token in FORBIDDEN_TEXT):
                errors.append(f"publication caption text remains: {cell_id}")
            style = cell.get("style", "")
            font_family = re.search(r"(?:^|;)fontFamily=([^;]+)", style)
            if font_family and font_family.group(1) != PUBLICATION_FONT_FAMILY:
                errors.append(
                    f"cell {cell_id} fontFamily {font_family.group(1)!r} "
                    f"!= {PUBLICATION_FONT_FAMILY!r}"
                )
            for match in re.finditer(r"fontSize=(\d+(?:\.\d+)?)", style):
                size = float(match.group(1))
                if cell.get("edge") == "1" and size < 17:
                    errors.append(f"edge {cell_id} fontSize {size:g} < 17")
                elif cell.get("vertex") == "1" and not style.startswith("text;") and size < 18:
                    errors.append(f"vertex {cell_id} fontSize {size:g} < 18")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict-publication",
        action="store_true",
        help="also reject in-canvas titles/captions and undersized text",
    )
    args = parser.parse_args()

    paths: list[Path] = []
    for directory in DEFAULT_DIRS:
        paths.extend(sorted(directory.glob("*.drawio")))

    failed = False
    for path in paths:
        errors = validate(path, args.strict_publication)
        rel = path.relative_to(ROOT)
        if errors:
            failed = True
            print(f"FAIL {rel}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"OK   {rel}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
