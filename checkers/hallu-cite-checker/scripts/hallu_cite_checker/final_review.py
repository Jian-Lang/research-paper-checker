"""Evidence-bound model review performed by the skill's host model."""
from pathlib import Path
import re
from .io import load, save, fingerprint, sha256, now
from .evidence import validate_record
from .normalize import venue, words, _VENUES

OUTCOMES = {'resolved', 'retained', 'uncertain', 'suspected_fabrication'}


def state_fingerprint(run):
    run = Path(run)
    manifest, evidence = load(run/'manifest.json'), load(run/'evidence.json')
    artifacts = set()
    for record in evidence.get('records', []):
        artifacts.update(record[k] for k in ('artifact', 'supporting_artifact') if record.get(k))
    captures = []
    for path in sorted((run/'discovery').glob('*.capture.json')):
        event = load(path)
        captures.append(event)
        if event.get('artifact'):
            artifacts.add(event['artifact'])
    hashes = {}
    for name in sorted(artifacts):
        path = (run/name).resolve()
        hashes[name] = sha256(path) if path.is_relative_to(run.resolve()) and path.is_file() else None
    actual_inputs = {}
    for item in manifest.get('inputs', []):
        path = Path(item['path'])
        actual_inputs[str(path)] = sha256(path) if path.is_file() else None
    policy = {name: sha256(Path(__file__).with_name(name))
              for name in ('audit.py', 'normalize.py', 'final_review.py', 'identity.py')}
    return fingerprint({'manifest': manifest, 'evidence': evidence, 'artifacts': hashes,
        'captures': captures, 'actual_inputs': actual_inputs, 'policy': policy,
        'annotations': load(run/'annotations.json') if (run/'annotations.json').exists() else {}})


def start_review(run):
    from .audit import audit
    run = Path(run).resolve()
    report = audit(run, write_reports=True, model_review=False)
    previous = load(run/'review-packet.json') if (run/'review-packet.json').exists() else {}
    targets = {r['id'] for r in previous.get('targets', [])}
    targets.update(r['id'] for r in report['references'] if r['status'] != 'VERIFIED')
    refs = {r['id']: r for r in report['references']}
    if targets - refs.keys():
        raise ValueError('Review inventory changed: a previously flagged entry was removed; use a fresh run')
    packet = {'schema_version': 1, 'state_fingerprint': state_fingerprint(run),
        'targets': [refs[key] for key in sorted(targets)], 'blockers': report['blockers'],
        'instructions': 'Host model must inspect every target against actual saved sources, supplement evidence if needed, and write model-review.json. This command does not invoke a model or perform the review.'}
    packet['packet_fingerprint'] = fingerprint(packet)
    save(run/'review-packet.json', packet)
    return packet


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _validate_equivalence(ref, record, item):
    from .audit import same
    if item.get('field') != 'venue':
        raise ValueError('Model equivalence can only resolve venue wording; import actual evidence for other fields')
    if (item.get('input') != ref['fields'].get('venue') or
            item.get('source') != record['fields'].get('venue')):
        raise ValueError('Venue equivalence does not match the original field values')
    if not _nonempty(item.get('reason')) or not _nonempty(item.get('source_context')):
        raise ValueError('Venue equivalence requires reasoning and an inspected source location')
    for field in ('title', 'authors'):
        if not ref['fields'].get(field) or not record['fields'].get(field) or not same(
                field, ref['fields'][field], record['fields'][field], ref, record):
            raise ValueError('Venue equivalence lacks matching paper identity')
    left, right = words(item['input']), words(item['source'])
    lv, rv = venue(left), venue(right)
    if record['kind'] == 'arxiv' or rv == 'arxiv':
        raise ValueError('An arXiv record cannot establish conference venue equivalence')
    if lv == rv or lv in _VENUES and rv in _VENUES:
        raise ValueError('Venue equivalence cannot bypass an edition check or change known conferences')
    markers = r'\b(?:workshops?|findings|industry|demonstrations?|doctoral|tutorials?|datasets? and benchmarks?)\b'
    if set(re.findall(markers, left)) != set(re.findall(markers, right)):
        raise ValueError('Venue equivalence cannot discard a workshop or track distinction')
    for value, fields in ((left, ref['fields']), (right, record['fields'])):
        years = re.findall(r'\b(?:19|20)\d{2}\b', value)
        if any(year != str(fields.get('year')) for year in years):
            raise ValueError('Venue equivalence cannot discard a conflicting embedded year')
    lo = re.findall(r'\b\d+(?:st|nd|rd|th)\b', left)
    ro = re.findall(r'\b\d+(?:st|nd|rd|th)\b', right)
    if lo and ro and lo != ro:
        raise ValueError('Venue equivalence cannot discard a conflicting conference edition')
    canonical = lv if lv in _VENUES else rv
    for value, fields in ((left, ref['fields']), (right, record['fields'])):
        ordinals = re.findall(r'\b(\d+)(?:st|nd|rd|th)\b', value)
        if ordinals and str(fields.get('year', '')).isdigit():
            n = int(ordinals[0])
            expected = 1983+n if canonical == 'icml' and n >= 20 else (2012+n if canonical == 'iclr' else None)
            if expected is not None and expected != int(fields['year']):
                raise ValueError('Venue equivalence cannot bypass edition/year consistency')


def load_review(run):
    """Validate the host-model receipt, never infer model work from a command."""
    run = Path(run).resolve()
    if not (run/'model-review.json').exists():
        return None
    if not (run/'review-packet.json').exists():
        raise ValueError('Missing review packet; run review first')
    packet, receipt = load(run/'review-packet.json'), load(run/'model-review.json')
    if packet['packet_fingerprint'] != fingerprint({k:v for k,v in packet.items() if k != 'packet_fingerprint'}):
        raise ValueError('Review packet was modified')
    if packet['state_fingerprint'] != state_fingerprint(run):
        raise ValueError('Review is stale: input, inventory, evidence or policy changed; refresh review')
    if receipt.get('packet_fingerprint') != packet['packet_fingerprint'] or not _nonempty(receipt.get('reviewer')):
        raise ValueError('Model review must identify its reviewer and current packet')
    if receipt.get('performed_by') != 'host_model':
        raise ValueError('Final review must be performed by the skill host model')
    decisions = receipt.get('decisions', [])
    ids = [d.get('ref_id') for d in decisions]
    targets = {r['id'] for r in packet['targets']}
    if len(ids) != len(set(ids)) or set(ids) != targets:
        raise ValueError('Model review must cover every flagged reference exactly once')
    if packet['blockers'] and receipt.get('blockers_reviewed') is not True:
        raise ValueError('Model must review remaining inventory/integrity blockers')
    manifest, evidence = load(run/'manifest.json'), load(run/'evidence.json')
    refs = {r['id']:r for r in manifest['references']}
    equivalents, identity_findings = {}, {}
    for decision in decisions:
        ident = decision['ref_id']
        if decision.get('outcome') not in OUTCOMES or not _nonempty(decision.get('reason')):
            raise ValueError('Each model decision needs an outcome and concrete reason')
        uncertain_fields = decision.get('uncertain_fields', [])
        if (not isinstance(uncertain_fields, list) or
                any(not isinstance(f, str) or f not in refs[ident]['fields'] for f in uncertain_fields)):
            raise ValueError('uncertain_fields must name actual supplied citation fields')
        if uncertain_fields and (decision['outcome'] != 'uncertain' or
                decision.get('uncertainty_kind') not in {'format', 'extraction', 'version', 'source_conflict'}):
            raise ValueError('Field uncertainty needs an uncertain outcome and a concrete uncertainty_kind')
        valid = [r for r in evidence['records'] if r['ref_id'] == ident and not validate_record(r, run)]
        cited = decision.get('evidence', [])
        for citation in cited:
            if not any(r['artifact'] == citation.get('artifact') and r['sha256'] == citation.get('sha256') for r in valid):
                raise ValueError('Model decision cites missing, unrelated or invalid evidence')
        if decision['outcome'] == 'resolved' and not cited:
            raise ValueError('Resolving a finding requires actual trusted evidence')
        if uncertain_fields and not cited:
            raise ValueError('Withholding a field conflict requires actual cited source evidence')
        if decision['outcome'] == 'suspected_fabrication':
            from .identity import validate_conflation
            identity_findings[ident] = validate_conflation(refs[ident],
                decision.get('investigation'), run, evidence['records'])
            if decision.get('equivalences'):
                raise ValueError('Suspected fabrication cannot also waive a metadata conflict')
        for item in decision.get('equivalences', []):
            matches = [r for r in valid if r['sha256'] == item.get('source_sha256') and r['role'] == 'primary']
            if len(matches) != 1 or not any(c.get('sha256') == item.get('source_sha256') for c in cited):
                raise ValueError('Equivalence must cite one valid primary record for this reference')
            _validate_equivalence(refs[ident], matches[0], item)
            equivalents.setdefault(ident, []).append(item)
    return {'packet': packet, 'receipt': receipt, 'equivalences': equivalents,
            'identity_findings': identity_findings}


def finalize(run):
    from .audit import audit
    context = load_review(run)
    if context is None:
        raise ValueError('Final model review is missing; run review and complete model-review.json')
    report = audit(run, write_reports=False)
    if report.get('report_stage') != 'final':
        raise ValueError('Final model review is incomplete: ' + '; '.join(report['final_review'].get('errors', [])))
    save(Path(run)/'report.json', report)
    from .report import render
    render(report, run)
    return report
