"""Validate model-investigated citation conflation without inventing a primary record."""
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import urlsplit, parse_qs
from .evidence import validate_record
from .io import load, sha256
from .normalize import author_equal, norm, venue, words


class _Abstract(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if self.depth:
            if tag not in {'br', 'img', 'meta', 'input', 'hr', 'link'}:
                self.depth += 1
        elif attrs.get('id') == 'abstract' or 'abstract' in attrs.get('class', '').split():
            self.depth = 1

    def handle_endtag(self, tag):
        if self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if self.depth:
            self.parts.append(data)


def _compact(value):
    return re.sub(r'[\s-]+', '', norm('title', value))


def validate_conflation(ref, investigation, run, records):
    """Return evidence-bound observations, never a proof of global nonexistence.

    The model supplies the hypothesis. A related abstract and an actually saved
    official catalogue must support it; an unrelated title or failed query alone
    cannot produce this finding. Catalogue support currently covers CVF main events.
    """
    run = Path(run).resolve()
    if not isinstance(investigation, dict) or investigation.get('kind') != 'metadata_conflation':
        raise ValueError('Suspected fabrication requires a metadata-conflation investigation')
    for field in ('title_search', 'author_search', 'venue_search', 'reason'):
        if not isinstance(investigation.get(field), str) or not investigation[field].strip():
            raise ValueError('Identity investigation must record title, author and venue searches and reasoning')
    valid = [r for r in records if not validate_record(r, run)]
    # A matching trusted identity must be investigated as a metadata discrepancy,
    # not branded as a fabricated paper based on an unrelated method name.
    if any(norm('title', r['fields'].get('title', '')) == norm('title', ref['fields'].get('title', ''))
           for r in valid if r['ref_id'] == ref['id'] and r['role'] == 'primary'):
        raise ValueError('A trusted matching title exists; compare its metadata instead of alleging conflation')
    related = investigation.get('related_work', {})
    matches = [r for r in valid if r['kind'] == 'official' and r['role'] == 'primary'
               and r['artifact'] == related.get('artifact') and r['sha256'] == related.get('sha256')]
    if not matches:
        raise ValueError('Conflation finding requires a valid saved official related-work record')
    record = matches[0]
    fields = record['fields']
    if (norm('title', fields.get('title', '')) == norm('title', ref['fields'].get('title', '')) or
            author_equal(ref['fields'].get('authors', []), fields.get('authors', []),
                         ref.get('authors_truncated', False))):
        raise ValueError('Related work must have a distinct title and byline; check legitimate versions first')
    parser = _Abstract()
    parser.feed((run / record['artifact']).read_text(encoding='utf-8'))
    abstract = ' '.join(parser.parts)
    quote = related.get('quote', '')
    if not isinstance(quote, str) or len(quote.strip()) < 30 or words(quote) not in words(abstract):
        raise ValueError('Related-work quote must occur in the actual saved abstract, not its bibliography')
    method = related.get('method', '')
    if (not isinstance(method, str) or len(method.strip()) < 4 or
            not re.search(r'(?<!\w)' + re.escape(method) + r'(?!\w)', quote, re.I) or
            not re.search(r'(?<!\w)' + re.escape(method) + r'(?!\w)', ref['fields'].get('title', ''), re.I)):
        raise ValueError('Related-work abstract and submitted title must actually name the investigated method')
    claimed = venue(ref['fields'].get('venue', ''))
    year = str(ref['fields'].get('year', ''))
    catalogue = investigation.get('catalogue', {})
    event = None
    for path in sorted((run / 'discovery').glob('*.capture.json')):
        candidate = load(path)
        if (not candidate.get('error') and candidate.get('kind') == 'official' and
                candidate.get('artifact') == catalogue.get('artifact') and
                candidate.get('sha256') == catalogue.get('sha256')):
            event = candidate
            break
    if event is None:
        raise ValueError('Conflation finding requires an actual successful official catalogue capture')
    expected_path = '/' + claimed.upper() + year
    for url in (event.get('source_url', ''), event.get('final_url', '')):
        parsed = urlsplit(url)
        if (claimed not in {'cvpr', 'iccv'} or not re.fullmatch(r'20\d{2}', year) or
                parsed.scheme != 'https' or parsed.netloc != 'openaccess.thecvf.com' or
                parsed.path != expected_path or parse_qs(parsed.query) != {'day': ['all']}):
            raise ValueError('Catalogue must be the cited CVF main conference/year all-papers page')
    artifact = (run / event['artifact']).resolve()
    if not artifact.is_relative_to(run) or not artifact.is_file() or sha256(artifact) != event['sha256']:
        raise ValueError('Catalogue artifact is missing or changed')
    body = artifact.read_text(encoding='utf-8')
    if not body.rstrip().lower().endswith('</html>'):
        raise ValueError('Catalogue response is truncated')
    from .official_formats import publisher_page
    prefix = '/content/' + claimed.upper() + year + '/html/'
    entries = {(href, title) for href, title in publisher_page(artifact).links
               if href.startswith(prefix) and href.endswith('_paper.html') and title}
    titles = {title for _, title in entries}
    if not titles or not re.search(r'<title>\s*' + claimed.upper() + r'\s+' + year +
                                    r'\s+Open Access Repository\s*</title>', body, re.I):
        raise ValueError('Catalogue has no recognizable papers for the claimed event')
    target = _compact(ref['fields'].get('title', ''))
    if any(_compact(title) == target or SequenceMatcher(None, target, _compact(title)).ratio() >= .85
           for title in titles):
        raise ValueError('Catalogue contains a matching or similar title; inspect that candidate first')
    return {'kind': 'suspected_metadata_conflation', 'reason': investigation['reason'],
        'scope': 'suspected citation identity; not proof that no publication exists anywhere',
        'related_work': {'fields': fields, 'source_url': record['source_url'],
            'artifact': record['artifact'], 'sha256': record['sha256'], 'quote': quote, 'method': method},
        'catalogue': {**catalogue, 'source_url': event['source_url'], 'entries_inspected': len(entries),
            'distinct_titles_inspected': len(titles),
            'observation': 'No matching or closely similar title in this captured official public catalogue; catalogue coverage is not universal.'}}
