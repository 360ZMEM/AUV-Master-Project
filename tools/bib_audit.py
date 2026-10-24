#!/usr/bin/env python3
"""Field-level BibTeX audit. See docs/thesis/bibliography/README.md."""
from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import html
import json
import re
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pybtex.database import parse_string
from pylatexenc.latex2text import LatexNodes2Text

from bib_audit_sources import EvidenceClient, lookup_crossref, lookup_datacite, lookup_openalex, html_record, utcnow

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/thesis/bibliography/20261022"
FIELDS = ("type", "doi", "title", "author", "year", "publication", "publisher", "volume", "number", "pages", "eid")
STATES = {"VERIFIED", "MISMATCH", "UNVERIFIABLE", "ACCESS_BLOCKED", "SOURCE_CONFLICT", "NOT_APPLICABLE"}
TYPE_MAP = {"journal-article": {"article"}, "book": {"book"}, "monograph": {"book"}, "reference-book": {"book"},
            "edited-book": {"book"}, "proceedings-article": {"inproceedings"},
            "book-chapter": {"incollection", "inproceedings"}, "report": {"report", "techreport"},
            "posted-content": {"online", "misc"}, "Preprint": {"online", "misc"}, "Book": {"book"}, "JournalArticle": {"article"}}


def plain(value):
    text = str(value or "")
    for _ in range(3):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    text = re.sub(r"(?<!\\)%", r"\\%", text)
    return LatexNodes2Text().latex_to_text(text)


def norm(value):
    text = unicodedata.normalize("NFKD", plain(value)).casefold()
    text = text.translate(str.maketrans({"ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "ł": "l"}))
    return "".join(c for c in text if c.isalnum() and not unicodedata.combining(c))


def normalize_doi(value):
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", str(value or "").strip(), flags=re.I).lower()


def strip_comments(text):
    return re.sub(r"(?<!\\)%[^\n]*", "", text)


def entry_blocks(text):
    """Find balanced original blocks for stable, minimum-diff patches (not parsing metadata)."""
    pattern = re.compile(r"(?im)^\s*@([a-z]+)\s*([({])")
    for match in pattern.finditer(text):
        kind = match[1].lower()
        if kind in {"comment", "preamble", "string"}:
            continue
        start = match.start()
        pos = match.end()
        depth, quote, escape = 1, False, False
        opener, closer = match[2], "}" if match[2] == "{" else ")"
        while pos < len(text) and depth:
            ch = text[pos]
            if not escape:
                if ch == '"':
                    quote = not quote
                if not quote and ch == opener:
                    depth += 1
                if not quote and ch == closer:
                    depth -= 1
            escape = ch == "\\" and not escape
            pos += 1
        block = text[start:pos]
        key = re.match(r"\s*([^,\s]+)\s*,", text[match.end():])
        if key:
            yield key[1], start, pos, block


def parse_bib(path, base):
    text = path.read_text(encoding="utf-8")
    # BibTeX comments outside entries may contain '@misc' examples; Pybtex
    # otherwise interprets them as commands. Do not strip percent-encoded URLs.
    database = parse_string(re.sub(r"(?m)^\s*%[^\n]*", "", text), "bibtex")
    blocks = {k: (s, e, b) for k, s, e, b in entry_blocks(text)}
    result = []
    for key, item in database.entries.items():
        fields = dict(item.fields)
        authors = []
        for person in item.persons.get("author", []):
            family = " ".join(person.prelast_names + person.last_names)
            given = " ".join(person.first_names + person.middle_names)
            authors.append({"family": family, "given": given})
        fields["author"] = authors or None
        fields["type"] = item.type
        fields["publication"] = fields.get("journal", fields.get("journaltitle", fields.get("booktitle")))
        scope = "research" if path.name == "auv-references.bib" and "ref" in path.parts else "template_fixture"
        if "vendor" in path.parts:
            scope = "upstream_vendor"
        if "backups" in path.parts:
            scope = "frozen_backup"
        result.append({"id": str(path.relative_to(base)) + "#" + key, "key": key,
                       "file": str(path.relative_to(base)), "scope": scope, "original": fields,
                       "line": text.count("\n", 0, blocks[key][0]) + 1,
                       "file_sha256": hashlib.sha256(text.encode()).hexdigest()})
    return result


def discover(base):
    paths = sorted((base / "thuthesis").rglob("*.bib"))
    return [entry for path in paths for entry in parse_bib(path, base)]


def scan_tex(base, entries):
    """Static superset scan plus document include graphs; build BCF is checked separately.

    TeX branches/macros are not executed. Dynamic keys are reported explicitly.
    Comments/verbatim code do not create references. nocite{*} expands per library.
    """
    excluded = {"build", "backups", "vendor"}
    files = [p for p in (base / "thuthesis").rglob("*.tex")
             if not excluded.intersection(p.relative_to(base / "thuthesis").parts)]
    tex = {}
    occurrences = []
    for path in files:
        text = strip_comments(path.read_text(encoding="utf-8"))
        text = re.sub(r"\\begin\{(verbatim\*?|lstlisting|minted)\}.*?\\end\{\1\}", "", text, flags=re.S)
        rel = str(path.relative_to(base))
        tex[rel] = text
        pattern = r"\\((?:[A-Za-z]*cite[A-Za-z]*|nocite))\*?\s*(?:\[[^\]]*\]\s*)*\{([^{}]*)\}"
        for match in re.finditer(pattern, text, re.I):
            groups = [match[2]]
            if match[1].lower().endswith("cites"):
                tail = text[match.end():]
                while True:
                    extra = re.match(r"\s*(?:\[[^\]]*\]\s*)*\{([^{}]*)\}", tail)
                    if not extra:
                        break
                    groups.append(extra[1])
                    tail = tail[extra.end():]
            for key in ",".join(groups).split(","):
                occurrences.append({"file": rel, "line": text.count("\n", 0, match.start()) + 1,
                                    "command": match[1], "key": key.strip(),
                                    "context": text[max(0, match.start()-120):match.end()+120]})
    by_file = defaultdict(list)
    for occurrence in occurrences:
        by_file[occurrence["file"]].append(occurrence)
    documents = {}
    for name in ("auv-thesis", "auv-middle-defense-main", "auv-middle-defense-school", "thuthesis-example"):
        pending = [f"thuthesis/{name}.tex"]
        seen, libraries, cites = set(), set(), []
        while pending:
            rel = pending.pop()
            if rel in seen or rel not in tex:
                continue
            seen.add(rel)
            text = tex[rel]
            cites.extend(by_file[rel])
            for match in re.finditer(r"\\(?:input|include)\s*\{([^{}]+)\}", text):
                target = match[1] if match[1].endswith(".tex") else match[1]+".tex"
                pending.append("thuthesis/" + target)
            for match in re.finditer(r"\\(?:addbibresource(?:\[[^]]*\])?|bibliography)\s*\{([^{}]+)\}", text):
                for bib in match[1].split(","):
                    libraries.add("thuthesis/" + (bib if bib.endswith(".bib") else bib + ".bib"))
        defined = {e["key"] for e in entries if e["file"] in libraries}
        keys = {c["key"] for c in cites}
        if "*" in keys:
            keys = (keys - {"*"}) | defined
        documents[name] = {"files": sorted(seen), "libraries": sorted(libraries),
                           "cited": sorted(keys), "undefined": sorted(keys-defined),
                           "unused": sorted(defined-keys)}
    allkeys = {e["key"] for e in entries if e["scope"] != "upstream_vendor"}
    return {"documents": documents, "occurrences": occurrences,
            "static_undefined": [c for c in occurrences if c["key"] not in allkeys | {"*"}],
            "method": "comment-stripped static include-graph superset; BCF compilation validates executed branches"}


def authors_equal(left, right):
    if not left or not right:
        return False
    # An explicit 'others' is a truncated author list, not evidence for unspecified names.
    if len(left) != len(right):
        return False
    for a, b in zip(left, right):
        if norm(a["family"]) != norm(b["family"]):
            return False
        ga, gb = plain(a.get("given", "")), plain(b.get("given", ""))
        if norm(ga) == norm(gb):
            continue
        # Allow initials vs full given names only if *all* tokens match initials.
        ta = re.findall(r"[^\W\d_]+", ga, re.U)
        tb = re.findall(r"[^\W\d_]+", gb, re.U)
        if len(ta) == 1 and len(ta[0]) > 1 and ta[0].isupper():
            ta = list(ta[0])
        if len(tb) == 1 and len(tb[0]) > 1 and tb[0].isupper():
            tb = list(tb[0])
        if len(ta) != len(tb) or not ta:
            return False
        for aa, bb in zip(ta, tb):
            if norm(aa) != norm(bb) and not (norm(aa)[0] == norm(bb)[0] and min(len(aa),len(bb)) == 1):
                return False
    return True


def equal_field(field, old, new):
    if field == "type":
        return bool(TYPE_MAP.get(old, {old}) & TYPE_MAP.get(new, {new}))
    if field == "author":
        return authors_equal(old, new)
    if field == "doi":
        return normalize_doi(old) == normalize_doi(new)
    return norm(old) == norm(new)


def identity(entry, record):
    a, b = entry["original"], record["fields"]
    # DOI alone NEVER establishes identity. Exact normalized title plus authors,
    # or exact title plus agreeing year/publication for authorless metadata.
    exact_title = norm(a.get("title")) == norm(b.get("title"))
    main_title_only = (":" in plain(a.get("title")) and
                       norm(plain(a["title"]).split(":",1)[0]) == norm(b.get("title")) and
                       normalize_doi(a.get("doi")) == normalize_doi(b.get("doi")))
    if not (exact_title or main_title_only) or not norm(a.get("title")):
        return False
    if a.get("author") and b.get("author"):
        return authors_equal(a["author"], b["author"])
    return bool(a.get("year") and a.get("volume") and a.get("pages") and
                normalize_doi(a.get("doi")) == normalize_doi(b.get("doi")) and
                equal_field("year", a["year"], b.get("year")) and
                equal_field("volume", a["volume"], b.get("volume")) and
                equal_field("pages", a["pages"], b.get("pages")))


def collect(entry, client, supplemental):
    original = entry["original"]
    doi = normalize_doi(original.get("doi"))
    records, attempts = lookup_crossref(client, doi=doi or None, title=plain(original.get("title")))
    if doi and not any(identity(entry, r) for r in records):
        extra, ev = lookup_datacite(client, doi)
        records.extend(extra)
        attempts.extend(ev)
        # Wrong DOI may resolve to a real but different paper. Retain both records;
        # title search is a candidate discovery, never automatic DOI replacement.
        extra, ev = lookup_crossref(client, title=plain(original.get("title")))
        records.extend(extra)
        attempts.extend(ev)
        extra, ev = lookup_openalex(client, doi)
        records.extend(extra)
        attempts.extend(ev)
    url = original.get("url")
    if url and (not doi or not any(identity(entry, r) for r in records)):
        attempts.append(client.fetch(url, "recorded publisher/official URL (body alone is not verification)"))
    # Curated assertions must point to a cached external body and a verbatim excerpt.
    # Each asserted field must be present in that excerpt (validated by the loader).
    for assertion in supplemental.get(entry["key"], []):
        ev = client.fetch(assertion["url"], assertion["source"])
        attempts.append(ev)
        if assertion.get("snapshot"):
            ev = client.import_web_snapshot(ROOT / assertion["snapshot"], assertion["url"], assertion["source"])
            attempts.append(ev)
        if ev.get("status") != "RETRIEVED":
            continue
        body = (client.directory / ev["body_file"]).read_bytes()
        if body.startswith(b"%PDF"):
            import subprocess
            proc = subprocess.run(["pdftotext", "-layout", str(client.directory/ev["body_file"]), "-"],
                                  capture_output=True, timeout=35, check=False)
            bodytext = proc.stdout.decode("utf-8", errors="replace") if proc.returncode == 0 else ""
        else:
            bodytext = html.unescape(body.decode(assertion.get("encoding", "utf-8"), errors="replace"))
        if assertion.get("html_metadata"):
            records.append(html_record(bodytext, ev))
            if not assertion.get("fields"):
                continue
        visible = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", "", bodytext, flags=re.S|re.I)
        visible = re.sub(r"<[^>]+>", " ", visible)
        visible = re.sub(r"L\d+(?:@P[\d-]+)?:\s*", " ", visible)
        visible = " ".join(html.unescape(visible).split())
        missing = [fragment for fragment in assertion.get("excerpts", [])
                   if fragment not in bodytext and " ".join(fragment.split()) not in visible]
        if missing or not assertion.get("excerpts"):
            attempts.append({"status": "UNVERIFIABLE", "url": assertion["url"],
                             "error": "curated_excerpt_absent", "missing": missing})
            continue
        quoted = " ".join(assertion["excerpts"])
        supported = {}
        for field, value in assertion["fields"].items():
            if field == "author":
                tokens = [part for a in value for part in [a.get("family"), a.get("given")] if part]
                ok = all(norm(token) in norm(quoted) for token in tokens)
            elif field == "type":
                ok = bool(assertion.get("basis"))
            else:
                ok = norm(value) in norm(quoted)
            if ok:
                supported[field] = value
            else:
                attempts.append({"status":"UNVERIFIABLE","url":assertion["url"],
                                 "error":"asserted_value_absent_from_excerpt","field":field})
        records.append({"fields": supported, "evidence": ev,
                        "provider": "official_curated", "lineage": assertion["lineage"],
                        "excerpts": assertion["excerpts"], "basis": assertion.get("basis"),
                        "identity_only_fields": assertion.get("identity_only_fields", []),
                        "review_only_fields": assertion.get("review_only_fields", []),
                        "identity_confirmed": assertion.get("identity_confirmed", False) and bool(supported.get("title")),
                        "authoritative_override": assertion.get("authoritative_override", []),
                        "locator_semantics": assertion.get("locator_semantics")})
    return {"records": records, "attempts": attempts}


def audit_entry(entry, collected):
    original = entry["original"]
    matches = [r for r in collected["records"] if identity(entry, r) or r.get("identity_confirmed")]
    identified_bodies = {(r["evidence"]["id"], norm(r["fields"].get("title"))) for r in matches}
    for r in collected["records"]:
        if r not in matches and (r["evidence"]["id"], norm(r["fields"].get("title"))) in identified_bodies:
            matches.append(r)
    anchor = normalize_doi(original.get("doi"))
    if anchor and any(normalize_doi(r["fields"].get("doi")) == anchor for r in matches):
        matches = [r for r in matches if not r["fields"].get("doi") or normalize_doi(r["fields"]["doi"]) == anchor]
    # All matched DOI identities must agree. Indices are not independent votes.
    dois = {normalize_doi(r["fields"].get("doi")) for r in matches if r["fields"].get("doi")}
    if len(dois) > 1:
        matches = []
    result = dict(entry, identity_verified=bool(matches), fields={}, attempts=collected["attempts"], records=collected["records"])
    for field in FIELDS:
        old = original.get(field)
        values = [(r, r["fields"].get(field)) for r in matches if r["fields"].get(field) not in (None, "", [])
                  and field not in r.get("identity_only_fields", [])]
        node = {"original": old, "suggested": None, "evidence": [], "required": field in required_fields(original)}
        if any(field in r.get("review_only_fields", []) for r in matches):
            node["review_only"] = True
        overrides = [(r, v) for r, v in values if field in r.get("authoritative_override", [])]
        if overrides:
            values = overrides
        # Publisher-deposit source outranks a secondary index, never count it twice.
        authoritative = [(r, v) for r, v in values if r["provider"] != "openalex"]
        if authoritative:
            values = authoritative
        if values:
            first_record, proposed = values[0]
            conflicts = [(r, v) for r, v in values[1:] if not equal_field(field, proposed, v) and norm(proposed) != norm(v)]
            node["suggested"] = proposed
            node["evidence"] = [{"url": r["evidence"]["url"], "source": r["evidence"]["source"],
                                 "retrieved_at": r["evidence"]["retrieved_at"], "evidence_id": r["evidence"]["id"],
                                 "body_sha256": r["evidence"].get("sha256"), "lineage": r["lineage"], "provider": r["provider"],
                                 "value": v, "excerpts": r.get("excerpts", []), "basis": r.get("basis")}
                                for r, v in values]
            node["status"] = "SOURCE_CONFLICT" if conflicts else ("VERIFIED" if equal_field(field, old, proposed) else "MISMATCH")
            if field == "publisher" and not old and not node["required"]:
                node["status"] = "NOT_APPLICABLE"
                node["reason"] = "optional_publisher_omitted_for_this_entry_type"
            # A lone page-like integer is ambiguous in Crossref's page field.
            # Never reinterpret it as pages or eid absent explicit source semantics.
            if field == "pages" and re.fullmatch(r"\d+", str(proposed)) and not first_record.get("locator_semantics"):
                node["status"] = "UNVERIFIABLE"
                node["reason"] = "single_numeric_locator_semantics_unknown"
            if field == "pages" and matches and any(str(r["fields"].get("eid")) == str(proposed) for r in matches):
                node["status"] = "MISMATCH" if old else "NOT_APPLICABLE"
                node["reason"] = "article_number_is_not_pagination"
        else:
            n_a = not old and field in {"doi", "volume", "number", "pages", "eid", "publisher"}
            if field in {"volume", "number", "publication"} and original["type"] in {"book", "online", "manual", "standard", "report"} and not old:
                n_a = True
            if field in {"doi", "pages"} and not old and original["type"] in {"article", "inproceedings"}:
                n_a = False  # Missing locator is unknown, not proof of non-applicability.
            node["status"] = "NOT_APPLICABLE" if n_a else ("ACCESS_BLOCKED" if not matches and any(a.get("status") == "ACCESS_BLOCKED" for a in collected["attempts"]) else "UNVERIFIABLE")
            if field == "pages" and not old and any(r["fields"].get("eid") for r in matches):
                node["status"] = "NOT_APPLICABLE"
            if field == "eid" and not old and any(r["fields"].get("pages") and re.search(r"\d[-–—]+\d", str(r["fields"]["pages"])) for r in matches):
                node["status"] = "NOT_APPLICABLE"
        result["fields"][field] = node
    result["required_unresolved"] = [f for f, v in result["fields"].items() if v["required"] and v["status"] != "VERIFIED"]
    result["manual_review_required"] = not result["identity_verified"] or bool(result["required_unresolved"])
    return result


def required_fields(original):
    fields = {"type", "title", "author"}
    if original.get("year") or original["type"] not in {"online", "manual"}:
        fields.add("year")
    if original["type"] in {"article", "inproceedings", "incollection"}:
        fields.add("publication")
    if original["type"] == "book":
        fields.add("publisher")
    return fields


def serialize_bib_value(field, value):
    if field == "author":
        return " and ".join((a["family"] + (", " + a["given"] if a.get("given") else "")) for a in value)
    return str(value).replace("&", r"\&")


def proposed_patch(base, results):
    """Only unique identity and publication fields; title/author/type changes require review."""
    safe, review, proposed_files = [], [], {}
    for row in results:
        if row["scope"] != "research":
            continue
        if row["original"].get("note"):
            safe.append({"file":row["file"],"key":row["key"],"field":"note",
                         "old":row["original"]["note"],"new":None,"action":"note_to_comment",
                         "reason":"project provenance and commentary are retained in source comments, not printed as bibliographic publication data",
                         "evidence":[]})
        page = row["fields"]["pages"]
        eid = row["fields"]["eid"]
        # The user expressly permits omitting unverified pagination. Move a
        # locator only when a source explicitly identifies it as article/paper ID.
        if page["original"] and page["status"] in {"UNVERIFIABLE", "MISMATCH"}:
            explicit_id = eid["suggested"] if eid["evidence"] and eid["status"] != "SOURCE_CONFLICT" else None
            convertible = explicit_id and norm(str(page["original"]).removeprefix("Paper ")) == norm(explicit_id)
            if convertible or page.get("reason") == "single_numeric_locator_semantics_unknown":
                safe.append({"file": row["file"], "key": row["key"], "field": "locator",
                             "old": page["original"], "new": explicit_id if convertible else None,
                             "action": "pages_to_eid" if convertible else "omit_unverified_pages",
                             "evidence": eid["evidence"] if convertible else page["evidence"]})
        for field, node in row["fields"].items():
            if node["status"] != "MISMATCH" or node["suggested"] is None:
                continue
            if field in {"pages", "eid"} and any(c["key"] == row["key"] and c["field"] == "locator" for c in safe):
                continue
            change = {"file": row["file"], "key": row["key"], "field": field,
                      "old": node["original"], "new": node["suggested"], "evidence": node["evidence"]}
            # DOI spelling changes require a fully verified unique official identity;
            # no invented pages or ambiguous locator conversion. Publisher conflicts
            # require an explicit external-evidence override.
            allowed = field in {"year", "volume", "number", "pages", "eid", "publication"}
            if field == "doi":
                allowed = (not row["required_unresolved"] and bool(node["evidence"]) and
                           all(e["provider"].startswith("official") for e in node["evidence"]))
            if field == "type" and change["old"] == "online" and change["new"] == "standard":
                allowed = bool(node["evidence"]) and all(e["provider"].startswith("official") for e in node["evidence"])
            if field == "pages":
                allowed = bool(re.fullmatch(r"\d+\s*[-–—]+\s*\d+", str(node["suggested"]))) and not node.get("reason")
            if field == "year" and row["original"]["type"] == "book":
                allowed = False  # Print/electronic editions require explicit review.
            if node.get("review_only"):
                allowed = False  # An explicit resource/version caveat must survive candidate generation.
            if row["identity_verified"] and allowed and node["evidence"] and all("OpenAlex" not in e["source"] for e in node["evidence"]):
                safe.append(change)
            else:
                review.append(change)
    for path in sorted({r["file"] for r in safe}):
        before = (base / path).read_text()
        changes = [c for c in safe if c["file"] == path]
        after = before
        for key, start, end, block in reversed(list(entry_blocks(before))):
            updated = block
            for change in (c for c in changes if c["key"] == key):
                field = change["field"]
                if field == "note" and change.get("action") == "note_to_comment":
                    updated = re.sub(r"(?im)^\s*note\s*=\s*\{[^\n]*\},?\s*$",
                                     lambda m: "  % audit-note: " + str(change["old"]), updated, count=1)
                    continue
                if field == "locator":
                    pattern = re.compile(r"(?im)^(\s*)pages(\s*=\s*)\{[^{}]*\}\s*,?[^\S\n]*\n?")
                    if change["action"] == "pages_to_eid":
                        updated = pattern.sub(lambda m: m[1]+"eid"+m[2]+"{"+str(change["new"])+"},\n", updated, count=1)
                    else:
                        updated = pattern.sub("", updated, count=1)
                    continue
                if field == "type":
                    updated = re.sub(r"(?i)@"+str(change["old"])+r"(?=\s*[({])", "@"+str(change["new"]), updated, count=1)
                    continue
                rawfield = "journal" if field == "publication" and re.search(r"(?im)^\s*journal\s*=", updated) else ("booktitle" if field == "publication" else field)
                value = serialize_bib_value(field, change["new"])
                if field == "pages":
                    value = re.sub(r"\s*[-–—]+\s*", "--", value)
                pattern = re.compile(r"(?im)^(\s*"+rawfield+r"\s*=\s*)\{([^{}]*)\}(\s*,?)")
                if pattern.search(updated):
                    updated = pattern.sub(lambda m: m[1]+"{"+value+"}"+m[3], updated, count=1)
                elif field == "eid" and change["old"] is None and updated.endswith("}"):
                    updated = updated[:-1].rstrip() + "\n  eid       = {"+value+"},\n}"
                else:
                    # Do not rewrite complex values or add missing fields implicitly.
                    review.append(dict(change, reason="not_a_simple_existing_braced_field"))
            after = after[:start]+updated+after[end:]
        proposed_files[path] = {"before": before, "after": after}
    patch = "".join("".join(difflib.unified_diff(v["before"].splitlines(True), v["after"].splitlines(True),
                                                fromfile="a/"+p, tofile="b/"+p)) for p, v in proposed_files.items())
    return patch, safe, review, proposed_files


def render(out, entries, citation_scan, results, collection, generated_at):
    out.mkdir(parents=True, exist_ok=True)
    data = {"schema_version": 1, "generated_at": generated_at, "entries": results,
            "coverage": {"entries": len(entries), "audited": len(results), "files": sorted({e["file"] for e in entries})},
            "citation_scan": citation_scan}
    (out / "audit_results.json").write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n")
    (out / "collection.json").write_text(json.dumps(collection, ensure_ascii=False, indent=2)+"\n")
    (out / "unverified_entries.json").write_text(json.dumps([
        {"id":r["id"],"scope":r["scope"],"identity_verified":r["identity_verified"],
         "required_unresolved":r["required_unresolved"],
         "unverified_fields":[f for f,n in r["fields"].items() if n["status"] not in {"VERIFIED","NOT_APPLICABLE"}]}
        for r in results if any(n["status"] not in {"VERIFIED","NOT_APPLICABLE"} for n in r["fields"].values())
    ],ensure_ascii=False,indent=2)+"\n")
    (out / "source_conflicts.json").write_text(json.dumps([
        {"id":r["id"],"field":f,**n} for r in results for f,n in r["fields"].items() if n["status"]=="SOURCE_CONFLICT"
    ],ensure_ascii=False,indent=2)+"\n")
    with (out / "field_differences.csv").open("w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["file", "citekey", "scope", "field", "status", "required", "original", "suggested", "evidence_urls"])
        for row in results:
            for field, node in row["fields"].items():
                writer.writerow([row["file"], row["key"], row["scope"], field, node["status"], node["required"],
                                 json.dumps(node["original"],ensure_ascii=False), json.dumps(node["suggested"],ensure_ascii=False),
                                 " | ".join(e["url"] for e in node["evidence"])])
    research = [r for r in results if r["scope"] == "research"]
    counts = Counter(n["status"] for r in results for n in r["fields"].values())
    lines = ["# BibTeX 全量真实性审计", "", f"生成时间（UTC）：{generated_at}。审计覆盖 {len(results)}/{len(entries)} 条，{len(data['coverage']['files'])} 个文献库；研究文献 {len(research)} 条。", "",
             "覆盖率不代表真实性通过率。外部查询失败从不视为成功；索引不按独立投票计数。", "",
             "| 范围 | 条目 | 身份已核验 | 必要字段待复核 |", "|---|---:|---:|---:|"]
    for scope in sorted({r["scope"] for r in results}):
        group = [r for r in results if r["scope"] == scope]
        lines.append(f"| {scope} | {len(group)} | {sum(r['identity_verified'] for r in group)} | {sum(r['manual_review_required'] for r in group)} |")
    lines += ["", "| 字段状态 | 数量 |", "|---|---:|"]+[f"| {k} | {counts[k]} |" for k in sorted(STATES)]
    lines += ["", "## 引用覆盖", "", "静态扫描为分支并集；最终 BCF/BBL 编译检查补充实际引用证据。", ""]
    for name, doc in citation_scan["documents"].items():
        lines += [f"- `{name}`：{len(doc['cited'])} 个引用键；未定义 {doc['undefined']}；未引用 {doc['unused']}。"]
    lines += ["", "## 文件", "", "- [逐字段结果](audit_results.json) / [差异表（含正确字段）](field_differences.csv)",
              "- [必要字段人工复核](manual_review.md) / [次要字段与页码](secondary_review.md)",
              "- [安全修正候选](safe_corrections.patch) / [争议修改候选](review_changes.json)",
              "- `evidence/`：HTTP 原始响应、时间、来源、SHA-256；`collection.json` 为候选集。", "",
              "本审计验证 L1 身份与 L2 书目字段；不将其等同于正文论断已被原文支持（L3）。"]
    (out / "audit_summary.md").write_text("\n".join(lines)+"\n")
    for name, predicate, intro in [
        ("manual_review.md", lambda r: r["manual_review_required"], "仅列研究文献中身份或必要字段未解决项；页码问题不升级为必要人工审核。"),
        ("secondary_review.md", lambda r: any(v["status"] not in {"VERIFIED", "NOT_APPLICABLE"} and not v["required"] for v in r["fields"].values()), "页码、文章编号、DOI、卷期等次要字段；可以舍弃缺乏证据的页码，但不凭 PDF 总页数补全。")]:
        lines = ["# " + ("必要字段人工复核" if name == "manual_review.md" else "次要字段复核"), "", intro, ""]
        for row in research:
            if not predicate(row):
                continue
            lines += [f"## {row['key']}", "", f"{plain(row['original'].get('title'))}", "",
                      f"身份核验：{row['identity_verified']}；必要字段未解决：{', '.join(row['required_unresolved']) or '无'}。", ""]
            for field, node in row["fields"].items():
                if node["status"] in {"VERIFIED", "NOT_APPLICABLE"} or (name == "manual_review.md" and not node["required"]):
                    continue
                if name == "secondary_review.md" and node["required"]:
                    continue
                urls = " ".join(f"[证据]({e['url']})" for e in node["evidence"])
                lines.append(f"- `{field}` {node['status']}：{node['original']} → {node['suggested']} {urls}")
            lines += ["", "检索记录：" + "；".join(f"[{a.get('status')}]({a.get('url')})" for a in row["attempts"] if a.get("url")), ""]
        (out / name).write_text("\n".join(lines)+"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--apply-safe", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--supplement", type=Path, default=ROOT/"docs/thesis/bibliography/official_evidence.json")
    parser.add_argument("--check", action="store_true", help="Nonzero if research required fields or undefined citations remain")
    args = parser.parse_args()
    entries = discover(args.root)
    cites = scan_tex(args.root, entries)
    supplement = json.loads(args.supplement.read_text()) if args.supplement.exists() else {}
    client = EvidenceClient(args.output / "evidence", offline=args.offline)
    # Dedupe repeated upstream fixture entries. Curated assertions are keyed by citekey.
    grouped = defaultdict(list)
    for entry in entries:
        key = json.dumps(entry["original"], sort_keys=True, ensure_ascii=False) + entry["key"]
        grouped[key].append(entry)
    collection = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(collect, group[0], client, supplement): group for group in grouped.values()}
        for index, future in enumerate(as_completed(jobs), 1):
            group = jobs[future]
            try:
                result = future.result()
            except Exception as exc:
                # Visible per-entry failure, never false positive; let remaining entries finish.
                result = {"records": [], "attempts": [{"status": "UNVERIFIABLE", "error": repr(exc)}]}
            for entry in group:
                collection[entry["id"]] = result
            if index % 10 == 0:
                print(f"Collected {index}/{len(jobs)} unique bibliographic records", flush=True)
    results = [audit_entry(e, collection[e["id"]]) for e in entries]
    for row in results:
        row["cited_in_documents"] = [name for name,doc in cites["documents"].items()
                                      if row["file"] in doc["libraries"] and row["key"] in doc["cited"]]
        row["uncited"] = not row["cited_in_documents"]
    render(args.output, entries, cites, results, collection, utcnow())
    patch, safe, review, proposed = proposed_patch(args.root, results)
    (args.output / "safe_corrections.patch").write_text(patch)
    (args.output / "safe_changes.json").write_text(json.dumps(safe, ensure_ascii=False, indent=2)+"\n")
    (args.output / "review_changes.json").write_text(json.dumps(review, ensure_ascii=False, indent=2)+"\n")
    (args.output / "review_fields.diff").write_text("# Field-level review only; not an applyable BibTeX patch.\n" + "".join(
        f"--- {r['file']}#{r['key']}:{r['field']} (current)\n+++ external suggestion (requires review)\n@@\n-"+
        json.dumps(r["old"],ensure_ascii=False)+"\n+"+json.dumps(r["new"],ensure_ascii=False)+"\n" for r in review))
    if args.apply_safe:
        for path, changes in proposed.items():
            target = args.root / path
            if target.read_text() != changes["before"]:
                raise RuntimeError("Source changed since audit; refusing write: " + path)
            backup = args.output / "before" / path
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                backup.write_text(changes["before"])
            target.write_text(changes["after"])
        print("Safe corrections applied; rerun audit to record final state.")
    print(json.dumps({"entries": len(results), "research": sum(r["scope"]=="research" for r in results),
                      "research_manual": sum(r["scope"]=="research" and r["manual_review_required"] for r in results),
                      "safe_candidates": len(safe), "review_candidates": len(review)}, ensure_ascii=False))
    if args.check and (any(r["manual_review_required"] for r in results if r["scope"] == "research") or
                      any(v["undefined"] for k,v in cites["documents"].items() if k.startswith("auv-"))):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
