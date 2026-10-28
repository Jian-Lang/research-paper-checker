---
name: hallu-cite-checker
description: Audit citation metadata in research paper PDFs or LaTeX/Overleaf projects with hallu-cite-checker. Use for fabricated references, hallucinated citations, BibTeX correctness, bibliography checks, and 幻觉引用检查. Does not assess whether citations support claims.
---

# Hallu Cite Checker

This checker audits citation metadata. Read [the citation workflow](references/hallu-cite-checker.md) before auditing. It is selected by the parent [Research Paper Checker](../../SKILL.md). Do not expand citation audits into paper reading, claim-support assessment or source corrections.

## Non-negotiable rules

- Enumerate every bibliography entry, including appendix/supplement lists. Never sample references or stop after the first error. PDF extraction and regex scanning are candidate inventories, not completeness guarantees.
- Google Scholar citation exports are trusted under the user's chosen policy, alongside official proceedings, publishers, Crossref and arXiv. A general search snippet, user-provided BibTeX or an LLM recollection is not independent evidence.
- Match one coherent version. arXiv and published versions are both legitimate, with their own title/year/venue. A conference claim needs a conference-version record, from Google Scholar or an official source. arXiv existence alone cannot validate acceptance.
- Compare every bibliographic field present in both input and the selected version's evidence. Under the user's policy, a coherent Google Scholar citation export matching all supplied shared fields, core metadata and claimed identifiers is sufficient for PASS; retain other official-source disagreements as nonblocking notes. Conflicting Scholar exports or an incomplete/nonmatching Scholar record do not grant this exception. Missing optional fields such as pages are permitted but disclosed. Missing title/authors/year, claimed venue or identifier evidence blocks verification.
- Before calling an author-order conflict a confirmed error, check legitimate versions. An official alternative version matching the submitted title and ordered authors makes the conflict UNVERIFIED, not REJECTED; it does not by itself validate the submitted conference metadata. Never claim a Scholar export was checked if only the user or a search snippet described it.
- No results, CAPTCHA, HTTP failures or inaccessible websites mean **UNVERIFIED**, not proof of nonexistence. Both UNVERIFIED and REJECTED fail the gate. Never promise universal zero error or equate a conditional PASS with mathematical certainty.
- Missing paper identity requires active investigation before final review: search the full title, method/acronym, claimed authors and venue/year independently. Evidence of metadata conflation must be highlighted as suspected fabrication, separate from ordinary access failures. Never silently substitute a related real paper as the citation's primary evidence. Use the evidence-bound investigation receipt in [final-review.md](references/final-review.md).
- Save actual source artifacts, URLs, retrieval timestamps, hashes and per-field comparisons. Never create evidence from memory or copy the input into an alleged source record. The host model handles extraction, discovery and final false-positive review; the deterministic gate validates evidence and permitted decisions.
- Before final export, follow [final-review.md](references/final-review.md): run `review RUN`, actively recheck every REJECTED/UNVERIFIED entry against actual sources, save evidence-backed decisions in `model-review.json`, then run `finalize RUN`. Missing, partial or stale review cannot finalize. Model-reviewed venue equivalences apply to one reference/source pair; substantive differences remain comparison targets. Never present preliminary automatic reports as final.
- Leave the submitted paper unchanged. Write a fresh run directory and report JSON, Markdown and HTML; give totals, coverage, source conflicts and unchecked fields.

## Tool location

Install once using the parent project's [installer](../../scripts/install_skill.py). Paths in this guide are relative to `checkers/hallu-cite-checker/` unless stated otherwise. Read this checker's installed `scripts/installation.json` for `python`, `entry`, `config`, and `output_root`. Invoke exact direct argv `PYTHON -I ENTRY ACTION ...`: no shell wrapper, environment assignment, `python -c`, or other interpreter. Every action, including capture, reviewed JSON writes and opening HTML, uses this entry. The installer saves a narrowly scoped Codex allow rule. Restart Codex after installation to load it; managed restrictions can override it. Do not request incremental permissions during an audit; return an execution/configuration error if the entry cannot run. Do not change global approval policy.

Run paths must be below the configured output root; input files may be elsewhere. Install dependencies during setup. Write reviewed manifests/annotations with `write-json`, save registered-host raw responses with `capture`, and open the final HTML with `open-report`. Inaccessible sources remain UNVERIFIED; do not escalate separate curl, Python snippets, source edits or browser commands during a run.

`replay PDF --bundle PRIOR_RUN` re-extracts a byte-identical PDF, checks every raw entry on its stated page, and recomputes decisions from saved evidence without old verdicts. It reuses prior visual extraction review and is not fresh full-network verification. State this distinction prominently.

Use a separate run for each changed input. The helper takes the same arguments as `hallu-cite-checker`; see the referenced workflow. Complete extraction review, evidence discovery and the gate before returning the result. If sources are blocked, continue with other trusted sources and report all remaining unresolved entries.

For a new PDF, start with `check INPUT`, which extracts candidates, queries live arXiv / Crossref records, resolves supported line-break variants, attempts official-source fallbacks, and writes reports. Its current automatic parser supports continuously numbered author-year bibliography lines. Other layouts remain blocked; do not report an unsupported extraction as an empty, correct bibliography. The `pdf` action alone only extracts text and is not a completed citation audit.

For an existing run, `refine RUN` reuses hash-validated saved sources and tries official fallbacks for unresolved records. Disclose evidence reuse. A line-break flag alone is not a reason to leave a reference unresolved when one coherent source uniquely supports every affected field. Automatic resolution may only keep/remove hyphens at actual recorded line breaks, preserves original text, and records source hashes and decisions. All other metadata differences remain comparison targets. Do not drop author-conflict candidates merely because the full byline does not already match. Accepted ICLR metadata requires the exact accepted main-conference venue ID; submitted/withdrawn/rejected notes cannot prove acceptance.

Malformed PDF characters are preserved in ASCII-escaped `page-NNN-raw-extraction.json`, with original offsets and context. Valid surrogate pairs are decoded losslessly; unresolved units appear as visible markers. Inspect bibliography-page anomalies before confirming coverage. A body-page anomaly may be excluded from citation blockers only after establishing that the bibliography scope is unaffected. Do not silently delete unknown characters or accept references containing them.

Use `preview RUN --page N` for original-page images during the skill's extraction review. Check every candidate and all supplied fields against the original bibliography, including line-break hyphens, then record any supported extraction resolution with `write-json` and confirm coverage. Automatic candidate/source matching does not replace that review. Extraction ambiguity downgrades source conflicts to UNVERIFIED.

## Report location

The installer defaults to the repository’s `REPORTS/` directory. Every audit gets its own named subdirectory with `report.html`, `report.md`, `report.json` and evidence. Read `scripts/installation.json` for the actual configured location; honor an explicitly configured output root. Never write reports into runtime code or reference documentation.
