#!/usr/bin/env python3
"""Repository-scoped draw.io inventory and rendered-geometry inspection.

The inspector is deliberately independent of any repair pass. A failed or
unmeasured label is never promoted to PASS. Files are rendered locally by the
installed draw.io Desktop and measured in Chromium with real Range fragments.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / ".diagram-governance/runs/20261018_governance"
POLICY = ROOT / "config/diagram-governance/policy.json"
DIRS = (
    "docs/thesis/figures/architecture",
    "docs/internals/figures/architecture",
    "AUV-Master-Mag/docs/figure",
    "AUV-Master-Mag/thesis/figures/architecture",
)
GENERATOR = {
    "docs/thesis/figures/architecture": "docs/thesis/figures/architecture/generate_architecture_diagrams.py",
    "docs/internals/figures/architecture": "docs/thesis/figures/architecture/generate_architecture_diagrams.py",
    "AUV-Master-Mag/docs/figure": "AUV-Master-Mag/docs/figure/generate_drawio_method_figures.py",
    "AUV-Master-Mag/thesis/figures/architecture": "docs/thesis/figures/architecture/sync_mag_architecture_copies.py",
}
JS_MEASURE = r"""() => {
  const svg = document.querySelector('svg');
  const groups = [...document.querySelectorAll('g[data-cell-id]')];
  const out = {};
  const rect = r => r && ({x:r.x,y:r.y,w:r.width,h:r.height,
    right:r.right,bottom:r.bottom});
  const own = (el,g) => el.closest('g[data-cell-id]') === g;
  for (const g of groups) {
    const id = g.getAttribute('data-cell-id');
    const shape = g.firstElementChild;
    const sr = shape && shape.getBoundingClientRect ? rect(shape.getBoundingClientRect()) : null;
    const fo = [...g.querySelectorAll('foreignObject')].find(e => own(e,g));
    const frags = [];
    let rendered = '';
    let family = null;
    let fontSize = null;
    let clipped = false;
    if (fo) {
      const walker = document.createTreeWalker(fo, NodeFilter.SHOW_TEXT);
      let n;
      while (n = walker.nextNode()) {
        if (!n.textContent.trim()) continue;
        const range = document.createRange(); range.selectNodeContents(n);
        const rr = [...range.getClientRects()].filter(x=>x.width>0 && x.height>0);
        rendered += n.textContent;
        for (const r of rr) frags.push(rect(r));
        const st = getComputedStyle(n.parentElement);
        if (!family && parseFloat(st.fontSize)>0) {
          family = st.fontFamily; fontSize = parseFloat(st.fontSize);
        }
        let a=n.parentElement;
        while (a && a!==fo) {
          const cs=getComputedStyle(a), ar=a.getBoundingClientRect();
          if (['hidden','clip'].includes(cs.overflowX)||['hidden','clip'].includes(cs.overflowY)) {
            if (rr.some(r=>r.left<ar.left-0.5||r.right>ar.right+0.5||r.top<ar.top-0.5||r.bottom>ar.bottom+0.5)) clipped=true;
          }
          a=a.parentElement;
        }
      }
    } else {
      const texts=[...g.querySelectorAll('text')].filter(e=>own(e,g));
      for (const t of texts) {
        const r=t.getBoundingClientRect();
        if(r.width>0&&r.height>0) frags.push(rect(r));
        rendered+=t.textContent;
        const st=getComputedStyle(t); family=st.fontFamily; fontSize=parseFloat(st.fontSize);
      }
    }
    const paths=shape ? [...shape.querySelectorAll('path')].filter(e=>e.getTotalLength && e.getTotalLength()>0):[];
    const fillPath=paths.find(e=>e.getAttribute('fill') && e.getAttribute('fill')!=='none');
    if(fillPath && fillPath.isPointInFill && fillPath.getScreenCTM()) {
      const inv=fillPath.getScreenCTM().inverse();
      const scale=Math.hypot(fillPath.getScreenCTM().a,fillPath.getScreenCTM().b);
      const margin=2*scale;
      for(const r of frags) {
        const pts=[[r.x-margin,r.y-margin],[r.right+margin,r.y-margin],
                   [r.x-margin,r.bottom+margin],[r.right+margin,r.bottom+margin]];
        r.insideFill=pts.every(([x,y])=>fillPath.isPointInFill(new DOMPoint(x,y).matrixTransform(inv)));
      }
    }
    const route=[];
    if (paths.length) {
      const p=paths[0], ctm=p.getScreenCTM(), len=p.getTotalLength();
      if(ctm&&len) for(let i=0;i<=Math.max(20,Math.ceil(len/5));i++){
        const pt=p.getPointAtLength(len*i/Math.max(20,Math.ceil(len/5)));
        route.push({x:ctm.a*pt.x+ctm.c*pt.y+ctm.e,y:ctm.b*pt.x+ctm.d*pt.y+ctm.f});
      }
    }
    out[id]={shape:sr,fragments:frags,rendered,family,fontSize,clipped,route};
  }
  return {cells:out,svg:rect(svg.getBoundingClientRect()),fontsReady:document.fonts.status};
}"""


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=64)
def resolved_font(family: str) -> str:
    p = subprocess.run(["fc-match", "-f", "%{family}", family], capture_output=True, text=True)
    return p.stdout.split(",", 1)[0].strip() if p.returncode == 0 else ""


def safe(path: Path) -> Path:
    if path.is_symlink():
        raise ValueError(f"unsafe symlink: {path}")
    path = path.resolve(strict=False)
    if not path.is_relative_to(ROOT):
        raise ValueError(f"unsafe path: {path}")
    return path


def cmd(*args: str, timeout: int = 50) -> dict:
    p = subprocess.run(list(args), cwd=ROOT, text=True, capture_output=True, timeout=timeout)
    return {"command": list(args), "exit_code": p.returncode,
            "stdout": p.stdout[-4000:], "stderr": p.stderr[-4000:]}


def model(path: Path) -> list[dict]:
    # ElementTree does not fetch external entities. It also rejects unknown ones.
    tree = ET.parse(path)
    root = tree.getroot()
    if root.tag == "mxGraphModel":
        diagrams = [root]
    else:
        diagrams = root.findall("diagram")
    pages = []
    for i, diagram in enumerate(diagrams):
        graph = diagram if diagram.tag == "mxGraphModel" else diagram.find("mxGraphModel")
        if graph is None:
            raise ValueError(f"compressed/unsupported page {i}; requires codec")
        cells = []
        for c in graph.findall(".//mxCell"):
            value = c.get("value", "")
            g = c.find("mxGeometry")
            cells.append({"id": c.get("id"), "value": value,
                          "text": html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"(?i)<br\s*/?>", "\n", value))),
                          "role": "edge" if c.get("edge") == "1" else "vertex" if c.get("vertex") == "1" else "other",
                          "parent": c.get("parent"), "source": c.get("source"), "target": c.get("target"),
                          "style": c.get("style", ""), "visible": c.get("visible", "1"),
                          "geometry": dict(g.attrib) if g is not None else None})
        pages.append({"index": i, "id": diagram.get("id") if graph is not diagram else None,
                      "name": diagram.get("name", f"page-{i+1}"), "cells": cells,
                      "page_width": graph.get("pageWidth"), "page_height": graph.get("pageHeight")})
    return pages


def semantic_snapshot(path: Path) -> list[dict]:
    semantic_style_keys = {"shape", "direction", "dashed", "dashPattern", "strokeColor",
                           "fillColor", "endArrow", "startArrow", "endFill", "startFill",
                           "fontStyle", "html", "whiteSpace", "perimeter"}
    result = []
    for p in model(path):
        cells = []
        for c in p["cells"]:
            style = dict(part.split("=", 1) for part in c["style"].split(";") if "=" in part)
            cells.append({k: c[k] for k in ("id", "value", "role", "parent", "source", "target", "visible")} |
                         {"semantic_style": {k: style[k] for k in sorted(semantic_style_keys) if k in style}})
        result.append({"id": p["id"], "name": p["name"], "cells": cells})
    return result


def semantic_equivalent_to_baseline(path: Path, original: list[dict]) -> bool:
    current = semantic_snapshot(path)
    if current == original:
        return True
    # This one approved two-page layout preserves every original semantic cell.
    # b2 is shown twice as a continuation anchor; f4 targets a transparent port
    # whose centre lies exactly on e2's left boundary. No other changes pass.
    if path.name != "auv_v2_five_layer_functional_architecture.drawio" or len(original) != 1 or len(current) != 2:
        return False
    if [p["id"] for p in current] != ["five-layer-part-1", "five-layer-part-2"]:
        return False
    top_ids = {"0", "1", "l1", "l2", "a1", "a2", "a3", "b1", "b2", "b3", "f1"}
    bottom_ids = {"0", "1", "l3", "l4", "l5", "c1", "c2", "c3", "d1", "d2", "d3", "d4", "e1", "e2", "e3", "f2", "f3", "f4", "b2", "e2_f4_port"}
    if [{c["id"] for c in page["cells"]} for page in current] != [top_ids, bottom_ids]:
        return False
    original_cells = {c["id"]: c for c in original[0]["cells"]}
    seen = set()
    for page_index, page in enumerate(current):
        for c in page["cells"]:
            cell_id = c["id"]
            if cell_id == "e2_f4_port":
                if page_index != 1 or c["value"] or c["role"] != "vertex":
                    return False
                continue
            expected = original_cells.get(cell_id)
            if expected is None:
                return False
            normalized = dict(c)
            if page_index == 1 and cell_id == "b2":
                normalized["parent"] = "l2"
            if cell_id == "f4":
                if normalized["target"] != "e2_f4_port":
                    return False
                normalized["target"] = "e2"
            if normalized != expected:
                return False
            seen.add(cell_id)
    if seen != set(original_cells):
        return False
    pages = model(path)
    bottom = {c["id"]: c for c in pages[1]["cells"]}
    lane = bottom["l5"]["geometry"]
    target = bottom["e2"]["geometry"]
    port = bottom["e2_f4_port"]["geometry"]
    left = float(lane["x"]) + float(target["x"])
    middle = float(lane["y"]) + float(target["y"]) + float(target["height"]) / 2
    return abs(float(port["x"]) + float(port["width"]) / 2 - left) < 0.01 and abs(float(port["y"]) + float(port["height"]) / 2 - middle) < 0.01


def baseline_semantics() -> dict:
    tracked = ROOT / "docs/thesis/diagram-governance/semantic-baseline.json"
    if tracked.exists():
        data = json.loads(tracked.read_text())
        missing = {p.relative_to(ROOT).as_posix() for p in current_paths()} - set(data)
        if missing:
            raise ValueError(f"tracked semantic baseline is missing: {sorted(missing)}")
        return data
    records = {}
    for path in current_paths():
        rel = path.relative_to(ROOT).as_posix()
        backup = RUN / "backup" / rel
        if not backup.exists():
            raise FileNotFoundError(f"baseline backup missing: {rel}")
        records[rel] = {"source_sha256": sha(backup), "pages": semantic_snapshot(backup)}
    return records


def current_paths() -> list[Path]:
    files = []
    for directory in DIRS:
        p = safe(ROOT / directory)
        files.extend(safe(x) for x in p.glob("*.drawio"))
    return sorted(files)


def source_type(path: Path) -> tuple[str, str]:
    directory = path.parent.relative_to(ROOT).as_posix()
    return "generated", GENERATOR[directory]


def inventory(write: bool = True) -> dict:
    records = []
    thesis_refs: dict[str, list[dict]] = {}
    for tex in sorted((ROOT / "thuthesis/data").glob("auv-*.tex")):
        for lineno, line in enumerate(tex.read_text(encoding="utf-8").splitlines(), 1):
            match = re.search(r"\\includegraphics\[([^]]*)\]\{architecture/([^}]+)\.pdf\}", line)
            if match:
                thesis_refs.setdefault(match.group(2), []).append({
                    "tex": tex.relative_to(ROOT).as_posix(), "line": lineno,
                    "options": match.group(1),
                    "artifact": f"docs/thesis/figures/architecture/{match.group(2)}.pdf"})
    for path in current_paths():
        typ, truth = source_type(path)
        pages = model(path)
        outputs = []
        for suffix in (".pdf", ".png", ".svg", ".drawio.png"):
            q = path.with_suffix(suffix) if suffix != ".drawio.png" else Path(str(path) + ".png")
            if q.exists(): outputs.append(q.relative_to(ROOT).as_posix())
        records.append({"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path),
                        "bytes": path.stat().st_size, "source_of_truth": truth,
                        "source_type": typ, "outputs": outputs,
                        "thesis_references": thesis_refs.get(path.stem, []) if
                        path.parent == ROOT / "docs/thesis/figures/architecture" else [],
                        "pages": [{"index": p["index"], "id": p["id"], "name": p["name"],
                                   "layout_type": ("layered-architecture" if sum("swimlane" in c["style"] for c in p["cells"]) >= 3
                                                   else "illustrated-plot" if any("strokeColor=#" in c["style"] and c["role"] == "edge" and c["value"] == "" for c in p["cells"]) and len(p["cells"]) > 20
                                                   else "flow-or-relations"),
                                   "render_profiles": ["all-visible-layers-light"],
                                   "vertices": sum(c["role"] == "vertex" for c in p["cells"]),
                                   "edges": sum(c["role"] == "edge" for c in p["cells"]),
                                   "labels": sum(bool(c["value"]) for c in p["cells"]),
                                   "hidden_cells": [c["id"] for c in p["cells"] if c["visible"] == "0"]}
                                  for p in pages]})
    result = {"schema_version": 1, "captured_at": datetime.now(timezone.utc).isoformat(),
              "files": records, "excluded_historical_backup":
              "毕业设计写作文档/潜在待完成事项/_backup_24_drawio_20260813 (21 frozen copies)"}
    if write:
        RUN.mkdir(parents=True, exist_ok=True)
        (RUN / "inventory-current.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        (RUN / "semantic-baseline.json").write_text(json.dumps(baseline_semantics(), ensure_ascii=False, indent=2))
    return result


def doctor() -> int:
    from importlib.metadata import version
    data = {"time_utc": datetime.now(timezone.utc).isoformat(), "os": platform.platform(),
            "architecture": platform.machine(), "shell": os.environ.get("SHELL"),
            "repo": str(ROOT), "node": cmd("node", "--version"),
            "npm": cmd("npm", "--version"), "drawio_path": shutil.which("drawio"),
            "drawio_version": cmd("drawio", "--version"), "drawio_help": cmd("drawio", "--help"),
            "latexmk": shutil.which("latexmk"), "pdftoppm": shutil.which("pdftoppm"),
            "fonts": {f: cmd("fc-match", "-f", "%{family}|%{style}|%{file}\n", f)
                      for f in ("Songti SC", "Noto Serif CJK SC", "Noto Serif CJK SC:style=Bold", "DejaVu Sans")},
            "playwright_version": version("playwright")}
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            data["chromium_version"] = b.version
            b.close()
    except Exception as e:
        data["chromium_error"] = str(e)
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "environment.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in data.items() if k not in ("drawio_help", "fonts")}, ensure_ascii=False, indent=2))
    return 2 if data.get("chromium_error") or data["drawio_version"]["exit_code"] else 0


def rendered_geometry(svg: Path) -> dict:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page(viewport={"width": 2200, "height": 1500}, device_scale_factor=1)
        page.goto(svg.resolve().as_uri(), wait_until="load")
        page.evaluate("document.fonts.ready")
        measured = page.evaluate(JS_MEASURE)
        b.close()
    return measured


def inside(rect: dict, shape: dict, style: str, role: str, margin: float) -> bool:
    if role == "edge":
        return True  # edge label requires route collision check below
    if "swimlane" in style:
        start = float(re.search(r"(?:^|;)startSize=([\d.]+)", style).group(1)) if "startSize=" in style else 40
        return (rect["x"] >= shape["x"] + margin and rect["right"] <= shape["right"] - margin and
                rect["y"] >= shape["y"] + margin and rect["bottom"] <= shape["y"] + start - margin)
    if "shape=parallelogram" in style:
        inset = 0.11 * shape["w"] + margin
        return (rect["x"] >= shape["x"] + inset and rect["right"] <= shape["right"] - inset and
                rect["y"] >= shape["y"] + margin and rect["bottom"] <= shape["bottom"] - margin)
    if "rhombus" in style:
        cx = shape["x"] + shape["w"] / 2
        cy = shape["y"] + shape["h"] / 2
        rx = max(1, shape["w"] / 2 - margin)
        ry = max(1, shape["h"] / 2 - margin)
        return all(abs(x-cx)/rx + abs(y-cy)/ry <= 0.90 for x in (rect["x"], rect["right"])
                   for y in (rect["y"], rect["bottom"]))
    if "shape=cylinder" in style:
        return (rect["x"] >= shape["x"] + margin and rect["right"] <= shape["right"] - margin and
                rect["y"] >= shape["y"] + 12 and rect["bottom"] <= shape["bottom"] - 12)
    return (rect["x"] >= shape["x"] + margin and rect["right"] <= shape["right"] - margin and
            rect["y"] >= shape["y"] + margin and rect["bottom"] <= shape["bottom"] - margin)


def paper_font_pt(source_font_pt: float, source_pdf_width_pt: float,
                  actual_insert_width_pt: float) -> float:
    if min(source_font_pt, source_pdf_width_pt, actual_insert_width_pt) <= 0:
        raise ValueError("invalid paper font geometry")
    return source_font_pt * actual_insert_width_pt / source_pdf_width_pt


def centers_aligned(rects: list[dict], axis: str, tolerance: float = 1.0) -> bool:
    if axis not in ("x", "y") or not rects:
        raise ValueError("axis or rect list invalid")
    centers = [r[axis] + r["w" if axis == "x" else "h"] / 2 for r in rects]
    return max(centers) - min(centers) <= tolerance


def check_page(page: dict, measured: dict, source: str, svg: str,
               render_source_sha: str | None = None,
               governed_source: str | None = None) -> dict:
    policy = json.loads(POLICY.read_text())
    cells = measured["cells"]
    errors = []
    if render_source_sha is not None and render_source_sha != sha(ROOT / source):
        errors.append({"rule": "H12", "code": "STALE_RENDER_SOURCE",
                       "expected_source_sha256": sha(ROOT / source),
                       "rendered_source_sha256": render_source_sha})
    expected = mapped = measured_count = 0
    for c in page["cells"]:
        if not c["value"] or c["visible"] == "0": continue
        expected += 1
        actual = cells.get(c["id"])
        if actual is None:
            errors.append({"rule": "H03", "code": "UNMAPPED_LABEL", "cell_id": c["id"]})
            continue
        mapped += 1
        if not actual["fragments"]:
            errors.append({"rule": "H03", "code": "UNMEASURED_LABEL", "cell_id": c["id"]})
            continue
        measured_count += 1
        family_match = re.search(r"(?:^|;)fontFamily=([^;]+)", c["style"])
        if family_match:
            requested_family = family_match.group(1).strip()
            actual_family = resolved_font(requested_family)
            allowed = {requested_family.casefold()}
            if requested_family == "Songti SC":
                allowed.add(policy["font_fallback_for_Songti_SC"].casefold())
            if actual_family.casefold() not in allowed:
                errors.append({"rule": "H03", "code": "FONT_FAMILY_UNAVAILABLE",
                               "cell_id": c["id"], "requested": requested_family,
                               "resolved": actual_family})
        expected_render_text = c["text"].replace("\n", "")
        if actual["rendered"].replace("\n", "") != expected_render_text:
            errors.append({"rule": "H03", "code": "RENDERED_TEXT_MISMATCH", "cell_id": c["id"],
                           "expected": expected_render_text, "rendered": actual["rendered"]})
        if actual["clipped"]:
            errors.append({"rule": "H04", "code": "CLIPPED_TEXT", "cell_id": c["id"]})
        shape = actual["shape"]
        if c["role"] == "vertex" and not shape:
            errors.append({"rule": "H04", "code": "SHAPE_NOT_RENDERED", "cell_id": c["id"]})
            continue
        if c["role"] == "vertex" and not c["style"].startswith("text;"):
            for f in actual["fragments"]:
                safe_shape = (inside(f, shape, c["style"], c["role"], policy["text_safety_margin_u"])
                              if "swimlane" in c["style"] or "shape=cylinder" in c["style"]
                              else f.get("insideFill", inside(f, shape, c["style"], c["role"],
                                                               policy["text_safety_margin_u"])))
                if not safe_shape:
                    errors.append({"rule": "H04", "code": "TEXT_OUTSIDE_SHAPE_SAFE_AREA",
                                   "cell_id": c["id"], "text_rect": f, "shape_rect": shape})
                    break
        box = measured["svg"]
        if any(f["x"] < box["x"] - 0.5 or f["y"] < box["y"] - 0.5 or
               f["right"] > box["right"] + 0.5 or f["bottom"] > box["bottom"] + 0.5
               for f in actual["fragments"]):
            errors.append({"rule": "H09", "code": "TEXT_OUTSIDE_EXPORTED_PAGE", "cell_id": c["id"]})
    by_id = {c["id"]: c for c in page["cells"] if c["id"]}
    vertices = [c for c in page["cells"] if c["role"] == "vertex" and c["visible"] != "0"
                and c["id"] in cells and cells[c["id"]]["shape"]]
    for i, a in enumerate(vertices):
        ra = cells[a["id"]]["shape"]
        if a["parent"] in by_id and "swimlane" in by_id[a["parent"]]["style"]:
            parent = by_id[a["parent"]]
            rp = cells.get(parent["id"], {}).get("shape")
            match = re.search(r"(?:^|;)startSize=([\d.]+)", parent["style"])
            if rp and match and not a["style"].startswith("text;"):
                header_bottom = rp["y"] + float(match.group(1))
                if ra["y"] < header_bottom + 8 - 0.5:
                    errors.append({"rule": "H06", "code": "CHILD_IN_HEADER_BUFFER",
                                   "cell_id": a["id"], "parent_id": parent["id"],
                                   "child_y": ra["y"], "header_bottom": header_bottom})
            if rp and (ra["x"] < rp["x"] - 0.5 or ra["right"] > rp["right"] + 0.5 or
                       ra["y"] < rp["y"] - 0.5 or ra["bottom"] > rp["bottom"] + 0.5):
                errors.append({"rule": "H05", "code": "CHILD_OUTSIDE_CONTAINER",
                               "cell_id": a["id"], "parent_id": parent["id"]})
        if "swimlane" in a["style"] or a["style"].startswith("text;") or ra["w"] < 5 or ra["h"] < 5:
            continue
        for b in vertices[i+1:]:
            if b["parent"] != a["parent"] or "swimlane" in b["style"] or b["style"].startswith("text;"):
                continue
            rb = cells[b["id"]]["shape"]
            if min(ra["right"], rb["right"]) - max(ra["x"], rb["x"]) > 0.5 and \
               min(ra["bottom"], rb["bottom"]) - max(ra["y"], rb["y"]) > 0.5:
                errors.append({"rule": "H05", "code": "SIBLING_SHAPES_OVERLAP",
                               "cell_id": a["id"], "other_id": b["id"]})
    for edge in [c for c in page["cells"] if c["role"] == "edge" and c["id"] in cells]:
        route = cells[edge["id"]]["route"]
        for fragment in cells[edge["id"]]["fragments"]:
            for vertex in vertices:
                if "swimlane" in vertex["style"]:
                    continue
                r = cells[vertex["id"]]["shape"]
                if min(fragment["right"], r["right"] + 2) - max(fragment["x"], r["x"] - 2) > 0 and \
                   min(fragment["bottom"], r["bottom"] + 2) - max(fragment["y"], r["y"] - 2) > 0:
                    errors.append({"rule": "H07", "code": "EDGE_LABEL_NEAR_NODE",
                                   "cell_id": edge["id"], "other_id": vertex["id"]})
        if len(route) < 3:
            errors.append({"rule": "H07", "code": "EDGE_ROUTE_UNMEASURED", "cell_id": edge["id"]})
            continue
        stroke_records = json.loads((ROOT / "config/diagram-governance/overrides.json").read_text())[
            "illustrative_strokes"]
        depiction_line = any(record["file"] == source and record["page_index"] == page["index"]
                              and edge["id"] in record["cell_ids"] for record in stroke_records)
        for vertex in vertices:
            if depiction_line:
                break  # plot curves intentionally pass through observation markers
            if vertex["id"] in (edge["source"], edge["target"]) or "swimlane" in vertex["style"]:
                continue
            r = cells[vertex["id"]]["shape"]
            if any(r["x"] - 8 < p["x"] < r["right"] + 8 and
                   r["y"] - 8 < p["y"] < r["bottom"] + 8 for p in route[1:-1]):
                errors.append({"rule": "H07", "code": "EDGE_NEAR_UNRELATED_NODE",
                               "cell_id": edge["id"], "other_id": vertex["id"]})
        for other in page["cells"]:
            if other["id"] == edge["id"] or not other["value"]:
                continue
            for frag in cells.get(other["id"], {}).get("fragments", []):
                if any(frag["x"] - 6 < p["x"] < frag["right"] + 6 and
                       frag["y"] - 6 < p["y"] < frag["bottom"] + 6 for p in route[1:-1]):
                    errors.append({"rule": "H07", "code": "EDGE_NEAR_UNRELATED_TEXT",
                                   "cell_id": edge["id"], "other_id": other["id"]})
                    break
    manifest = json.loads((ROOT / "config/diagram-governance/manifest.json").read_text())
    configured = next((p for p in manifest["pages"] if p["file"] == (governed_source or source) and
                       p["page_index"] == page["index"]), None)
    if configured:
        for group in configured.get("alignment_groups", []):
            ids = group["ids"]
            rects = [cells.get(i, {}).get("shape") for i in ids]
            if any(r is None for r in rects):
                errors.append({"rule": "H08", "code": "ALIGNMENT_GROUP_UNMEASURED", "cell_ids": ids})
                continue
            axis = group["axis"]
            centers = [r[axis] + r["w" if axis == "x" else "h"] / 2 for r in rects]
            if group["kind"] == "center":
                deviation = max(centers) - min(centers)
            else:
                gaps = [centers[i+1] - centers[i] for i in range(len(centers)-1)]
                deviation = max(gaps) - min(gaps)
            if deviation > group["tolerance_u"]:
                errors.append({"rule": "H08", "code": "ALIGNMENT_GROUP_OUT_OF_TOLERANCE",
                               "cell_ids": ids, "deviation_u": deviation})
        order = configured.get("fixed_layer_order")
        if order:
            ys = [cells.get(i, {}).get("shape", {}).get("y") for i in order]
            if any(y is None for y in ys) or ys != sorted(ys):
                errors.append({"rule": "H08", "code": "FIXED_LAYER_ORDER_CHANGED", "cell_ids": order})
    # Numeric completeness is a hard gate. More geometric rules are reported as
    # incomplete until tested; this avoids an XML-only false-green verdict.
    status = "FAIL" if errors else "NEEDS_REVIEW"
    return {"file": source, "page_index": page["index"], "page_id": page["id"],
            "page_name": page["name"], "source_sha256": sha(ROOT/source),
            "svg": svg, "svg_sha256": sha(ROOT/svg), "status": status,
            "coverage": {"expected_labels": expected, "mapped_labels": mapped,
                         "measured_labels": measured_count}, "errors": errors,
            "pending_hard_checks": ["H05", "H06", "H07", "H08", "H10", "H11", "H12", "H13", "H14"],
            "visual_review": "PENDING"}


def verify(fresh: bool, only_file: str | None = None) -> int:
    records = []
    render_dir = RUN / ("fresh" if fresh else "checks")
    sources = [p for p in current_paths() if only_file is None or p.relative_to(ROOT).as_posix() == only_file]
    if only_file and not sources:
        print("file outside current inventory:", only_file)
        return 3
    source_hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in sources}
    baseline = baseline_semantics()
    for source in sources:
        rel = source.relative_to(ROOT).as_posix()
        try:
            pages = model(source)
        except Exception as e:
            records.append({"file": rel, "status": "BLOCKED", "error": str(e)})
            continue
        for page in pages:
            target = render_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            svg = target.with_name(target.stem + f"_p{page['index']}.svg")
            call = cmd("drawio", "--export", "--page-index", str(page["index"]),
                       "--format", "svg", "--output", str(svg), str(source))
            if call["exit_code"] or not svg.exists():
                records.append({"file": rel, "page_index": page["index"],
                                "status": "BLOCKED", "render": call})
                continue
            try:
                rec = check_page(page, rendered_geometry(svg), rel,
                                 svg.relative_to(ROOT).as_posix(), sha(source))
                png = svg.with_suffix(".png")
                png_call = cmd("drawio", "--export", "--page-index", str(page["index"]),
                               "--scale", "2", "--format", "png", "--output", str(png), str(source))
                rec["png"] = png.relative_to(ROOT).as_posix() if png.exists() and png_call["exit_code"] == 0 else None
                rec["png_render_call"] = png_call
                if rec["png"] is None:
                    rec["errors"].append({"rule": "H11", "code": "FINAL_IMAGE_NOT_RENDERED"})
                if not semantic_equivalent_to_baseline(source, baseline[rel]["pages"]):
                    rec["errors"].append({"rule": "H01", "code": "SEMANTIC_SNAPSHOT_CHANGED"})
                if rec["errors"]:
                    rec["status"] = "FAIL"
                rec["render_call"] = call
                records.append(rec)
            except Exception as e:
                records.append({"file": rel, "page_index": page["index"],
                                "status": "BLOCKED", "error": repr(e)})
            print(rel, page["index"], records[-1]["status"],
                  len(records[-1].get("errors", [])), flush=True)
    out_name = "checks-fresh.json" if fresh else "checks.json"
    if only_file:
        out_name = f"checks-target-{hashlib.sha256(only_file.encode()).hexdigest()[:12]}.json"
    out = RUN / out_name
    after_hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in sources}
    if after_hashes != source_hashes:
        for rec in records:
            rec.setdefault("errors", []).append({"rule": "H13", "code": "VERIFY_MODIFIED_SOURCE"})
            rec["status"] = "FAIL"
    out.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    hash_name = f"verify-source-hashes-{hashlib.sha256(only_file.encode()).hexdigest()[:12]}.json" if only_file else (
        "verify-source-hashes-fresh.json" if fresh else "verify-source-hashes.json")
    (RUN / hash_name).write_text(
        json.dumps({"before": source_hashes, "after": after_hashes}, ensure_ascii=False, indent=2))
    print("saved", out.relative_to(ROOT), "pages", len(records),
          "fail", sum(r["status"] == "FAIL" for r in records),
          "blocked", sum(r["status"] == "BLOCKED" for r in records))
    if any(r["status"] == "FAIL" for r in records): return 1
    return 2  # pending hard checks prevent PASS


def report() -> int:
    """Summarize measured disk evidence without promoting unreviewed pages."""
    inventory_path = RUN / "inventory-current.json"
    checks_path = RUN / "checks-fresh.json"
    if not inventory_path.exists() or not checks_path.exists():
        print("report: BLOCKED—run inventory and fresh verify first")
        return 2
    inv = json.loads(inventory_path.read_text())
    checks = json.loads(checks_path.read_text())
    by_key = {(r["file"], r.get("page_index", 0)): r for r in checks}
    manual_path = ROOT / "docs/thesis/diagram-governance/manual_review.json"
    manual = json.loads(manual_path.read_text()) if manual_path.exists() else {}
    selftest_path = RUN / "selftest/result.json"
    selftest_result = json.loads(selftest_path.read_text()) if selftest_path.exists() else {}
    destination = ROOT / "docs/thesis/diagram-governance"
    destination.mkdir(parents=True, exist_ok=True)
    image_base = "../../../.diagram-governance/runs/20261018_governance/"
    status_counts = {s: sum(r.get("status") == s for r in checks)
                     for s in ("PASS", "FAIL", "BLOCKED", "NEEDS_REVIEW")}
    rule_counts: dict[str, int] = {}
    for row in checks:
        for error in row.get("errors", []):
            rule = error.get("rule", "UNKNOWN")
            rule_counts[rule] = rule_counts.get(rule, 0) + 1
    environment_path = RUN / "environment.json"
    environment = json.loads(environment_path.read_text()) if environment_path.exists() else {}
    drawio_output = environment.get("drawio_version", {}).get("stdout", "not recorded").strip()
    drawio_version = drawio_output.splitlines()[-1] if drawio_output else "not recorded"
    chromium_version = environment.get("chromium_version", "not recorded")
    evidence_manifest = {"schema_version": 1, "policy_sha256": sha(POLICY),
                         "fontconfig_sha256": sha(ROOT / "config/diagram-governance/fonts.conf"),
                         "drawio_version": drawio_version, "chromium_version": chromium_version,
                         "files": []}
    for item in inv["files"]:
        source = ROOT / item["path"]
        backup = RUN / "backup" / item["path"]
        outputs = [ROOT / p for p in item["outputs"]]
        evidence_manifest["files"].append({"path": item["path"], "sha256": sha(source),
            "baseline_sha256": sha(backup) if backup.exists() else
                               baseline_semantics().get(item["path"], {}).get("source_sha256"),
            "outputs": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p)}
                        for p in outputs if p.exists()]})
    (destination / "evidence_manifest.json").write_text(
        json.dumps(evidence_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# draw.io 全量治理：阶段性实测报告", "",
             "本报告由 `node tools/diagram-governance/cli.mjs report` 从本机 fresh 检查结果生成。状态仅反映已完成的检查；没有看图或尚未验证的页面不会判定 PASS。",
             "", f"- 当前图源：{len(inv['files'])} 文件，{sum(len(f['pages']) for f in inv['files'])} 页；冻结历史副本 21 份不计入当前范围。",
             f"- fresh 状态：PASS {status_counts['PASS']}，FAIL {status_counts['FAIL']}，BLOCKED {status_counts['BLOCKED']}，NEEDS_REVIEW {status_counts['NEEDS_REVIEW']}。",
             f"- 缺陷/合法/变异自测：{sum(selftest_result.get('checks', {}).values())}/{len(selftest_result.get('checks', {}))}；结果 {selftest_result.get('status', 'MISSING')}。",
             f"- 错误条目按规则：{', '.join(f'{k}={v}' for k, v in sorted(rule_counts.items())) or '无'}。",
             f"- 渲染环境：draw.io `{drawio_version}`；Chromium `{chromium_version}`；策略 SHA-256 `{sha(POLICY)}`；逐文件和产物哈希见 [evidence_manifest.json](evidence_manifest.json)。",
             "- 完整 PASS 尚未获得：实际论文阅读尺寸、所有页面及高风险局部人工看图、正式产物一致性和幂等检查未全部完成。",
             "", "## 逐页状态", "",
             "| 图源 / 页 | 权威源 | 标签覆盖 | fresh 状态与错误 | 论文引用 | 前后图像 | 看图记录 |",
             "|---|---|---:|---|---|---|---|" ]
    html_rows = []
    for item in inv["files"]:
        for p in item["pages"]:
            rel, idx = item["path"], p["index"]
            row = by_key.get((rel, idx), {"status": "BLOCKED", "errors": [{"code": "NO_FRESH_RESULT"}]})
            cov = row.get("coverage", {})
            cover = f"{cov.get('measured_labels', 0)}/{cov.get('expected_labels', p['labels'])}"
            errors = row.get("errors", [])
            error_label = ", ".join(sorted({e.get("code", "UNKNOWN") for e in errors}))
            source = f"{rel} / p{idx}"
            refs = ", ".join(f"{r['tex']}:{r['line']}" for r in item["thesis_references"]) or "未由 auv-thesis 直接引用"
            baseline_dir = RUN / "baseline" / Path(rel).parent
            baseline_page = idx if (baseline_dir / f"{Path(rel).stem}_p{idx}.png").exists() else 0
            before_source = baseline_dir / f"{Path(rel).stem}_p{baseline_page}.png"
            before_destination = destination / "evidence" / "baseline" / Path(rel).parent / before_source.name
            if before_source.exists():
                before_destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(before_source, before_destination)
            before = before_destination.relative_to(destination).as_posix()
            after = row.get("png")
            after_link = ""
            if after:
                after_destination = destination / "evidence" / "fresh" / Path(rel).parent / f"{Path(rel).stem}_p{idx}.png"
                after_destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / after, after_destination)
                after_link = after_destination.relative_to(destination).as_posix()
            review = manual.get(rel, {}).get("visual_review", "PENDING")
            lines.append(f"| `{source}` | `{item['source_of_truth']}` | {cover} | {row['status']}: {error_label or '暂无几何错误；其他门槛待验'} | {refs} | [前]({before})" +
                         (f" / [后]({after_link})" if after else "") + f" | {review} |")
            html_rows.append("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in
                             (source, item["source_of_truth"], cover, row["status"], error_label, refs, review)) +
                             f'<td><a href="{html.escape(before)}">前</a>' +
                             (f' / <a href="{html.escape(after_link)}">后</a>' if after else "") + "</td></tr>")
    lines += ["", "## 实际剩余问题（精确对象 ID）", ""]
    for item in inv["files"]:
        for p in item["pages"]:
            row = by_key.get((item["path"], p["index"]), {})
            if not row.get("errors"):
                continue
            groups: dict[str, set[str]] = {}
            for error in row["errors"]:
                name = f"{error.get('rule', 'UNKNOWN')}:{error.get('code', 'UNKNOWN')}"
                ids = [str(error[k]) for k in ("cell_id", "other_id", "parent_id") if error.get(k)]
                groups.setdefault(name, set()).add("→".join(ids) if ids else "page")
            detail = "; ".join(f"{name} [{', '.join(sorted(ids))}]" for name, ids in sorted(groups.items()))
            lines.append(f"- `{item['path']}` p{p['index']}：{detail}。")
    paper_path = RUN / "paper_baseline.json"
    if paper_path.exists():
        paper = json.loads(paper_path.read_text())
        lines += ["", "## 现有论文 PDF 阅读尺寸基线", "",
                  "以下为本轮开始时现有 `auv-thesis.pdf` 的实际页面解析结果，尚未将失败候选图写入论文；物理页码来自编译映射，需在最终构建再核对。",
                  "", "| 图源 | 物理页（基线映射） | 实际最小字（PDF pt） | 9 pt 门槛 |", "|---|---:|---:|---|"]
        for p in paper:
            lines.append(f"| `{p['stem']}` | {p['physical_page_assumed']} | {p['paper_min_size']:.1f} | {'PASS' if p['paper_min_size'] >= 9 else 'FAIL'} |")
    final_paper_path = destination / "paper_review.json"
    if final_paper_path.exists():
        final_paper = json.loads(final_paper_path.read_text())
        lines += ["", "## 已核对的最终论文阅读尺寸", "",
                  "只列已在重编译 PDF 内核对的图，不代表其他图通过 H10。",
                  "", "| 图源 | 物理页 | 最小字号（pt） | 9 pt 门槛 |", "|---|---:|---:|---|"]
        for p in final_paper:
            lines.append(f"| `{p['stem']}` | {p['physical_page']} | {p['paper_min_size']:.2f} | {'PASS' if p['paper_min_size'] >= 9 else 'FAIL'} |")
    lines += ["", "## 试点前后图像", "",
              "- 简单图（已写回）：[原图](evidence/mission_fsm_before.png) → [正式导出](evidence/mission_fsm_after.png)。",
              "- 五层图（双页已写回）：[原图](evidence/five_layer_before.png) → [正式合并预览](evidence/five_layer_after.png) → [论文物理页 41](evidence/five_layer_thesis_page41.png)。[单页失败候选](evidence/five_layer_trial_not_approved.png)保留为否决证据。",
              "", "## 可复现入口", "",
              "- 全流程复查（清点、自测、fresh 渲染/检测与报告）：`node tools/diagram-governance/cli.mjs run --all`。",
              "- 只读验收：`node tools/diagram-governance/cli.mjs verify --all --strict --fresh`。",
              "- 原件保存在 `.diagram-governance/runs/20261018_governance/`；逐页前后图像同步到本报告的 `evidence/baseline/` 和 `evidence/fresh/`。",
              "", "## 未通过的阶段门", "",
              "两个试点已写回；其他 FAIL/NEEDS_REVIEW 页面仍需修复、实际看图、论文阅读尺寸核对与幂等验收。不得将当前报告解读为图像治理已全部完成。", ""]
    (destination / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    html_page = ("<!doctype html><html lang=zh-CN><meta charset=utf-8><title>draw.io 治理实测报告</title>"
                 "<style>body{font:15px/1.6 sans-serif;margin:2rem}table{border-collapse:collapse;width:100%}"
                 "td,th{border:1px solid #ccc;padding:.4rem;vertical-align:top}tr:nth-child(even){background:#f7f7f7}</style>"
                 "<h1>draw.io 全量治理：阶段性实测报告</h1><p>状态不得替代实际看图；目前没有全仓 PASS。</p>"
                 f"<p>{len(inv['files'])} 文件 / {sum(len(f['pages']) for f in inv['files'])} 页；FAIL {status_counts['FAIL']}，BLOCKED {status_counts['BLOCKED']}，NEEDS_REVIEW {status_counts['NEEDS_REVIEW']}。</p>"
                 "<table><thead><tr><th>图源/页</th><th>权威源</th><th>标签</th><th>状态</th><th>错误</th><th>论文引用</th><th>看图</th><th>图像</th></tr></thead><tbody>"
                 + "".join(html_rows) + "</tbody></table></html>")
    (destination / "index.html").write_text(html_page, encoding="utf-8")
    print("saved", (destination / "summary.md").relative_to(ROOT), "and index.html")
    return 1 if status_counts["FAIL"] else 2 if status_counts["BLOCKED"] or status_counts["NEEDS_REVIEW"] else 0


def selftest() -> int:
    """Render a two-page fixture, then mutate the renderer output and model."""
    test_dir = RUN / "selftest"
    test_dir.mkdir(parents=True, exist_ok=True)
    fixture = test_dir / "fixture.drawio"
    first = '''<mxGraphModel dx="900" dy="500" grid="1" page="1" pageWidth="900" pageHeight="500"><root>
      <mxCell id="0"/><mxCell id="1" parent="0"/>
      <mxCell id="bad_rect" value="很长的中文标签必须被检查器抓到" style="rounded=0;whiteSpace=wrap;html=1;fontFamily=Songti SC;fontSize=24;" vertex="1" parent="1"><mxGeometry x="20" y="20" width="85" height="30" as="geometry"/></mxCell>
      <mxCell id="good_rect" value="合法节点" style="rounded=0;whiteSpace=wrap;html=1;fontFamily=Songti SC;fontSize=20;" vertex="1" parent="1"><mxGeometry x="20" y="95" width="260" height="80" as="geometry"/></mxCell>
      <mxCell id="diamond" value="菱形斜边外的长文字" style="rhombus;whiteSpace=wrap;html=1;fontFamily=Songti SC;fontSize=22;" vertex="1" parent="1"><mxGeometry x="330" y="20" width="140" height="105" as="geometry"/></mxCell>
      <mxCell id="lane" value="合法层标题" style="swimlane;startSize=40;html=1;fontFamily=Songti SC;fontSize=20;" vertex="1" parent="1"><mxGeometry x="310" y="190" width="350" height="155" as="geometry"/></mxCell>
      <mxCell id="bad_child" value="侵犯标题带" style="rounded=0;html=1;fontFamily=Songti SC;fontSize=18;" vertex="1" parent="lane"><mxGeometry x="30" y="27" width="180" height="42" as="geometry"/></mxCell>
      <mxCell id="legal_child" value="正常包含" style="rounded=0;html=1;fontFamily=Songti SC;fontSize=18;" vertex="1" parent="lane"><mxGeometry x="35" y="82" width="180" height="55" as="geometry"/></mxCell>
      <mxCell id="missing_font" value="缺字字体" style="rounded=0;html=1;fontFamily=AuvDefinitelyMissingFont;fontSize=20;" vertex="1" parent="1"><mxGeometry x="690" y="50" width="175" height="70" as="geometry"/></mxCell>
      <mxCell id="clip_rect" value="被固定容器裁剪的中文长文字内容" style="rounded=0;whiteSpace=wrap;overflow=hidden;html=1;fontFamily=Songti SC;fontSize=24;" vertex="1" parent="1"><mxGeometry x="500" y="20" width="90" height="28" as="geometry"/></mxCell>
      <mxCell id="short_cylinder" value="&lt;b&gt;圆柱标题&lt;/b&gt;&lt;br&gt;底部椭圆弧穿字" style="shape=cylinder3;boundedLbl=1;html=1;fontFamily=Songti SC;fontSize=22;" vertex="1" parent="1"><mxGeometry x="25" y="220" width="185" height="48" as="geometry"/></mxCell>
      <mxCell id="outer_container" value="" style="swimlane;startSize=40;html=1;" vertex="1" parent="1"><mxGeometry x="690" y="220" width="170" height="95" as="geometry"/></mxCell>
      <mxCell id="outside_child" value="越界子模块" style="rounded=0;html=1;fontFamily=Songti SC;fontSize=16;" vertex="1" parent="outer_container"><mxGeometry x="10" y="70" width="145" height="55" as="geometry"/></mxCell>
      <mxCell id="edge_source" value="" style="rounded=0;html=1;" vertex="1" parent="1"><mxGeometry x="20" y="315" width="45" height="50" as="geometry"/></mxCell>
      <mxCell id="edge_target" value="" style="rounded=0;html=1;" vertex="1" parent="1"><mxGeometry x="265" y="315" width="45" height="50" as="geometry"/></mxCell>
      <mxCell id="edge_obstacle" value="阻挡" style="rounded=0;html=1;fontFamily=Songti SC;fontSize=18;" vertex="1" parent="1"><mxGeometry x="130" y="317" width="60" height="45" as="geometry"/></mxCell>
      <mxCell id="crossing_edge" value="" style="edgeStyle=none;html=1;endArrow=block;" edge="1" parent="1" source="edge_source" target="edge_target"><mxGeometry relative="1" as="geometry"/></mxCell>
      <mxCell id="external_note" value="外部说明" style="text;html=1;fontFamily=Songti SC;fontSize=18;" vertex="1" parent="1"><mxGeometry x="30" y="390" width="180" height="50" as="geometry"/></mxCell>
    </root></mxGraphModel>'''
    second = '''<mxGraphModel dx="500" dy="300" grid="1" page="1" pageWidth="500" pageHeight="300"><root>
      <mxCell id="0"/><mxCell id="1" parent="0"/>
      <mxCell id="second_page_only" value="第二页必须导出" style="rounded=0;html=1;fontFamily=Songti SC;fontSize=20;" vertex="1" parent="1"><mxGeometry x="30" y="30" width="270" height="70" as="geometry"/></mxCell>
    </root></mxGraphModel>'''
    fixture.write_text(f'<mxfile host="drawio" version="24.7.17"><diagram id="p1" name="defects">{first}</diagram><diagram id="p2" name="legal">{second}</diagram></mxfile>', encoding="utf-8")
    calls = []
    for index in (0, 1):
        out = test_dir / f"fixture-p{index}.svg"
        call = cmd("drawio", "--export", "--format", "svg", "--page-index", str(index),
                   "--output", str(out), str(fixture), timeout=60)
        calls.append(call)
        if call["exit_code"] or not out.exists():
            report = {"status": "BLOCKED", "reason": "fixture export failed", "calls": calls}
            (test_dir / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
            print(report["reason"])
            return 2
    pages = model(fixture)
    measured0 = rendered_geometry(test_dir / "fixture-p0.svg")
    measured1 = rendered_geometry(test_dir / "fixture-p1.svg")
    result0 = check_page(pages[0], measured0, fixture.relative_to(ROOT).as_posix(),
                         (test_dir / "fixture-p0.svg").relative_to(ROOT).as_posix())
    result1 = check_page(pages[1], measured1, fixture.relative_to(ROOT).as_posix(),
                         (test_dir / "fixture-p1.svg").relative_to(ROOT).as_posix())
    found = {(x["cell_id"], x["code"]) for x in result0["errors"]}
    checks = {
        "A_long_chinese_overflow": ("bad_rect", "TEXT_OUTSIDE_SHAPE_SAFE_AREA") in found,
        "B_clipped_inner_text": ("clip_rect", "CLIPPED_TEXT") in found,
        "C_diamond_true_path": ("diamond", "TEXT_OUTSIDE_SHAPE_SAFE_AREA") in found,
        "D_child_enters_header": ("bad_child", "CHILD_IN_HEADER_BUFFER") in found,
        "E_cylinder_safe_area": ("short_cylinder", "TEXT_OUTSIDE_SHAPE_SAFE_AREA") in found,
        "F_relative_child_escape": ("outside_child", "CHILD_OUTSIDE_CONTAINER") in found,
        "G_unrelated_node_crossing": any(x["cell_id"] == "crossing_edge" and
                                         x.get("other_id") == "edge_obstacle" and x["rule"] == "H07"
                                         for x in result0["errors"]),
        "H_second_page_selected": result1["coverage"]["expected_labels"] == 1 and
                                  result1["coverage"]["measured_labels"] == 1 and
                                  "第二页必须导出" in measured1["cells"]["second_page_only"]["rendered"],
        "J_missing_family": ("missing_font", "FONT_FAMILY_UNAVAILABLE") in found,
        "M_legal_rectangle_not_flagged": not any(x["cell_id"] == "good_rect" and
                                             x["rule"] == "H04" for x in result0["errors"]),
        "O_external_note_not_internal_overflow": not any(x["cell_id"] == "external_note" and
                                                       x["rule"] == "H04" for x in result0["errors"]),
        "N_endpoint_contact_legal": not any(x["cell_id"] == "crossing_edge" and
                                            x.get("other_id") in ("edge_source", "edge_target")
                                            for x in result0["errors"]),
        "L_small_paper_font_rejected": paper_font_pt(24, 1000, 200) < 9 and
                                        paper_font_pt(24, 1000, 400) >= 9,
        "Q_center_alignment_mutation": centers_aligned([
            {"x": 0, "y": 0, "w": 100, "h": 50}, {"x": 10, "y": 2, "w": 80, "h": 46}], "x") and
            not centers_aligned([{"x": 0, "y": 0, "w": 100, "h": 50},
                                 {"x": 12, "y": 2, "w": 80, "h": 46}], "x"),
    }
    # Mutation: a formerly legal rectangle becomes too short and narrow.
    mutated = test_dir / "mutated.drawio"
    mutated.write_text(fixture.read_text().replace('x="20" y="95" width="260" height="80"',
                                                   'x="20" y="95" width="70" height="24"'), encoding="utf-8")
    svg_mut = test_dir / "mutated.svg"
    mutation_call = cmd("drawio", "--export", "--format", "svg", "--page-index", "0",
                        "--output", str(svg_mut), str(mutated), timeout=60)
    if mutation_call["exit_code"] == 0 and svg_mut.exists():
        mut = check_page(model(mutated)[0], rendered_geometry(svg_mut),
                         mutated.relative_to(ROOT).as_posix(), svg_mut.relative_to(ROOT).as_posix())
        checks["mutation_shrunken_node"] = any(x["cell_id"] == "good_rect" and x["rule"] == "H04"
                                               for x in mut["errors"])
    else:
        checks["mutation_shrunken_node"] = False
    # Mutation: label ID mapping is lost while visible text remains in the SVG.
    lost_id = test_dir / "lost-id.svg"
    lost_id.write_text((test_dir / "fixture-p0.svg").read_text().replace(
        'data-cell-id="good_rect"', 'data-cell-id="unknown_good_rect"'), encoding="utf-8")
    missing = check_page(pages[0], rendered_geometry(lost_id), fixture.relative_to(ROOT).as_posix(),
                         lost_id.relative_to(ROOT).as_posix())
    checks["I_mutation_lost_id"] = any(x["cell_id"] == "good_rect" and
                                        x["code"] == "UNMAPPED_LABEL" for x in missing["errors"])
    stale = check_page(model(mutated)[0], measured0, mutated.relative_to(ROOT).as_posix(),
                       (test_dir / "fixture-p0.svg").relative_to(ROOT).as_posix(), sha(fixture))
    checks["K_stale_preview_rejected"] = any(x["code"] == "STALE_RENDER_SOURCE" for x in stale["errors"])
    report = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
              "renderer_calls": calls + [mutation_call], "fixture_sha256": sha(fixture),
              "mutated_sha256": sha(mutated), "page_errors": result0["errors"]}
    (test_dir / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(report["status"], sum(checks.values()), "/", len(checks), "selftest assertions")
    for name, ok in checks.items(): print("PASS" if ok else "FAIL", name)
    return 0 if all(checks.values()) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("doctor", "inventory", "selftest", "pilot", "run", "verify", "report"))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--file", help="repository-relative current .drawio path for targeted read-only verification")
    args = parser.parse_args()
    if args.action == "doctor": return doctor()
    if args.action == "inventory":
        data = inventory()
        print(len(data["files"]), "files", sum(len(f["pages"]) for f in data["files"]), "pages")
        return 0
    if args.action == "verify": return verify(args.fresh, args.file)
    if args.action == "report": return report()
    if args.action == "selftest": return selftest()
    if args.action == "pilot":
        print("pilot: read-only validation of the selected simple and complex pages")
        outcomes = [verify(True, p) for p in (
            "AUV-Master-Mag/docs/figure/fig_mission_fsm.drawio",
            "docs/thesis/figures/architecture/auv_v2_five_layer_functional_architecture.drawio")]
        return 1 if 1 in outcomes else 2 if 2 in outcomes else 0
    if args.action == "run":
        if args.write:
            print("run --write: BLOCKED—automatic repairs cannot meet the candidate gate; source files were not written")
            return 2
        outcomes = [doctor()]
        inventory()
        outcomes.append(selftest())
        outcomes.append(verify(True))
        outcomes.append(report())
        return 1 if 1 in outcomes else 2 if 2 in outcomes else 0
    return 3


if __name__ == "__main__":
    sys.exit(main())
