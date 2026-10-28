from __future__ import annotations
from collections import Counter
from pathlib import Path
from .evidence import validate_record
from .io import load, save, sha256, now, fingerprint
from .normalize import norm, author_equal, arxiv, venue, words, authors, same_name
import re

OPTIONAL = {"pages", "volume", "issue", "publisher", "address", "series", "isbn", "issn", "month", "editor", "edition", "chapter", "language"}
CORE = {"title", "authors", "year", "venue", "doi", "arxiv_id", "url"}


def same(field, a, b, ref, record):
    if field == "authors":
        return author_equal(a, b, ref.get("authors_truncated", False), record.get("authors_truncated", False))
    if field == "arxiv_id":
        a, b = arxiv(a), arxiv(b)
        return a == b or (not re.search(r"v\d+$", a) and a == re.sub(r"v\d+$", "", b))
    if field == 'url':
        from urllib.parse import urlsplit
        left, right = urlsplit(str(a)), urlsplit(str(b))
        if (left.netloc == right.netloc == 'arxiv.org' and left.scheme in {'http', 'https'}
                and right.scheme in {'http', 'https'} and not left.query and not right.query
                and not left.fragment and not right.fragment):
            base = r'/abs/((?:\d{4}\.\d{4,5}|[a-z-]+/\d{7}))'
            lmatch = re.fullmatch(base, left.path)
            rmatch = re.fullmatch(base + r'v[1-9]\d*', right.path)
            if lmatch and rmatch and lmatch[1] == rmatch[1]:
                return True
    return norm(field, a) == norm(field, b)


def compare(ref, record):
    rows = []
    fields, source = ref["fields"], record["fields"]
    for field, value in fields.items():
        if record["role"] == "linked_version" and field not in {"doi", "arxiv_id", "url"}:
            continue
        if field not in CORE | OPTIONAL:
            result = "UNSUPPORTED_FIELD"
        elif field not in source or not source[field]:
            result = "SOURCE_MISSING"
        else:
            result = "MATCH" if same(field, value, source[field], ref, record) else "CONFLICT"
            if field == "pages" and result == "CONFLICT":
                left, right = norm(field, value), norm(field, source[field])
                if "-" not in right and left.startswith(right + "-"):
                    result = "PARTIAL_SOURCE_MATCH"
                elif "-" not in left and right.startswith(left + "-"):
                    result = "MATCH"
            if field == "title" and result == "CONFLICT":
                compact = lambda v: re.sub(r"[\s-]+", "", words(v))
                if compact(value) == compact(source[field]):
                    result = "AMBIGUOUS_FORMAT"
            if field == "venue" and result == "CONFLICT":
                # Short container titles cannot disprove a longer subtitle,
                # nor establish its correctness. Keep the item unresolved.
                left, right = words(value), words(source[field])
                if left.startswith(right + " ") or right.startswith(left + " "):
                    result = "AMBIGUOUS_FORMAT"
            if field == "authors" and result == "CONFLICT":
                names = authors(source[field])
                if any(not re.search(r'[\w]', name) for name in names):
                    result = 'AMBIGUOUS_FORMAT'
                # A duplicated deposited byline is a source defect, not proof
                # that the submitted bibliography invented an author.
                if len(names) >= 6 and any(all(same_name(a, b) for a, b in zip(names[:3], names[i:i+3]))
                                          for i in range(3, len(names)-2)):
                    result = "AMBIGUOUS_FORMAT"
            if field == "venue" and result == "MATCH":
                # Main-conference edition years/ordinals must not disappear in aliases.
                if venue(value) in {"cvpr", "iccv", "iclr", "icml", "aaai", "miccai", "findings of acl", "acl", "kdd", "ccl"}:
                    left_years = re.findall(r"(?:19|20)\d{2}", str(value))
                    right_years = re.findall(r"(?:19|20)\d{2}", str(source[field]))
                    if left_years and any(y != str(ref["fields"].get("year")) for y in left_years):
                        result = "CONFLICT"
                    if right_years and any(y != str(source.get("year")) for y in right_years):
                        result = "CONFLICT"
                    if venue(value) == "iclr":
                        for v, yr in ((value, ref["fields"].get("year")), (source[field], source.get("year"))):
                            for spelling, expected in (("thirteenth", "2025"), ("fourteenth", "2026")):
                                if spelling in words(v) and str(yr) != expected:
                                    result = "CONFLICT"
                    left_ord = re.findall(r"\b(\d+)(?:st|nd|rd|th)\b", words(value))
                    right_ord = re.findall(r"\b(\d+)(?:st|nd|rd|th)\b", words(source[field]))
                    if left_ord and right_ord and left_ord != right_ord:
                        result = "CONFLICT"
                    for v, yr in ((value, fields.get("year")), (source[field], source.get("year"))):
                        ordinals = re.findall(r"\b(\d+)(?:st|nd|rd|th)\b", words(v))
                        if ordinals and str(yr).isdigit():
                            n = int(ordinals[0])
                            expected = 1983 + n if venue(value) == "icml" and n >= 20 else (2012 + n if venue(value) == "iclr" else None)
                            if expected is not None and int(yr) != expected:
                                result = "CONFLICT"
        if field == 'venue' and result in {'CONFLICT', 'AMBIGUOUS_FORMAT'}:
            if any(item['input'] == value and item['source'] == source.get(field)
                   and item['source_sha256'] == record.get('sha256')
                   for item in ref.get('_reviewed_venue_equivalences', [])):
                result = 'MATCH'
        rows.append({"field": field, "input": value, "source": source.get(field), "result": result})
    return rows


def audit_reference(ref, records, run):
    problems = list(ref.get("issues", []))
    valid, evidence_results = [], []
    for record in records:
        errors = validate_record(record, run)
        if not errors and record.get("role") in {"linked_version", "alternative_version"}:
            for identity_field in ("title", "authors"):
                if not record["fields"].get(identity_field) or not ref["fields"].get(identity_field):
                    errors.append("linked_identity_missing:" + identity_field)
                elif not same(identity_field, ref["fields"][identity_field], record["fields"][identity_field], ref, record):
                    errors.append("linked_identity_conflict:" + identity_field)
        rows = compare(ref, record) if not errors else []
        evidence_results.append({"source_url": record.get("source_url"), "kind": record.get("kind"),
                                 "version_id": record.get("version_id"), "role": record.get("role"),
                                 "integrity_errors": errors, "comparisons": rows,
                                 "artifact": record.get("artifact"), "sha256": record.get("sha256")})
        if errors:
            problems.extend(errors)
        else:
            valid.append((record, rows))
    for required in {"title", "authors", "year"}:
        if not ref["fields"].get(required):
            problems.append("missing_input_" + required)
    primaries = [(r, rows) for r, rows in valid if r["role"] == "primary"]
    required_for_scholar = {"title", "authors", "year"} | ({"venue"} if ref["fields"].get("venue") else set()) | ({"doi", "arxiv_id", "url"} & ref["fields"].keys())
    scholar_records = [(r, rows) for r, rows in primaries if r["kind"] == "google_scholar"]
    scholar_matches = [(r, rows) for r, rows in scholar_records
        if required_for_scholar <= {row["field"] for row in rows if row["result"] == "MATCH"}
        and all(row["result"] == "MATCH" or row["field"] in OPTIONAL and row["result"] in {"SOURCE_MISSING", "PARTIAL_SOURCE_MATCH"} for row in rows)]
    scholar_conflicting = any(row["result"] in {"CONFLICT", "AMBIGUOUS_FORMAT", "UNSUPPORTED_FIELD"}
                              for _, rows in scholar_records for row in rows)
    scholar_override = bool(scholar_matches) and not scholar_conflicting
    warnings = []
    if scholar_override:
        selected = scholar_matches[0]
        warnings = [{"code": "nonblocking_source_disagreement", "source_url": r["source_url"], "comparisons": rows}
                    for r, rows in primaries if r["kind"] != "google_scholar" and any(row["result"] != "MATCH" for row in rows)]
        primaries = [selected]
    conflicts, verified_fields, source_missing = [], set(), set()
    for r, rows in primaries:
        conflicts.extend(row for row in rows if row["result"] == "CONFLICT")
        verified_fields.update(row["field"] for row in rows if row["result"] == "MATCH")
        source_missing.update(row["field"] for row in rows if row["result"] in {"SOURCE_MISSING", "PARTIAL_SOURCE_MATCH"})
        problems.extend("ambiguous_format:" + row["field"] for row in rows if row["result"] == "AMBIGUOUS_FORMAT")
        problems.extend("unsupported_field:" + row["field"] for row in rows if row["result"] == "UNSUPPORTED_FIELD")
    coherent = bool(primaries) and all(
        all(left['fields'].get(f) and right['fields'].get(f) and (
            author_equal(left['fields'][f], right['fields'][f]) if f == 'authors' else
            norm(f, left['fields'][f]) == norm(f, right['fields'][f]))
            for f in ('title', 'authors', 'year', 'venue'))
        and all(norm(f, left['fields'][f]) == norm(f, right['fields'][f])
                for f in ('doi', 'arxiv_id') if left['fields'].get(f) and right['fields'].get(f))
        for i, (left, _) in enumerate(primaries) for right, _ in primaries[i+1:])
    if len({r["version_id"] for r, _ in primaries}) > 1 and not coherent:
        problems.append("multiple_primary_versions: choose one coherent citation version")
    if not primaries:
        problems.append("no_trusted_primary_evidence")
    for field in {"doi", "arxiv_id", "url"} & ref["fields"].keys():
        matches = [r for r, rows in valid if r["role"] != "alternative_version" and any(row["field"] == field and row["result"] == "MATCH" for row in rows)]
        if matches:
            verified_fields.add(field)
        else:
            problems.append("unverified_identifier:" + field)
    required = {"title", "authors", "year"} | ({"venue"} if ref["fields"].get("venue") else set())
    problems.extend("unverified_core_field:" + f for f in sorted(required - verified_fields))
    if not ref.get("locations") or not ref.get("raw"):
        problems.append("missing_input_provenance")
    disputed_fields = {row["field"] for row in conflicts} & verified_fields
    problems.extend("trusted_sources_disagree:" + f for f in sorted(disputed_fields))
    alternate_fields = {row["field"] for r, rows in valid if r["role"] == "alternative_version"
                        for row in rows if row["result"] == "MATCH"}
    version_disputes = {row["field"] for row in conflicts} & alternate_fields
    problems.extend("alternative_version_matches:" + f for f in sorted(version_disputes))
    # Deposits may disagree even when neither matches the input. Keep that
    # source uncertainty distinct from a confirmed citation error.
    source_disputes = set()
    for i, (left, left_rows) in enumerate(primaries):
        supplied = {k: v for k, v in left["fields"].items() if k in ref["fields"]}
        for right, right_rows in primaries[i + 1:]:
            agreed = ({row['field'] for row in left_rows if row['result'] == 'MATCH'} &
                      {row['field'] for row in right_rows if row['result'] == 'MATCH'})
            source_disputes.update(row["field"] for row in compare(
                {"fields": supplied}, right) if row["result"] == "CONFLICT"
                and not (row['field'] == 'venue' and 'venue' in agreed)
                and not (row['field'] == 'arxiv_id' and
                         re.sub(r'v\d+$', '', arxiv(row['input'])) ==
                         re.sub(r'v\d+$', '', arxiv(row['source']))))
    problems.extend("trusted_sources_disagree:" + f for f in sorted(source_disputes))
    undisputed_conflicts = [row for row in conflicts if row["field"] not in disputed_fields | version_disputes | source_disputes]
    # Confirm each field against a source that actually supplies that conflict.
    # An unrelated source dispute must not hide a separately established error;
    # conversely, an official source missing a field cannot confirm its deposit.
    confirmed_conflicts = [row for row in undisputed_conflicts if any(
        r['kind'] not in {'crossref', 'datacite'} and any(
            c['field'] == row['field'] and c['result'] == 'CONFLICT' and
            c['source'] == row['source'] for c in rows) for r, rows in primaries)]
    deposit_only = bool(undisputed_conflicts) and not confirmed_conflicts
    if deposit_only:
        problems.append("conflict_requires_official_confirmation")
    status = "REJECTED" if confirmed_conflicts and not ref.get('issues') else ("UNVERIFIED" if problems else "VERIFIED")
    return {"id": ref["id"], "status": status, "fields": ref["fields"], "raw": ref.get("raw", ""), "locations": ref.get("locations", []),
            "problems": sorted(set(problems)), "conflicts": conflicts,
            "confirmed_conflicts": confirmed_conflicts if not ref.get('issues') else [],
            "verified_fields": sorted(verified_fields),
            "unchecked_optional_fields": sorted((source_missing & OPTIONAL) - verified_fields),
            "acceptance_policy": "matching_google_scholar_export" if scholar_override else "official_version_comparison",
            "format_resolutions": ref.get('format_resolutions', []),
            "warnings": warnings,
            "evidence": evidence_results}




def discovery_candidates(ref, evidence, run):
    """Display exact-title discovery evidence without asserting identity."""
    candidates = []
    seen = set()
    for event in evidence.get('attempts',[]):
        if event.get('ref_id') != ref['id'] or not event.get('artifact') or not event.get('sha256'):
            continue
        if not event.get('source_url','').startswith('https://api.crossref.org/works?'):
            continue
        path = (Path(run)/event['artifact']).resolve()
        if not path.is_relative_to(Path(run).resolve()) or not path.is_file() or sha256(path)!=event['sha256']:
            continue
        try:
            items = load(path)['message']['items']
        except (ValueError,KeyError,TypeError):
            continue
        for item in items:
            title = item.get('title',[''])[0]
            if norm('title',title)!=norm('title',ref['fields'].get('title','')) or item.get('DOI') in seen:
                continue
            seen.add(item.get('DOI'))
            fields = {'title':title}
            for key,target in (('page','pages'),('DOI','doi')):
                if item.get(key):
                    fields[target]=item[key]
            if item.get('container-title'):
                fields['venue']=item['container-title'][-1]
            for key in ('published-print','published','published-online','issued'):
                dates=item.get(key,{}).get('date-parts',[])
                if dates and dates[0]:
                    fields['year']=str(dates[0][0])
                    break
            if item.get('author'):
                fields['authors']=[(a.get('family','')+', '+a.get('given','')).strip(', ') for a in item['author']]
            candidates.append({'source_url':event['source_url'],'artifact':event['artifact'],
                'sha256':event['sha256'],'identity_confirmed':False,
                'comparisons':compare(ref,{'fields':fields,'role':'primary'})})
    return candidates


def audit(run, write_reports=True, model_review=True):
    run = Path(run).resolve()
    manifest, evidence = load(run / "manifest.json"), load(run / "evidence.json")
    blockers = list(manifest.get("issues", []))
    refs = manifest.get("references", [])
    ids = [r["id"] for r in refs]
    if len(set(ids)) != len(ids):
        blockers.append({"code": "duplicate_reference_ids"})
    if not refs:
        blockers.append({"code": "empty_inventory"})
    coverage = manifest.get("coverage", {})
    if not (coverage.get("reviewed") is True and coverage.get("reviewer") and coverage.get("note")
            and coverage.get("reference_count") == len(refs)
            and coverage.get("reference_fingerprint") == fingerprint(refs)):
        blockers.append({"code": "coverage_not_confirmed", "detail": "Complete source/reference reconciliation is required"})
    if not manifest.get("inputs"):
        blockers.append({"code": "missing_input_fingerprint"})
    for source in manifest.get("inputs", []):
        try:
            if sha256(Path(source["path"])) != source["sha256"]:
                blockers.append({"code": "input_changed", "path": source["path"]})
        except (OSError, KeyError):
            blockers.append({"code": "input_unavailable", "path": source.get("path")})
    for record in evidence.get("records", []):
        if record.get("ref_id") not in ids:
            blockers.append({"code": "orphan_evidence", "ref_id": record.get("ref_id")})
    review_context, review_errors = None, []
    if model_review:
        from .final_review import load_review
        try:
            review_context = load_review(run)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            review_errors.append(str(exc))
    results = []
    decisions = {d['ref_id']:d for d in review_context['receipt']['decisions']} if review_context else {}
    for ref in refs:
        records = [e for e in evidence.get("records", []) if e.get("ref_id") == ref["id"]]
        clean_ref = {k:v for k,v in ref.items() if not k.startswith('_reviewed_')}
        baseline = audit_reference(clean_ref, records, run)
        reviewed = dict(clean_ref)
        reviewed['_reviewed_venue_equivalences'] = review_context['equivalences'].get(ref['id'], []) if review_context else []
        result = audit_reference(reviewed, records, run) if reviewed['_reviewed_venue_equivalences'] else baseline
        decision = decisions.get(ref['id'])
        if review_context and baseline['status'] != 'VERIFIED' and not decision:
            review_errors.append('New flagged reference lacks review: ' + ref['id'])
        if decision:
            if decision['outcome'] == 'resolved' and result['status'] != 'VERIFIED':
                review_errors.append('Model resolution still lacks complete matching evidence: ' + ref['id'])
            if decision['outcome'] == 'retained' and result['status'] == 'VERIFIED':
                review_errors.append('Resolved reference must be recorded as resolved: ' + ref['id'])
            if decision['outcome'] == 'suspected_fabrication':
                if result['status'] == 'VERIFIED':
                    review_errors.append('Verified identity cannot be labelled suspected fabrication: ' + ref['id'])
                result['identity_finding'] = review_context['identity_findings'][ref['id']]
            if decision['outcome'] == 'uncertain':
                confirmed = result.get('confirmed_conflicts', [])
                uncertain_fields = decision.get('uncertain_fields', [])
                if confirmed and not uncertain_fields:
                    review_errors.append('Downgrading a confirmed error requires explicit uncertain_fields: ' + ref['id'])
                result['withheld_conflicts'] = [c for c in confirmed if c['field'] in uncertain_fields]
                result['confirmed_conflicts'] = [c for c in confirmed if c['field'] not in uncertain_fields]
                result['status'] = 'REJECTED' if result['confirmed_conflicts'] else 'UNVERIFIED'
                result['problems'] = sorted(set(result['problems'] + ['model_review_uncertainty']))
            result['model_review'] = {'automated_status': baseline['status'], **decision}
        results.append(result)
    for ref, result in zip(refs, results):
        if not result['evidence']:
            result['discovery_candidates'] = discovery_candidates(ref, evidence, run)
    if review_errors and review_context:
        # Invalid review cannot clear even one automated finding.
        results = [audit_reference({k:v for k,v in ref.items() if not k.startswith('_reviewed_')},
            [e for e in evidence.get("records", []) if e.get("ref_id") == ref["id"]], run) for ref in refs]
    counts = Counter(r["status"] for r in results)
    passed = bool(refs) and not blockers and all(r["status"] == "VERIFIED" for r in results)
    report = {"schema_version": 1, "created_at": now(), "tool": "hallu-cite-checker/0.1.0",
              "verdict": "PASS" if passed else "FAIL", "scope": "citation_metadata_only",
              "coverage": coverage, "input_files": manifest.get("inputs", []), "blockers": blockers,
              "execution": manifest.get('execution', {}),
              "validation_notes": load(run/'annotations.json') if (run/'annotations.json').exists() else {},
              "counts": {s: counts[s] for s in ("VERIFIED", "REJECTED", "UNVERIFIED")},
              "risk_counts": {"suspected_fabrication": sum(bool(r.get('identity_finding')) for r in results)},
              "references": results, "retrieval_attempts": evidence.get("attempts", []),
              "limits": ["PASS is conditional on reviewed extraction, evidence acquisition, source accuracy and missing-field policy; it is not a universal zero-error guarantee.",
                         "Optional fields absent from all trusted records are disclosed, not inferred.",
                         "No search results or inaccessible sources prove nonexistence."]}
    report['report_stage'] = 'final' if review_context and not review_errors else 'preliminary'
    report['final_review'] = {
        'completed': report['report_stage'] == 'final',
        'reviewer': review_context['receipt']['reviewer'] if review_context else None,
        'reviewed_count': len(decisions) if review_context and not review_errors else 0,
        'errors': review_errors,
        'decisions': list(decisions.values()) if review_context and not review_errors else []}
    if write_reports:
        save(run / "report.json", report)
        from .report import render
        render(report, run)
    return report
