"""Evidence-preserving network access and explicit metadata adapters.

No lookup failure is bibliographic evidence. Cached bodies are immutable and
content addressed; an offline replay never goes to the network.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from html.parser import HTMLParser
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode

import requests


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class EvidenceClient:
    def __init__(self, directory, offline=False, delay=0.55, retries=2, timeout=18):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.offline, self.delay, self.retries, self.timeout = offline, delay, retries, timeout
        self.lock = threading.Lock()
        self.last = 0.0

    def fetch(self, url, source, accept=None):
        headers = {"User-Agent": "AUV-Bibliography-Audit/1.0 (mailto:xgw24@mails.tsinghua.edu.cn)"}
        if accept:
            headers["Accept"] = accept
        key = hashlib.sha256((url + (accept or "")).encode()).hexdigest()
        target = self.directory / (key + ".json")
        if target.exists():
            data = json.loads(target.read_text())
            body = self.directory / data["body_file"] if data.get("body_file") else None
            if body and hashlib.sha256(body.read_bytes()).hexdigest() != data["sha256"]:
                raise ValueError(f"Evidence body hash mismatch: {body}")
            return data
        if self.offline:
            return {"id": key, "url": url, "source": source, "status": "UNVERIFIABLE",
                    "error": "offline_cache_miss", "retrieved_at": None}
        attempts = []
        body = b""
        data = {"id": key, "url": url, "source": source}
        for attempt in range(self.retries + 1):
            with self.lock:
                time.sleep(max(0, self.delay - (time.monotonic() - self.last)))
                self.last = time.monotonic()
            timestamp = utcnow()
            try:
                response = requests.get(url, headers=headers, timeout=self.timeout)
                body = response.content
                code = response.status_code
                data.update(http_status=code, retrieved_at=timestamp,
                            final_url=response.url, content_type=response.headers.get("Content-Type", ""))
                attempts.append({"at": timestamp, "http_status": code})
                if code == 200:
                    data["status"] = "RETRIEVED"  # Never VERIFIED merely because HTTP 200.
                    break
                data["status"] = "ACCESS_BLOCKED" if code in (401, 403, 429) else "UNVERIFIABLE"
                if code not in (429, 500, 502, 503, 504):
                    break
                if attempt < self.retries:
                    try:
                        pause = float(response.headers.get("Retry-After", 2 ** attempt))
                    except ValueError:
                        pause = 2 ** attempt
                    time.sleep(min(10, max(0, pause)))
            except requests.RequestException as exc:
                data.update(status="UNVERIFIABLE", retrieved_at=timestamp, error=type(exc).__name__)
                attempts.append({"at": timestamp, "error": type(exc).__name__})
                if attempt < self.retries:
                    time.sleep(2 ** attempt)
        if body:
            digest = hashlib.sha256(body).hexdigest()
            body_file = digest + ".body"
            (self.directory / body_file).write_bytes(body)
            data.update(body_file=body_file, sha256=digest)
        data["attempts"] = attempts
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        return data

    def json_body(self, evidence):
        if evidence.get("status") != "RETRIEVED":
            return None
        try:
            return json.loads((self.directory / evidence["body_file"]).read_bytes())
        except (ValueError, KeyError):
            return None

    def import_web_snapshot(self, path, url, source):
        snapshot = json.loads(Path(path).read_text())
        if snapshot["url"] != url or url not in snapshot["body"]:
            raise ValueError("Snapshot URL does not match assertion")
        body = snapshot["body"].encode("utf-8")
        digest = hashlib.sha256(body).hexdigest()
        key = hashlib.sha256((url + ":web_snapshot:" + digest).encode()).hexdigest()
        (self.directory / (digest + ".body")).write_bytes(body)
        record = {"id": key, "url": url, "source": source, "status": "RETRIEVED",
                  "retrieved_at": snapshot["retrieved_at"], "body_file": digest + ".body",
                  "sha256": digest, "access_method": snapshot["access_method"],
                  "snapshot_path": str(path), "content_type": "text/plain; extracted by web tool"}
        (self.directory / (key + ".json")).write_text(json.dumps(record, ensure_ascii=False, indent=2)+"\n")
        return record


def crossref_record(message, evidence):
    def year(field):
        parts = message.get(field, {}).get("date-parts", [[]])[0]
        return str(parts[0]) if parts and isinstance(parts[0], int) and 1000 <= parts[0] <= 2999 else None
    # Final print year has priority. Deposit/created/indexed are never publication dates.
    publication_year = year("published-print") or year("published") or year("issued") or year("published-online")
    names = []
    for author in message.get("author", []):
        names.append({"family": author.get("family", author.get("name", "")),
                      "given": author.get("given", "")})
    title = (message.get("title") or [None])[0]
    subtitle = (message.get("subtitle") or [None])[0]
    if title and subtitle:
        title += ": " + subtitle
    fields = {
        "type": message.get("type"), "doi": message.get("DOI"),
        "title": title, "author": names or None,
        "year": publication_year,
        "publication": (message.get("container-title") or [None])[0],
        "publisher": message.get("publisher"), "volume": message.get("volume"),
        "number": message.get("issue"), "pages": message.get("page"),
        "eid": message.get("article-number"), "isbn": message.get("ISBN"),
    }
    return {"fields": fields, "evidence": evidence,
            "lineage": "publisher_deposit:crossref:" + message.get("DOI", "").lower(),
            "date_basis": "published-print" if year("published-print") else "publication_date",
            "provider": "crossref", "raw_type": message.get("type")}


def lookup_crossref(client, doi=None, title=None):
    if doi:
        url = "https://api.crossref.org/works/" + quote(doi, safe="")
    else:
        url = "https://api.crossref.org/works?" + urlencode({"query.bibliographic": title, "rows": 3})
    evidence = client.fetch(url, "Crossref publisher-deposited metadata")
    payload = client.json_body(evidence)
    if not payload or not isinstance(payload.get("message"), dict):
        return [], [evidence]
    messages = [payload["message"]] if doi else payload["message"].get("items", [])
    return [crossref_record(m, evidence) for m in messages], [evidence]


def lookup_datacite(client, doi):
    url = "https://api.datacite.org/dois/" + quote(doi, safe="")
    ev = client.fetch(url, "DataCite registrant metadata")
    payload = client.json_body(ev)
    if not payload or not payload.get("data"):
        return [], [ev]
    a = payload["data"]["attributes"]
    fields = {"doi": a.get("doi"), "title": (a.get("titles") or [{}])[0].get("title"),
              "author": [{"family": n.get("familyName", n.get("name", "")), "given": n.get("givenName", "")}
                         for n in a.get("creators", [])], "year": str(a.get("publicationYear", "")),
              "publisher": a.get("publisher"), "type": a.get("types", {}).get("resourceTypeGeneral")}
    return [{"fields": fields, "provider": "datacite", "evidence": ev,
             "lineage": "registrant_deposit:datacite:" + doi.lower()}], [ev]


def lookup_openalex(client, doi):
    ev = client.fetch("https://api.openalex.org/works/https://doi.org/" + quote(doi, safe=""),
                      "OpenAlex (derived; Crossref lineage not independent)")
    data = client.json_body(ev)
    if not data or not data.get("id"):
        return [], [ev]
    b = data.get("biblio", {})
    fields = {"title": data.get("title"), "doi": (data.get("doi") or "").replace("https://doi.org/", ""),
              "year": str(data.get("publication_year", "")), "volume": b.get("volume"),
              "number": b.get("issue"),
              "publication": ((data.get("primary_location") or {}).get("source") or {}).get("display_name")}
    # Index first/last pages alone are retained as secondary evidence, not automatically corrected.
    if b.get("first_page") and b.get("last_page"):
        fields["pages"] = b["first_page"] + "--" + b["last_page"]
    return [{"fields": fields, "evidence": ev, "provider": "openalex",
             "lineage": "possibly_crossref_derived:" + doi.lower()}], [ev]


class MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "meta":
            values = dict(attrs)
            key = (values.get("name") or values.get("property") or "").lower()
            if key and values.get("content"):
                self.meta.setdefault(key, []).append(values["content"])


def html_record(text, evidence):
    parser = MetaParser()
    parser.feed(text)
    meta = parser.meta
    def one(*names):
        return next((meta[name][0] for name in names if meta.get(name)), None)
    # Only explicit scholarly citation metadata, not general page update dates.
    date = one("citation_year", "citation_date", "dc.date", "citation_publication_date")
    match = re.search(r"\b([12]\d{3})\b", date or "")
    names = meta.get("citation_author", meta.get("dc.creator", []))
    authors = []
    for name in names:
        if "," in name:
            family, given = name.split(",", 1)
        elif re.search(r"[\u4e00-\u9fff]", name):
            family, given = name, ""
        else:
            parts = name.split()
            family, given = (parts[-1], " ".join(parts[:-1])) if parts else ("", "")
        authors.append({"family": family.strip(), "given": given.strip()})
    first, last = one("citation_firstpage"), one("citation_lastpage")
    journal = one("citation_journal_title")
    conference = one("citation_conference_title")
    fields = {"title": one("citation_title", "dc.title"), "author": authors or None,
              "doi": one("citation_doi", "dc.identifier.doi"), "year": match[1] if match else None,
              "publication": journal or conference, "volume": one("citation_volume"),
              "number": one("citation_issue"), "publisher": one("citation_publisher"),
              "pages": first + "--" + last if first and last else None,
              "eid": one("citation_article_number"),
              "type": "article" if journal else ("inproceedings" if conference else None)}
    return {"fields": fields, "evidence": evidence, "provider": "official_html",
            "lineage": "publisher_html:" + evidence["url"], "raw_meta": meta}
