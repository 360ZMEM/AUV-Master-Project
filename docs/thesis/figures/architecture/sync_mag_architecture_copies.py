"""Synchronize approved architecture assets into the AUV-Master-Mag snapshot."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
THESIS_SOURCE = ROOT / "docs" / "thesis" / "figures" / "architecture"
INTERNAL_SOURCE = ROOT / "docs" / "internals" / "figures" / "architecture"
TARGET = ROOT / "AUV-Master-Mag" / "thesis" / "figures" / "architecture"

THESIS_NAMES = [
    "auv_runtime_dataflow",
    "auv_system_autonomy_functional_loop",
    "auv_system_capability_map",
    "auv_system_subsystem_organization",
    "auv_system_verification_deployment_ladder",
    "auv_v2_dual_brain_async_hardware",
    "auv_v2_five_layer_functional_architecture",
    "auv_v2_uncertainty_highway",
]
INTERNAL_NAMES = [
    "auv_code_layer_architecture",
    "auv_ros2_node_topology",
    "auv_safety_arbiter_deployment",
]
SUFFIXES = [".drawio"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    records: list[tuple[str, str, str]] = []

    for source_dir, names in (
        (THESIS_SOURCE, THESIS_NAMES),
        (INTERNAL_SOURCE, INTERNAL_NAMES),
    ):
        for name in names:
            for suffix in SUFFIXES:
                source = source_dir / f"{name}{suffix}"
                if not source.is_file():
                    raise FileNotFoundError(source)
                target = TARGET / source.name
                shutil.copy2(source, target)
                records.append(
                    (
                        source.relative_to(ROOT).as_posix(),
                        target.relative_to(ROOT / "AUV-Master-Mag").as_posix(),
                        sha256(target),
                    )
                )

    lines = [
        "# Architecture Snapshot Source",
        "",
        "This directory is a one-way editable-source snapshot of canonical Draw.io files",
        "in `AUV-Master-Project`. PNG, SVG, PDF, and embedded-PNG publication assets remain",
        "owned by the main repository. Do not regenerate these sources with the historical local",
        "`generate_architecture_diagrams.py`; run the main-repository sync script instead:",
        "",
        "`python3 docs/thesis/figures/architecture/sync_mag_architecture_copies.py`",
        "",
        "| Canonical source | Snapshot path | SHA256 |",
        "| --- | --- | --- |",
    ]
    lines.extend(f"| `{source}` | `{target}` | `{digest}` |" for source, target, digest in records)
    lines.append("")
    (TARGET / "_SOURCE.md").write_text("\n".join(lines), encoding="utf-8")

    for source, target, _ in records:
        print(f"{source} -> AUV-Master-Mag/{target}")


if __name__ == "__main__":
    main()
