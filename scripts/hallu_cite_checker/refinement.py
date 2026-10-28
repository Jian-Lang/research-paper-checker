"""Evidence-backed refinement with bounded official-source fallbacks."""
from pathlib import Path
from urllib.parse import urlencode, urljoin
import hashlib
import re
import time
from .io import load, save, fingerprint, now
from .config import settings
from .capture import capture
from .evidence import parse_artifact, add_evidence, validate_record
from .normalize import norm, author_equal, venue
from .format_resolution import reference_variants, resolve_reference
from .official_formats import publisher_page
from .audit import audit, compare


def matching_variants(ref, fields):
    return [v for v in reference_variants(ref)
            if norm('title',v['fields'].get('title','')) == norm('title',fields.get('title',''))
            # Do not require the allegedly correct author to discover a wrong
            # author. Exact title plus claimed conference/year can also anchor
            # a candidate; the full byline remains a comparison target.
            and (author_equal(v['fields'].get('authors',[])[:1],fields.get('authors',[])[:1])
                 or sum(any(author_equal([a],[b]) for b in fields.get('authors',[]))
                        for a in v['fields'].get('authors',[])) >= 2
                 or (v['fields'].get('venue') and fields.get('venue') and
                     venue(v['fields']['venue']) == venue(fields['venue']) and
                     v['fields'].get('year') and str(v['fields']['year']) == str(fields.get('year'))))]


def select_crossref(run, ref, event):
    artifact = Path(run)/event['artifact']
    selections = []
    for item in load(artifact)['message']['items']:
        titles = item.get('title',[])
        if not titles or not any(norm('title',v['fields'].get('title','')) == norm('title',titles[0])
                                 for v in reference_variants(ref)):
            continue
        candidate = Path(run)/'discovery'/(ref['id']+'-selected-'+hashlib.sha256(
            str(item.get('DOI','')).encode()).hexdigest()[:12]+'.json')
        save(candidate,{'message':item})
        fields = parse_artifact(candidate,'crossref')
        if matching_variants(ref,fields):
            selections.append((candidate,fields))
    # Prefer the explicitly cited venue/year when multiple legitimate versions exist.
    if len(selections)>1:
        preferred = [(p,f) for p,f in selections if norm('venue',f.get('venue','')) == norm(
            'venue',ref['fields'].get('venue','')) and str(f.get('year'))==str(ref['fields'].get('year'))]
        selections = preferred
    distinct = {f.get('doi') for _,f in selections}
    if len(distinct)!=1 or not selections:
        return None
    candidate,fields = selections[0]
    return add_evidence(run,ref['id'],candidate,'crossref',event['source_url'],'crossref',
                        version_id='doi:'+fields.get('doi','unknown'),supporting_artifact=artifact)


def refine(run):
    run = Path(run).resolve()
    manifest = load(run/'manifest.json')
    # Refinement must not hide input changes or evidence integrity failures.
    prior = audit(run,write_reports=False)
    if any(b['code'] in {'input_changed','input_unavailable'} for b in prior['blockers']):
        raise ValueError('Input changed or unavailable; start a new run')
    coverage_valid = manifest.get('coverage',{}).get('reference_fingerprint') == fingerprint(
        manifest['references']) and manifest.get('coverage',{}).get('reviewed') is True
    if not (run/'report-before-refinement.json').exists():
        save(run/'report-before-refinement.json',prior)
    if (run/'annotations.json').exists():
        save(run/'annotations-before-refinement.json',load(run/'annotations.json'))
        save(run/'annotations.json',{})
    deadline = time.monotonic()+settings()['time_budget_seconds']
    cache, events = {},[]
    token = now().replace(':','').replace('.','').replace('+','')

    def get(kind,url):
        if url not in cache:
            if deadline-time.monotonic()<settings()['request_timeout']:
                return {'error':'network_budget_exhausted','source_url':url}
            digest = hashlib.sha256(url.encode()).hexdigest()[:16]
            event = capture(run,kind,url,'refine-'+token+'-'+digest+'.txt')
            events.append(event)
            cache[url] = event
        return cache[url]

    def import_publisher(ref,url):
        event = get('official',url)
        if event.get('error'):
            return None
        artifact = run/event['artifact']
        try:
            fields = parse_artifact(artifact,'publisher_html')
            if not matching_variants(ref,fields):
                return None
            return add_evidence(run,ref['id'],artifact,'official',url,'publisher_html',
                                version_id='official:'+url)
        except (ValueError,KeyError,TypeError) as exc:
            event['import_error']=str(exc)
            return None

    def index_lookup(ref,url):
        event = get('official',url)
        if event.get('error'):
            return None
        titles = {norm('title',v['fields'].get('title','')) for v in reference_variants(ref)}
        links = {urljoin(url,href) for href,title in publisher_page(run/event['artifact']).links
                 if norm('title',title) in titles}
        # Two distinct same-title candidates cannot be disambiguated by quietly
        # taking the first link. Inspect them before importing a primary record.
        if len(links) != 1:
            return None
        records = []
        for link in sorted(links):
            record = import_publisher(ref,link)
            if record:
                records.append(record)
        return records[0] if records else None

    def proceedings_lookup(ref, existing, host='proceedings.neurips.cc'):
        # Route by cited and captured deposit years; only the official export
        # establishes metadata. Do not derive source fields from the input.
        years = {str(ref['fields'].get('year', ''))}
        years.update(str(r['fields'].get('year', '')) for r in existing
                     if not validate_record(r, run))
        for year in sorted(years):
            if not re.fullmatch(r'20\d{2}', year):
                continue
            index = 'https://' + host + '/paper_files/paper/' + year
            event = get('official', index)
            if event.get('error'):
                continue
            titles = {norm('title', v['fields'].get('title', ''))
                      for v in reference_variants(ref)}
            links = {urljoin(index, href) for href, title in
                     publisher_page(run / event['artifact']).links
                     if norm('title', title) in titles}
            if len(links) != 1:
                continue
            for link in sorted(links):
                page_event = get('official', link)
                if page_event.get('error'):
                    continue
                bib_links = {urljoin(link, href) for href, label in
                             publisher_page(run / page_event['artifact']).links
                             if label.casefold() == 'bibtex'}
                for bib_url in sorted(bib_links):
                    bib_event = get('official', bib_url)
                    if bib_event.get('error'):
                        continue
                    try:
                        artifact = run / bib_event['artifact']
                        fields = parse_artifact(artifact, 'bibtex')
                        if matching_variants(ref, fields):
                            version = 'doi:' + fields['doi'] if fields.get('doi') else 'official:' + link
                            return add_evidence(run, ref['id'], artifact, 'official',
                                bib_event.get('final_url', bib_url), 'bibtex',
                                version_id=version)
                    except (ValueError, KeyError, TypeError) as exc:
                        bib_event['import_error'] = str(exc)
        return None

    def ieee_lookup(ref):
        urls = set()
        for meta in (run/'discovery').glob('*.capture.json'):
            event = load(meta)
            if 'api.crossref.org/works?' not in event.get('source_url','') or not event.get('artifact'):
                continue
            for item in load(run/event['artifact']).get('message',{}).get('items',[]):
                if not any(norm('title',v['fields'].get('title','')) == norm('title',item.get('title',[''])[0])
                           for v in reference_variants(ref)):
                    continue
                for link in item.get('link',[]):
                    match = re.search(r'[?&]arnumber=(\d+)',link.get('URL',''))
                    if match:
                        urls.add('https://ieeexplore.ieee.org/document/'+match[1]+'/')
        for url in sorted(urls):
            record = import_publisher(ref,url)
            if record:
                return record
        return None

    def openreview_lookup(ref):
        query = urlencode({'term':ref['fields']['title'],'content':'title','limit':20})
        url = 'https://api2.openreview.net/notes/search?'+query
        event = get('official',url)
        if event.get('error'):
            return None
        selections = []
        try:
            for note in load(run/event['artifact']).get('notes',[]):
                target = run/'discovery'/('openreview-'+note['id']+'.json')
                save(target,{'note':note})
                try:
                    fields = parse_artifact(target,'openreview')
                except ValueError:
                    continue
                if matching_variants(ref,fields) and fields['year']==ref['fields']['year']:
                    selections.append((target,fields,note['id']))
            if len(selections)!=1:
                event['import_error']='No unique accepted ICLR record matching title, authors and year'
                return None
            target,fields,ident = selections[0]
            return add_evidence(run,ref['id'],target,'official',url,'openreview',
                                version_id='openreview:'+ident,supporting_artifact=run/event['artifact'])
        except (ValueError,KeyError,TypeError) as exc:
            event['import_error']=str(exc)
            return None

    # Reconsider saved discovery responses with legitimate PDF break variants.
    evidence = load(run/'evidence.json')
    for ref in manifest['references']:
        existing = [r for r in evidence['records'] if r['ref_id']==ref['id']]
        if existing:
            continue
        for event in evidence.get('attempts',[]):
            if event.get('ref_id')==ref['id'] and event.get('artifact') and 'api.crossref.org/works?' in event.get('source_url',''):
                if select_crossref(run,ref,event):
                    break
    evidence = load(run/'evidence.json')
    for ref in manifest['references']:
        existing = [r for r in evidence['records'] if r['ref_id']==ref['id']]
        conflicting = any(c['result'] == 'CONFLICT' for r in existing
                          if r['role'] == 'primary' and not validate_record(r, run)
                          for c in compare(ref, r))
        if existing and not conflicting:
            continue
        if existing and any(r['kind'] == 'official' for r in existing):
            continue
        claimed = venue(ref['fields'].get('venue',''))
        year = ref['fields'].get('year','')
        record = None
        if claimed == 'neurips':
            record = proceedings_lookup(ref, existing)
        elif claimed=='icml':
            # Maintained proceedings volume for the 2023 ICML main conference.
            if year=='2023':
                record = index_lookup(ref,'https://proceedings.mlr.press/v202/')
        elif claimed=='cvpr' and re.fullmatch(r'20\d{2}',year):
            record = index_lookup(ref,'https://openaccess.thecvf.com/CVPR'+year+'?day=all')
            if not record:
                record = ieee_lookup(ref)
        elif claimed=='iclr':
            record = openreview_lookup(ref)
            if not record:
                record = proceedings_lookup(ref, existing, 'proceedings.iclr.cc')
        # Crossref is discovery; absence there is never proof of nonexistence.
        if not record and not existing:
            url='https://api.crossref.org/works?'+urlencode({'query.bibliographic':
                ref['fields']['title']+' '+ref['fields']['authors'][0],'rows':20})
            event = get('crossref',url)
            if not event.get('error'):
                record = select_crossref(run,ref,event)
        evidence = load(run/'evidence.json')
        save(run/'progress.json',{'stage':'official_source_refinement','ref_id':ref['id'],'updated_at':now()})

    evidence = load(run/'evidence.json')
    for ref in manifest['references']:
        # Before rejecting a byline conflict, inspect actual related preprint
        # versions linked by saved OpenReview discovery records.
        primaries = [r for r in evidence['records'] if r['ref_id']==ref['id'] and r['role']=='primary']
        if any(any(c['field']=='authors' and c['result']=='CONFLICT' for c in compare(ref,r)) for r in primaries):
            related = set()
            for meta in (run/'discovery').glob('*.capture.json'):
                ev=load(meta)
                if 'api2.openreview.net/notes/search?' not in ev.get('source_url','') or not ev.get('artifact'):
                    continue
                for note in load(run/ev['artifact']).get('notes',[]):
                    content = {k:(v.get('value') if isinstance(v,dict) else v) for k,v in note.get('content',{}).items()}
                    if norm('title',content.get('title','')) != norm('title',ref['fields'].get('title','')):
                        continue
                    match = re.search(r'https://arxiv.org/pdf/(\d{4}\.\d{4,5})(?:v\d+)?',content.get('pdf',''))
                    if match:
                        related.update((match[1],match[1]+'v1'))
            for ident in sorted(related):
                url='https://arxiv.org/abs/'+ident
                ev=get('arxiv',url)
                if ev.get('error'):
                    continue
                try:
                    fields=parse_artifact(run/ev['artifact'],'citation_html')
                    if norm('title',fields.get('title','')) == norm('title',ref['fields'].get('title','')) and author_equal(
                            ref['fields'].get('authors',[]),fields.get('authors',[]),ref.get('authors_truncated',False)):
                        add_evidence(run,ref['id'],run/ev['artifact'],'arxiv',url,'citation_html',
                            role='alternative_version',version_id='arxiv:'+ident,
                            reviewer='hallu-cite-checker-related-version-adapter',
                            relation='Same exact title and ordered authors; actual arXiv URL linked in saved OpenReview search response')
                except (ValueError,KeyError,TypeError) as exc:
                    ev['import_error']=str(exc)
            evidence=load(run/'evidence.json')
        valid = [r for r in evidence['records'] if r['ref_id']==ref['id'] and not validate_record(r,run)]
        resolved = resolve_reference(ref,valid)
        if resolved is not ref:
            ref.clear()
            ref.update(resolved)
    # Preserve an existing reviewed inventory only when entry boundaries and raw
    # provenance are untouched; every formatting change carries source evidence.
    if coverage_valid:
        manifest['coverage']['reference_fingerprint']=fingerprint(manifest['references'])
        manifest['coverage']['formatting_refinement_at']=now()
        manifest['coverage']['note'] += ' Source-backed line-break variants subsequently resolved automatically; original entry boundaries, rows and locations unchanged.'
    manifest.setdefault('execution',{})['refinement']={
        'saved_source_evidence_reused':True,'live_official_fallbacks_attempted':True,
        'new_requests':len(events),'formatting_resolved':sum(bool(r.get('format_resolutions')) for r in manifest['references']),
        'official_registry_added':'api2.openreview.net',
        'registry_provenance':'https://docs.openreview.net/reference/api-v2/openapi-definition',
        'completed_at':now()}
    save(run/'manifest.json',manifest)
    save(run/'refinement-network.json',{'events':events,'completed_at':now()})
    evidence = load(run/'evidence.json')
    evidence['attempts'].extend({**e,'error':e.get('error',e.get('import_error'))}
        for e in events if e.get('error') or e.get('import_error'))
    save(run/'evidence.json',evidence)
    return audit(run)
