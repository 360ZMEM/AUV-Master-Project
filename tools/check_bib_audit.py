#!/usr/bin/env python3
"""Validate audit evidence integrity and actual BCF/BBL/PDF outputs.

Tool acceptance and scholarly release readiness are independent booleans.
"""
import argparse
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from bib_audit import FIELDS, ROOT, STATES, discover, norm


def validate_report(directory, root=ROOT):
    data = json.loads((directory/"audit_results.json").read_text())
    current = discover(root)
    errors = []
    if {r["id"] for r in data["entries"]} != {r["id"] for r in current}:
        errors.append("BibTeX entry coverage mismatch")
    current_hashes = {r["file"]: r["file_sha256"] for r in current}
    count = 0
    for row in data["entries"]:
        if row["file_sha256"] != current_hashes.get(row["file"]):
            errors.append("Source changed since audit: " + row["file"])
        if set(row["fields"]) != set(FIELDS):
            errors.append("Missing audited fields: " + row["id"])
        for field, node in row["fields"].items():
            if node["status"] not in STATES:
                errors.append("Invalid status: " + row["id"] + ":" + field)
            if node["status"] != "VERIFIED":
                continue
            count += 1
            if not node["evidence"]:
                errors.append("VERIFIED without evidence: " + row["id"] + ":" + field)
            for evidence in node["evidence"]:
                metadata = directory/"evidence"/(evidence["evidence_id"]+".json")
                if not metadata.exists():
                    errors.append("Missing evidence metadata: " + str(metadata))
                    continue
                record = json.loads(metadata.read_text())
                body = directory/"evidence"/record.get("body_file", "absent")
                if (record.get("status") != "RETRIEVED" or not body.is_file() or
                    hashlib.sha256(body.read_bytes()).hexdigest() != evidence.get("body_sha256") or
                    record.get("url") != evidence.get("url") or not evidence.get("retrieved_at")):
                    errors.append("Evidence integrity failure: " + row["id"] + ":" + field)
    research = [r for r in data["entries"] if r["scope"] == "research"]
    unresolved = [r["key"] for r in research if r["manual_review_required"]]
    undefined = {k:v["undefined"] for k,v in data["citation_scan"]["documents"].items()
                 if k.startswith("auv-") and v["undefined"]}
    return {"coverage": len(data["entries"]), "verified_fields_checked": count, "errors": errors,
            "research_required_review": unresolved, "undefined": undefined,
            "release_ready": not unresolved and not undefined}, data


def check_compiled(root, directory, data):
    paths = {"auv-thesis": "thuthesis/build/auv-thesis/auv-thesis",
             "auv-middle-defense-main": "thuthesis/build/middle-main/auv-middle-defense-main",
             "auv-middle-defense-school": "thuthesis/build/middle-school/auv-middle-defense-school"}
    checks = {}
    for name, relative in paths.items():
        base = root/relative
        errors = []
        required = [base.with_suffix(ext) for ext in [".pdf", ".bcf", ".bbl", ".log", ".blg"]]
        missing = [str(p) for p in required if not p.exists()]
        if missing:
            checks[name] = {"passed":False, "errors":["missing compiled files", *missing]}
            continue
        log = base.with_suffix(".log").read_text(errors="replace")
        bad = re.findall(r"^.*(?:Undefined control sequence|Citation .* undefined|Reference .* undefined|LaTeX Error|Please \(re\)run Biber|Missing character).*$", log, re.M)
        errors.extend(bad)
        blg = base.with_suffix(".blg").read_text(errors="replace")
        errors.extend(re.findall(r"^.*(?:WARN|ERROR).*$",blg,re.M))
        # Attribute names and namespaces differ between Biber versions.
        xml = ET.parse(base.with_suffix(".bcf"))
        actual = {n.text for n in xml.iter() if n.tag.rsplit("}",1)[-1] == "citekey" and n.text and n.text != "*"}
        bbl = base.with_suffix(".bbl").read_text()
        rendered = set(re.findall(r"\\entry\{([^}]+)\}", bbl))
        expected = set(data["citation_scan"]["documents"][name]["cited"])
        if not actual <= expected:
            errors.append("Executed BCF contains citations absent from static graph: " + str(sorted(actual-expected)))
        if actual != rendered:
            errors.append("BCF and BBL entry sets differ: " + str(sorted(actual^rendered)))
        proc = subprocess.run(["pdftotext", "-layout", str(base.with_suffix(".pdf")), "-"], capture_output=True, check=True)
        text = proc.stdout.decode("utf-8")
        pages = text.split("\f")
        reference_pages = [p for i,p in enumerate(pages) if i > 10 and re.search(r"^\s*参\s*考\s*文\s*献\s*$",p,re.M)]
        reference_text = "\f".join(reference_pages)
        if not reference_text:
            errors.append("No reference pages extracted from PDF")
        if re.search(r"题录经|待核对|Crossref 不可解析",reference_text):
            errors.append("Project audit notes leaked into final bibliography")
        extracted = directory/"compiled"/(name+"_bibliography.txt")
        extracted.parent.mkdir(parents=True, exist_ok=True)
        extracted.write_text(reference_text)
        info = subprocess.check_output(["pdfinfo",str(base.with_suffix(".pdf"))]).decode()
        count = int(re.search(r"Pages:\s+(\d+)",info)[1])
        checks[name] = {"passed":not errors,"errors":errors,"pages":count,"cited_keys":len(actual),
                        "static_conditional_only_keys": sorted(expected-actual),
                        "bbl_entries":len(rendered),"bibliography_pages_extracted":len(reference_pages),
                        "pdf":relative+".pdf","pdf_sha256":hashlib.sha256(base.with_suffix(".pdf").read_bytes()).hexdigest(),
                        "gb_style":"gb7714-2015", "type_flags":sorted(set(re.findall(r"\[(?:J|C|M|S|R|EB)(?:/OL)?\]",reference_text)))}
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report",type=Path,default=ROOT/"docs/thesis/bibliography/20261022")
    parser.add_argument("--compiled",action="store_true")
    parser.add_argument("--require-release-ready",action="store_true")
    args = parser.parse_args()
    result,data = validate_report(args.report)
    if args.compiled:
        result["compiled"] = check_compiled(ROOT,args.report,data)
    result["audit_acceptance_passed"] = not result["errors"] and not result["undefined"] and all(v["passed"] for v in result.get("compiled",{}).values())
    (args.report/"acceptance.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result["audit_acceptance_passed"] and (result["release_ready"] or not args.require_release_ready) else 2


if __name__ == "__main__":
    raise SystemExit(main())
