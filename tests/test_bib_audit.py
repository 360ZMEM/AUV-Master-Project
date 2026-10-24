"""Negative controls for bibliographic verification (no live API dependency)."""
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import bib_audit as audit
from bib_audit_sources import EvidenceClient, crossref_record


def entry(**updates):
    fields = {"type": "article", "doi": "10.1234/test", "title": "A real study",
              "author": [{"family": "Smith", "given": "J."}], "year": "2020",
              "publication": "Journal", "volume": "3", "number": "2", "pages": "10--15"}
    fields.update(updates)
    return {"id": "test#one", "key": "one", "file": "test.bib", "scope": "research", "original": fields}


def record(**updates):
    fields = entry()["original"].copy()
    fields.update(type="journal-article", author=[{"family": "Smith", "given": "John"}])
    fields.update(updates)
    return {"fields": fields, "provider": "crossref", "lineage": "publisher_deposit:crossref:10.1234/test",
            "evidence": {"id": "abc", "url": "https://api.crossref.org/works/10.1234/test", "source": "Crossref",
                         "retrieved_at": "2026-10-18T00:00:00+00:00", "sha256": "abc"}}


def test_doi_does_not_establish_identity():
    result = audit.audit_entry(entry(), {"records": [record(title="Different article")], "attempts": []})
    assert not result["identity_verified"]
    assert result["fields"]["doi"]["status"] != "VERIFIED"


def test_authors_are_ordered_and_complete():
    assert audit.authors_equal(entry()["original"]["author"], record()["fields"]["author"])
    assert not audit.authors_equal([{"family": "Smith", "given": "John"}], [{"family": "Smith", "given": "Jane"}])
    assert not audit.authors_equal(entry()["original"]["author"], record()["fields"]["author"]*2)


def test_evidence_required_for_verified():
    result = audit.audit_entry(entry(), {"records": [], "attempts": [{"status": "UNVERIFIABLE", "http_status": 404}]})
    assert all(n["status"] != "VERIFIED" for n in result["fields"].values())
    assert result["manual_review_required"]


def test_print_year_not_deposit_or_online_year():
    source = {"published-print": {"date-parts": [[2021, 3]]}, "published-online": {"date-parts": [[2020]]},
              "created": {"date-parts": [[2019]]}, "DOI": "test"}
    assert crossref_record(source, {})["fields"]["year"] == "2021"


def test_pages_and_article_number_are_different():
    result = audit.audit_entry(entry(pages="114689"), {"records": [record(pages=None, eid="114689")], "attempts": []})
    assert result["fields"]["pages"]["status"] != "VERIFIED"
    assert result["fields"]["eid"]["status"] == "MISMATCH"


def test_single_numeric_locator_is_unknown():
    result = audit.audit_entry(entry(pages="114689"), {"records": [record(pages="114689")], "attempts": []})
    assert result["fields"]["pages"]["status"] == "UNVERIFIABLE"


def test_unknown_pages_are_secondary_only():
    result = audit.audit_entry(entry(), {"records": [record(pages=None)], "attempts": []})
    assert result["fields"]["pages"]["status"] == "UNVERIFIABLE"
    assert not result["manual_review_required"]


def test_conflicting_authoritative_sources_not_majority_vote():
    result = audit.audit_entry(entry(), {"records": [record(year="2020"), record(year="2021"), record(year="2020")], "attempts": []})
    assert result["fields"]["year"]["status"] == "SOURCE_CONFLICT"


def test_openalex_crossref_lineage_not_independent_vote():
    secondary = record(year="2021")
    secondary["provider"] = "openalex"
    secondary["lineage"] = "possibly_crossref_derived:10.1234/test"
    result = audit.audit_entry(entry(), {"records": [record(), secondary], "attempts": []})
    assert result["fields"]["year"]["status"] == "VERIFIED"
    assert len(result["fields"]["year"]["evidence"]) == 1


def test_nested_braces_macros_and_percent_encoded_urls(tmp_path):
    path = tmp_path/"a.bib"
    path.write_text('% @misc mentioned in comment\n@string{j="Journal"}\n@article{one,title={A {Nested} title},journal=j,url={https://x/%20},year=2020}\n')
    rows = audit.parse_bib(path, tmp_path)
    assert len(rows) == 1
    assert rows[0]["original"]["publication"] == "Journal"
    assert rows[0]["original"]["url"] == "https://x/%20"


def test_citation_graph_optional_arguments_multicite_and_comments(tmp_path):
    directory = tmp_path/"thuthesis"
    directory.mkdir()
    (directory/"auv-thesis.tex").write_text(r"\addbibresource{ref/x.bib}\input{part}"+"\n"+r"% \cite{bad}")
    (directory/"part.tex").write_text(r"\textcite[see][4]{one,two} \autocites{three}{four} \cite{missing}")
    rows = [{"key": k, "file": "thuthesis/ref/x.bib", "scope": "research"} for k in ["one", "two", "three", "four"]]
    scan = audit.scan_tex(tmp_path, rows)
    assert "bad" not in scan["documents"]["auv-thesis"]["cited"]
    assert "missing" in scan["documents"]["auv-thesis"]["undefined"]
    # Multicites must scan every brace group, not silently discard subsequent keys.
    assert "four" in scan["documents"]["auv-thesis"]["cited"]


@pytest.mark.parametrize("status", [403, 404, 429, 503])
def test_http_failure_never_success(tmp_path, status):
    response = Mock(status_code=status, content=b"failure", url="https://example.test", headers={})
    with patch("bib_audit_sources.requests.get", return_value=response):
        evidence = EvidenceClient(tmp_path, delay=0, retries=0).fetch("https://example.test", "test")
    assert evidence["status"] != "RETRIEVED"
    assert evidence["http_status"] == status


def test_timeout_explicitly_unverifiable(tmp_path):
    with patch("bib_audit_sources.requests.get", side_effect=requests.Timeout):
        evidence = EvidenceClient(tmp_path, delay=0, retries=0).fetch("https://example.test", "test")
    assert evidence["status"] == "UNVERIFIABLE"
    assert evidence["error"] == "Timeout"


def test_offline_cache_miss_never_requests(tmp_path):
    with patch("bib_audit_sources.requests.get", side_effect=AssertionError("network forbidden")):
        result = EvidenceClient(tmp_path, offline=True).fetch("https://example.test", "test")
    assert result["error"] == "offline_cache_miss"


def test_cached_body_tamper_detected(tmp_path):
    response = Mock(status_code=200, content=b'{}', url="https://example.test", headers={})
    client = EvidenceClient(tmp_path, delay=0, retries=0)
    with patch("bib_audit_sources.requests.get", return_value=response):
        evidence = client.fetch("https://example.test", "test")
    (tmp_path/evidence["body_file"]).write_bytes(b'corrupt')
    with pytest.raises(ValueError, match="hash mismatch"):
        client.fetch("https://example.test", "test")


def test_safe_patch_preserves_keys_format_and_comments(tmp_path):
    path = tmp_path/"test.bib"
    before = '% retain comment\n@article{one,\n  year = {2019},\n  pages = {10--15},\n}\n'
    path.write_text(before)
    row = audit.audit_entry(entry(year="2019"), {"records": [record()], "attempts": []})
    diff, safe, review, files = audit.proposed_patch(tmp_path, [row])
    assert "-  year = {2019}" in diff
    assert "@article{one," in files["test.bib"]["after"]
    assert files["test.bib"]["after"].startswith('% retain comment')
    assert path.read_text() == before


def test_early_access_no_fabricated_pages():
    row = audit.audit_entry(entry(pages="1--12"), {"records": [record(pages=None, volume=None, number=None)], "attempts": []})
    assert row["fields"]["pages"]["status"] == "UNVERIFIABLE"
    assert row["fields"]["pages"]["suggested"] is None


def test_null_year_is_unknown_not_string_none():
    record = crossref_record({"issued": {"date-parts": [[None]]}}, {})
    assert record["fields"]["year"] is None


def test_percent_sign_is_not_latex_comment_in_external_title():
    assert audit.norm(r"80\% of claims") == audit.norm("80% of claims")


def test_preprint_is_not_replaced_by_later_publication_same_title():
    original = entry(type="online", doi="10.48550/arxiv.1234")
    preprint = record(type="Preprint", doi="10.48550/arxiv.1234")
    published = record(type="proceedings-article", doi="10.1109/published")
    result = audit.audit_entry(original, {"records": [preprint, published], "attempts": []})
    assert result["identity_verified"]
    assert result["fields"]["doi"]["status"] == "VERIFIED"
    assert result["fields"]["type"]["status"] == "VERIFIED"


def test_explicit_article_number_moves_locator_without_guessing(tmp_path):
    (tmp_path/"test.bib").write_text('@article{one,\n pages = {114689},\n}\n')
    row = audit.audit_entry(entry(pages="114689"), {"records": [record(pages=None, eid="114689")], "attempts": []})
    _, _, _, files = audit.proposed_patch(tmp_path, [row])
    assert "eid = {114689}" in files["test.bib"]["after"]
    assert "pages" not in files["test.bib"]["after"]


def test_unconfirmed_numeric_pages_can_only_be_omitted(tmp_path):
    (tmp_path/"test.bib").write_text('@article{one,\n pages = {361},\n}\n')
    row = audit.audit_entry(entry(pages="361"), {"records": [record(pages="361")], "attempts": []})
    _, _, _, files = audit.proposed_patch(tmp_path, [row])
    assert "eid" not in files["test.bib"]["after"]
    assert "pages" not in files["test.bib"]["after"]


def test_retry_after_rate_limit_and_recovery_recorded(tmp_path):
    blocked = Mock(status_code=429,content=b'limited',url="https://example.test",headers={"Retry-After":"1"})
    success = Mock(status_code=200,content=b'{}',url="https://example.test",headers={})
    with patch("bib_audit_sources.requests.get",side_effect=[blocked,success]), patch("bib_audit_sources.time.sleep") as sleep:
        result = EvidenceClient(tmp_path,delay=0,retries=1).fetch("https://example.test","test")
    assert [a["http_status"] for a in result["attempts"]] == [429,200]
    assert any(call.args == (1.0,) for call in sleep.call_args_list)


def test_malformed_http_200_is_not_bibliographic_verification(tmp_path):
    from bib_audit_sources import lookup_crossref
    response = Mock(status_code=200,content=b'<html>captcha</html>',url="https://api.crossref.org",headers={})
    with patch("bib_audit_sources.requests.get",return_value=response):
        records,evidence = lookup_crossref(EvidenceClient(tmp_path,delay=0,retries=0),doi="10.1234/test")
    assert not records
    result = audit.audit_entry(entry(),{"records":records,"attempts":evidence})
    assert not any(n["status"]=="VERIFIED" for n in result["fields"].values())


def test_curated_assertion_without_external_excerpt_is_rejected(tmp_path):
    client = EvidenceClient(tmp_path,offline=True)
    body=b'<html>Different title</html>'
    digest=hashlib.sha256(body).hexdigest()
    (tmp_path/(digest+'.body')).write_bytes(body)
    ev={"id":"test","url":"https://official.test","status":"RETRIEVED","body_file":digest+'.body',"sha256":digest,"retrieved_at":"now","source":"official"}
    claim={"url":"https://official.test","source":"official","lineage":"test","identity_confirmed":True,
           "fields":{"title":"A real study"},"excerpts":["A real study"]}
    with patch.object(client,"fetch",return_value=ev),patch("bib_audit.lookup_crossref",return_value=([],[])),patch("bib_audit.lookup_datacite",return_value=([],[])),patch("bib_audit.lookup_openalex",return_value=([],[])):
        result=audit.collect(entry(),client,{"one":[claim]})
    assert not result["records"]
    assert any(a.get("error")=="curated_excerpt_absent" for a in result["attempts"])


def test_publication_date_with_resource_caveat_cannot_be_applied_automatically(tmp_path):
    before = '@article{one,\n year = {2020},\n}\n'
    (tmp_path / 'test.bib').write_text(before)
    client = EvidenceClient(tmp_path / 'evidence', offline=True)
    body = b'<h1>A real study</h1> Published 2021'
    digest = hashlib.sha256(body).hexdigest()
    (client.directory / (digest + '.body')).write_bytes(body)
    ev = {"id": "test", "url": "https://official.test", "status": "RETRIEVED",
          "body_file": digest + '.body', "sha256": digest,
          "retrieved_at": "2026-10-22T00:00:00+00:00", "source": "official"}
    claim = {"url": "https://official.test", "source": "official", "lineage": "test",
             "identity_confirmed": True, "fields": {"title": "A real study", "year": "2021"},
             "excerpts": ["A real study", "Published 2021"], "review_only_fields": ["year"]}
    with patch.object(client, "fetch", return_value=ev), \
         patch("bib_audit.lookup_crossref", return_value=([], [])), \
         patch("bib_audit.lookup_datacite", return_value=([], [])), \
         patch("bib_audit.lookup_openalex", return_value=([], [])):
        collected = audit.collect(entry(), client, {"one": [claim]})
    row = audit.audit_entry(entry(), collected)
    assert row['fields']['year']['status'] == 'MISMATCH'
    diff, safe, review, files = audit.proposed_patch(tmp_path, [row])
    assert not safe and not diff and not files
    assert any(c['field'] == 'year' and c['new'] == '2021' for c in review)
    assert (tmp_path / 'test.bib').read_text() == before
