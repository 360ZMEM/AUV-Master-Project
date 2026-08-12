#!/usr/bin/env python3
"""Build the thesis evidence artifact manifest from a reviewed catalog."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = (
    ROOT
    / "毕业设计写作文档"
    / "潜在待完成事项"
    / "06_现有证据Artifact_Manifest.catalog.json"
)
DEFAULT_JSON = (
    ROOT
    / "毕业设计写作文档"
    / "潜在待完成事项"
    / "06_现有证据Artifact_Manifest.json"
)
DEFAULT_MARKDOWN = (
    ROOT
    / "毕业设计写作文档"
    / "潜在待完成事项"
    / "06_现有证据Artifact_Manifest.md"
)
HASH_CHUNK_BYTES = 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate machine-readable and reviewable thesis artifact manifests."
    )
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument(
        "--check",
        action="store_true",
        help="regenerate in memory and fail when committed outputs differ",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_git(*args: str) -> str | None:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def repository_state() -> dict[str, Any]:
    commit = run_git("rev-parse", "HEAD")
    submodule_text = run_git("submodule", "status") or ""
    submodules: list[dict[str, str]] = []
    for line in submodule_text.splitlines():
        fields = line.strip().split()
        if len(fields) >= 2:
            submodules.append(
                {
                    "path": fields[1],
                    "commit": fields[0].lstrip("-+U"),
                    "status_prefix": line[:1],
                }
            )
    return {
        "current_commit": commit,
        "worktree_state": "not_evaluated",
        "note": (
            "This is the manifest-generation revision, not the historical "
            "experiment revision unless an experiment manifest records it. "
            "Global dirty-state probing is intentionally skipped because this "
            "workspace requires an unavailable git-lfs filter; catalogued "
            "artifacts are verified by their own SHA256 values."
        ),
        "submodules": submodules,
    }


def resolve_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    return path if path.is_absolute() else ROOT / path


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def add_candidate(
    candidates: dict[str, dict[str, Any]],
    path: Path,
    *,
    role: str,
    required: bool,
    known_gap: bool = False,
) -> None:
    key = str(path.resolve(strict=False))
    candidate = candidates.setdefault(
        key,
        {
            "path_obj": path,
            "roles": set(),
            "required": False,
            "known_gap": False,
        },
    )
    candidate["roles"].add(role)
    candidate["required"] = candidate["required"] or required
    candidate["known_gap"] = candidate["known_gap"] or known_gap


def add_csv_references(
    candidates: dict[str, dict[str, Any]],
    reference: dict[str, Any],
) -> None:
    csv_path = resolve_path(reference["path"])
    add_candidate(
        candidates,
        csv_path,
        role="run_index",
        required=True,
    )
    if not csv_path.is_file():
        return
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle)
        if reference["column"] not in (rows.fieldnames or []):
            raise ValueError(
                f"{display_path(csv_path)} has no column {reference['column']!r}"
            )
        for row in rows:
            raw_value = str(row.get(reference["column"], "")).strip()
            if raw_value:
                add_candidate(
                    candidates,
                    resolve_path(raw_value),
                    role=reference.get("role", "referenced_input"),
                    required=bool(reference.get("required", True)),
                )


def collect_candidates(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for item in spec.get("files", []):
        add_candidate(
            candidates,
            resolve_path(item["path"]),
            role=item["role"],
            required=bool(item.get("required", True)),
        )
    for item in spec.get("globs", []):
        matches = sorted(glob.glob(str(resolve_path(item["pattern"])), recursive=True))
        if not matches and item.get("required", True):
            add_candidate(
                candidates,
                resolve_path(item["pattern"]),
                role=item["role"],
                required=True,
            )
        for match in matches:
            path = Path(match)
            if path.is_file():
                add_candidate(
                    candidates,
                    path,
                    role=item["role"],
                    required=bool(item.get("required", True)),
                )
    for reference in spec.get("csv_references", []):
        add_csv_references(candidates, reference)
    for item in spec.get("known_missing", []):
        add_candidate(
            candidates,
            resolve_path(item["path"]),
            role=item["role"],
            required=False,
            known_gap=True,
        )
    return candidates


def inspect_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    path: Path = candidate["path_obj"]
    exists = path.exists()
    is_file = path.is_file()
    record: dict[str, Any] = {
        "path": display_path(path),
        "roles": sorted(candidate["roles"]),
        "required": candidate["required"],
        "known_gap": candidate["known_gap"],
        "exists": exists,
        "kind": "file" if is_file else ("directory" if path.is_dir() else "missing"),
        "size_bytes": None,
        "mtime_utc": None,
        "sha256": None,
    }
    if is_file:
        stat = path.stat()
        record.update(
            {
                "size_bytes": stat.st_size,
                "mtime_utc": dt.datetime.fromtimestamp(
                    stat.st_mtime, tz=dt.timezone.utc
                ).isoformat(),
                "sha256": sha256_file(path),
            }
        )
    return record


def artifact_digest(files: list[dict[str, Any]]) -> str:
    lines = [
        f"{item['path']}\0{item['size_bytes']}\0{item['sha256']}"
        for item in files
        if item["exists"] and item["kind"] == "file"
    ]
    return sha256_bytes(("\n".join(sorted(lines)) + "\n").encode("utf-8"))


def build_artifact(spec: dict[str, Any]) -> dict[str, Any]:
    candidates = collect_candidates(spec)
    files = [
        inspect_candidate(candidate)
        for _, candidate in sorted(candidates.items(), key=lambda item: item[0])
    ]
    missing_required = [
        item["path"] for item in files if item["required"] and not item["exists"]
    ]
    known_gaps = [item["path"] for item in files if item["known_gap"]]
    raw_files = [
        item
        for item in files
        if any("raw" in role for role in item["roles"])
    ]
    present_files = [
        item for item in files if item["exists"] and item["kind"] == "file"
    ]
    role_counts: Counter[str] = Counter()
    for item in files:
        for role in item["roles"]:
            role_counts[role] += 1
    return {
        "id": spec["id"],
        "title": spec["title"],
        "data_layer": spec["data_layer"],
        "evidence_grade": spec["evidence_grade"],
        "declared_status": spec["declared_status"],
        "sample_scope": spec["sample_scope"],
        "claims_supported": spec["claims_supported"],
        "claim_boundaries": spec["claim_boundaries"],
        "provenance_gaps": spec.get("provenance_gaps", []),
        "required_complete": not missing_required,
        "missing_required": missing_required,
        "known_gaps": known_gaps,
        "file_count": len(files),
        "present_file_count": len(present_files),
        "raw_reference_count": len(raw_files),
        "raw_reference_present_count": sum(
            1 for item in raw_files if item["exists"] and item["kind"] == "file"
        ),
        "total_bytes": sum(item["size_bytes"] or 0 for item in present_files),
        "role_counts": dict(sorted(role_counts.items())),
        "artifact_digest_sha256": artifact_digest(files),
        "files": files,
    }


def render_markdown(manifest: dict[str, Any], json_sha256: str) -> str:
    grades = manifest["grade_definitions"]
    lines = [
        "# 06 现有证据 Artifact Manifest",
        "",
        "## 1. 用途",
        "",
        "本文件由 `tools/build_thesis_artifact_manifest.py` 从审核后的 catalog 生成。",
        "JSON 是机器可读事实源，本 Markdown 只提供审阅摘要。校验值覆盖当前可访问",
        "文件的路径、字节数与 SHA256；历史实验未记录的 Git commit 不用当前 commit",
        "冒充，而是保留为 provenance gap。",
        "",
        f"- 生成时间（UTC）：`{manifest['generated_at_utc']}`",
        f"- 当前仓库 commit：`{manifest['repository']['current_commit']}`",
        f"- 当前工作树状态：`{manifest['repository']['worktree_state']}`",
        f"- Catalog SHA256：`{manifest['catalog_sha256']}`",
        f"- JSON SHA256：`{json_sha256}`",
        "",
        "## 2. 证据等级",
        "",
        "| 等级 | 定义 |",
        "|---|---|",
    ]
    for grade in ("A", "B", "C", "D"):
        lines.append(f"| {grade} | {grades[grade]} |")
    lines.extend(
        [
            "",
            "## 3. 总表",
            "",
            "| ID | 证据 | 数据层 | 等级 | 状态 | 样本范围 | 文件 | 原始输入 | 必需项 |",
            "|---|---|---|---:|---|---|---:|---:|---:|",
        ]
    )
    for artifact in manifest["artifacts"]:
        required = "完整" if artifact["required_complete"] else "缺失"
        lines.append(
            "| {id} | {title} | {layer} | {grade} | {status} | {scope} | "
            "{present}/{total} | {raw_present}/{raw_total} | {required} |".format(
                id=artifact["id"],
                title=artifact["title"],
                layer=artifact["data_layer"],
                grade=artifact["evidence_grade"],
                status=artifact["declared_status"],
                scope=artifact["sample_scope"],
                present=artifact["present_file_count"],
                total=artifact["file_count"],
                raw_present=artifact["raw_reference_present_count"],
                raw_total=artifact["raw_reference_count"],
                required=required,
            )
        )
    lines.extend(["", "## 4. 分项边界", ""])
    for artifact in manifest["artifacts"]:
        lines.extend(
            [
                f"### {artifact['id']} {artifact['title']}",
                "",
                f"- Artifact digest：`{artifact['artifact_digest_sha256']}`",
                f"- 可访问字节数：`{artifact['total_bytes']}`",
                "- 可支持结论：" + "；".join(artifact["claims_supported"]),
                "- 不可外推：" + "；".join(artifact["claim_boundaries"]),
            ]
        )
        if artifact["provenance_gaps"]:
            lines.append(
                "- Provenance gaps：" + "；".join(artifact["provenance_gaps"])
            )
        if artifact["missing_required"]:
            lines.append(
                "- **缺失必需项**：" + "；".join(artifact["missing_required"])
            )
        if artifact["known_gaps"]:
            lines.append(
                "- **已知缺失包**：" + "；".join(artifact["known_gaps"])
            )
        primary = [
            item["path"]
            for item in artifact["files"]
            if item["exists"]
            and any(
                role
                in {
                    "raw_input",
                    "machine_summary",
                    "run_manifest",
                    "run_index",
                    "authority_report",
                    "build_product",
                }
                for role in item["roles"]
            )
        ]
        if primary:
            shown = primary[:8]
            suffix = f"；另有 {len(primary) - len(shown)} 项见 JSON" if len(primary) > 8 else ""
            lines.append("- 主要文件：" + "；".join(f"`{path}`" for path in shown) + suffix)
        lines.append("")
    lines.extend(
        [
            "## 5. 当前最重要缺口",
            "",
            "1. 历史 sweep manifest 均未保存实验时 Git/submodule commit 和完整配置快照；",
            "2. Jetson smoke 与 microbench 的原始 bag、CSV/JSON 结果未在当前工作区；",
            "3. 45 Hz 短背景记录有原始 NPZ，但标准化阈值摘要要等 R06/R07；",
            "4. NIS 原始与聚合数据完整，但自由度和 internal/proxy 语义要等 R05；",
            "5. 代理极端场景只有单 seed，不能据此比较两种控制模式的统计优劣。",
            "",
            "## 6. 重生成",
            "",
            "```bash",
            "python3 tools/build_thesis_artifact_manifest.py",
            "python3 tools/build_thesis_artifact_manifest.py --check",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def build_outputs(
    catalog_path: Path,
    *,
    generated_at_utc: str | None = None,
) -> tuple[bytes, bytes]:
    catalog_data = catalog_path.read_bytes()
    catalog = json.loads(catalog_data.decode("utf-8"))
    manifest = {
        "schema_version": 1,
        "generated_at_utc": generated_at_utc
        or dt.datetime.now(tz=dt.timezone.utc).isoformat(),
        "catalog_path": display_path(catalog_path),
        "catalog_sha256": sha256_bytes(catalog_data),
        "grade_definitions": catalog["grade_definitions"],
        "repository": repository_state(),
        "artifacts": [build_artifact(spec) for spec in catalog["artifacts"]],
    }
    json_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    ).encode("utf-8")
    markdown_bytes = (
        render_markdown(manifest, sha256_bytes(json_bytes)).rstrip() + "\n"
    ).encode("utf-8")
    return json_bytes, markdown_bytes


def main() -> int:
    args = parse_args()
    generated_at_utc = None
    if args.check and args.output_json.is_file():
        current_manifest = json.loads(args.output_json.read_text(encoding="utf-8"))
        generated_at_utc = current_manifest.get("generated_at_utc")
    json_bytes, markdown_bytes = build_outputs(
        args.catalog,
        generated_at_utc=generated_at_utc,
    )
    outputs = (
        (args.output_json, json_bytes),
        (args.output_markdown, markdown_bytes),
    )
    if args.check:
        failed = False
        for path, expected in outputs:
            current = path.read_bytes() if path.is_file() else None
            if current == expected:
                print(f"OK       {display_path(path)}")
            else:
                print(f"DIFFERS  {display_path(path)}")
                failed = True
        return 1 if failed else 0
    for path, data in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(f"WROTE {display_path(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
