"""Trusted structured publisher exports and accepted OpenReview notes."""
from html.parser import HTMLParser
from pathlib import Path
import json
import re
from .inventory import parse_bib
from .citation_html import parse_citation_html


class PublisherPage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.active_link = None
        self.bib_depth = 0
        self.bib_parts = []
        self.paper_depth = 0
        self.paper_title = []
        self.in_paper_title = False
        self.paper_links = []

    def handle_starttag(self,tag,attrs):
        attrs = dict(attrs)
        if tag == 'div':
            if self.paper_depth:
                self.paper_depth += 1
            elif 'paper' in attrs.get('class','').split():
                self.paper_depth = 1
                self.paper_title, self.paper_links = [], []
        if tag == 'p' and self.paper_depth and 'title' in attrs.get('class','').split():
            self.in_paper_title = True
        if tag == 'a' and self.paper_depth:
            self.paper_links.append(attrs.get('href',''))
        if tag == 'a':
            self.active_link = [attrs.get('href',''),[]]
        if self.bib_depth:
            self.bib_depth += 1
        elif ('bibref' in attrs.get('class','').split() or
              tag == 'pre' and 'bib' in attrs.get('id','').lower()):
            self.bib_depth = 1

    def handle_endtag(self,tag):
        if tag == 'p':
            self.in_paper_title = False
        if tag == 'div' and self.paper_depth:
            self.paper_depth -= 1
            if not self.paper_depth:
                title = ''.join(self.paper_title).strip()
                self.links.extend((url,title) for url in self.paper_links if url.endswith('.html'))
        if tag == 'a' and self.active_link:
            self.links.append((self.active_link[0],''.join(self.active_link[1]).strip()))
            self.active_link = None
        if self.bib_depth:
            self.bib_depth -= 1

    def handle_data(self,data):
        if self.in_paper_title:
            self.paper_title.append(data)
        if self.active_link:
            self.active_link[1].append(data)
        if self.bib_depth:
            self.bib_parts.append(data)


def publisher_page(path):
    parser = PublisherPage()
    parser.feed(Path(path).read_text(encoding='utf-8'))
    return parser


def parse_publisher_html(path):
    parser = publisher_page(path)
    if parser.bib_parts:
        entries = parse_bib(''.join(parser.bib_parts),str(path))
        if len(entries)!=1 or entries[0]['issues']:
            raise ValueError('Official page BibTeX is not one clean record')
        return entries[0]['fields']
    return parse_citation_html(path)


def parse_openreview(path):
    note = json.loads(Path(path).read_text(encoding='utf-8'))['note']
    content = {k:(v.get('value') if isinstance(v,dict) else v)
               for k,v in note['content'].items()}
    match = re.fullmatch(r'ICLR.cc/((?:19|20)\d{2})/Conference',content.get('venueid',''))
    if not match or not content.get('venue') or re.search(
            r'submitted|under review|withdrawn|rejected',content['venue'],re.I):
        raise ValueError('OpenReview note does not establish accepted ICLR main conference')
    if not content.get('title') or not content.get('authors') or not note.get('id'):
        raise ValueError('Incomplete OpenReview identity')
    fields = {'title':content['title'],'authors':content['authors'],
              'venue':content['venue'],'year':match[1]}
    if content.get('doi'):
        fields['doi'] = content['doi']
    return fields
