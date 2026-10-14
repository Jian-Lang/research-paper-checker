# hallu-cite-checker workflow

## 1. Establish the inventory

For a complete new-PDF execution use `check INPUT [--out NEW_RUN]` at the installed entry. It writes a provisional report, attempts live lookup for each candidate and checkpoints progress. The current candidate parser requires continuously numbered author-year bibliography lines; unsupported layouts and incomplete sections remain blockers. Inspect `extraction-review.json`, then use `preview RUN --page N` to reconcile original bibliography pages. Do not stop at `pdf` and call it an audit.

PDF Unicode recovery preserves raw strings as ASCII-escaped JSON and reports each unresolved code unit's original offset and context. Correct surrogate pairs are decoded; lone units are explicit markers. Bibliography-page defects block verification. Line-break hyphens may be resolved automatically against actual original rows and one trusted record: no arbitrary hyphen edits or fuzzy title changes. Unresolved variants remain UNVERIFIED. Source prose or a search result without real structured citation metadata is never imported as an arXiv citation record.

`check` includes evidence-backed formatting resolution and bounded official fallbacks. `refine RUN` applies that step to an existing run, reusing saved evidence and attempting new official captures. It retains original entry boundaries and text, checks hashes, and logs every formatting resolution. Valid prior coverage can carry forward only for unchanged entry provenance; ordinary manifest edits still invalidate coverage. Disclose that refinement is not fresh retrieval of every source. Fallbacks include CVF, the ICML 2023 proceedings index, accepted ICLR API V2 notes, and IEEE structured metadata when accessible. Official API ownership: https://docs.openreview.net/reference/api-v2/openapi-definition. Publisher HTML has a 50 MB bound; metadata APIs retain 10 MB. Empty responses are source failures.

For installed use, read `scripts/installation.json` and replace each `hallu-cite-checker` below with exact direct argv `PYTHON -I ENTRY`. No shell wrapper or separate elevated commands. All RUN / --out paths must be below the configured output root.

Use `capture RUN --kind official --url URL --name source.html` to save a registered-host response; `write-json RUN --name manifest.json --payload-json JSON` to save reviewed extraction; `open-report RUN` to open the final HTML. These have no interactive approval flow. Infrastructure blocking this entry is a setup error, not a citation verdict.

```sh
hallu-cite-checker latex /path/to/overleaf-project --out /path/to/new-run
hallu-cite-checker pdf /path/to/paper.pdf --out /path/to/new-run
```

LaTeX inventories every `.bib` entry, scans `.tex` citation locations, and fingerprints `.tex/.bib/.bbl/.aux`. It deliberately includes unused .bib entries: usage is not permission to skip their audit. Reconcile the chosen project's bibliography lists and all relevant subprojects. Crossref/xdata inheritance, custom macros, hand-written thebibliography, malformed .bib, duplicate keys and dynamic includes need explicit review. If source dependencies fall outside the supplied root, include them in `inputs`. Never execute arbitrary TeX merely to discover references; prefer supplied compiled PDF/.bbl. Do not remove an extraction issue without recording its resolution and recovered entries.

PDF writes plain and layout text per page. **It does not automatically populate parsed references.** Inspect bibliography pages visually and use both text views to populate `manifest.json.references`; OCR if required. Confirm the first and last entry, number continuity, columns and every appendix/supplement bibliography; author-year lists need explicit counting. A scanned or damaged page remains a blocker until reviewed, not an empty bibliography. Preserve every displayed field without inventing missing data.

A PDF reference example:

```json
{
  "id": "12",
  "fields": {"title": "Example title", "authors": ["A. Smith", "B. Jones"], "year": "2024", "venue": "ICLR"},
  "raw": "[12] A. Smith and B. Jones. Example title. ICLR, 2024.",
  "locations": [{"file": "paper.pdf", "page": 7, "label": "12"}],
  "issues": [],
  "authors_truncated": false
}
```

Use canonical fields `title, authors, year, venue, pages, volume, issue, doi, arxiv_id, url, publisher, address, series, isbn, issn, month, editor, edition, chapter, language`. Unsupported bibliographic fields block automatic verification; handle them explicitly rather than silently dropping them. BibTeX `ID/ENTRYTYPE/abstract/keywords/file/annotation/annote` are housekeeping. For an explicit `et al.` store the displayed author prefix and mark `authors_truncated`; missing authors in an untruncated list are errors. Do not silently strip a venue, year, workshop label or identifier to obtain a match.

Only after source reconciliation:

```sh
hallu-cite-checker confirm-coverage RUN --reviewer Codex --note 'Reviewed pages 7–10 and appendix; 42 entries, labels 1–42, all metadata transcribed.'
```

This stamps count and reference hash. It is an accountable review attestation, not automatic proof of extraction correctness. Edits after confirmation invalidate it. Never confirm solely because a parser finished.

## 2. Find actual trusted records

For each reference, use DOI/arXiv ID first, then exact title plus authors. Search engines discover candidates; open and inspect the underlying source. Query all entries, never just suspicious titles. Prefer a raw Google Scholar **Cite → BibTeX** export when accessible, or an official export/page/PDF. Scholar snippet or merged “all versions” title alone cannot establish metadata. An OpenReview submission is not acceptance: inspect decision/venue or use an accepted-record citation. Workshop/main-track, Findings/main conference and journal/preprint distinctions must be preserved.

Google Scholar is a user-approved trusted source: a coherent export matching the input's supplied shared fields, core fields, conference claim and identifiers is sufficient. Other official-source disagreements must be reported as nonblocking notes under this policy; do not let them automatically veto a fully matching Scholar export. Conflicting Scholar exports or an incomplete/nonmatching export do not grant this exception. Use `primary` for the chosen version and `linked_version` for reviewed related identifiers. Use `alternative_version` for a genuine alternative record matching the submitted title and ordered authors, with reviewer and relation. This role can downgrade a version-dependent conflict to UNVERIFIED; it cannot validate a conference, combine metadata across versions, or establish an identifier. Title resemblance alone is insufficient.

Automatic direct lookups:

```sh
hallu-cite-checker fetch RUN REF --kind crossref --id 10.xxxx/yyyy
hallu-cite-checker fetch RUN REF --kind arxiv --id 2401.01234
```

No automatic Scholar scraping/CAPTCHA bypass. If blocked, use official sources; save failed attempts, never declare the paper fake just because Scholar is unavailable.

Import an actual saved export:

```sh
hallu-cite-checker add-evidence RUN REF /tmp/source.bib --kind google_scholar --url 'https://scholar.google.com/scholar.bib?...' --format bibtex --version-id 'conference:iclr:2024:example'
```

For source pages without structured exports create a *reviewed extraction*, not a guessed bibliography. Save the response/screenshot separately:

```json
{
  "fields": {"title": "Example title", "authors": ["Alice Smith", "Bob Jones"], "year": "2024", "venue": "ICLR"},
  "reviewer": "Codex",
  "field_provenance": {"title": "source heading", "authors": "author block", "year": "official venue line", "venue": "official accepted conference record"}
}
```

```sh
hallu-cite-checker add-evidence RUN REF extracted.json --kind official --url 'https://openreview.net/forum?id=...' --format reviewed_metadata --supporting-artifact saved-source.html --version-id 'conference:iclr:2024:example'
```

Retain source wording, then let the comparator normalize formatting. If the venue contains a year or parenthetical alias not supported by the deterministic table, verify the equivalence before adding a maintained alias/normalizer; do not change paper fields. Never synthesize an export by combining preprint year, conference venue and journal pages.

For a linked arXiv version of a conference citation:

```sh
hallu-cite-checker fetch RUN REF --kind arxiv --id 2401.01234 --role linked_version --reviewer Codex --relation 'Official conference page links this arXiv ID; saved relation evidence at ...'
```

The evidence artifact must identify that preprint; preserve the evidence supporting the cross-version relationship. The v0.1 engine also requires matching title and authors for linked versions. A genuine changed-title version remains UNVERIFIED until a reviewed relationship adapter is implemented; never waive this check by changing the submitted title. All claimed identifiers need matching evidence. An incorrect DOI cannot disappear under the missing-optional-field rule.

The maintained source-host registry is in `hallu_cite_checker/evidence.py`. Add an official host only after inspecting and establishing its ownership; list that change in the report. Do not treat arbitrary mirrors or search-result pages as official. Source capture is trusted operator/agent work: a source URL and file hash alone cannot cryptographically prove web provenance.

## 3. Compare and gate

```sh
hallu-cite-checker audit RUN
```

Exit codes: 0 PASS; 1 FAIL; 2 execution failure. Reports: `report.json`, `report.md`, `report.html`.

- VERIFIED: verified identity/core fields and any claimed identifiers, no source conflict or unresolved extraction problem. Missing optional source fields are listed, not inferred.
- REJECTED: observed input/source conflict without supporting alternative-version metadata or a fully matching Scholar export. Check legitimate alternative versions before declaring an author-order conflict a definite error. Preserve differences and source links.
- UNVERIFIED: missing evidence, malformed source, unsupported fields, identity/version ambiguity, invalid integrity, incomplete core data. Blocks PASS.
- Project PASS requires a nonempty, reviewed complete inventory, unchanged source files, valid evidence artifacts and all VERIFIED references. An unverified empty input never passes.

Normalization is conservative: LaTeX formatting/case/accents, dash formatting in page ranges, DOI prefixes, approved venue aliases and author initials. Preserve full ordered author lists unless explicitly truncated in the original citation. Unknown alias, name-particle or punctuation ambiguity should be UNVERIFIED until the equivalence is reviewed, not silently fuzzy-matched.

Final response: verdict and totals, specific conflicting citations with page/key/source, unresolved records and optional unchecked fields. A single blind sample or successful regression suite does not establish universal zero-error performance. State the actual validation coverage. Do not repair the source unless asked.
