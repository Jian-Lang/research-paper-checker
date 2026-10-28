# Final model review

Run this after extraction review and automatic evidence comparison, before delivering final reports. The skill's host model performs the review; no second model API, API key, permission prompt or human approval is needed. `review` only prepares a packet and must never be described as performing model review.

1. Run `review RUN` and inspect every target in `review-packet.json`, including REJECTED and UNVERIFIED entries. Never sample or automatically copy prior verdicts.
2. Inspect each original citation and actual saved sources. Check extraction, names/initials, venue aliases, main/workshop/Findings/track distinctions, accepted versus submitted status, coherent versions, online versus proceedings years, pagination and source disagreements. Fetch more trusted evidence where useful. Model memory or a familiar title is insufficient. When no paper identity is established, also search the method/acronym and claimed authors independently, and inspect the claimed venue/year's official proceedings where available. A method name inside another paper is not a matching publication. Investigate possible metadata conflation instead of stopping at an empty exact-title lookup; keep failed access separate from evidence of a fabricated citation.
3. Import new evidence through the fixed entry. Correct only extraction errors demonstrated by the original input; preserve raw text and record corrections. Never change supplied metadata or delete an unresolved issue merely to obtain a pass. Reconfirm coverage after inventory changes. After source, inventory or annotation updates, run `review RUN` again; it preserves earlier targets, including entries that now pass.
4. Record a concrete reason for each target and an outcome: `resolved` (fully verified after recomputation), `retained` (the error/uncertainty still stands), or `uncertain` (ambiguity; preserve as UNVERIFIED). Describe the field differences and inspected source locations. Cite actual saved evidence and hashes. For blocked sources, record the attempt and limitation; never invent an export.
5. Save `model-review.json` with `write-json`, then run `finalize RUN`. It checks complete review coverage, current input/evidence hashes and the recomputed result before final JSON, Markdown and HTML export. Only then open HTML with `open-report RUN`. Intermediate reports are explicitly preliminary.

The model may resolve venue wording without editing the global alias table. Record a per-reference equivalence between the unchanged input value and one actual primary source value, with the inspected context establishing equivalence. This affects only that venue comparison, never year, authors, pages, volume, DOI or another reference. The runtime refuses known different conferences, conflicting embedded years/editions and explicit workshop/track differences. Never use equivalence to prove conference acceptance from an arXiv record.

For other fields, resolve a false alarm through actual evidence or a documented extraction correction, then recompute. Source conflicts remain unresolved unless the established policy permits a coherent matching Scholar export. Final review is not a target to reduce the unresolved count.

When a publisher metadata endpoint is blocked, inspect the corresponding archived full paper before stopping. A saved publisher reference-format panel, conference copyright block and exact DOI can establish the published version even when the archive's abstract page only says arXiv. Extract only fields actually visible there, preserve the full PDF as supporting evidence, and cross-check its DOI/title/year against the publisher deposit. An arXiv date or conference claim without this version evidence is insufficient. Use reviewed_metadata with per-field locations; never copy the submitted citation into a supposed export.

Classify errors per field. One independently confirmed supplied-field error is enough for REJECTED, even if another field remains unresolved or different sources disagree about that other field. Uncertainty about whether the whole work is fabricated does not erase an established author/year/venue error. Use `uncertain` only for a concrete extraction, format, version or source ambiguity affecting the asserted error; a failed request elsewhere is not such a reason. The report must prominently show unresolved field conflicts as well as confirmed errors, so uncertainty cannot bury a citation needing correction.

To withhold a confirmed field conflict, an `uncertain` decision must include `uncertain_fields` (the affected supplied field names), `uncertainty_kind` (`format`, `extraction`, `version` or `source_conflict`), actual cited source evidence and a concrete reason. Other confirmed field errors remain REJECTED. A generic uncertainty statement cannot downgrade the whole entry. Suspected fabrication also does not erase a separately confirmed field error.

Example receipt; replace every value with inspected run data:

```json
{
  "schema_version": 1,
  "performed_by": "host_model",
  "reviewer": "Codex",
  "packet_fingerprint": "<from review-packet.json>",
  "blockers_reviewed": true,
  "decisions": [{
    "ref_id": "<target id>",
    "outcome": "resolved",
    "reason": "<what was a false alarm, where evidence establishes this, and what remains>",
    "evidence": [{"artifact": "evidence/<actual-file>", "sha256": "<actual hash>"}],
    "equivalences": [{
      "field": "venue",
      "input": "<unchanged paper venue>",
      "source": "<unchanged primary record venue>",
      "source_sha256": "<same actual hash>",
      "reason": "<why these denote the same venue and edition>",
      "source_context": "<location in the inspected source establishing equivalence>"
    }]
  }]
}
```

Omit `equivalences` when unnecessary. `retained` and `uncertain` may cite no evidence if no trusted record was retrieved; preserve actual failed attempts in the run. An all-verified run still needs a host-model receipt with an empty decisions list. A receipt is an accountable model attestation, not cryptographic proof of correct reasoning. Invalid or stale reviews cannot clear findings or produce a final report.

## Suspected fabricated identity

Use `outcome: "suspected_fabrication"` for an evidence-supported metadata-conflation finding. It remains unverified at the gate, but HTML and Markdown prominently separate it from routine unresolved entries. Do not leave an investigated conflation hypothesis buried in a generic uncertainty note. This is a model judgment supported by inspected sources, not a deterministic proof of nonexistence.

Include `investigation` with `kind: "metadata_conflation"`, nonempty `title_search`, `author_search`, `venue_search`, and `reason` descriptions; `related_work: {artifact, sha256, method, quote}`; and `catalogue: {artifact, sha256}`. The related work must be an actual saved official primary record (it may belong to another reference), with a distinct title and byline. Quote the method's occurrence in its abstract, not a reference list. Do not import it as the alleged paper's identity. The runtime validates the record, abstract quote and hash. A successful official all-papers catalogue capture must also support the investigation; failed requests and search snippets cannot establish this finding.

The catalogue validator currently supports CVF CVPR/ICCV main-conference `?day=all` pages for the claimed year. It checks the URL, saved response, recognizable entries, truncation and matching/similar title candidates. It records absence only from that captured public catalogue, not a guarantee of exhaustive publication coverage. Other venues or unsupported fabrication patterns remain unverified with an explicit investigation limitation; do not invent a supported finding or broaden this validator by guessing. Ordinary confirmed metadata errors still use REJECTED.
