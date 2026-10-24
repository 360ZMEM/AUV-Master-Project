#!/usr/bin/env python3
"""Export named native sources with the locked local font mapping."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
os.environ["FONTCONFIG_FILE"] = str(ROOT / "config/diagram-governance/fonts.conf")


def export(stem: Path):
    source = stem.with_suffix(".drawio")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    records = []
    for fmt, suffix, extra in [("pdf", ".pdf", []), ("svg", ".svg", []),
                               ("png", ".png", ["--scale", "2"]),
                               ("png", ".drawio.png", ["--scale", "2", "--embed-diagram"])]:
        out = Path(str(stem) + suffix)
        cmd = ["drawio", "--export", "--format", fmt, *extra, "--output", str(out), str(source)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=True)
        if fmt == "svg":
            # Preserve the source's editable family name. Standalone SVG users
            # see the exact family used here, even without our fontconfig alias.
            tree = ET.parse(out)
            for element in tree.iter():
                for key, value in list(element.attrib.items()):
                    if key in ("font-family", "style"):
                        element.set(key, value.replace("Songti SC", "Noto Serif CJK SC"))
            tree.write(out, encoding="utf-8", xml_declaration=True)
        records.append({"path": out.relative_to(ROOT).as_posix(), "command": cmd,
                        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "exit_code": result.returncode})
    if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
        raise RuntimeError("export changed native source")
    return {"source": source.relative_to(ROOT).as_posix(), "source_sha256": source_hash, "outputs": records}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stem", nargs="+")
    args = parser.parse_args()
    # Draw.io/Electron is serialized across independent invocations.
    import fcntl
    render_lock = (ROOT / ".diagram-governance/render.lock").open("a")
    fcntl.flock(render_lock, fcntl.LOCK_EX)
    output = ROOT / ".diagram-governance/runs/20261021_presentation_polish/exports.json"
    previous = json.loads(output.read_text()) if output.exists() else {}
    for stem in args.stem:
        result = export(ROOT / stem)
        previous[result["source"]] = result
        # Persist each completed source so an interruption never discards the
        # audit trail for already-written publication files.
        output.write_text(json.dumps(previous, ensure_ascii=False, indent=2) + "\n")
        print("exported", stem, flush=True)
