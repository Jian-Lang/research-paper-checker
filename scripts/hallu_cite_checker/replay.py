"""Re-run an unchanged paper from captured evidence, never from old verdicts."""
import copy
import subprocess
import unicodedata
from pathlib import Path
from .io import load, save, sha256, fingerprint, now
from .inventory import inventory_pdf
from .evidence import add_evidence, validate_record
from .audit import audit


def compact(value):
    return ''.join(unicodedata.normalize('NFKC', value).casefold().split())


def replay_pdf(pdf, bundle, output):
    pdf, bundle, output = Path(pdf).resolve(), Path(bundle).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('Replay output must be a fresh directory')
    previous = load(bundle / 'manifest.json')
    references = previous['references']
    coverage = previous.get('coverage', {})
    if previous.get('mode') != 'pdf' or not any(i['sha256'] == sha256(pdf) for i in previous['inputs']):
        raise ValueError('Reviewed inventory belongs to a different input PDF')
    if not coverage.get('reviewed') or coverage.get('reference_count') != len(references) or coverage.get('reference_fingerprint') != fingerprint(references):
        raise ValueError('Cached extraction review is missing or changed')
    evidence = load(bundle / 'evidence.json')
    for record in evidence['records']:
        if validate_record(record, bundle):
            raise ValueError('Invalid captured evidence: ' + record.get('ref_id', '?'))
    extracted = subprocess.run(['pdftotext', '-enc', 'UTF-8', str(pdf), '-'],
                              capture_output=True, text=True, check=True).stdout
    pages = extracted.split('\f')
    for ref in references:
        if not isinstance(ref.get('raw'), str) or not ref['raw'] or not ref.get('locations'):
            raise ValueError('Missing raw reference provenance: ' + ref['id'])
        page_numbers = {loc['page'] for loc in ref['locations']}
        if not any(0 < n <= len(pages) and compact(ref['raw']) in compact(pages[n-1]) for n in page_numbers):
            raise ValueError('Fresh PDF extraction differs at reference: ' + ref['id'])
    manifest = inventory_pdf(pdf, output)
    if manifest['issues']:
        raise ValueError('Fresh extraction has unresolved page issues; see manifest.json')
    manifest['references'] = copy.deepcopy(references)
    for ref in manifest['references']:
        for loc in ref['locations']:
            loc['file'] = str(pdf)
    manifest['coverage'] = {'reviewed': True, 'reviewer': 'replay of ' + coverage['reviewer'],
        'reference_count': len(references), 'reference_fingerprint': fingerprint(manifest['references']),
        'reviewed_at': now(), 'note': 'Reused prior visual reconciliation of byte-identical PDF; every raw entry rechecked on its stated page against fresh pdftotext output. Not a new blind extraction review.',
        'prior_review': coverage}
    manifest['execution'] = {'mode': 'captured_evidence_replay', 'source_bundle': str(bundle),
        'fresh_pdf_extraction': True, 'raw_entries_reconciled': len(references),
        'fresh_network_verification': False, 'old_verdicts_imported': False}
    save(output / 'manifest.json', manifest)
    for record in evidence['records']:
        added = add_evidence(output, record['ref_id'], bundle / record['artifact'], record['kind'],
            record['source_url'], record['format'], record['role'], record['version_id'],
            record.get('relation', ''), record.get('reviewer', ''),
            bundle / record['supporting_artifact'] if record.get('supporting_artifact') else None)
        current = load(output / 'evidence.json')
        current['records'][-1]['retrieved_at'] = record['retrieved_at']
        current['records'][-1]['imported_at'] = added['retrieved_at']
        save(output / 'evidence.json', current)
    if (bundle / 'annotations.json').exists():
        save(output / 'annotations.json', load(bundle / 'annotations.json'))
    save(output / 'replay-validation.json', manifest['execution'])
    return audit(output)
