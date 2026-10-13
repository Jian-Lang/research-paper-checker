"""Read-only regressions for failure modes encountered in the blind sample."""
import unittest
from unittest.mock import patch
from hallu_cite_checker.normalize import text, author_equal, canonical_fields
from hallu_cite_checker.audit import compare, audit_reference
from hallu_cite_checker.evidence import trusted


def rows(input_fields, source_fields):
    return {r['field']: r['result'] for r in compare({'fields': input_fields},
        {'role': 'primary', 'fields': source_fields})}


class MetadataRegressions(unittest.TestCase):
    def test_html_entity(self):
        self.assertEqual(text('2D&amp;3D'), text('2D&3D'))

    def test_middle_name_omission(self):
        self.assertTrue(author_equal(['Smit, A.'], ['Smit, Andries Petrus']))
        self.assertFalse(author_equal(['Smit, A. Q.'], ['Smit, Andries Petrus']))

    def test_author_order_still_matters(self):
        self.assertFalse(author_equal(['A. Smit', 'P. Duckworth', 'N. Grinsztajn'],
                                     ['Andries Petrus Smit', 'Nathan Grinsztajn', 'Paul Duckworth']))

    def test_singular_page(self):
        self.assertEqual(canonical_fields({'page': '10--20'})[0], {'pages': '10--20'})

    def test_incorrect_conference_edition_blocks(self):
        self.assertEqual(rows({'venue':'Proceedings of the 40th International Conference on Machine Learning', 'year':'2024'},
                              {'venue':'ICML', 'year':'2024'})['venue'], 'CONFLICT')

    def test_correct_conference_edition_matches(self):
        self.assertEqual(rows({'venue':'Proceedings of the 41st International Conference on Machine Learning', 'year':'2024'},
                              {'venue':'ICML', 'year':'2024'})['venue'], 'MATCH')

    def test_short_book_title_does_not_prove_subtitle(self):
        self.assertEqual(rows({'venue':'Book: First Workshops'}, {'venue':'Book'})['venue'], 'AMBIGUOUS_FORMAT')

    def test_main_venue_does_not_prove_workshop(self):
        self.assertNotEqual(rows({'venue':'ICML Workshop'}, {'venue':'ICML'})['venue'], 'MATCH')

    def test_meaning_changing_title_words_rejected(self):
        self.assertEqual(rows({'title':'Reduce False-Positive Findings'}, {'title':'Reduce False Positives'})['title'], 'CONFLICT')

    def test_hyphen_ambiguity_never_auto_passes(self):
        self.assertEqual(rows({'title':'Multi-disciplinary team'}, {'title':'Multidisciplinary team'})['title'], 'AMBIGUOUS_FORMAT')

    def test_source_first_page_only_is_disclosed(self):
        self.assertEqual(rows({'pages':'10-20'}, {'pages':'10'})['pages'], 'PARTIAL_SOURCE_MATCH')

    def test_wrong_page_range_rejected(self):
        self.assertEqual(rows({'pages':'10-20'}, {'pages':'10-21'})['pages'], 'CONFLICT')

    def test_duplicated_deposited_authors_remain_unresolved(self):
        self.assertEqual(rows({'authors':['A. Smith','B. Jones','C. Wu','Consortium']},
            {'authors':['Alice Smith','Bob Jones','Carol Wu']*2})['authors'], 'AMBIGUOUS_FORMAT')

    def test_disagreeing_sources_fail_without_calling_input_fabricated(self):
        ref = {'id':'x', 'fields':{'title':'Paper','authors':['Alice Smith'],'year':'2024'},
               'raw':'Paper by Alice Smith, 2024', 'locations':[{'page':1}]}
        base = {'role':'primary','version_id':'same','source_url':'https://api.crossref.org/works/x',
                'kind':'crossref','fields':ref['fields']}
        conflict = {**base, 'fields':{**ref['fields'],'year':'2025'}}
        with patch('hallu_cite_checker.audit.validate_record', return_value=[]):
            result = audit_reference(ref, [base, conflict], '.')
        self.assertEqual(result['status'], 'UNVERIFIED')
        self.assertTrue(result['conflicts'])

    def test_medrxiv_host_is_exact(self):
        self.assertTrue(trusted('official','https://api.medrxiv.org/details/medrxiv/x'))
        self.assertFalse(trusted('official','https://api.medrxiv.org.evil.org/details/x'))

    def test_matching_scholar_export_takes_precedence(self):
        ref = {'id':'x','fields':{'title':'Paper','authors':['Alice Smith','Bob Jones'],'year':'2024','venue':'ICML'},
               'raw':'Paper by Smith and Jones','locations':[{'page':1}]}
        scholar = {'role':'primary','version_id':'icml:2024:x','kind':'google_scholar',
                   'source_url':'https://scholar.google.com/scholar.bib?x','fields':ref['fields']}
        official = {**scholar,'kind':'official','source_url':'https://proceedings.mlr.press/x',
                    'fields':{**ref['fields'],'authors':['Bob Jones','Alice Smith']}}
        with patch('hallu_cite_checker.audit.validate_record',return_value=[]):
            result = audit_reference(ref,[scholar,official],'.')
        self.assertEqual(result['status'],'VERIFIED')
        self.assertEqual(result['acceptance_policy'],'matching_google_scholar_export')
        self.assertTrue(result['warnings'])

    def test_alternative_author_order_downgrades_conflict(self):
        ref = {'id':'x','fields':{'title':'Paper','authors':['Alice Smith','Bob Jones'],'year':'2024','venue':'ICML'},
               'raw':'Paper by Smith and Jones','locations':[{'page':1}]}
        official = {'role':'primary','version_id':'icml:2024:x','kind':'official',
                    'source_url':'https://proceedings.mlr.press/x','fields':{**ref['fields'],'authors':['Bob Jones','Alice Smith']}}
        alternate = {**official,'role':'alternative_version','version_id':'arxiv:2023:x',
                     'fields':{**ref['fields'],'year':'2023','venue':'arXiv'}}
        with patch('hallu_cite_checker.audit.validate_record',return_value=[]):
            result = audit_reference(ref,[official,alternate],'.')
        self.assertEqual(result['status'],'UNVERIFIED')
        self.assertIn('alternative_version_matches:authors',result['problems'])
        self.assertTrue(result['conflicts'])

    def test_scholar_preprint_does_not_validate_conference(self):
        ref = {'id':'x','fields':{'title':'Paper','authors':['Alice Smith'],'year':'2024','venue':'ICML'},
               'raw':'Paper by Smith','locations':[{'page':1}]}
        source = {'role':'primary','version_id':'arxiv:x','kind':'google_scholar',
                  'source_url':'https://scholar.google.com/scholar.bib?x','fields':{**ref['fields'],'venue':'arXiv'}}
        with patch('hallu_cite_checker.audit.validate_record',return_value=[]):
            result = audit_reference(ref,[source],'.')
        self.assertNotEqual(result['status'],'VERIFIED')
        self.assertNotEqual(result['acceptance_policy'],'matching_google_scholar_export')


if __name__ == '__main__':
    unittest.main()
