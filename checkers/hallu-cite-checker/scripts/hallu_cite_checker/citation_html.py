"""Structured citation metadata embedded by publishers, not page prose."""
from html.parser import HTMLParser
from pathlib import Path
import re


class CitationMeta(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        name = attrs.get('name', attrs.get('property', '')).lower()
        if tag.lower() == 'meta' and name.startswith('citation_') and attrs.get('content'):
            self.meta.setdefault(name, []).append(attrs['content'])


def parse_citation_html(path):
    parser = CitationMeta()
    parser.feed(Path(path).read_text(encoding='utf-8'))
    meta, fields = parser.meta, {}
    single = {'title':'citation_title','doi':'citation_doi','volume':'citation_volume',
              'issue':'citation_issue','publisher':'citation_publisher'}
    for field, key in single.items():
        values = meta.get(key, [])
        if len(set(values)) > 1:
            raise ValueError('Conflicting embedded metadata: ' + key)
        if values:
            fields[field] = values[0]
    if meta.get('citation_author'):
        fields['authors'] = meta['citation_author']
    for key in ('citation_publication_date','citation_date'):
        if meta.get(key):
            match = re.match(r'(?:19|20)\d{2}', meta[key][0])
            if match:
                fields['year'] = match[0]
                break
    for key in ('citation_conference_title','citation_journal_title','citation_booktitle'):
        if meta.get(key):
            fields['venue'] = meta[key][0]
            break
    if meta.get('citation_arxiv_id'):
        fields['arxiv_id'] = meta['citation_arxiv_id'][0]
        fields['venue'] = 'arXiv'
    if meta.get('citation_firstpage'):
        fields['pages'] = meta['citation_firstpage'][0]
        if meta.get('citation_lastpage'):
            fields['pages'] += '-' + meta['citation_lastpage'][0]
    if not fields.get('title') or not fields.get('authors') or not fields.get('year'):
        raise ValueError('Page has no complete structured citation metadata')
    return fields
