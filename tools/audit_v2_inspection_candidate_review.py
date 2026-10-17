#!/usr/bin/env python3
"""Archive a source/version review; never infer deployment from unit tests."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
GROUPS = (
    ("auv_cable_tracking_v2", "auv_cable_tracking_v2", "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2"),
    ("auv_decision_ros", "auv_decision_ros", "brain_linux/src/auv_control/auv_decision_ros"),
    ("auv_controller", "auv_controller", "brain_linux/src/auv_controller/auv_controller"),
    ("auv_common", "common", "common"),
    ("auv_bridge", "auv_bridge", "brain_linux/src/auv_bridge/auv_bridge"),
)
BASELINE_SCOPE = (
    "brain_linux/src/auv_controller", "brain_linux/src/auv_control",
    "brain_linux/src/auv_bridge", "brain_linux/src/auv_interfaces",
    "common", "csd_vx6.8_lastest",
)


def git_read(*arguments: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT}", "-c", "core.autocrlf=false",
         *arguments], cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ros-test-log", type=Path, required=True)
    parser.add_argument("--mag-test-log", type=Path, required=True)
    parser.add_argument("--target-probe", type=Path, required=True)
    parser.add_argument("--runtime-import-paths", type=Path, required=True)
    parser.add_argument("--environment-record", type=Path, required=True)
    args = parser.parse_args()
    mag_log = args.mag_test_log.read_text()
    summaries = re.findall(r"[^\n]*\d+ passed[^\n]*", mag_log)
    if not summaries:
        raise ValueError("magnetic test terminal summary is required before archiving")
    mag_counts = {key: int(match.group(1)) if (match := re.search(rf"(\d+) {key}\b", summaries[-1])) else 0
                  for key in ("passed", "failed", "skipped", "error")}
    baseline = git_read("rev-parse", "origin/main").strip()
    raw_diff = git_read("diff", "--ignore-space-at-eol", baseline, "--", *BASELINE_SCOPE)
    changed_content = []
    for line in git_read("diff", "--ignore-space-at-eol", "--numstat", baseline,
                         "--", *BASELINE_SCOPE).splitlines():
        added, removed, name = line.split("\t", 2)
        if (added, removed) != ("0", "0"):
            changed_content.append({"path": name, "added_lines": added, "removed_lines": removed})
    untracked = git_read("ls-files", "--others", "--exclude-standard", "--", *BASELINE_SCOPE).splitlines()
    xml_path = ROOT / "brain_linux/build/auv_cable_tracking_v2/pytest.xml"
    xml = ET.parse(xml_path).getroot()
    suites = list(xml.iter("testsuite"))
    counts = {key: sum(int(s.get(key, "0")) for s in suites)
              for key in ("tests", "failures", "errors", "skipped")}
    source_paths = set()
    pairs = []
    for package, module, source_dir in GROUPS:
        source = ROOT / source_dir
        files = sorted(source.glob("*.py") if module == "common" else source.rglob("*.py"))
        for path in files:
            installed = (ROOT / "brain_linux/install" / package
                         / "lib/python3.10/site-packages" / module / path.relative_to(source))
            source_paths.add(path)
            pairs.append({"source": str(path.relative_to(ROOT)),
                          "installed": str(installed.relative_to(ROOT)),
                          "source_sha256": digest(path),
                          "installed_sha256": digest(installed) if installed.is_file() else None})
    for directory in ("AUV-Master-Mag/src", "brain_linux/src/auv_cable_tracking_v2/config",
                      "brain_linux/src/auv_cable_tracking_v2/launch",
                      "brain_linux/src/auv_cable_tracking_v2/test", "AUV-Master-Mag/tests/v2"):
        source_paths.update(p for p in (ROOT / directory).rglob("*")
                            if p.is_file() and p.suffix in (".py", ".yaml", ".json"))
    source_paths.add(Path(__file__).resolve())
    source_paths.update(ROOT / name for name in untracked
                        if Path(name).suffix in (".py", ".c", ".h", ".yaml", ".json"))
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    for path in sorted(source_paths):
        target = output / "source_snapshot" / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    for name, path in (("ros_test.log", args.ros_test_log), ("mag_test.log", args.mag_test_log),
                       ("pytest.xml", xml_path), ("target_probe.json", args.target_probe),
                       ("runtime_import_paths.json", args.runtime_import_paths),
                       ("environment.json", args.environment_record)):
        shutil.copyfile(path, output / name)
    (output / "scoped_origin_main.diff").write_text(raw_diff)
    prior_path = (ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/data"
                  / "inspection_v2_candidate_snapshot_20260927.json")
    prior = json.loads(prior_path.read_text())
    changed = [name for name, sha in prior["source_sha256"].items()
               if not (ROOT / name).is_file() or digest(ROOT / name) != sha]
    payload = {
        "schema_version": 1,
        "role": "current_source_and_installed_runtime_review",
        "scope": "selected Python modules/config/launch/tests; not a complete build or field bundle",
        "ros_package_test_counts": counts,
        "magnetic_test_terminal_summary": summaries[-1].strip(),
        "magnetic_test_counts": mag_counts,
        "source_install_pairs": pairs,
        "all_selected_installed_modules_match_source": all(
            p["source_sha256"] == p["installed_sha256"] for p in pairs),
        "historical_snapshot_sha256": digest(prior_path),
        "origin_main_scope_review": {
            "commit": baseline, "scope": BASELINE_SCOPE,
            "comparison": "tracked content with end-of-line whitespace ignored; mode differences retained in patch",
            "tracked_content_changed": changed_content,
            "untracked_files": untracked,
            "does_not_prove_whole_repository_equivalence": True,
        },
        "changed_since_historical_snapshot": changed,
        "historical_full_route_evidence_reassigned_to_current_version": False,
        "current_version_complete_same_session_task_verified": False,
        "unit_test_files_are_review_evidence_not_physical_authorization": True,
        "goal_achieved": False,
        "field_release_authorized": False,
        "files_sha256": {str(p.relative_to(output)): digest(p)
                         for p in sorted(output.rglob("*")) if p.is_file()},
    }
    (output / "review.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"checked_runtime_modules": len(pairs),
                      "all_match": payload["all_selected_installed_modules_match_source"],
                      "ros_test_counts": counts, "historical_changed_files": len(changed),
                      "field_release_authorized": False}))


if __name__ == "__main__":
    main()
