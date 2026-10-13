"""Bounded reproducible PDF audit; extraction review is a separate skill step."""
from pathlib import Path
import re
import time
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from .io import load, save, now
from .inventory import inventory_pdf
from .normalize import norm, author_equal
from .evidence import add_evidence, parse_artifact
from .capture import capture
from .audit import audit
from .config import settings

YEAR = re.compile(r'(?<!\d)((?:19|20)\d{2})([a-z]?)\.\s*')
STOP = re.compile(r'^(?:[A-Z](?:\.\d+)?\s+(?:Additional|Appendix|Supplementary|Implementation|Experimental)|Appendix\b)', re.I)


def joined(lines):
    result = ''
    ambiguous = False
    for line in lines:
        line = line.strip()
        if result.endswith('-') and line and line[0].islower():
            result = result[:-1] + line
            ambiguous = True
        else:
            result += (' ' if result else '') + line
    return re.sub(r'\s+', ' ', result), ambiguous


def author_list(prefix):
    prefix = prefix.strip().rstrip(',')
    truncated = bool(re.search(r'(?:et al\.|and \d+ others\.?)\s*$', prefix))
    prefix = re.sub(r',?\s*(?:et al\.|and \d+ others\.?)\s*$', '', prefix).rstrip(', ')
    prefix = prefix.rstrip(' .')
    names = [n.strip() for n in re.split(r',\s*(?:and\s+)?|\s+and\s+', prefix) if n.strip()]
    for name in names:
        pieces = name.split()
        if not 2 <= len(pieces) <= 7:
            return None
        if any(not all(c.isalpha() or c in "-.'’´" for c in token) for token in pieces):
            return None
        if re.search(r'\b(?:Conference|Proceedings|pages|volume|Springer|preprint|IEEE|Learning|Recognition)\b', name, re.I):
            return None
    return (names, truncated) if names else None


def numbered_sections(run, manifest):
    rows, sections, active, expected = [], [], False, None
    diagnostics = []
    for page in manifest['pages']:
        n = page['page']
        plain = (Path(run)/f'page-{n:03d}.txt').read_text(encoding='utf-8')
        for raw in plain.splitlines():
            if active and raw.strip().endswith(str(expected)):
                body = raw.strip()[:-len(str(expected))].rstrip()
                match = (None, body, str(expected))
            else:
                match = re.fullmatch(r'(.*?)(\d{3,4})', raw.strip())
            if not match:
                if active and raw.strip() and raw.strip() != str(n):
                    diagnostics.append('unaccounted_reference_line:page_' + str(n))
                continue
            body, number = match[1].rstrip(), int(match[2])
            if re.fullmatch(r'References|Bibliography', body, re.I):
                if active:
                    sections.append(rows)
                rows, active, expected = [], True, number + 1
                continue
            if not active:
                continue
            if STOP.match(body):
                sections.append(rows)
                rows, active, expected = [], False, None
                continue
            if number != expected:
                diagnostics.append(f'reference_line_number_gap:{expected}:{number}')
            expected = number + 1
            rows.append({'page':n,'line_number':number,'text':body,'raw':raw})
    if active:
        sections.append(rows)
    if not sections:
        diagnostics.append('unsupported_pdf_bibliography_layout:automatic_numbered_author_year_parser')
    return sections, diagnostics


def parse_reference(rows, number, reconstructed=None):
    raw = '\n'.join(r['raw'] for r in rows)
    content, hyphens = joined([r['text'] for r in rows])
    if reconstructed is not None:
        content = re.sub(r'\s+', ' ', reconstructed)
    year = YEAR.search(content)
    issues = []
    fields = {}
    truncated = False
    if not year or not author_list(content[:year.start()]):
        issues.append('reference_author_year_parse_failed')
    else:
        names, truncated = author_list(content[:year.start()])
        fields.update(authors=names, year=year[1])
        rest = content[year.end():]
        if YEAR.search(rest):
            issues.append('multiple_year_sentences_require_extraction_review')
        preprint = re.search(r'\.?\s*arXiv\s+preprint\s+arXiv\s*:\s*(\d{4}\.\d{4,5}(?:v\d+)?)', rest, re.I)
        if preprint:
            fields.update(title=rest[:preprint.start()].strip().rstrip('.'), venue='arXiv', arxiv_id=preprint[1])
            if rest[preprint.end():].strip(' .'):
                issues.append('unparsed_reference_metadata_tail')
        else:
            boundary = re.search(r'\.\s*In\s*(?=[A-Z0-9])', rest)
            if not boundary:
                boundary = re.search(r'\.\s*(?=Advances in|Journal of|Transactions on|Proceedings of)', rest, re.I)
            if not boundary:
                fields['title'] = rest.strip().rstrip('.')
                issues.append('reference_title_venue_boundary_uncertain')
            else:
                fields['title'] = rest[:boundary.start()].strip().rstrip('.')
                tail = rest[boundary.end():].strip()
                pages = re.search(r'\bpages\s+([0-9]+\s*[–-]\s*[0-9]+)', tail, re.I)
                journal = re.search(r',\s*(\d+)\s*:\s*([0-9]+\s*[–-]\s*[0-9]+)', tail)
                volume = re.search(r',\s*volume\s+(\d+)', tail, re.I)
                cut = len(tail)
                if pages:
                    fields['pages'] = re.sub(r'\s+', '', pages[1])
                    cut = min(cut, pages.start())
                if journal:
                    fields.update(volume=journal[1], pages=re.sub(r'\s+', '', journal[2]))
                    cut = min(cut, journal.start())
                if volume:
                    fields['volume'] = volume[1]
                    cut = min(cut, volume.start())
                publisher = re.search(r'\.\s*(IEEE|Springer|PmLR)\.?\s*$', tail, re.I)
                if publisher:
                    fields['publisher'] = publisher[1]
                    cut = min(cut, publisher.start())
                fields['venue'] = tail[:cut].strip(' ,.')
                residual = tail[cut:]
                residual = re.sub(r'[,\s.:]+|\bpages\b|\bvolume\b|\d+|[–-]|IEEE|Springer|PmLR', '', residual, flags=re.I)
                if residual:
                    issues.append('unparsed_reference_metadata_tail')
    if '[UNRESOLVED U+' in content:
        issues.append('reference_contains_unresolved_unicode')
    if hyphens:
        # Do not call a reconstruction mismatch a confirmed input error.
        issues.append('line_break_hyphen_reconstruction_requires_review')
    return {'id':f'ref-{number:03d}','fields':fields,'raw':raw,
            'locations':[{'page':p,'first_line':min(r['line_number'] for r in rows if r['page']==p),
                          'last_line':max(r['line_number'] for r in rows if r['page']==p)}
                         for p in sorted({r['page'] for r in rows})],
            'issues':issues,'authors_truncated':truncated,
            'extraction':{'method':'numbered_author_year','original_rows':rows,
                          'year_suffix':year[2] if year else '', 'hyphen_reconstruction':hyphens}}


def populate(run):
    manifest = load(Path(run)/'manifest.json')
    sections, diagnostics = numbered_sections(run, manifest)
    groups = []
    for rows in sections:
        starts = []
        for i in range(len(rows)):
            if i and not rows[i-1]['text'].rstrip().endswith('.'):
                continue
            candidate, _ = joined([r['text'] for r in rows[i:i+9]])
            year = YEAR.search(candidate)
            if year and author_list(candidate[:year.start()]):
                starts.append(i)
        if not starts or starts[0] != 0:
            diagnostics.append('unparsed_bibliography_prefix')
        for i, start in enumerate(starts):
            end = starts[i+1] if i+1 < len(starts) else len(rows)
            groups.append(rows[start:end])
    manifest['references'] = [parse_reference(g, i+1) for i,g in enumerate(groups)]
    bibliography_pages = {r['page'] for g in groups for r in g}
    extraction_issues = list(manifest['issues'])
    # Nonbibliographic anomalies remain recorded; only verified scope exclusion removes blockers.
    manifest['extraction_diagnostics'] = extraction_issues
    manifest['issues'] = [issue for issue in extraction_issues if issue.get('page') in bibliography_pages or not bibliography_pages]
    manifest['issues'].extend({'code':'automatic_bibliography_parse', 'detail':d} for d in sorted(set(diagnostics)))
    manifest['coverage'].update(reference_count=len(groups), bibliography_pages=sorted(bibliography_pages),
        note='Automatic candidates only. Skill must reconcile original bibliography pages, boundaries, line coverage and every supplied field before confirming coverage.')
    manifest['execution'] = {'mode':'fresh_network_check','automatic_pdf_candidates':True,
        'old_evidence_imported':False,'fresh_network_verification':True,
        'bibliography_pages':sorted(bibliography_pages),'parser':'numbered_author_year',
        'nonbibliographic_extraction_anomalies':len(extraction_issues)-len(manifest['issues'])}
    save(Path(run)/'manifest.json', manifest)
    save(Path(run)/'extraction-review.json', {'candidate_count':len(groups),
        'candidate_pages':sorted(bibliography_pages),'diagnostics':diagnostics,
        'references':[{'id':r['id'],'title':r['fields'].get('title'),
                       'locations':r['locations'],'issues':r['issues']} for r in manifest['references']]})
    return manifest


def check_pdf(pdf, run):
    run = Path(run)
    inventory_pdf(pdf, run)
    manifest = populate(run)
    audit(run)  # Always deliver a provisional report before networking.
    config = settings()
    deadline = time.monotonic() + config['time_budget_seconds']
    pacing = threading.Lock()
    next_request = {'crossref':0.0,'arxiv':0.0}

    def lookup(ref):
        if time.monotonic() >= deadline:
            return {'ref_id':ref['id'],'error':'network_budget_exhausted'}
        fields = ref['fields']
        if fields.get('arxiv_id'):
            url = 'https://arxiv.org/abs/' + fields['arxiv_id']
            kind, fmt = 'arxiv', 'citation_html'
        elif fields.get('title'):
            url = 'https://api.crossref.org/works?' + urllib.parse.urlencode({'query.title':fields['title'],'rows':3})
            kind, fmt = 'crossref', 'crossref_candidates'
        else:
            return {'ref_id':ref['id'],'error':'missing_query_metadata'}
        for attempt in range(config['max_attempts']):
            with pacing:
                start = max(time.monotonic(), next_request[kind])
                next_request[kind] = start + (0.8 if kind=='crossref' else 0.35)
            delay = start-time.monotonic()
            if delay > 0:
                time.sleep(min(delay,max(0,deadline-time.monotonic())))
            if deadline-time.monotonic() < config['request_timeout']:
                return {'ref_id':ref['id'],'error':'network_budget_exhausted'}
            name = ref['id'] + '-try' + str(attempt+1) + ('.html' if kind=='arxiv' else '.json')
            event = capture(run, kind, url, name)
            if not event.get('error') or attempt+1 == config['max_attempts']:
                break
            if not any(marker in event['error'] for marker in ('429','502','503','504','SSL','timed out')):
                break
            time.sleep(min(2*(attempt+1),max(0,deadline-time.monotonic())))
        return {'ref_id':ref['id'],'format':fmt,**event}

    refs = {r['id']:r for r in manifest['references']}
    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(lookup, ref) for ref in manifest['references']]
        for future in as_completed(futures):
            event = future.result()
            results.append(event)
            if not event.get('error'):
                artifact = run/event['artifact']
                try:
                    ref = refs[event['ref_id']]
                    if event['format'] == 'citation_html':
                        fields = parse_artifact(artifact, 'citation_html')
                        if fields.get('arxiv_id') != ref['fields']['arxiv_id']:
                            raise ValueError('arXiv page does not confirm requested identifier')
                        add_evidence(run, ref['id'], artifact, 'arxiv', event['source_url'], 'citation_html',
                                     version_id='arxiv:' + fields['arxiv_id'])
                    else:
                        msg = load(artifact)
                        candidates = []
                        for item in msg['message']['items']:
                            if norm('title', item.get('title',[''])[0]) == norm('title', ref['fields']['title']):
                                candidates.append(item)
                        # Candidate search is not itself proof; ambiguity stays unresolved.
                        if len(candidates) != 1:
                            raise ValueError('No unique exact-title Crossref candidate; remains UNVERIFIED')
                        candidate = run/'discovery'/(ref['id'] + '-selected.json')
                        save(candidate, {'message':candidates[0]})
                        fields = parse_artifact(candidate, 'crossref')
                        if not author_equal(ref['fields'].get('authors',[]), fields.get('authors',[]), ref.get('authors_truncated',False)):
                            raise ValueError('Crossref candidate identity is not established by ordered authors')
                        add_evidence(run, ref['id'], candidate, 'crossref', event['source_url'], 'crossref',
                                     version_id='doi:' + fields.get('doi','unknown'), supporting_artifact=artifact)
                except Exception as exc:
                    event['import_error'] = str(exc)
            evidence = load(run/'evidence.json')
            if event.get('error') or event.get('import_error'):
                evidence['attempts'].append({**event,'error':event.get('error',event.get('import_error'))})
                save(run/'evidence.json', evidence)
            save(run/'network-check.json', {'results':results,'completed':len(results),'total':len(refs)})
            save(run/'progress.json', {'stage':'fresh_network_check','completed':len(results),'total':len(refs),'updated_at':now()})
            audit(run)
    from .refinement import refine
    return refine(run)
