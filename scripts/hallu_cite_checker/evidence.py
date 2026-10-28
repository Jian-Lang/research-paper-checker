from __future__ import annotations
import json
import re
import shutil
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from .io import load, save, sha256, now
from .inventory import parse_bib
from .normalize import doi, arxiv

HOSTS = {
    "google_scholar": {"scholar.google.com", "scholar.google.com.hk", "scholar.google.co.uk", "scholar.google.de", "scholar.google.fr", "scholar.google.co.jp"},
    "arxiv": {"arxiv.org", "export.arxiv.org"},
    "crossref": {"api.crossref.org", "search.crossref.org"},
    "datacite": {"api.datacite.org"},
    "official": {"openaccess.thecvf.com", "proceedings.neurips.cc", "papers.nips.cc", "proceedings.mlr.press", "openreview.net", "aclanthology.org", "ojs.aaai.org", "www.ijcai.org", "ijcai.org", "link.springer.com", "ieeexplore.ieee.org", "dl.acm.org", "www.sciencedirect.com", "www.nature.com", "www.science.org", "jmlr.org", "www.jmlr.org", "papers.miccai.org", "zenodo.org", "www.cancerimagingarchive.net", "www.medrxiv.org", "acsjournals.onlinelibrary.wiley.com", "pubs.rsna.org", "jamanetwork.com"},
}
# Public service documented by medRxiv at https://api.medrxiv.org/.
HOSTS["official"].add("api.medrxiv.org")
# Official API V2: https://docs.openreview.net/reference/api-v2/openapi-definition
HOSTS["official"].add("api2.openreview.net")
# Official ICLR proceedings and publisher-hosted citation exports.
HOSTS["official"].add("proceedings.iclr.cc")


def trusted(kind, url):
    parts = urllib.parse.urlsplit(url)
    return parts.scheme == "https" and parts.hostname in HOSTS.get(kind, set()) and parts.username is None


def parse_artifact(path, fmt):
    if fmt in {'publisher_html', 'openreview'}:
        from .official_formats import parse_publisher_html, parse_openreview
        return (parse_publisher_html if fmt == 'publisher_html' else parse_openreview)(path)
    if fmt == "citation_html":
        from .citation_html import parse_citation_html
        return parse_citation_html(path)
    raw = Path(path).read_text(encoding="utf-8")
    if fmt == "bibtex":
        entries = parse_bib(raw, str(path))
        if len(entries) != 1 or entries[0]["issues"]:
            raise ValueError("Evidence BibTeX must contain exactly one clean record")
        return entries[0]["fields"]
    if fmt == "crossref":
        msg = json.loads(raw)["message"]
        fields = {}
        if msg.get("title"):
            fields["title"] = msg["title"][0]
        containers = msg.get("container-title", [])
        if containers:
            fields["venue"] = containers[-1]
            if len(containers) > 1:
                fields["series"] = containers[0]
        if msg.get("author"):
            fields["authors"] = [((a.get("family", "") + ", " + a.get("given", "")).strip(", ")) or a.get("name", "") for a in msg["author"]]
        for key in ("published-print", "published", "published-online", "issued"):
            date = msg.get(key, {}).get("date-parts", [])
            if date and date[0]:
                fields["year"] = str(date[0][0])
                break
        for dest, source in {"doi": "DOI", "pages": "page", "volume": "volume", "issue": "issue", "publisher": "publisher", "url": "URL"}.items():
            if msg.get(source):
                fields[dest] = msg[source]
        if not fields.get("pages") and msg.get("article-number"):
            fields["pages"] = msg["article-number"]
        return fields
    if fmt == "datacite":
        msg = json.loads(raw)["data"]["attributes"]
        publisher = msg["publisher"]
        publisher = publisher.get("name", "") if isinstance(publisher, dict) else publisher
        return {"title": msg["titles"][0]["title"],
                "authors": [(c.get("familyName", "") + ", " + c.get("givenName", "")).strip(", ") if c.get("familyName") else c["name"] for c in msg["creators"]],
                "year": str(msg["publicationYear"]), "venue": publisher,
                "doi": msg["doi"], "url": msg["url"]}
    if fmt == "arxiv":
        doc = ET.fromstring(raw)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        entries = doc.findall("a:entry", ns)
        if len(entries) != 1:
            raise ValueError("arXiv response must contain exactly one record")
        entry = entries[0]
        ident = entry.findtext("a:id", "", ns)
        if "/abs/" not in ident:
            raise ValueError("arXiv response is an error or lacks an identifier")
        return {"title": " ".join(entry.findtext("a:title", "", ns).split()),
                "authors": [e.findtext("a:name", "", ns) for e in entry.findall("a:author", ns)],
                "year": entry.findtext("a:published", "", ns)[:4], "venue": "arXiv",
                "arxiv_id": arxiv(ident), "url": ident.replace("http://", "https://")}
    if fmt == "reviewed_metadata":
        data = json.loads(raw)
        if not isinstance(data.get("fields"), dict) or not data.get("reviewer") or not data.get("field_provenance"):
            raise ValueError("Reviewed metadata needs fields, reviewer and per-field provenance")
        if set(data["fields"]) - set(data["field_provenance"]):
            raise ValueError("Every reviewed field must have source provenance")
        return data["fields"]
    raise ValueError("Unsupported evidence format")


def add_evidence(run, ref_id, artifact, kind, url, fmt, role="primary", version_id="", relation="", reviewer="", supporting_artifact=None):
    run, artifact = Path(run).resolve(), Path(artifact).resolve()
    data, manifest = load(run / "evidence.json"), load(run / "manifest.json")
    if ref_id not in {r["id"] for r in manifest["references"]}:
        raise ValueError("Unknown reference ID: " + ref_id)
    if not trusted(kind, url):
        raise ValueError("Untrusted URL for source kind; verify the official host before extending the registry")
    if role not in {"primary", "linked_version", "alternative_version"} or not version_id:
        raise ValueError("Evidence needs primary/linked_version role and explicit version identity")
    if role in {"linked_version", "alternative_version"} and (not relation or not reviewer):
        raise ValueError("Linked versions require a reviewed same-work relation")
    if fmt == "reviewed_metadata" and not supporting_artifact:
        raise ValueError("Reviewed metadata requires the saved source response/BibTeX/screenshot")
    fields = parse_artifact(artifact, fmt)
    digest = sha256(artifact)
    dest = run / "evidence" / (digest + (artifact.suffix or ".txt"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest != artifact:
        shutil.copyfile(artifact, dest)
    record = {"ref_id": ref_id, "kind": kind, "source_url": url, "retrieved_at": now(),
              "artifact": str(dest.relative_to(run)), "sha256": digest, "format": fmt,
              "fields": fields, "role": role, "version_id": version_id,
              "relation": relation, "reviewer": reviewer, "authors_truncated": False}
    if supporting_artifact:
        support = Path(supporting_artifact).resolve()
        sd = sha256(support)
        sp = run / "evidence" / (sd + (support.suffix or ".txt"))
        if sp != support:
            shutil.copyfile(support, sp)
        record["supporting_artifact"] = str(sp.relative_to(run))
        record["supporting_sha256"] = sd
    data["records"].append(record)
    save(run / "evidence.json", data)
    return record


def fetch_identifier(run, ref_id, kind, identifier, role="primary", relation="", reviewer=""):
    run = Path(run).resolve()
    if kind == "crossref":
        identifier = doi(identifier)
        if not re.fullmatch(r"10\.\d{4,9}/\S+", identifier):
            raise ValueError("Invalid DOI syntax")
        url = "https://api.crossref.org/works/" + urllib.parse.quote(identifier, safe="")
    elif kind == "arxiv":
        identifier = arxiv(identifier)
        if not re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?", identifier):
            raise ValueError("Invalid arXiv ID syntax")
        url = "https://export.arxiv.org/api/query?id_list=" + urllib.parse.quote(identifier, safe="")
    else:
        raise ValueError("Automatic fetch supports only Crossref DOI and arXiv IDs")
    data = load(run / "evidence.json")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "hallu-cite-checker/0.1 (citation metadata audit)"})
        with urllib.request.urlopen(request, timeout=30) as response:
            if not trusted(kind, response.geturl()):
                raise ValueError("Redirect left the trusted source host")
            raw = response.read(10_000_001)
            if len(raw) > 10_000_000:
                raise ValueError("Metadata response exceeded 10 MB")
        import hashlib
        target = run / "evidence" / ("fetch-" + hashlib.sha256(raw).hexdigest() + (".json" if kind == "crossref" else ".xml"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        return add_evidence(run, ref_id, target, kind, url, kind, role, kind + ":" + identifier, relation, reviewer)
    except Exception as exc:
        data["attempts"].append({"ref_id": ref_id, "source_url": url, "retrieved_at": now(), "error": str(exc)})
        save(run / "evidence.json", data)
        raise


def validate_record(record, run):
    problems = []
    if not trusted(record.get("kind"), record.get("source_url", "")):
        problems.append("untrusted_source")
    try:
        datetime.fromisoformat(record["retrieved_at"])
    except (KeyError, ValueError, TypeError):
        problems.append("missing_retrieval_timestamp")
    if not record.get("version_id") or record.get("role") not in {"primary", "linked_version", "alternative_version"}:
        problems.append("missing_version_or_role")
    try:
        path = (Path(run) / record["artifact"]).resolve()
        if not path.is_relative_to(Path(run).resolve()) or sha256(path) != record["sha256"]:
            problems.append("artifact_integrity_failure")
        elif parse_artifact(path, record["format"]) != record["fields"]:
            problems.append("metadata_artifact_mismatch")
        if record["format"] == "reviewed_metadata" or record.get("supporting_artifact"):
            support = (Path(run) / record["supporting_artifact"]).resolve()
            if not support.is_relative_to(Path(run).resolve()) or sha256(support) != record["supporting_sha256"]:
                problems.append("supporting_artifact_integrity_failure")
    except (KeyError, OSError, ValueError, TypeError) as exc:
        problems.append("invalid_artifact: " + str(exc))
    if record.get("role") in {"linked_version", "alternative_version"} and not (record.get("relation") and record.get("reviewer")):
        problems.append("unproven_version_relation")
    return problems
