"""PDF Unicode, extraction and candidate-source regression checks."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from hallu_cite_checker.pdf_unicode import pdf_text
from hallu_cite_checker.inventory import inventory_pdf
from hallu_cite_checker.automatic import populate
from hallu_cite_checker.audit import audit_reference
from hallu_cite_checker.citation_html import parse_citation_html
from hallu_cite_checker.io import save, load


class PDFRegressions(unittest.TestCase):

    def test_others_truncation_with_period_does_not_merge_adjacent_papers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save(root/'manifest.json', {'pages':[{'page':1}],'issues':[],'coverage':{'reviewed':False}})
            (root/'page-001.txt').write_text(
                'References538\nAlice Smith and Bob Jones. 2024. First paper. arXiv preprint arXiv:2401.12345.539\n'
                'Carol Wu, Dan Green, and 8 others.540\n2025. Second paper. arXiv preprint arXiv:2501.12345.541\n'
                'A Additional Related Work542\n1\n')
            references = populate(root)['references']
            self.assertEqual(len(references), 2)
            self.assertEqual(references[0]['fields']['title'], 'First paper')
            self.assertEqual(references[1]['fields']['title'], 'Second paper')
            self.assertEqual(references[1]['fields']['authors'], ['Carol Wu', 'Dan Green'])
            self.assertTrue(references[1]['authors_truncated'])

    def test_booktitle_parenthetical_volume_is_preserved(self):
        from hallu_cite_checker.automatic import parse_reference
        ref = parse_reference([{'page':1,'line_number':539,'raw':'citation',
            'text':'Alice Smith and Bob Jones. 2026. Paper. InProceedings of the Association for Computational Linguistics (Volume 1: Long Papers), pages 10–20.'}],1)
        self.assertEqual(ref['fields']['venue'], 'Proceedings of the Association for Computational Linguistics (Volume 1: Long Papers)')
        self.assertNotIn('volume',ref['fields'])
        self.assertEqual(ref['issues'], [])
    def test_valid_unicode_is_unchanged(self):
        value = 'Renée, 数学 𝑥 🚀'
        actual, events = pdf_text(value)
        self.assertEqual(actual, value)
        self.assertEqual(events, [])

    def test_valid_surrogate_pair_is_losslessly_decoded(self):
        actual, events = pdf_text('X\ud83d\ude80Y')
        self.assertEqual(actual, 'X🚀Y')
        self.assertEqual(events[0]['offset'], 1)
        self.assertEqual(events[0]['action'], 'paired_surrogates_decoded')
        actual.encode('utf-8')

    def test_unpaired_characters_are_not_deleted(self):
        actual, events = pdf_text('A\ud835B\udc00C')
        self.assertEqual(actual, 'A[UNRESOLVED U+D835]B[UNRESOLVED U+DC00]C')
        self.assertEqual([e['offset'] for e in events], [1, 3])
        self.assertEqual(len(events), 2)
        actual.encode('utf-8')

    def test_adjacent_high_surrogates_remain_distinct(self):
        actual, events = pdf_text('\ud835\ud835x')
        self.assertEqual(len(events), 2)
        self.assertTrue(actual.endswith('x'))
        self.assertEqual(actual.count('[UNRESOLVED'), 2)

    def test_malformed_page_is_saved_and_later_pages_extracted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'paper.pdf'
            source.write_bytes(b'%PDF fixture')
            raw = 'Body ' * 10 + '\ud835X'
            pages = [SimpleNamespace(extract_text=lambda **kw: 'Normal first page. ' * 3),
                     SimpleNamespace(extract_text=lambda **kw: raw),
                     SimpleNamespace(extract_text=lambda **kw: 'Normal last page. ' * 3)]
            with patch('hallu_cite_checker.inventory.PdfReader', return_value=SimpleNamespace(pages=pages)):
                manifest = inventory_pdf(source, root/'run')
            self.assertEqual(len(manifest['pages']), 3)
            self.assertFalse(manifest['coverage']['reviewed'])
            self.assertTrue(any(i['code']=='page_unicode_unresolved' and i['page']==2 for i in manifest['issues']))
            saved = load(root/'run/page-002-raw-extraction.json')
            self.assertEqual(saved['plain'], raw)
            self.assertEqual(saved['plain_events'][0]['offset'], len('Body ' * 10))
            self.assertIn('[UNRESOLVED U+D835]', (root/'run/page-002.txt').read_text())
            self.assertIn('Normal last page', (root/'run/page-003.txt').read_text())

    def test_numbered_author_year_continuation_does_not_create_extra_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save(root/'manifest.json', {'pages':[{'page':1}],'issues':[],'coverage':{'reviewed':False}})
            (root/'page-001.txt').write_text(
                'References538\nAlice Smith,539\nBob Jones. 2024. Reliable learning. In2024540\n'
                'International Conference on Learning Representations, pages 10–20.541\n'
                'Carol Wu and Dan Green. 2025. Another paper. arXiv preprint arXiv:2501.12345.542\n'
                'A Additional Related Work543\n1\n')
            result = populate(root)
            self.assertEqual(len(result['references']), 2)
            self.assertFalse(result['coverage']['reviewed'])
            self.assertEqual(result['references'][0]['fields']['authors'], ['Alice Smith','Bob Jones'])
            self.assertEqual(result['references'][0]['fields']['venue'], '2024 International Conference on Learning Representations')
            self.assertEqual(result['references'][1]['fields']['arxiv_id'], '2501.12345')
            self.assertEqual(result['issues'], [])

    def test_uncertain_extraction_cannot_turn_source_difference_into_rejection(self):
        ref = {'id':'x','fields':{'title':'Uncertain title','authors':['Alice Smith'],'year':'2024'},
               'locations':[{'page':1}],'raw':'Unknown glyph','issues':['reference_contains_unresolved_unicode']}
        evidence = {'role':'primary','kind':'arxiv','version_id':'arxiv:x','source_url':'https://arxiv.org/abs/x',
                    'fields':{**ref['fields'],'title':'Different title'}}
        with patch('hallu_cite_checker.audit.validate_record', return_value=[]):
            result = audit_reference(ref,[evidence],'.')
        self.assertEqual(result['status'], 'UNVERIFIED')

    def test_html_citation_uses_structured_authors_and_date(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'source.html'
            source.write_text('<meta name="citation_title" content="A &amp; B"><meta name="citation_author" content="Alice Smith">'
                '<meta name="citation_author" content="Bob Jones"><meta name="citation_date" content="2025/02/03">'
                '<meta name="citation_arxiv_id" content="2502.01234">')
            fields = parse_citation_html(source)
            self.assertEqual(fields, {'title':'A & B','authors':['Alice Smith','Bob Jones'],'year':'2025',
                                      'arxiv_id':'2502.01234','venue':'arXiv'})

    def test_page_prose_without_metadata_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'source.html'
            source.write_text('<h1>A paper with plausible authors, 2025</h1>')
            with self.assertRaises(ValueError):
                parse_citation_html(source)
