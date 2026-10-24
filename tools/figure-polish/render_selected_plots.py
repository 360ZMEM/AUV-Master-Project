#!/usr/bin/env python3
"""Re-render plots from cached inputs; never run simulations or rewrite results."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / ".diagram-governance/runs/20261021_presentation_polish"
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
os.environ["THESIS_FIGURE_AUDIT_DIR"] = str(RUN / "mpl")
# Debian eagerly installs a regular mpl_toolkits namespace at interpreter
# startup. Point it at the matching, project-local Matplotlib distribution.
import mpl_toolkits
local_toolkits = ROOT / ".diagram-governance/plotdeps/mpl_toolkits"
if local_toolkits.is_dir():
    mpl_toolkits.__path__ = [str(local_toolkits)] + [p for p in mpl_toolkits.__path__ if p != str(local_toolkits)]


def module(path):
    spec = importlib.util.spec_from_file_location(Path(path).stem, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def principles():
    import matplotlib.pyplot as plt
    import thesis_plot_style as tps
    for name, stem in [("single_phase_field", "single_phase_field_direction"),
                       ("three_phase_helical_field", "three_phase_helical_field"),
                       ("fwhm_depth_principle", "fwhm_depth_principle")]:
        m = module("tools/independent/plot_" + name + ".py")
        value = m.make_figure()
        fig = value[0] if isinstance(value, tuple) else value
        tps.save_figure(fig, ROOT / "docs/thesis/figures/magnetics" / stem)
        plt.close(fig)


def r13():
    m = module("tools/plot_r13_v2_formal_audit.py")
    m.setup_style()
    inputs = [m.DEFAULT_AGGREGATE / "r13_v2_paired_effects.csv",
              m.DEFAULT_BUNDLE / "r13_v2_authority_policy_summary_by_scenario_mode.csv",
              m.DEFAULT_OUTPUT / "r13_v2_p_track_samples_ua.csv"]
    available = [p for p in inputs if p.exists()]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in available}
    if inputs[0].exists():
        m.plot_control_rate(m.read_csv_rows(inputs[0]), m.DEFAULT_FIGURE_OUTPUT)
    if inputs[1].exists():
        m.plot_authority(m.read_csv_rows(inputs[1]), m.DEFAULT_FIGURE_OUTPUT)
    if inputs[2].exists():
        samples = m.read_pt_samples(m.DEFAULT_BUNDLE, inputs[2], skip_mcap=True)
        m.plot_p_track(samples, m.DEFAULT_FIGURE_OUTPUT)
    assert before == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in available}
    missing = [str(p.relative_to(ROOT)) for p in inputs if not p.exists()]
    return {"status": "PARTIAL_INPUTS_MISSING" if missing else "RENDERED_AWAITING_REVIEW", "missing_inputs": missing}


def terrain():
    m = module("tools/plot_terrain_following_figures.py")
    m.setup_style()
    out = ROOT / "docs/thesis/figures/terrain_following"
    source = ROOT / "results/control/terrain_following_20260823_215036"
    m.plot_tz_tracking(out, source, 3.0, 10.0)
    m.plot_3d_terrain_trajectory(out, source, ROOT / "config/bridge_params.protocol_udp.pvs.terrain.yaml", 3.0)


def pipelines():
    for path in ["tools/render_cable_active_crossing_figure.py", "tools/render_cable_perception_pipeline_figure.py"]:
        module(path).render()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", action="append", choices=["principles", "r13", "terrain", "pipelines"])
    args = parser.parse_args()
    results = []
    for name in args.group or ["principles", "r13", "terrain", "pipelines"]:
        try:
            details = globals()[name]()
            results.append({"group": name, **(details if isinstance(details, dict) else {"status": "RENDERED_AWAITING_REVIEW"})})
        except (Exception, SystemExit):
            results.append({"group": name, "status": "BLOCKED", "traceback": traceback.format_exc()})
        print(name, results[-1]["status"], flush=True)
    (RUN / "plot_runs.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    sys.exit(1 if any(r["status"] in {"BLOCKED", "PARTIAL_INPUTS_MISSING"} for r in results) else 0)
