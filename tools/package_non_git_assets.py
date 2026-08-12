#!/usr/bin/env python3
"""Package non-Git project assets without overwriting tracked files.

The archive is intended for moving local-only assets to another checkout after
Git/LFS/submodules have already been synchronized.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import subprocess
import tarfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


LATEX_BUILD_SUFFIXES = {
    ".aux",
    ".bbl",
    ".bcf",
    ".blg",
    ".fdb_latexmk",
    ".fls",
    ".lof",
    ".log",
    ".lot",
    ".nav",
    ".out",
    ".run.xml",
    ".snm",
    ".toc",
    ".xdv",
}

CACHE_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    ".ipynb_checkpoints",
    ".tox",
}

BACKUP_DIR_MARKERS = (
    "backup",
    "_backup",
    "bak",
)

STAGE_DIR_NAMES = {
    ".tmp_math_review",
    ".tmr8637_crops",
    ".tmr8637_review",
    ".tmr8637_pdf_review",
    "image_audit_tmp",
    "tmp",
    "temp",
    "build",
    "dist",
    "install",
    "log",
    "default",
}

DROP_FILE_NAMES = {
    ".DS_Store",
    "CACHEDIR.TAG",
}


@dataclass(frozen=True)
class Repo:
    label: str
    abs_path: Path
    archive_prefix: str


@dataclass(frozen=True)
class Candidate:
    source_repo: str
    repo_rel: str
    archive_rel: str
    abs_path: Path
    size: int


def run_git(repo: Path, args: list[str]) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def decode_zlist(raw: bytes) -> list[str]:
    return [os.fsdecode(part) for part in raw.split(b"\0") if part]


def repo_root() -> Path:
    return Path(os.fsdecode(run_git(Path.cwd(), ["rev-parse", "--show-toplevel"]).strip())).resolve()


def submodule_paths(root: Path) -> list[str]:
    gitmodules = root / ".gitmodules"
    if not gitmodules.exists():
        return []
    result = subprocess.run(
        ["git", "config", "--file", str(gitmodules), "--get-regexp", r"^submodule\..*\.path$"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    paths: list[str] = []
    for line in result.stdout.splitlines():
        fields = line.split(maxsplit=1)
        if len(fields) == 2:
            paths.append(fields[1])
    return paths


def repos(root: Path) -> list[Repo]:
    result = [Repo(label="root", abs_path=root, archive_prefix="")]
    for sub_path in submodule_paths(root):
        abs_path = root / sub_path
        if abs_path.exists():
            result.append(Repo(label=sub_path, abs_path=abs_path, archive_prefix=sub_path))
    return result


def git_other_files(repo: Repo) -> set[str]:
    untracked = decode_zlist(run_git(repo.abs_path, ["ls-files", "-z", "--others", "--exclude-standard"]))
    ignored = decode_zlist(
        run_git(repo.abs_path, ["ls-files", "-z", "--others", "--ignored", "--exclude-standard"])
    )
    return set(untracked) | set(ignored)


def git_tracked_archive_paths(repo: Repo) -> set[str]:
    paths = set()
    for rel in decode_zlist(run_git(repo.abs_path, ["ls-files", "-z"])):
        paths.add(join_archive(repo.archive_prefix, rel))
    return paths


def join_archive(prefix: str, rel: str) -> str:
    rel = rel.replace(os.sep, "/")
    return f"{prefix}/{rel}" if prefix else rel


def has_latex_build_suffix(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(suffix) for suffix in LATEX_BUILD_SUFFIXES) or ".synctex" in lower


def classify_exclusion(path: str, output_dir_rel: str) -> str | None:
    normalized = path.replace("\\", "/")
    components = normalized.split("/")
    lower_components = [component.lower() for component in components]
    name = components[-1]
    lower_name = name.lower()

    if output_dir_rel and (normalized == output_dir_rel or normalized.startswith(output_dir_rel + "/")):
        return "package_output"
    if name in DROP_FILE_NAMES:
        return "cache_or_os_metadata"
    if any(component in CACHE_DIR_NAMES for component in components):
        return "cache"
    if lower_name.endswith((".pyc", ".pyo", ".class")):
        return "cache"
    if lower_name.endswith((".o", ".obj", ".d")):
        return "build_intermediate"
    if lower_name.endswith((".bak", ".backup", ".orig", ".old", ".tmp", "~")) or lower_name.startswith("~$"):
        return "backup_or_temporary_file"
    if has_latex_build_suffix(lower_name):
        return "latex_build_product"
    for component in lower_components:
        if component in STAGE_DIR_NAMES:
            return "stage_or_build_directory"
        if any(marker in component for marker in BACKUP_DIR_MARKERS):
            return "backup_directory"
        if component.startswith("_backup_orig_") or component.startswith(".audit_backup_"):
            return "backup_directory"
    return None


def collect(root: Path, output_dir: Path) -> tuple[list[Candidate], list[tuple[str, str]]]:
    output_dir_rel = output_dir.resolve().relative_to(root).as_posix()

    tracked_paths: set[str] = set()
    candidates: list[Candidate] = []
    excluded: list[tuple[str, str]] = []

    repo_list = repos(root)
    for repo in repo_list:
        tracked_paths.update(git_tracked_archive_paths(repo))

    seen: set[str] = set()
    for repo in repo_list:
        for repo_rel in sorted(git_other_files(repo)):
            archive_rel = join_archive(repo.archive_prefix, repo_rel)
            if archive_rel in seen:
                continue
            seen.add(archive_rel)

            reason = classify_exclusion(archive_rel, output_dir_rel)
            if reason:
                excluded.append((archive_rel, reason))
                continue
            if archive_rel in tracked_paths:
                excluded.append((archive_rel, "tracked_path_collision"))
                continue

            abs_path = repo.abs_path / repo_rel
            if not abs_path.is_file():
                excluded.append((archive_rel, "not_a_regular_file"))
                continue
            candidates.append(
                Candidate(
                    source_repo=repo.label,
                    repo_rel=repo_rel,
                    archive_rel=archive_rel,
                    abs_path=abs_path,
                    size=abs_path.stat().st_size,
                )
            )
    return candidates, excluded


def write_manifest(path: Path, rows: list[Candidate]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(["archive_path", "bytes", "source_repo", "repo_relative_path", "sha256"])
        for item in rows:
            writer.writerow([item.archive_rel, item.size, item.source_repo, item.repo_rel, sha256(item.abs_path)])


def write_exclusions(path: Path, rows: list[tuple[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(["archive_path", "reason"])
        for archive_rel, reason in rows:
            writer.writerow([archive_rel, reason])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_manifest_to_archive(tar: tarfile.TarFile, path: Path, arcname: str) -> None:
    tar.add(path, arcname=arcname, recursive=False)


def create_archive(archive_path: Path, candidates: list[Candidate], manifest_path: Path, exclusions_path: Path) -> None:
    with tarfile.open(archive_path, "w:gz") as tar:
        for item in candidates:
            tar.add(item.abs_path, arcname=item.archive_rel, recursive=False)
        add_manifest_to_archive(tar, manifest_path, "_non_git_asset_manifest.tsv")
        add_manifest_to_archive(tar, exclusions_path, "_non_git_asset_exclusions.tsv")


def human_bytes(value: int) -> str:
    units = ["B", "KiB", "MiB", "GiB"]
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.2f} {unit}"
        amount /= 1024
    return f"{value} B"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="non_git_asset_bundles",
        help="Directory under the repository root for archives and manifests.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Write manifests only; do not create tar.gz.")
    args = parser.parse_args()

    root = repo_root()
    output_dir = (root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"auv_non_git_assets_{timestamp}"
    manifest_path = output_dir / f"{stem}_manifest.tsv"
    exclusions_path = output_dir / f"{stem}_exclusions.tsv"
    summary_path = output_dir / f"{stem}_summary.md"
    archive_path = output_dir / f"{stem}.tar.gz"

    candidates, excluded = collect(root, output_dir)
    candidates.sort(key=lambda item: item.archive_rel)
    excluded.sort()

    write_manifest(manifest_path, candidates)
    write_exclusions(exclusions_path, excluded)

    total_bytes = sum(item.size for item in candidates)
    by_repo: dict[str, tuple[int, int]] = {}
    for item in candidates:
        count, size = by_repo.get(item.source_repo, (0, 0))
        by_repo[item.source_repo] = (count + 1, size + item.size)

    archive_sha = ""
    if not args.dry_run:
        create_archive(archive_path, candidates, manifest_path, exclusions_path)
        archive_sha = sha256(archive_path)

    with summary_path.open("w", encoding="utf-8") as stream:
        stream.write("# Non-Git Asset Bundle Summary\n\n")
        stream.write(f"- root: `{root}`\n")
        stream.write(f"- archive: `{archive_path if not args.dry_run else '(dry-run)'}`\n")
        stream.write(f"- manifest: `{manifest_path}`\n")
        stream.write(f"- exclusions: `{exclusions_path}`\n")
        stream.write(f"- included files: {len(candidates)}\n")
        stream.write(f"- included bytes: {total_bytes} ({human_bytes(total_bytes)})\n")
        stream.write(f"- excluded files: {len(excluded)}\n")
        if archive_sha:
            stream.write(f"- archive sha256: `{archive_sha}`\n")
        stream.write("\n## By Repository\n\n")
        for repo, (count, size) in sorted(by_repo.items()):
            stream.write(f"- `{repo}`: {count} files, {size} bytes ({human_bytes(size)})\n")
        stream.write("\n## Restore\n\n")
        stream.write("After cloning/pulling Git, LFS, and submodules, extract from the repository root:\n\n")
        stream.write("```bash\n")
        stream.write(f"tar -xzf {archive_path.name if not args.dry_run else '<archive.tar.gz>'} -C /path/to/AUV-Master-Project\n")
        stream.write("```\n")

    print(f"included_files={len(candidates)}")
    print(f"included_bytes={total_bytes} ({human_bytes(total_bytes)})")
    print(f"excluded_files={len(excluded)}")
    print(f"manifest={manifest_path}")
    print(f"exclusions={exclusions_path}")
    print(f"summary={summary_path}")
    if not args.dry_run:
        print(f"archive={archive_path}")
        print(f"archive_sha256={archive_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
