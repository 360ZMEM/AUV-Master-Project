#!/usr/bin/env python3
"""Read-only rendered audit under the user's 2026-10-21 polish scope.

The earlier 9 pt policy and historical reports remain intact. This run permits
only explicitly recorded presentation wording/palette changes. Text containment,
mapping and collision checks use the unchanged shape-aware inspector.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/diagram-governance"))
import governance as g

RUN = ROOT / ".diagram-governance/runs/20261021_presentation_polish"
EDITS = ROOT / "docs/thesis/figure-polish/presentation_edits.json"


def straight_runs(route: list[dict]) -> list[tuple]:
    runs = []
    for a, b in zip(route, route[1:]):
        if abs(a["y"] - b["y"]) < .05 and abs(a["x"] - b["x"]) > .05:
            item = ("h", a["y"], a["x"], b["x"])
        elif abs(a["x"] - b["x"]) < .05 and abs(a["y"] - b["y"]) > .05:
            item = ("v", a["x"], a["y"], b["y"])
        else:
            continue
        if runs and item[0] == runs[-1][0] and abs(item[1] - runs[-1][1]) < .05 and abs(item[2] - runs[-1][3]) < .2:
            runs[-1] = (*runs[-1][:3], item[3])
        else:
            runs.append(item)
    return runs


def coincident_routes(cells: list[dict], measured: dict) -> list[dict]:
    edges = [c for c in cells if c["role"] == "edge"]
    errors = []
    for i, left in enumerate(edges):
        a_runs = straight_runs(measured["cells"][left["id"]]["route"])
        for right in edges[i + 1:]:
            # A tree fork may share a trunk from its same source. A reverse
            # incoming/outgoing line through a different source is ambiguous.
            if left["source"] is not None and left["source"] == right["source"]:
                continue
            hits = []
            for a in a_runs:
                for b in straight_runs(measured["cells"][right["id"]]["route"]):
                    if a[0] != b[0] or abs(a[1] - b[1]) > .5:
                        continue
                    length = min(max(a[2:]), max(b[2:])) - max(min(a[2:]), min(b[2:]))
                    if length > 10:
                        hits.append(round(length, 2))
            if hits:
                errors.append({"rule": "H07", "code": "COINCIDENT_DISTINCT_EDGE_ROUTES", "cell_id": left["id"],
                               "other_id": right["id"], "shared_run_u": max(hits)})
    return errors


def semantic_check(source: Path) -> bool:
    rel = source.relative_to(ROOT).as_posix()
    before = copy.deepcopy(g.semantic_snapshot(RUN / "backup" / rel))
    edits = json.loads(EDITS.read_text()).get(rel, []) if EDITS.exists() else []
    for edit in edits:
        cell = next(c for c in before[edit["page"]]["cells"] if c["id"] == edit["cell_id"])
        if cell != edit["before"]:
            return False
        # Wording and palette are permitted; graph meaning and containment are
        # immutable in this polish pass, even in a recorded edit.
        for key in ("id", "role", "parent", "source", "target", "visible"):
            if cell[key] != edit["after"][key]:
                return False
        cell.update(edit["after"])
    return before == g.semantic_snapshot(source)


def inspect(source: Path) -> list[dict]:
    rel = source.relative_to(ROOT).as_posix()
    before = g.sha(source)
    records = []
    for page in g.model(source):
        svg = RUN / "fresh" / rel
        svg = svg.with_name(svg.stem + f"_p{page['index']}.svg")
        svg.parent.mkdir(parents=True, exist_ok=True)
        call = g.cmd("drawio", "--export", "--page-index", str(page["index"]),
                     "--format", "svg", "--output", str(svg), str(source))
        if call["exit_code"]:
            records.append({"file": rel, "page": page["index"], "status": "BLOCKED", "render": call})
            continue
        measured = g.rendered_geometry(svg)
        rec = g.check_page(page, measured, rel, str(svg.relative_to(ROOT)), before)
        rec["errors"] += coincident_routes(page["cells"], measured)
        png = svg.with_suffix(".png")
        png_call = g.cmd("drawio", "--export", "--page-index", str(page["index"]), "--scale", "2",
                         "--format", "png", "--output", str(png), str(source))
        if png_call["exit_code"]:
            rec["errors"].append({"code": "PNG_RENDER_FAILED"})
        if not semantic_check(source):
            rec["errors"].append({"code": "UNRECORDED_SEMANTIC_CHANGE"})
        rec.update({"png": str(png.relative_to(ROOT)), "measured": measured,
                    "render": call, "visual_review": "PENDING", "layout_status": "FAIL" if rec["errors"] else "PASS"})
        # Layout PASS is only a sub-check. Final visual/paper integration is a
        # separate deliverable, and no unviewed page becomes final PASS.
        rec["status"] = "FAIL" if rec["errors"] else "NEEDS_REVIEW"
        records.append(rec)
        print(rel, page["index"], rec["status"], len(rec["errors"]), flush=True)
    if before != g.sha(source):
        raise RuntimeError("source changed during read-only inspection: " + rel)
    key = __import__("hashlib").sha256(rel.encode()).hexdigest()[:12]
    history = RUN / "history" / key / before[:12]
    history.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, history / source.name)
    for rec in records:
        for kind in ("svg", "png"):
            if rec.get(kind):
                artifact = ROOT / rec[kind]
                shutil.copy2(artifact, history / artifact.name)
    (history / "checks.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
    per_source = RUN / "checks_by_source"
    per_source.mkdir(exist_ok=True)
    (per_source / (key + ".json")).write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    # Draw.io/Electron is serialized across independent invocations.
    import fcntl
    render_lock = (ROOT / ".diagram-governance/render.lock").open("a")
    fcntl.flock(render_lock, fcntl.LOCK_EX)
    paths = g.current_paths() if args.all else [ROOT / p for p in args.file]
    records = []
    for p in paths:
        try:
            records += inspect(p)
        except Exception as exc:
            records.append({"file":p.relative_to(ROOT).as_posix(),"page_index":None,
                            "status":"BLOCKED","errors":[{"code":"INSPECTION_FAILED","reason":repr(exc)}]})
            print(p.relative_to(ROOT),"BLOCKED",repr(exc),flush=True)
    out = RUN / ("checks_all.json" if args.all else "checks_selected.json")
    out.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
    return 1 if any(r["status"] in {"FAIL", "BLOCKED"} for r in records) else 2


if __name__ == "__main__":
    sys.exit(main())
