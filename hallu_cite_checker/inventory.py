from __future__ import annotations
import re
import json
from pathlib import Path
import bibtexparser
from bibtexparser.bparser import BibTexParser
from pypdf import PdfReader
from .io import save, sha256, now
from .normalize import canonical_fields
from .pdf_unicode import pdf_text


def strip_comments(s):
    return re.sub(r"(?<!\\)%[^\n]*", "", s)


def parse_bib(text, source):
    text = text.replace("\u00a0", " ")
    parser = BibTexParser(common_strings=True, ignore_nonstandard_types=False)
    database = parser.parse(text, partial=False)
    # Bibtexparser treats unparsed garbage as comments; prevent silent skipped entries.
    starts = len(re.findall(r"(?m)^\s*@(?!(?:comment|string|preamble)\b)[a-zA-Z]+\s*[({]", text, re.I))
    if starts != len(database.entries):
        raise ValueError(f"BibTeX count mismatch: {starts} starts vs {len(database.entries)} entries")
    if any("@" in comment for comment in database.comments):
        raise ValueError("unparsed BibTeX content requires review")
    refs = []
    for i, entry in enumerate(database.entries):
        fields, issues = canonical_fields(entry)
        match = re.search(r"@\w+\s*[({]\s*" + re.escape(entry["ID"]) + r"\s*,", text, re.I)
        line = text[:match.start()].count("\n") + 1 if match else None
        refs.append({"id": entry["ID"], "fields": fields, "raw": entry,
                     "locations": [{"file": source, "line": line}], "issues": issues,
                     "authors_truncated": False})
    return refs


def inventory_latex(path, output):
    root = Path(path).resolve()
    output = Path(output).resolve()
    if not root.is_dir():
        raise ValueError("LaTeX input must be a directory")
    paths = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in {".tex", ".bib", ".bbl", ".aux"}
                   and output not in p.parents and not any(x.startswith(".") for x in p.relative_to(root).parts))
    inputs, refs, issues, citations = [], [], [], []
    for p in paths:
        rel = str(p.relative_to(root))
        inputs.append({"path": str(p), "sha256": sha256(p)})
        content = p.read_text(encoding="utf-8")
        if p.suffix == ".bib":
            try:
                refs.extend(parse_bib(content, rel))
            except Exception as exc:
                issues.append({"code": "bib_parse_failure", "location": rel, "detail": str(exc)})
        if p.suffix == ".tex":
            text = strip_comments(content)
            for m in re.finditer(r"\\(?:[A-Za-z]*cite[A-Za-z]*|nocite)\*?\s*(?:\[[^\]]*\]\s*)*\{([^{}]+)\}", text):
                for key in m[1].split(","):
                    if key.strip() != "*":
                        citations.append({"key": key.strip(), "file": rel, "line": text[:m.start()].count("\n") + 1})
    ids = [r["id"] for r in refs]
    if len(set(ids)) != len(ids):
        issues.append({"code": "duplicate_citation_keys", "detail": sorted({k for k in ids if ids.count(k) > 1})})
    for c in citations:
        if c["key"] not in ids:
            issues.append({"code": "unresolved_citation", "detail": c})
    manifest = {"schema_version": 1, "mode": "latex", "created_at": now(), "inputs": inputs,
                "references": refs, "citation_locations": citations, "issues": issues,
                "coverage": {"reviewed": False, "reviewer": "", "reference_count": len(refs),
                             "reference_fingerprint": "", "note": "Review all .bib/.bbl and bibliography lists, including appendices. Regex citation locations are advisory, not a TeX execution proof."}}
    if not inputs or not refs:
        manifest["issues"].append({"code": "empty_inventory", "detail": "No complete bibliography found"})
    save(output / "manifest.json", manifest)
    save(output / "evidence.json", {"schema_version": 1, "records": [], "attempts": []})
    return manifest


def inventory_pdf(path, output):
    path, output = Path(path).resolve(), Path(output).resolve()
    reader = PdfReader(path)
    output.mkdir(parents=True, exist_ok=True)
    pages, issues = [], []
    for n, page in enumerate(reader.pages, 1):
        try:
            plain = page.extract_text() or ""
        except Exception as exc:
            plain = ""
            issues.append({"code": "page_plain_extraction_failure", "page": n, "detail": str(exc)})
        try:
            layout = page.extract_text(extraction_mode="layout") or ""
        except Exception as exc:
            layout = ""
            issues.append({"code": "page_layout_extraction_failure", "page": n, "detail": str(exc)})
        raw_plain, raw_layout = plain, layout
        plain, plain_events = pdf_text(raw_plain)
        layout, layout_events = pdf_text(raw_layout)
        if plain_events or layout_events:
            (output / f"page-{n:03d}-raw-extraction.json").write_text(
                json.dumps({'plain':raw_plain, 'layout':raw_layout,
                            'plain_events':plain_events,'layout_events':layout_events}, ensure_ascii=True, indent=2) + "\n",
                encoding="utf-8")
            for mode, events in (('plain',plain_events),('layout',layout_events)):
                unresolved = [e for e in events if e['action']=='unresolved_surrogate']
                if unresolved:
                    issues.append({'code':'page_unicode_unresolved','page':n,'mode':mode,
                                   'count':len(unresolved),'detail':'Unknown characters preserved as visible markers; raw extraction and original offsets saved.'})
        (output / f"page-{n:03d}.txt").write_text(plain, encoding="utf-8")
        (output / f"page-{n:03d}-layout.txt").write_text(layout, encoding="utf-8")
        pages.append({"page": n, "characters": len(plain)})
        if len(plain.strip()) < 20:
            issues.append({"code": "page_text_missing", "page": n, "detail": "Visually review/OCR this page; do not assume there are no references."})
    manifest = {"schema_version": 1, "mode": "pdf", "created_at": now(),
                "inputs": [{"path": str(path), "sha256": sha256(path)}], "pages": pages,
                "references": [], "issues": issues,
                "coverage": {"reviewed": False, "reviewer": "", "reference_count": 0,
                             "reference_fingerprint": "", "note": "Populate every bibliography entry with page/label/raw text; visually reconcile numbering and appendices. Extraction alone never establishes coverage."}}
    save(output / "manifest.json", manifest)
    save(output / "evidence.json", {"schema_version": 1, "records": [], "attempts": []})
    return manifest
