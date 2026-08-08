#!/usr/bin/env python3
"""Stage the canonical thesis bibliography into the LaTeX projects."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "毕业设计写作文档"
    / "参考文献"
    / "文献引用信息"
    / "references.bib"
)
THESIS_TARGET = ROOT / "thuthesis" / "ref" / "auv-references.bib"
BEAMER_TARGET = ROOT / "thubeamer-1.2" / "ref" / "auv-references.bib"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bibtex_compatible(source_data: bytes) -> bytes:
    """Remove BibLaTeX-only syntax that confuses traditional BibTeX."""

    output: list[str] = []
    for line in source_data.decode("utf-8").splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("%"):
            continue
        if stripped.lower().startswith("@online{"):
            indentation = line[: len(line) - len(stripped)]
            line = indentation + "@misc{" + stripped[len("@online{") :]
        output.append(line)
    return "".join(output).encode("utf-8")


def stage(*, check: bool) -> int:
    source_data = SOURCE.read_bytes()
    targets = (
        (THESIS_TARGET, source_data),
        (BEAMER_TARGET, bibtex_compatible(source_data)),
    )
    failed = False

    for target, expected in targets:
        current = target.read_bytes() if target.exists() else None
        if check:
            if current != expected:
                print(f"STALE {target.relative_to(ROOT)}")
                failed = True
            else:
                print(f"OK    {target.relative_to(ROOT)}")
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        if current == expected:
            print(f"UNCHANGED {target.relative_to(ROOT)}")
            continue

        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(expected)
        temporary.replace(target)
        print(f"UPDATED   {target.relative_to(ROOT)}")

    print(f"CANONICAL_SHA256 {sha256(source_data)}")
    print(f"BEAMER_SHA256    {sha256(bibtex_compatible(source_data))}")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify staged copies without modifying them",
    )
    args = parser.parse_args()
    return stage(check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
