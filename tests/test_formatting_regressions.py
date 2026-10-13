"""Formatting resolution must depend on observed breaks, not fuzzy matching."""
import unittest
import tempfile
from pathlib import Path
from hallu_cite_checker.automatic import parse_reference
from hallu_cite_checker.format_resolution import resolve_reference
from hallu_cite_checker.normalize import author_equal
from hallu_cite_checker.official_formats import parse_openreview, parse_publisher_html
from hallu_cite_checker.io import save


def reference(lines):
    return parse_reference([{'text':t,'raw':t,'page':1,'line_number':539+i}
                            for i,t in enumerate(lines)],1)


def record(fields):
    return {'role':'primary','kind':'arxiv','fields':fields,
            'source_url':'https://arxiv.org/abs/2401.12345','sha256':'fixture'}


class FormattingRegressions(unittest.TestCase):
    def test_wrapped_word_is_resolved_when_source_matches(self):
        ref=reference(['Alice Smith. 2024. Reliable reason-','ing. arXiv preprint arXiv:2401.12345.'])
        result=resolve_reference(ref,[record(ref['fields'])])
        self.assertEqual(result['issues'],[])
        self.assertEqual(result['raw'],ref['raw'])
        self.assertTrue(result['format_resolutions'])
        self.assertEqual(result['format_resolutions'][0]['break_choices'][0]['keep_hyphen'],False)

    def test_real_compound_hyphen_is_retained_only_at_observed_break(self):
        ref=reference(['Alice Smith. 2024. Vision-','language reasoning. arXiv preprint arXiv:2401.12345.'])
        source={**ref['fields'],'title':'Vision-language reasoning'}
        result=resolve_reference(ref,[record(source)])
        self.assertEqual(result['fields']['title'],'Vision-language reasoning')
        self.assertEqual(result['issues'],[])
        self.assertEqual(result['format_resolutions'][0]['original_fields']['title'],'Visionlanguage reasoning')

    def test_unobserved_hyphen_edit_is_not_permitted(self):
        ref=reference(['Alice Smith. 2024. Visionlanguage reason-','ing. arXiv preprint arXiv:2401.12345.'])
        result=resolve_reference(ref,[record({**ref['fields'],'title':'Vision-language reasoning'})])
        self.assertEqual(result,ref)
        self.assertTrue(result['issues'])

    def test_unrelated_title_is_never_reconstructed(self):
        ref=reference(['Alice Smith. 2024. Reliable reason-','ing. arXiv preprint arXiv:2401.12345.'])
        result=resolve_reference(ref,[record({**ref['fields'],'title':'Unreliable reasoning'})])
        self.assertEqual(result,ref)

    def test_real_page_error_survives_hyphen_resolution(self):
        ref=reference(['Alice Smith. 2024. Reliable reason-','ing. In International Conference on Learning Representations, pages 10–20.'])
        result=resolve_reference(ref,[record({**ref['fields'],'pages':'11-21'})])
        self.assertEqual(result['issues'],[])
        self.assertEqual(result['fields']['pages'],'10–20')

    def test_pdf_prefix_acute_and_composed_name_match(self):
        self.assertTrue(author_equal(['Ivan Vuli ´c'],['Vulić, Ivan']))
        self.assertFalse(author_equal(['Ivan Vuli ´c'],['Vulić, Ivo']))

    def test_submitted_openreview_note_is_not_acceptance(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'note.json'
            save(p,{'note':{'id':'x','content':{'title':{'value':'Title'},'authors':{'value':['Alice Smith']},
                'venueid':{'value':'ICLR.cc/2026/Conference/Submission'},
                'venue':{'value':'Submitted to ICLR 2026'}}}})
            with self.assertRaises(ValueError):parse_openreview(p)

    def test_accepted_openreview_note_supplies_no_invented_pages(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'note.json'
            save(p,{'note':{'id':'x','content':{'title':{'value':'Title'},'authors':{'value':['Alice Smith']},
                'venueid':{'value':'ICLR.cc/2026/Conference'},'venue':{'value':'ICLR 2026 Poster'}}}})
            f=parse_openreview(p)
            self.assertEqual(f['year'],'2026')
            self.assertNotIn('pages',f)

    def test_official_embedded_bibtex_is_parsed_without_page_prose(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'page.html'
            p.write_text('<p>Not citation data: Other paper, 2030</p><div class="bibref">'
                '@InProceedings{x, title={Reliable reasoning}, author={Alice Smith}, year={2024}, '
                'booktitle={CVPR}, pages={10--20}}</div>')
            f=parse_publisher_html(p)
            self.assertEqual(f['title'],'Reliable reasoning')
            self.assertEqual(f['year'],'2024')
