"""Export the two-page five-layer source for the thesis and Markdown previews.

The PDF keeps both native pages. PNG/SVG are vertical previews; edit the .drawio.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from PIL import Image


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
STEM = "auv_v2_five_layer_functional_architecture"
SVG_NS = "http://www.w3.org/2000/svg"


def main() -> None:
    source = HERE / f"{STEM}.drawio"
    env = dict(os.environ)
    env["FONTCONFIG_FILE"] = str(ROOT / "config/diagram-governance/fonts.conf")
    with tempfile.TemporaryDirectory(prefix="five-layer-export-") as temp_name:
        temp = Path(temp_name)
        subprocess.run(["drawio", "--export", "--all-pages", "--format", "pdf",
                        "--output", str(temp / f"{STEM}.pdf"), str(source)], check=True, env=env)
        for index in (0, 1):
            for fmt in ("svg", "png"):
                subprocess.run(["drawio", "--export", "--page-index", str(index),
                                "--format", fmt, "--output", str(temp / f"part{index}.{fmt}"),
                                str(source)], check=True, env=env)

        images = [Image.open(temp / f"part{i}.png").convert("RGBA") for i in (0, 1)]
        width = max(image.width for image in images)
        gap = 24
        output = Image.new("RGBA", (width, sum(image.height for image in images) + gap), "white")
        y = 0
        for image in images:
            output.alpha_composite(image, ((width - image.width) // 2, y))
            y += image.height + gap
        output.convert("RGB").save(temp / f"{STEM}.png")

        page_svg = [ET.parse(temp / f"part{i}.svg").getroot() for i in (0, 1)]
        # Keep the public SVG on the same installed serif face used for PNG/PDF.
        # The editable .drawio source still retains its original Songti family.
        for element in page_svg:
            for child in element.iter():
                for key, value in list(child.attrib.items()):
                    if "Songti SC" in value:
                        child.set(key, value.replace("Songti SC", "Noto Serif CJK SC"))
        sizes = [(float(element.get("width").removesuffix("px")),
                  float(element.get("height").removesuffix("px"))) for element in page_svg]
        vector_width = max(w for w, _ in sizes)
        vector_height = sum(h for _, h in sizes) + gap
        ET.register_namespace("", SVG_NS)
        ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
        composite = ET.Element(f"{{{SVG_NS}}}svg", {"width": f"{vector_width}px",
                          "height": f"{vector_height}px",
                          "viewBox": f"0 0 {vector_width} {vector_height}"})
        y = 0
        for element, (page_width, page_height) in zip(page_svg, sizes):
            element.set("x", str((vector_width - page_width) / 2))
            element.set("y", str(y))
            composite.append(element)
            y += page_height + gap
        ET.ElementTree(composite).write(temp / f"{STEM}.svg", encoding="utf-8", xml_declaration=True)
        for suffix in (".pdf", ".png", ".svg"):
            shutil.copy2(temp / f"{STEM}{suffix}", HERE / f"{STEM}{suffix}")
        shutil.copy2(temp / f"{STEM}.png", HERE / f"{STEM}.drawio.png")


if __name__ == "__main__":
    main()
